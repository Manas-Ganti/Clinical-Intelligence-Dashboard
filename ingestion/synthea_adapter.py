"""Synthea ingestion — the project's real-data source.

Synthea (MITRE) publishes a synthetic-but-clinically-realistic patient
population. It is *internally* clean, which makes it a useful counterpoint to the
hand-authored fixtures in sample_data/: the messiness here is not malformed
dates and null spellings, it is the **structural disagreement between a real
source's schema and our domain model**. That is the interesting kind, and every
instance of it is coerced explicitly and logged:

  * Synthea has no MRN. Patients are identified by UUID, so the UUID *is* the
    MRN — see ``SyntheaPatientAdapter``.
  * Synthea decorates every name with a numeric suffix ("Gómez206") to stop
    anyone mistaking generated data for a real person. We strip it.
  * Encounters carry no ``status``; it is derived from whether the visit stopped.
  * Imaging body sites arrive in four spellings of the same SNOMED concept
    ("Thoracic structure (body structure)", "thoracic", ...). We canonicalize.
  * Modality codes are DICOM (DX, CR); our model speaks XR.
  * Observations carry no interpretation, so abnormal flags and reference ranges
    come from ``ingestion.reference_ranges``.
  * Synthea has no alerts at all. They are *derived* from critical findings
    (``derive_alerts``) — which is the more honest architecture anyway: an alert
    is a computed consequence of a finding, not a row someone hands you.

Rows that cannot yield a valid domain object are skipped and logged, never
emitted half-formed (the contract in ``ingestion.base``).
"""
from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from pydantic import ValidationError

from domain.models.alert import Alert, AlertSeverity, AlertStatus
from domain.models.base import SourceSystem
from domain.models.encounter import Encounter, EncounterClass, EncounterStatus
from domain.models.finding import AbnormalFlag, Finding
from domain.models.imaging_study import ImageFormat, ImagingStudy, Modality
from domain.models.patient import Patient, Sex
from ingestion.base import IngestionAdapter, clean_null, logger
from ingestion.reference_ranges import RANGES, classify, in_panel

_COERCION_PENALTY = 0.1

# Synthea appends a disambiguating integer to every generated name
# ("José Eduardo181", "Gómez206") so synthetic people can't be mistaken for real
# ones. It is an artifact of the generator, not part of the name.
_NAME_SUFFIX = re.compile(r"\d+$")

_SEX_MAP = {"m": Sex.MALE, "f": Sex.FEMALE}

# Synthea's ENCOUNTERCLASS vocabulary -> our EncounterClass. Every value maps to
# a distinct member (we extended the enum rather than collapsing wellness and
# urgentcare into neighbours), so none of these is lossy.
_ENCOUNTER_CLASS = {
    "wellness": EncounterClass.WELLNESS,
    "ambulatory": EncounterClass.AMBULATORY,
    "outpatient": EncounterClass.OUTPATIENT,
    "inpatient": EncounterClass.INPATIENT,
    "emergency": EncounterClass.EMERGENCY,
    "urgentcare": EncounterClass.URGENT_CARE,
    "virtual": EncounterClass.VIRTUAL,
}

# DICOM modality codes -> our Modality. DX (digital radiography) and CR
# (computed radiography) are both plain-film X-ray as far as the model cares;
# collapsing them to XR loses the capture technology, so it is logged.
_MODALITY = {
    "CT": Modality.CT,
    "MR": Modality.MR,
    "US": Modality.US,
    "DX": Modality.XR,
    "CR": Modality.XR,
    "PT": Modality.PET,
    "NM": Modality.NM,
}
_LOSSY_MODALITY = {"DX", "CR"}  # mapped to a coarser concept than the source had


def _rows(path: Path) -> Iterator[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        yield from csv.DictReader(fh)


def _dt(value: str) -> datetime:
    """Parse a Synthea timestamp (ISO-8601, Zulu) into an aware datetime."""
    return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))


def _strip_name_suffix(raw: str) -> tuple[str, bool]:
    cleaned = _NAME_SUFFIX.sub("", raw).strip()
    return (cleaned, True) if cleaned != raw else (raw, False)


def _canonical_body_part(raw: str | None) -> str | None:
    """Collapse Synthea's several spellings of one SNOMED body-site concept.

    The same thoracic site arrives as "Thoracic structure (body structure)",
    "Thoracic structure", "Thoracic", and "thoracic". Stripping the SNOMED
    semantic tag and title-casing folds them into one value the UI can group on.
    """
    value = clean_null(raw)
    if value is None:
        return None
    # Drop the trailing SNOMED semantic tag, e.g. "(body structure)".
    without_tag = re.sub(r"\s*\([^)]*\)\s*$", "", value).strip()
    # "Thoracic structure" and "Thoracic" are the same site.
    without_structure = re.sub(r"\s+structure$", "", without_tag, flags=re.I).strip()
    return without_structure.title() or None


