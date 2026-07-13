"""Clinical reference ranges — the panel the dashboard ingests, and what's abnormal.

Real observation feeds (Synthea, and most EHR extracts) ship a code, a value, and
a unit — but no interpretation. Deciding whether 6.9 mmol/L of potassium is
"normal", "high", or "call someone now" is a *clinical* judgement, and it has to
live somewhere explicit and reviewable rather than being buried in an adapter.
This table is that place.

It does two jobs:

1. **Scope.** Only codes listed here are ingested as Findings. Synthea emits ~278k
   numeric observations, most of which are body height, pain scores, and
   quality-of-life indices — not clinically actionable. Restricting to this panel
   is a deliberate filter, not an oversight.

2. **Interpretation.** ``classify()`` maps a value to an ``AbnormalFlag`` using
   adult reference ranges, and ``CRITICAL`` uses standard laboratory *panic
   values* — the thresholds at which a lab is obligated to phone a clinician —
   rather than an arbitrary multiple of the normal range. A Finding flagged
   CRITICAL is what spawns an Alert downstream.

Ranges are adult, non-pregnant, and unit-specific; they are intentionally simple
(no age/sex stratification), which is the right level of fidelity for a demo and
is documented as such rather than pretended otherwise.
"""
from __future__ import annotations

from dataclasses import dataclass

from domain.models.finding import AbnormalFlag


@dataclass(frozen=True)
class ReferenceRange:
    """Normal range for one observation code, plus optional panic values."""

    code: str  # LOINC
    display: str  # canonical display name (source spellings vary)
    unit: str  # canonical unit; a source reporting anything else is a coercion
    low: float
    high: float
    # Panic values. Absent means "this analyte has no standard critical
    # threshold" — out-of-range is still flagged HIGH/LOW, just never CRITICAL.
    critical_low: float | None = None
    critical_high: float | None = None


# The ingested panel: vitals, basic metabolic, lipids, haematology.
_PANEL: tuple[ReferenceRange, ...] = (
    # -- vitals ----------------------------------------------------------- #
    ReferenceRange("8480-6", "Systolic Blood Pressure", "mm[Hg]", 90, 120, 70, 180),
    ReferenceRange("8462-4", "Diastolic Blood Pressure", "mm[Hg]", 60, 80, None, 120),
    ReferenceRange("8867-4", "Heart Rate", "/min", 60, 100, 40, 130),
    ReferenceRange("9279-1", "Respiratory Rate", "/min", 12, 20, 8, 30),
    ReferenceRange("39156-5", "Body Mass Index", "kg/m2", 18.5, 24.9),
    # -- basic metabolic panel -------------------------------------------- #
    ReferenceRange("2339-0", "Glucose", "mg/dL", 70, 99, 50, 400),
    ReferenceRange("6299-2", "Urea Nitrogen", "mg/dL", 7, 20, None, 100),
    ReferenceRange("38483-4", "Creatinine", "mg/dL", 0.6, 1.2, None, 4.0),
    ReferenceRange("49765-1", "Calcium", "mg/dL", 8.5, 10.2, 6.0, 13.0),
    ReferenceRange("2947-0", "Sodium", "mmol/L", 135, 145, 120, 160),
    ReferenceRange("6298-4", "Potassium", "mmol/L", 3.5, 5.1, 2.5, 6.5),
    ReferenceRange("2069-3", "Chloride", "mmol/L", 98, 107),
    ReferenceRange("20565-8", "Carbon Dioxide", "mmol/L", 22, 29, 10, 40),
    # -- lipids ------------------------------------------------------------ #
    # Lipids are risk markers, not acute derangements: a high LDL is a reason to
    # start a statin, never a reason to phone the ward. No panic values.
    ReferenceRange("2093-3", "Total Cholesterol", "mg/dL", 0, 200),
    ReferenceRange("2571-8", "Triglycerides", "mg/dL", 0, 150),
    ReferenceRange("18262-6", "LDL Cholesterol", "mg/dL", 0, 100),
    ReferenceRange("2085-9", "HDL Cholesterol", "mg/dL", 40, 200),
    # -- haematology ------------------------------------------------------- #
    ReferenceRange("718-7", "Hemoglobin", "g/dL", 12.0, 17.5, 7.0, 20.0),
    ReferenceRange("4548-4", "Hemoglobin A1c", "%", 4.0, 5.6),
    ReferenceRange("787-2", "MCV", "fL", 80, 100),
    ReferenceRange("785-6", "MCH", "pg", 27, 33),
    ReferenceRange("786-4", "MCHC", "g/dL", 32, 36),
)

RANGES: dict[str, ReferenceRange] = {r.code: r for r in _PANEL}


def in_panel(code: str) -> bool:
    """True if this observation code is one the dashboard ingests."""
    return code in RANGES


def classify(code: str, value: float) -> AbnormalFlag:
    """Interpret a value against its reference range.

    Panic values are checked first: a potassium of 6.9 is CRITICAL, not merely
    HIGH, and the severity must not depend on which branch happens to run first.
    """
    ref = RANGES.get(code)
    if ref is None:
        return AbnormalFlag.NORMAL

    if ref.critical_low is not None and value <= ref.critical_low:
        return AbnormalFlag.CRITICAL
    if ref.critical_high is not None and value >= ref.critical_high:
        return AbnormalFlag.CRITICAL
    if value < ref.low:
        return AbnormalFlag.LOW
    if value > ref.high:
        return AbnormalFlag.HIGH
    return AbnormalFlag.NORMAL
