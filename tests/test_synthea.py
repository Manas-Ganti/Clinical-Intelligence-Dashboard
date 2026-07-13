"""Synthea ingestion tests.

These build their own tiny CSVs rather than reading data/synthea/, so the suite
runs identically whether or not the real 9 MB export has been fetched. The rows
are copied verbatim from the real Synthea schema (column names, Zulu timestamps,
numeric name suffixes, SNOMED semantic tags), so they exercise the same coercion
paths the full dataset does.
"""
from pathlib import Path

import pytest

from domain.models.alert import AlertSeverity, AlertStatus
from domain.models.base import SourceSystem
from domain.models.encounter import EncounterClass, EncounterStatus
from domain.models.finding import AbnormalFlag
from domain.models.imaging_study import ImageFormat, Modality
from domain.models.patient import Sex
from ingestion.reference_ranges import classify, in_panel
from ingestion.synthea_adapter import (
    SyntheaEncounterAdapter,
    SyntheaImagingAdapter,
    SyntheaObservationAdapter,
    SyntheaPatientAdapter,
    derive_alerts,
)

P1 = "1d604da9-9a81-4ba9-80c2-de3375d59b40"
P2 = "034e9e3b-2def-4559-bb2a-7850888ae060"
E1 = "d0c40d10-8d87-447e-836e-99d26ad52ea5"

PATIENTS_CSV = (
    "Id,BIRTHDATE,DEATHDATE,SSN,PREFIX,FIRST,LAST,MARITAL,RACE,ETHNICITY,GENDER\n"
    f"{P1},1989-05-25,,999-76-6866,Mr.,José Eduardo181,Gómez206,M,white,hispanic,M\n"
    f"{P2},1954-02-03,2019-08-14,999-11-2222,Mrs.,Milo271,Feil794,S,black,nonhispanic,F\n"
)

ENCOUNTERS_CSV = (
    "Id,START,STOP,PATIENT,ENCOUNTERCLASS,CODE,DESCRIPTION,REASONDESCRIPTION\n"
    f"{E1},2010-01-23T17:45:28Z,2010-01-23T18:10:28Z,{P1},wellness,185349003,Encounter,Acute bronchitis (disorder)\n"
    f"enc-urgent,2011-03-01T08:00:00Z,2011-03-01T09:30:00Z,{P1},urgentcare,50849002,Encounter,\n"
    # No STOP -> the visit is still running; Synthea has no status column at all.
    f"enc-open,2012-05-05T10:00:00Z,,{P2},inpatient,1505002,Encounter,\n"
    # References a patient we never ingested -> must be skipped, not linked to None.
    "enc-orphan,2013-01-01T10:00:00Z,2013-01-01T11:00:00Z,no-such-patient,ambulatory,1,Encounter,\n"
)

OBSERVATIONS_CSV = (
    "DATE,PATIENT,ENCOUNTER,CODE,DESCRIPTION,VALUE,UNITS,TYPE\n"
    # In panel, normal.
    f"2010-01-23T17:45:28Z,{P1},{E1},718-7,Hemoglobin [Mass/volume] in Blood,14.2,g/dL,numeric\n"
    # In panel, below the normal range but above the panic value -> LOW.
    f"2010-02-23T17:45:28Z,{P1},{E1},718-7,Hemoglobin [Mass/volume] in Blood,9.4,g/dL,numeric\n"
    # In panel, below the panic value -> CRITICAL, and should spawn an Alert.
    f"2010-03-23T17:45:28Z,{P1},{E1},718-7,Hemoglobin [Mass/volume] in Blood,6.1,g/dL,numeric\n"
    # In panel, above the panic value -> CRITICAL.
    f"2010-04-23T17:45:28Z,{P1},{E1},6298-4,Potassium,6.9,mmol/L,numeric\n"
    # Off panel (body height) -> dropped, not ingested as a Finding.
    f"2010-01-23T17:45:28Z,{P1},{E1},8302-2,Body Height,193.3,cm,numeric\n"
    # In panel by code but non-numeric -> dropped (Finding.value is a float).
    f"2010-01-23T17:45:28Z,{P1},{E1},718-7,Hemoglobin,unmeasurable,g/dL,text\n"
)

