"""Phase 1 domain-model tests: valid data builds, invalid data raises.

Each model gets at least one "happy path" construction and one or more checks
that a contract violation (bad enum, impossible date, broken invariant) is
rejected with a Pydantic ``ValidationError``.
"""
from datetime import date, datetime, timedelta

import pytest
from pydantic import ValidationError

from domain.models.alert import Alert, AlertSeverity, AlertStatus, AuditEntry
from domain.models.base import SourceSystem
from domain.models.encounter import Encounter, EncounterClass, EncounterStatus
from domain.models.finding import AbnormalFlag, Finding
from domain.models.imaging_study import ImageFormat, ImagingStudy, Modality
from domain.models.patient import Patient, Sex

NOW = datetime(2026, 5, 25, 12, 0, 0)


def envelope(**overrides):
    """Common DomainBase fields, overridable per test."""
    base = dict(
        id="00000000-0000-0000-0000-000000000001",
        created_at=NOW,
        updated_at=NOW,
        source_system=SourceSystem.CSV_UPLOAD,
        source_record_id="src-1",
        data_quality_score=1.0,
    )
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# Patient
# --------------------------------------------------------------------------- #
def test_patient_valid():
    p = Patient(
        **envelope(),
        mrn="MRN1",
        given_name="Ada",
        family_name="Lovelace",
        birth_date=date(1815, 12, 10),
        sex=Sex.FEMALE,
    )
    assert p.sex is Sex.FEMALE
    assert p.deceased is False


def test_patient_future_birthdate_rejected():
    with pytest.raises(ValidationError):
        Patient(
            **envelope(),
            mrn="MRN1",
            given_name="A",
            family_name="B",
            birth_date=date.today() + timedelta(days=1),
            sex=Sex.MALE,
        )


def test_patient_bad_sex_rejected():
    with pytest.raises(ValidationError):
        Patient(
            **envelope(),
            mrn="MRN1",
            given_name="A",
            family_name="B",
            birth_date=date(1990, 1, 1),
            sex="alien",
        )


def test_data_quality_score_out_of_range_rejected():
    with pytest.raises(ValidationError):
        Patient(
            **envelope(data_quality_score=1.5),
            mrn="M",
            given_name="A",
            family_name="B",
            birth_date=date(1990, 1, 1),
            sex=Sex.MALE,
        )


# --------------------------------------------------------------------------- #
# Encounter
# --------------------------------------------------------------------------- #
def test_encounter_valid():
    e = Encounter(
        **envelope(),
        patient_id="p1",
        encounter_class=EncounterClass.INPATIENT,
        status=EncounterStatus.FINISHED,
        period_start=NOW,
        period_end=NOW + timedelta(hours=2),
    )
    assert e.period_end > e.period_start


def test_encounter_ongoing_has_no_end():
    e = Encounter(
        **envelope(),
        patient_id="p1",
        encounter_class=EncounterClass.EMERGENCY,
        status=EncounterStatus.IN_PROGRESS,
        period_start=NOW,
    )
    assert e.period_end is None


def test_encounter_end_before_start_rejected():
    with pytest.raises(ValidationError):
        Encounter(
            **envelope(),
            patient_id="p1",
            encounter_class=EncounterClass.INPATIENT,
            status=EncounterStatus.FINISHED,
            period_start=NOW,
            period_end=NOW - timedelta(hours=2),
        )


# --------------------------------------------------------------------------- #
# Finding
# --------------------------------------------------------------------------- #
def test_finding_valid():
    f = Finding(
        **envelope(),
        patient_id="p1",
        code="718-7",
        display="Hemoglobin",
        value=9.2,
        unit="g/dL",
        abnormal_flag=AbnormalFlag.LOW,
        observed_at=NOW,
    )
    assert f.abnormal_flag is AbnormalFlag.LOW
    assert f.abnormal_flag is not AbnormalFlag.NORMAL


def test_finding_defaults_to_normal_flag():
    f = Finding(
        **envelope(),
        patient_id="p1",
        code="718-7",
        display="Hemoglobin",
        value=14.0,
        unit="g/dL",
        observed_at=NOW,
    )
    assert f.abnormal_flag is AbnormalFlag.NORMAL


def test_finding_inverted_reference_range_rejected():
    with pytest.raises(ValidationError):
        Finding(
            **envelope(),
            patient_id="p1",
            code="718-7",
            display="Hgb",
            value=9.2,
            unit="g/dL",
            observed_at=NOW,
            reference_range_low=15.0,
            reference_range_high=12.0,
        )


# --------------------------------------------------------------------------- #
# ImagingStudy
# --------------------------------------------------------------------------- #
def test_imaging_study_valid():
    s = ImagingStudy(
        **envelope(source_system=SourceSystem.PACS),
        patient_id="p1",
        modality=Modality.CT,
        study_date=NOW,
        series_count=3,
        image_uri="s3://bucket/study/1",
        source_format=ImageFormat.DICOM,
    )
    assert s.series_count == 3


def test_imaging_study_uri_without_scheme_rejected():
    with pytest.raises(ValidationError):
        ImagingStudy(
            **envelope(source_system=SourceSystem.PACS),
            patient_id="p1",
            modality=Modality.MR,
            study_date=NOW,
            series_count=1,
            image_uri="/local/path/no/scheme",
            source_format=ImageFormat.NIFTI,
        )


def test_imaging_study_zero_series_rejected():
    with pytest.raises(ValidationError):
        ImagingStudy(
            **envelope(source_system=SourceSystem.PACS),
            patient_id="p1",
            modality=Modality.CT,
            study_date=NOW,
            series_count=0,
            image_uri="s3://b/k",
            source_format=ImageFormat.DICOM,
        )


# --------------------------------------------------------------------------- #
# Alert + AuditEntry (CLAUDE.md rule #5)
# --------------------------------------------------------------------------- #
def test_alert_active_valid_without_audit():
    a = Alert(
        **envelope(),
        patient_id="p1",
        severity=AlertSeverity.WARNING,
        message="Low Hgb",
        triggered_at=NOW,
    )
    assert a.status is AlertStatus.ACTIVE
    assert a.audit_trail == []


def test_alert_acknowledged_without_audit_rejected():
    with pytest.raises(ValidationError):
        Alert(
            **envelope(),
            patient_id="p1",
            severity=AlertSeverity.CRITICAL,
            message="Critical Hgb",
            triggered_at=NOW,
            status=AlertStatus.ACKNOWLEDGED,
        )


def test_alert_acknowledged_with_audit_ok():
    entry = AuditEntry(
        acknowledged_by="dr.smith",
        acknowledged_at=NOW,
        prior_status=AlertStatus.ACTIVE,
        new_status=AlertStatus.ACKNOWLEDGED,
        note="reviewed",
    )
    a = Alert(
        **envelope(),
        patient_id="p1",
        severity=AlertSeverity.CRITICAL,
        message="Critical Hgb",
        triggered_at=NOW,
        status=AlertStatus.ACKNOWLEDGED,
        audit_trail=[entry],
    )
    assert a.audit_trail[0].acknowledged_by == "dr.smith"
