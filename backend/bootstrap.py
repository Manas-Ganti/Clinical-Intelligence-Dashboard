"""One-time sample-data seeding so a fresh boot shows a populated dashboard.

Wires the ingestion layer to the service layer — going through both, never around
them. Secondary objects (encounters, findings, alerts, imaging) reference their
patient by MRN; we build the MRN -> canonical id map from the just-seeded
patients and hand it to those adapters.
"""
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db_models import PatientORM
from backend.services import (
    alert_service,
    encounter_service,
    finding_service,
    imaging_service,
    patient_service,
)
from ingestion.csv_adapter import CSVPatientAdapter
from ingestion.csv_clinical import (
    AlertCSVAdapter,
    EncounterCSVAdapter,
    FindingCSVAdapter,
    ImagingStudyCSVAdapter,
)
from ingestion.fhir_adapter import FHIRPatientAdapter
from ingestion.reconcile import reconcile

_DATA = Path(__file__).parent.parent / "ingestion" / "sample_data"


def seed_if_empty(db: Session) -> dict[str, int]:
    """Seed all sample data only if the patients table is empty.

    Returns a dict of per-object insert counts (empty if already seeded).
    """
    if db.scalar(select(PatientORM).limit(1)) is not None:
        return {}

    counts: dict[str, int] = {}

    # Source 1: CSV.
    csv_patients = list(CSVPatientAdapter(_DATA / "patients.csv").read())
    n_csv = patient_service.bulk_create(db, csv_patients)

    # Source 2: FHIR. Reconcile against the CSV patients on (MRN, birth_date) so
    # the same person collapses to one canonical record; only genuinely new
    # patients are inserted (e.g. Ada appears in both and is deduped).
    fhir_patients = list(FHIRPatientAdapter(_DATA / "fhir_bundle.json").read())
    new_fhir, merged = reconcile(csv_patients, fhir_patients)
    n_fhir = patient_service.bulk_create(db, new_fhir) if new_fhir else 0
    counts["patients"] = n_csv + n_fhir
    counts["patients_reconciled"] = merged

    mrn_to_id = {p.mrn: p.id for p in patient_service.list_patients(db)}

    counts["encounters"] = encounter_service.bulk_create(
        db, list(EncounterCSVAdapter(_DATA / "encounters.csv", mrn_to_id).read())
    )
    counts["findings"] = finding_service.bulk_create(
        db, list(FindingCSVAdapter(_DATA / "findings.csv", mrn_to_id).read())
    )
    counts["alerts"] = alert_service.bulk_create(
        db, list(AlertCSVAdapter(_DATA / "alerts.csv", mrn_to_id).read())
    )
    counts["imaging"] = imaging_service.bulk_create(
        db, list(ImagingStudyCSVAdapter(_DATA / "imaging.csv", mrn_to_id).read())
    )
    return counts
