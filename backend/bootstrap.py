"""One-time seeding so a fresh boot shows a populated dashboard.

Two sources, and which one runs depends on what's on disk:

* **Synthea** (``data/synthea/csv``, fetched by ``scripts/fetch_synthea.py``) —
  the real dataset: 1,171 patients, ~53k encounters, ~150k findings. Used
  whenever it is present.
* **The hand-authored fixtures** in ``ingestion/sample_data`` — a handful of
  deliberately malformed rows that exercise the CSV adapter's coercion paths and
  the CSV↔FHIR reconciliation demo. Used as the fallback so the repo stays
  clonable and testable without a 9 MB download.

Either way this wires ingestion to the service layer — going through both, never
around them.
"""
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import SEED_SOURCE
from backend.db_models import PatientORM
from backend.services import (
    alert_service,
    encounter_service,
    finding_service,
    imaging_service,
    patient_service,
)
from ingestion.base import logger
from ingestion.csv_adapter import CSVPatientAdapter
from ingestion.csv_clinical import (
    AlertCSVAdapter,
    EncounterCSVAdapter,
    FindingCSVAdapter,
    ImagingStudyCSVAdapter,
)
from ingestion.fhir_adapter import FHIRPatientAdapter
from ingestion.reconcile import reconcile
from ingestion.synthea_adapter import (
    SyntheaEncounterAdapter,
    SyntheaImagingAdapter,
    SyntheaObservationAdapter,
    SyntheaPatientAdapter,
    derive_alerts,
)

_ROOT = Path(__file__).parent.parent
_SAMPLE = _ROOT / "ingestion" / "sample_data"
_SYNTHEA = _ROOT / "data" / "synthea" / "csv"

SeedSource = Literal["auto", "synthea", "sample"]


def seed_if_empty(db: Session, source: SeedSource | None = None) -> dict[str, int]:
    """Seed the database only if the patients table is empty.

    ``source`` is explicit on purpose. An earlier version simply used Synthea
    whenever ``data/synthea`` happened to exist on disk, which meant the test
    suite's behaviour depended on whether the developer had run the fetch script
    — tests must pin ``source="sample"`` and get the same fixtures every time.

    Defaults to the ``SEED_SOURCE`` env var, itself defaulting to ``"auto"``:
    Synthea when it has been fetched, the hand-authored fixtures otherwise.

    Returns a dict of per-object insert counts (empty if already seeded).
    """
    if db.scalar(select(PatientORM).limit(1)) is not None:
        return {}

    resolved: SeedSource = source or SEED_SOURCE  # type: ignore[assignment]
    if resolved == "auto":
        resolved = "synthea" if (_SYNTHEA / "patients.csv").exists() else "sample"

    if resolved == "synthea":
        if not (_SYNTHEA / "patients.csv").exists():
            raise FileNotFoundError(
                f"SEED_SOURCE=synthea but no data at {_SYNTHEA}. "
                "Run: python scripts/fetch_synthea.py"
            )
        logger.info("seeding", source="synthea", path=str(_SYNTHEA))
        return _seed_synthea(db)

    logger.info(
        "seeding",
        source="sample_fixtures",
        hint="run scripts/fetch_synthea.py for the real dataset",
    )
    return _seed_sample(db)


def _seed_synthea(db: Session) -> dict[str, int]:
    """Seed from the real Synthea export."""
    counts: dict[str, int] = {}

    patients = list(SyntheaPatientAdapter(_SYNTHEA / "patients.csv").read())
    counts["patients"] = patient_service.bulk_create(db, patients)

    # Synthea identifies patients by UUID and we carry that through as the MRN,
    # so this map is exact — no fuzzy matching needed within a single source.
    mrn_to_id = {p.mrn: p.id for p in patients}

    # The encounter adapter records source-uuid -> canonical-id as it reads, so
    # findings and imaging studies can link to the visit they belong to.
    enc_adapter = SyntheaEncounterAdapter(_SYNTHEA / "encounters.csv", mrn_to_id)
    encounters = list(enc_adapter.read())
    counts["encounters"] = encounter_service.bulk_create(db, encounters)
    enc_map = enc_adapter.id_by_source_id

    findings = list(
        SyntheaObservationAdapter(
            _SYNTHEA / "observations.csv", mrn_to_id, enc_map
        ).read()
    )
    counts["findings"] = finding_service.bulk_create(db, findings)

    counts["imaging"] = imaging_service.bulk_create(
        db,
        list(
            SyntheaImagingAdapter(
                _SYNTHEA / "imaging_studies.csv", mrn_to_id, enc_map
            ).read()
        ),
    )

    # Synthea ships no alerts — they are derived from findings that breached a
    # panic value, and each one links back to the finding that caused it.
    counts["alerts"] = alert_service.bulk_create(db, derive_alerts(findings))
    return counts


def _seed_sample(db: Session) -> dict[str, int]:
    """Seed from the hand-authored fixtures (CSV + FHIR, with reconciliation)."""
    counts: dict[str, int] = {}

    # Source 1: CSV.
    csv_patients = list(CSVPatientAdapter(_SAMPLE / "patients.csv").read())
    n_csv = patient_service.bulk_create(db, csv_patients)

    # Source 2: FHIR. Reconcile against the CSV patients on (MRN, birth_date) so
    # the same person collapses to one canonical record; only genuinely new
    # patients are inserted (e.g. Ada appears in both and is deduped).
    fhir_patients = list(FHIRPatientAdapter(_SAMPLE / "fhir_bundle.json").read())
    new_fhir, merged = reconcile(csv_patients, fhir_patients)
    n_fhir = patient_service.bulk_create(db, new_fhir) if new_fhir else 0
    counts["patients"] = n_csv + n_fhir
    counts["patients_reconciled"] = merged

    mrn_to_id = {p.mrn: p.id for p in patient_service.list_patients(db)}

    counts["encounters"] = encounter_service.bulk_create(
        db, list(EncounterCSVAdapter(_SAMPLE / "encounters.csv", mrn_to_id).read())
    )
    counts["findings"] = finding_service.bulk_create(
        db, list(FindingCSVAdapter(_SAMPLE / "findings.csv", mrn_to_id).read())
    )
    counts["alerts"] = alert_service.bulk_create(
        db, list(AlertCSVAdapter(_SAMPLE / "alerts.csv", mrn_to_id).read())
    )
    counts["imaging"] = imaging_service.bulk_create(
        db, list(ImagingStudyCSVAdapter(_SAMPLE / "imaging.csv", mrn_to_id).read())
    )
    return counts