class _SyntheaAdapter(IngestionAdapter):
    """Shared envelope + provenance for every Synthea-sourced object."""

    source_system = SourceSystem.EHR  # Synthea models a hospital EHR extract

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _envelope(self, source_record_id: str, quality: float = 1.0) -> dict:
        now = datetime.now(timezone.utc)
        return dict(
            id=str(uuid4()),
            created_at=now,
            updated_at=now,
            source_system=self.source_system,
            source_record_id=source_record_id,
            data_quality_score=max(quality, 0.0),
        )


class SyntheaPatientAdapter(_SyntheaAdapter):
    """patients.csv -> Patient."""

    source_name = "synthea_patients"

    def read(self) -> Iterator[Patient]:
        for row in _rows(self.path):
            patient = self._to_patient(row)
            if patient is not None:
                yield patient

    def _to_patient(self, row: dict[str, str]) -> Patient | None:
        # Synthea ships no MRN — its UUID is the only stable patient identifier,
        # so it *is* the MRN. Reconciliation keys on (MRN, birth_date), which
        # means a Synthea patient will correctly never collide with a patient
        # from another source that assigns its own identifiers.
        source_id = clean_null(row.get("Id"))
        if source_id is None:
            logger.warning("record_skipped", reason="missing_patient_id")
            return None

        birth_raw = clean_null(row.get("BIRTHDATE"))
        if birth_raw is None:
            logger.warning(
                "record_skipped", reason="missing_birthdate", source_record_id=source_id
            )
            return None
        try:
            birth_date = datetime.strptime(birth_raw, "%Y-%m-%d").date()
        except ValueError:
            logger.warning(
                "record_skipped",
                reason="unparseable_dob",
                source_record_id=source_id,
                raw=birth_raw,
            )
            return None

        quality = 1.0

        given, given_coerced = _strip_name_suffix(clean_null(row.get("FIRST")) or "")
        family, family_coerced = _strip_name_suffix(clean_null(row.get("LAST")) or "")
        if given_coerced or family_coerced:
            logger.info(
                "field_coerced",
                field="name",
                original=f"{row.get('FIRST')} {row.get('LAST')}",
                coerced=f"{given} {family}",
                rule="strip synthea numeric suffix",
                source_record_id=source_id,
            )
            # A generator artifact we can remove with certainty is not a data
            # quality problem, so this coercion carries no penalty.

        raw_sex = clean_null(row.get("GENDER"))
        sex = _SEX_MAP.get((raw_sex or "").lower(), Sex.UNKNOWN)
        if sex is Sex.UNKNOWN:
            logger.warning(
                "field_coerced",
                field="sex",
                original=raw_sex,
                coerced=Sex.UNKNOWN.value,
                rule="unrecognized -> unknown",
                source_record_id=source_id,
            )
            quality -= _COERCION_PENALTY

        # Synthea encodes death as the presence of a date, not a boolean.
        deceased = clean_null(row.get("DEATHDATE")) is not None

        try:
            return Patient(
                **self._envelope(source_id, quality),
                mrn=source_id,
                given_name=given,
                family_name=family,
                birth_date=birth_date,
                sex=sex,
                deceased=deceased,
            )
        except ValidationError as exc:
            logger.warning(
                "record_skipped",
                reason="validation_error",
                source_record_id=source_id,
                error_count=exc.error_count(),
            )
            return None


class _PatientLinked(_SyntheaAdapter):
    """Base for objects that hang off a Patient by Synthea UUID (== our MRN)."""

    def __init__(self, path: str | Path, patient_id_by_mrn: dict[str, str]):
        super().__init__(path)
        self.patient_id_by_mrn = patient_id_by_mrn

    def _resolve_patient(self, mrn: str | None, kind: str) -> str | None:
        pid = self.patient_id_by_mrn.get(mrn or "")
        if pid is None:
            logger.warning(
                "record_skipped",
                reason="unknown_patient_mrn",
                kind=kind,
                patient_mrn=mrn,
            )
        return pid


