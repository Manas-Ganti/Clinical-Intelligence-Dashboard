"""Encounter domain model — a single clinical visit/interaction."""
from datetime import datetime
from enum import Enum

from pydantic import model_validator

from domain.models.base import DomainBase


class EncounterClass(str, Enum):
    INPATIENT = "inpatient"
    OUTPATIENT = "outpatient"
    EMERGENCY = "emergency"
    AMBULATORY = "ambulatory"
    VIRTUAL = "virtual"


class EncounterStatus(str, Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class Encounter(DomainBase):
    patient_id: str  # references Patient.id (the canonical one)
    encounter_class: EncounterClass
    status: EncounterStatus
    period_start: datetime
    period_end: datetime | None = None  # None while the encounter is ongoing
    reason: str | None = None

    @model_validator(mode="after")
    def period_end_after_start(self) -> "Encounter":
        if self.period_end is not None and self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self