IMAGING_CSV = (
    "Id,DATE,PATIENT,ENCOUNTER,BODYSITE_CODE,BODYSITE_DESCRIPTION,MODALITY_CODE,MODALITY_DESCRIPTION,SOP_CODE,SOP_DESCRIPTION\n"
    # The four spellings of one thoracic concept that really occur in Synthea.
    f"img-1,2014-07-08T15:35:36Z,{P1},{E1},51185008,Thoracic structure (body structure),DX,Digital Radiography,1.2.840,X-Ray\n"
    f"img-2,2014-07-09T15:35:36Z,{P1},{E1},51185008,Thoracic structure,CR,Computed Radiography,1.2.840,X-Ray\n"
    f"img-3,2014-07-10T15:35:36Z,{P1},{E1},51185008,thoracic,CT,Computed Tomography,1.2.840,CT\n"
    f"img-4,2014-07-11T15:35:36Z,{P1},{E1},51185008,Thoracic,US,Ultrasound,1.2.840,US\n"
)


@pytest.fixture
def csvs(tmp_path: Path) -> Path:
    (tmp_path / "patients.csv").write_text(PATIENTS_CSV, encoding="utf-8")
    (tmp_path / "encounters.csv").write_text(ENCOUNTERS_CSV, encoding="utf-8")
    (tmp_path / "observations.csv").write_text(OBSERVATIONS_CSV, encoding="utf-8")
    (tmp_path / "imaging_studies.csv").write_text(IMAGING_CSV, encoding="utf-8")
    return tmp_path


@pytest.fixture
def patients(csvs: Path):
    return list(SyntheaPatientAdapter(csvs / "patients.csv").read())


@pytest.fixture
def mrn_map(patients):
    return {p.mrn: p.id for p in patients}


# -- patients ------------------------------------------------------------- #
def test_strips_synthea_numeric_name_suffix(patients):
    """"Gómez206" is a generator artifact, not a surname."""
    p = patients[0]
    assert p.given_name == "José Eduardo"
    assert p.family_name == "Gómez"


def test_uuid_becomes_the_mrn(patients):
    """Synthea has no MRN column; its UUID is the only stable identifier."""
    assert patients[0].mrn == P1
    assert patients[0].source_record_id == P1
    assert patients[0].source_system is SourceSystem.EHR


def test_sex_and_deceased_mapped(patients):
    assert patients[0].sex is Sex.MALE
    assert patients[0].deceased is False
    # Synthea encodes death as the presence of a DEATHDATE, not a boolean.
    assert patients[1].sex is Sex.FEMALE
    assert patients[1].deceased is True


# -- encounters ----------------------------------------------------------- #
def test_wellness_and_urgentcare_keep_their_identity(csvs, mrn_map):
    """The enum was extended rather than collapsing these into neighbours."""
    encs = list(SyntheaEncounterAdapter(csvs / "encounters.csv", mrn_map).read())
    by_class = {e.encounter_class for e in encs}
    assert EncounterClass.WELLNESS in by_class
    assert EncounterClass.URGENT_CARE in by_class


def test_status_derived_from_stop_timestamp(csvs, mrn_map):
    """Synthea has no status column — a visit with no STOP is still in progress."""
    encs = {
        e.source_record_id: e
        for e in SyntheaEncounterAdapter(csvs / "encounters.csv", mrn_map).read()
    }
    assert encs[E1].status is EncounterStatus.FINISHED
    assert encs[E1].period_end is not None
    assert encs["enc-open"].status is EncounterStatus.IN_PROGRESS
    assert encs["enc-open"].period_end is None


def test_encounter_with_unknown_patient_is_skipped(csvs, mrn_map):
    encs = list(SyntheaEncounterAdapter(csvs / "encounters.csv", mrn_map).read())
    assert "enc-orphan" not in {e.source_record_id for e in encs}
    assert len(encs) == 3


# -- observations --------------------------------------------------------- #
def test_off_panel_and_non_numeric_observations_dropped(csvs, mrn_map):
    """Body height is off-panel; a 'text' row can't populate a float value."""
    finds = list(
        SyntheaObservationAdapter(csvs / "observations.csv", mrn_map).read()
    )
    assert len(finds) == 4  # 6 rows in, minus body-height and the text row
    assert not in_panel("8302-2")  # body height
    assert all(f.code in {"718-7", "6298-4"} for f in finds)


