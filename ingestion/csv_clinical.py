"""CSV adapters for the clinical objects that hang off a Patient.

Each row references its patient by MRN (the stable source key); the adapter
resolves MRN -> canonical patient_id using a map built after patients are
ingested. Rows whose MRN is unknown are skipped and logged — a small
foreshadowing of the Phase 4 reconciliation step.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from domain.models.alert import Alert, AlertSeverity, AlertStatus
from domain.models.base import SourceSystem
from domain.models.encounter import Encounter, EncounterClass, EncounterStatus
from domain.models.finding import AbnormalFlag, Finding
from domain.models.imaging_study import ImageFormat, ImagingStudy, Modality
from ingestion.base import IngestionAdapter, clean_null, logger


def _rows(path: Path) -> Iterator[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        yield from csv.DictReader(fh)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.strip())


class _PatientLinkedAdapter(IngestionAdapter):
    """Shared base: resolves patient MRN -> canonical id, skips unknown MRNs."""

    source_system = SourceSystem.CSV_UPLOAD

    def __init__(self, path: str | Path, patient_id_by_mrn: dict[str, str]):
        self.path = Path(path)
        self.patient_id_by_mrn = patient_id_by_mrn

    def _envelope(self, source_record_id: str) -> dict:
        now = datetime.now(timezone.utc)
        return dict(
            id=str(uuid4()),
            created_at=now,
            updated_at=now,
            source_system=self.source_system,
            source_record_id=source_record_id,
            data_quality_score=1.0,
        )

    def _resolve(self, mrn: str | None, kind: str) -> str | None:
        pid = self.patient_id_by_mrn.get(mrn or "")
        if pid is None:
            logger.warning(
                "record_skipped", reason="unknown_patient_mrn", kind=kind, patient_mrn=mrn
            )
        return pid


class EncounterCSVAdapter(_PatientLinkedAdapter):
    source_name = "csv_encounters"

    def read(self) -> Iterator[Encounter]:
        for i, row in enumerate(_rows(self.path)):
            mrn = clean_null(row.get("patient_mrn"))
            pid = self._resolve(mrn, "encounter")
            if pid is None:
                continue
            end = clean_null(row.get("end"))
            yield Encounter(
                **self._envelope(f"{mrn}-enc-{i}"),
                patient_id=pid,
                encounter_class=EncounterClass(row["class"].strip().lower()),
                status=EncounterStatus(row["status"].strip().lower()),
                period_start=_dt(row["start"]),
                period_end=_dt(end) if end else None,
                reason=clean_null(row.get("reason")),
            )


class FindingCSVAdapter(_PatientLinkedAdapter):
    source_name = "csv_findings"

    def read(self) -> Iterator[Finding]:
        for i, row in enumerate(_rows(self.path)):
            mrn = clean_null(row.get("patient_mrn"))
            pid = self._resolve(mrn, "finding")
            if pid is None:
                continue
            flag = (clean_null(row.get("abnormal_flag")) or "normal").lower()
            yield Finding(
                **self._envelope(f"{mrn}-fnd-{i}"),
                patient_id=pid,
                code=row["code"].strip(),
                display=row["display"].strip(),
                value=float(row["value"]),
                unit=row["unit"].strip(),
                abnormal_flag=AbnormalFlag(flag),
                observed_at=_dt(row["observed_at"]),
            )


class AlertCSVAdapter(_PatientLinkedAdapter):
    source_name = "csv_alerts"

    def read(self) -> Iterator[Alert]:
        for i, row in enumerate(_rows(self.path)):
            mrn = clean_null(row.get("patient_mrn"))
            pid = self._resolve(mrn, "alert")
            if pid is None:
                continue
            yield Alert(
                **self._envelope(f"{mrn}-alt-{i}"),
                patient_id=pid,
                severity=AlertSeverity(row["severity"].strip().lower()),
                status=AlertStatus.ACTIVE,  # seeded alerts start active (Phase 4d acks them)
                message=row["message"].strip(),
                triggered_at=_dt(row["triggered_at"]),
            )


class ImagingStudyCSVAdapter(_PatientLinkedAdapter):
    source_name = "csv_imaging"
    source_system = SourceSystem.PACS

    def read(self) -> Iterator[ImagingStudy]:
        for i, row in enumerate(_rows(self.path)):
            mrn = clean_null(row.get("patient_mrn"))
            pid = self._resolve(mrn, "imaging")
            if pid is None:
                continue
            yield ImagingStudy(
                **self._envelope(f"{mrn}-img-{i}"),
                patient_id=pid,
                modality=Modality(row["modality"].strip().upper()),
                body_part=clean_null(row.get("body_part")),
                study_date=_dt(row["study_date"]),
                series_count=int(row["series_count"]),
                image_uri=row["image_uri"].strip(),
                source_format=ImageFormat(row["source_format"].strip().lower()),
            )