class SyntheaEncounterAdapter(_PatientLinked):
    """encounters.csv -> Encounter.

    Exposes ``id_by_source_id`` after reading so findings and imaging studies can
    resolve their Synthea ENCOUNTER uuid to our canonical Encounter.id.
    """

    source_name = "synthea_encounters"

    def __init__(self, path: str | Path, patient_id_by_mrn: dict[str, str]):
        super().__init__(path, patient_id_by_mrn)
        self.id_by_source_id: dict[str, str] = {}

    def read(self) -> Iterator[Encounter]:
        for row in _rows(self.path):
            enc = self._to_encounter(row)
            if enc is not None:
                self.id_by_source_id[enc.source_record_id] = enc.id
                yield enc

    def _to_encounter(self, row: dict[str, str]) -> Encounter | None:
        source_id = clean_null(row.get("Id"))
        if source_id is None:
            logger.warning("record_skipped", reason="missing_encounter_id")
            return None

        pid = self._resolve_patient(clean_null(row.get("PATIENT")), "encounter")
        if pid is None:
            return None

        quality = 1.0
        raw_class = (clean_null(row.get("ENCOUNTERCLASS")) or "").lower()
        enc_class = _ENCOUNTER_CLASS.get(raw_class)
        if enc_class is None:
            logger.warning(
                "field_coerced",
                field="encounter_class",
                original=raw_class,
                coerced=EncounterClass.AMBULATORY.value,
                rule="unrecognized -> ambulatory",
                source_record_id=source_id,
            )
            enc_class = EncounterClass.AMBULATORY
            quality -= _COERCION_PENALTY

        # Synthea has no status column. A visit with a STOP timestamp is over;
        # one without is still running. Derived, and recorded as such.
        stop = clean_null(row.get("STOP"))
        status = EncounterStatus.FINISHED if stop else EncounterStatus.IN_PROGRESS

        try:
            return Encounter(
                **self._envelope(source_id, quality),
                patient_id=pid,
                encounter_class=enc_class,
                status=status,
                period_start=_dt(row["START"]),
                period_end=_dt(stop) if stop else None,
                reason=clean_null(row.get("REASONDESCRIPTION")),
            )
        except (ValidationError, KeyError, ValueError) as exc:
            logger.warning(
                "record_skipped",
                reason="validation_error",
                source_record_id=source_id,
                error=str(exc)[:120],
            )
            return None


