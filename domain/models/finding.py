"""Finding domain model — an observation or lab result for a patient."""
from datetime import datetime
from enum import Enum

from pydantic import model_validator

from domain.models.base import DomainBase


class AbnormalFlag(str, Enum):
    NORMAL = "normal"
    HIGH = "high"
    LOW = "low"
    CRITICAL = "critical"


class Finding(DomainBase):
    patient_id: str
    encounter_id: str | None = None
    code: str  # observation code, e.g. a LOINC code
    display: str  # human-readable name of the observation
    value: float
    unit: str  # normalized unit (e.g. g/dL), set by the ingestion layer
    abnormal_flag: AbnormalFlag = AbnormalFlag.NORMAL
    reference_range_low: float | None = None
    reference_range_high: float | None = None
    observed_at: datetime
    # Pre-normalization value/unit, kept for auditability so a clinician can
    # always trace a displayed number back to exactly what the source reported.
    raw_value: str | None = None
    raw_unit: str | None = None

    @model_validator(mode="after")
    def reference_range_ordered(self) -> "Finding":
        lo, hi = self.reference_range_low, self.reference_range_high
        if lo is not None and hi is not None and lo > hi:
            raise ValueError(
                "reference_range_low cannot exceed reference_range_high"
            )
        return self