def test_findings_are_interpreted_against_reference_ranges(csvs, mrn_map):
    finds = sorted(
        SyntheaObservationAdapter(csvs / "observations.csv", mrn_map).read(),
        key=lambda f: f.observed_at,
    )
    hgb_normal, hgb_low, hgb_critical, potassium = finds

    assert hgb_normal.abnormal_flag is AbnormalFlag.NORMAL
    assert hgb_low.abnormal_flag is AbnormalFlag.LOW
    # 6.1 g/dL is below the 7.0 panic value, not merely below the normal range.
    assert hgb_critical.abnormal_flag is AbnormalFlag.CRITICAL
    assert potassium.abnormal_flag is AbnormalFlag.CRITICAL

    # The range that produced the judgement travels with the finding.
    assert hgb_normal.reference_range_low == 12.0
    assert hgb_normal.reference_range_high == 17.5
    # And so does what the source actually said, for auditability.
    assert hgb_normal.raw_value == "14.2"
    assert hgb_normal.raw_unit == "g/dL"


def test_findings_link_to_their_encounter(csvs, mrn_map):
    enc_adapter = SyntheaEncounterAdapter(csvs / "encounters.csv", mrn_map)
    list(enc_adapter.read())
    finds = list(
        SyntheaObservationAdapter(
            csvs / "observations.csv", mrn_map, enc_adapter.id_by_source_id
        ).read()
    )
    canonical = enc_adapter.id_by_source_id[E1]
    assert all(f.encounter_id == canonical for f in finds)


def test_panic_values_outrank_plain_out_of_range():
    """Severity must not depend on which branch happens to run first."""
    assert classify("718-7", 14.0) is AbnormalFlag.NORMAL
    assert classify("718-7", 9.4) is AbnormalFlag.LOW
    assert classify("718-7", 6.1) is AbnormalFlag.CRITICAL
    assert classify("8480-6", 185) is AbnormalFlag.CRITICAL  # systolic BP
    # Lipids are risk markers with no panic value: high, never critical.
    assert classify("18262-6", 900) is AbnormalFlag.HIGH


# -- imaging -------------------------------------------------------------- #
def test_body_site_spellings_canonicalized(csvs, mrn_map):
    """Four Synthea spellings of one SNOMED concept collapse to one value."""
    studies = list(SyntheaImagingAdapter(csvs / "imaging_studies.csv", mrn_map).read())
    assert {s.body_part for s in studies} == {"Thoracic"}


def test_dicom_radiography_codes_map_to_xr(csvs, mrn_map):
    studies = {
        s.source_record_id: s
        for s in SyntheaImagingAdapter(csvs / "imaging_studies.csv", mrn_map).read()
    }
    assert studies["img-1"].modality is Modality.XR  # DX
    assert studies["img-2"].modality is Modality.XR  # CR
    assert studies["img-3"].modality is Modality.CT
    assert studies["img-4"].modality is Modality.US
    assert studies["img-1"].source_format is ImageFormat.DICOM
    assert studies["img-1"].source_system is SourceSystem.PACS
    # image_uri must carry a scheme the blob store can resolve.
    assert studies["img-1"].image_uri.startswith("file://")


# -- derived alerts -------------------------------------------------------- #
def test_alerts_derived_only_from_critical_findings(csvs, mrn_map):
    finds = list(SyntheaObservationAdapter(csvs / "observations.csv", mrn_map).read())
    alerts = derive_alerts(finds)

    critical = [f for f in finds if f.abnormal_flag is AbnormalFlag.CRITICAL]
    assert len(alerts) == len(critical) == 2
    assert all(a.severity is AlertSeverity.CRITICAL for a in alerts)
    # Seeded alerts start ACTIVE and unaudited; Phase 4d is what acknowledges them.
    assert all(a.status is AlertStatus.ACTIVE for a in alerts)
    assert all(a.audit_trail == [] for a in alerts)


def test_alert_links_back_to_the_finding_that_caused_it(csvs, mrn_map):
    """A clinician acking an alert must be able to see exactly why it fired."""
    finds = list(SyntheaObservationAdapter(csvs / "observations.csv", mrn_map).read())
    alerts = derive_alerts(finds)

    by_finding = {f.id: f for f in finds}
    for a in alerts:
        assert a.finding_id in by_finding
        cause = by_finding[a.finding_id]
        assert a.patient_id == cause.patient_id
        assert a.triggered_at == cause.observed_at
        # The triggering value appears in the message, not just a code.
        assert str(cause.value) in a.message