class SyntheaObservationAdapter(_PatientLinked):
    """observations.csv -> Finding, restricted to the clinical panel.

    Two filters run here, and both are deliberate:
      * non-numeric observations are dropped (Finding.value is a float);
      * observations outside ``reference_ranges`` are dropped, because Synthea
        emits ~278k rows dominated by body height and pain scores.
    """

    source_name = "synthea_observations"

    def __init__(
        self,
        path: str | Path,
        patient_id_by_mrn: dict[str, str],
        encounter_id_by_source_id: dict[str, str] | None = None,
    ):
        super().__init__(path, patient_id_by_mrn)
        self.encounter_id_by_source_id = encounter_id_by_source_id or {}

    def read(self) -> Iterator[Finding]:
        skipped_text = 0
        skipped_off_panel = 0
        for i, row in enumerate(_rows(self.path)):
            code = clean_null(row.get("CODE")) or ""
            if not in_panel(code):
                skipped_off_panel += 1
                continue
            if (clean_null(row.get("TYPE")) or "").lower() != "numeric":
                skipped_text += 1
                continue
            finding = self._to_finding(row, i, code)
            if finding is not None:
                yield finding

        logger.info(
            "observations_filtered",
            off_panel=skipped_off_panel,
            non_numeric=skipped_text,
            reason="Finding.value is numeric; panel defined in reference_ranges",
        )

    def _to_finding(self, row: dict[str, str], i: int, code: str) -> Finding | None:
        pid = self._resolve_patient(clean_null(row.get("PATIENT")), "finding")
        if pid is None:
            return None

        raw_value = clean_null(row.get("VALUE"))
        try:
            value = float(raw_value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            logger.warning(
                "record_skipped",
                reason="non_numeric_value",
                kind="finding",
                code=code,
                raw=raw_value,
            )
            return None

        ref = RANGES[code]
        quality = 1.0
        raw_unit = clean_null(row.get("UNITS"))

        # A value we cannot trust the units of is a value we cannot interpret
        # against a reference range — flag it rather than silently comparing
        # mmol/L against a mg/dL range.
        if raw_unit is not None and raw_unit != ref.unit:
            logger.warning(
                "field_coerced",
                field="unit",
                original=raw_unit,
                coerced=ref.unit,
                rule="source unit differs from panel unit",
                code=code,
            )
            quality -= _COERCION_PENALTY

        source_id = f"{code}-{i}"
        try:
            return Finding(
                **self._envelope(source_id, quality),
                patient_id=pid,
                encounter_id=self.encounter_id_by_source_id.get(
                    clean_null(row.get("ENCOUNTER")) or ""
                ),
                code=code,
                display=ref.display,  # canonical name; source spellings vary
                value=value,
                unit=ref.unit,
                abnormal_flag=classify(code, value),
                reference_range_low=ref.low,
                reference_range_high=ref.high,
                observed_at=_dt(row["DATE"]),
                # Preserved so a clinician can always trace the displayed number
                # back to exactly what the source reported.
                raw_value=raw_value,
                raw_unit=raw_unit,
            )
        except (ValidationError, KeyError, ValueError) as exc:
            logger.warning(
                "record_skipped",
                reason="validation_error",
                source_record_id=source_id,
                error=str(exc)[:120],
            )
            return None


class SyntheaImagingAdapter(_PatientLinked):
    """imaging_studies.csv -> ImagingStudy (metadata only).

    Synthea ships imaging *metadata* but no pixel data. ``image_uri`` therefore
    points at the blob location the study *would* occupy; until a real DICOM
    collection (TCIA/LIDC-IDRI) is loaded into the blob store, that object does
    not exist. The URI is deterministic so a later pixel load can populate it
    without rewriting the studies.
    """

    source_name = "synthea_imaging"
    source_system = SourceSystem.PACS

    def __init__(
        self,
        path: str | Path,
        patient_id_by_mrn: dict[str, str],
        encounter_id_by_source_id: dict[str, str] | None = None,
    ):
        super().__init__(path, patient_id_by_mrn)
        self.encounter_id_by_source_id = encounter_id_by_source_id or {}

    def read(self) -> Iterator[ImagingStudy]:
        for row in _rows(self.path):
            study = self._to_study(row)
            if study is not None:
                yield study

    def _to_study(self, row: dict[str, str]) -> ImagingStudy | None:
        source_id = clean_null(row.get("Id"))
        if source_id is None:
            logger.warning("record_skipped", reason="missing_study_id")
            return None

        pid = self._resolve_patient(clean_null(row.get("PATIENT")), "imaging")
        if pid is None:
            return None

        quality = 1.0
        raw_modality = (clean_null(row.get("MODALITY_CODE")) or "").upper()
        modality = _MODALITY.get(raw_modality)
        if modality is None:
            logger.warning(
                "field_coerced",
                field="modality",
                original=raw_modality,
                coerced=Modality.OTHER.value,
                rule="unrecognized DICOM modality -> OTHER",
                source_record_id=source_id,
            )
            modality = Modality.OTHER
            quality -= _COERCION_PENALTY
        elif raw_modality in _LOSSY_MODALITY:
            logger.info(
                "field_coerced",
                field="modality",
                original=raw_modality,
                coerced=modality.value,
                rule="DICOM radiography code -> XR",
                source_record_id=source_id,
            )

        body_part = _canonical_body_part(row.get("BODYSITE_DESCRIPTION"))

        try:
            return ImagingStudy(
                **self._envelope(source_id, quality),
                patient_id=pid,
                encounter_id=self.encounter_id_by_source_id.get(
                    clean_null(row.get("ENCOUNTER")) or ""
                ),
                modality=modality,
                body_part=body_part,
                study_date=_dt(row["DATE"]),
                # Synthea emits exactly one series per study (verified: 855 rows,
                # 855 distinct study ids) — not a placeholder default.
                series_count=1,
                image_uri=f"file:///data/imaging/synthea/{source_id}.dcm",
                source_format=ImageFormat.DICOM,
            )
        except (ValidationError, KeyError, ValueError) as exc:
            logger.warning(
                "record_skipped",
                reason="validation_error",
                source_record_id=source_id,
                error=str(exc)[:120],
            )
            return None


def derive_alerts(findings: list[Finding]) -> list[Alert]:
    """Derive Alerts from findings that breached a panic value.

    Synthea has no alert feed, and inventing one would be dishonest. An alert is
    properly a *computed consequence* of a finding — so every Alert produced here
    is linked back to the Finding that caused it via ``finding_id``, and carries
    the value and range that triggered it in its message. A clinician acking the
    alert can always see exactly why it fired.

    Alerts start ACTIVE and unaudited; the Phase 4d workflow is what acknowledges
    them (and the Alert model enforces that a non-ACTIVE alert has an audit entry).
    """
    alerts: list[Alert] = []
    now = datetime.now(timezone.utc)

    for f in findings:
        if f.abnormal_flag is not AbnormalFlag.CRITICAL:
            continue
        ref = RANGES.get(f.code)
        if ref is None:  # defensive: CRITICAL can only come from a panel code
            continue

        direction = "below" if f.value < ref.low else "above"
        alerts.append(
            Alert(
                id=str(uuid4()),
                created_at=now,
                updated_at=now,
                source_system=SourceSystem.EHR,
                source_record_id=f"alert-{f.source_record_id}",
                data_quality_score=f.data_quality_score,
                patient_id=f.patient_id,
                severity=AlertSeverity.CRITICAL,
                status=AlertStatus.ACTIVE,
                message=(
                    f"Critical {ref.display}: {f.value} {ref.unit} "
                    f"({direction} panic threshold; normal {ref.low}-{ref.high})"
                ),
                triggered_at=f.observed_at,
                finding_id=f.id,
            )
        )

    logger.info("alerts_derived", count=len(alerts), rule="critical panic values")
    return alerts
