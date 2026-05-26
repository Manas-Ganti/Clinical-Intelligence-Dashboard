"""SQL ingestion adapter — reads patients from an external relational source.

Works against any SQLAlchemy-supported database (the demo/tests use SQLite,
production would point at a Postgres warehouse). Rows missing an MRN or birth date
are skipped and logged.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterator
from uuid import uuid4

from sqlalchemy import Engine, text

from domain.models.base import SourceSystem
from domain.models.patient import Patient, Sex
from ingestion.base import IngestionAdapter, logger

_SEX = {"m": Sex.MALE, "male": Sex.MALE, "f": Sex.FEMALE, "female": Sex.FEMALE}


class SQLPatientAdapter(IngestionAdapter[Patient]):
    source_name = "ehr_sql"

    def __init__(self, engine: Engine, table: str = "legacy_patients"):
        self.engine = engine
        self.table = table

    def read(self) -> Iterator[Patient]:
        with self.engine.connect() as conn:
            rows = conn.execute(text(f"SELECT * FROM {self.table}")).mappings().all()
        for row in rows:
            patient = self._to_patient(dict(row))
            if patient is not None:
                yield patient

    def _to_patient(self, row: dict) -> Patient | None:
        mrn = str(row.get("patient_id") or "").strip()
        birth = row.get("birth_date")
        if not mrn or not birth:
            logger.warning("record_skipped", reason="missing_mrn_or_birthdate", source="sql")
            return None
        bd = birth if isinstance(birth, date) else date.fromisoformat(str(birth))
        now = datetime.now(timezone.utc)
        return Patient(
            id=str(uuid4()),
            created_at=now,
            updated_at=now,
            source_system=SourceSystem.EHR,
            source_record_id=mrn,
            data_quality_score=1.0,
            mrn=mrn,
            given_name=str(row.get("given_name") or ""),
            family_name=str(row.get("family_name") or ""),
            birth_date=bd,
            sex=_SEX.get(str(row.get("sex") or "").lower(), Sex.UNKNOWN),
            deceased=bool(row.get("deceased")),
        )
