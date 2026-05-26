"""FHIR R4 ingestion adapter — maps Patient resources from a Bundle to domain Patients.

This is where FHIR's nested, reference-heavy JSON gets flattened onto our flat
domain model. Phase 4a maps Patient; Observation/Encounter mapping follows the
same pattern when needed. Resources missing an MRN or birth date are skipped and
logged (they can't be reconciled).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from domain.models.base import SourceSystem
from domain.models.patient import Patient, Sex
from ingestion.base import IngestionAdapter, logger

# FHIR administrative-gender codes line up with our Sex enum values.
_FHIR_GENDER = {
    "male": Sex.MALE,
    "female": Sex.FEMALE,
    "other": Sex.OTHER,
    "unknown": Sex.UNKNOWN,
}


class FHIRPatientAdapter(IngestionAdapter[Patient]):
    source_name = "fhir_api"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def read(self) -> Iterator[Patient]:
        bundle = json.loads(self.path.read_text(encoding="utf-8"))
        for entry in bundle.get("entry", []):
            res = entry.get("resource", {})
            if res.get("resourceType") != "Patient":
                continue
            patient = self._to_patient(res)
            if patient is not None:
                yield patient

    def _to_patient(self, res: dict) -> Patient | None:
        mrn = next(
            (i.get("value") for i in res.get("identifier", []) if i.get("value")),
            None,
        )
        birth = res.get("birthDate")
        if not mrn or not birth:
            logger.warning(
                "record_skipped",
                reason="missing_mrn_or_birthdate",
                source="fhir",
                resource_id=res.get("id"),
            )
            return None
        name = (res.get("name") or [{}])[0]
        now = datetime.now(timezone.utc)
        return Patient(
            id=str(uuid4()),
            created_at=now,
            updated_at=now,
            source_system=SourceSystem.FHIR_API,
            source_record_id=res.get("id") or mrn,
            data_quality_score=1.0,
            mrn=mrn,
            given_name=" ".join(name.get("given", [])) or "",
            family_name=name.get("family", "") or "",
            birth_date=date.fromisoformat(birth),
            sex=_FHIR_GENDER.get(res.get("gender", "unknown"), Sex.UNKNOWN),
            deceased=bool(res.get("deceasedBoolean", False)),
        )
