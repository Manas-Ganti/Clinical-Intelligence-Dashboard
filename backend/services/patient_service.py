"""Patient service — the ONLY place patient SQL lives (CLAUDE.md rule #2).

Maps between PatientORM (persistence) and Patient (domain). Routes call these
functions and receive typed domain objects; they never see the ORM or SQL.
"""
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db_models import PatientORM
from backend.services.exceptions import NotFoundError
from domain.models.patient import Patient

logger = structlog.get_logger()


def _to_domain(row: PatientORM) -> Patient:
    # DomainBase sets from_attributes=True, so Pydantic reads ORM attributes and
    # coerces the stored enum strings (sex, source_system) back to enum members.
    return Patient.model_validate(row)


def _to_orm(p: Patient) -> PatientORM:
    return PatientORM(
        id=p.id,
        mrn=p.mrn,
        given_name=p.given_name,
        family_name=p.family_name,
        birth_date=p.birth_date,
        sex=p.sex.value,
        deceased=p.deceased,
        created_at=p.created_at,
        updated_at=p.updated_at,
        source_system=p.source_system.value,
        source_record_id=p.source_record_id,
        data_quality_score=p.data_quality_score,
    )


def list_patients(db: Session) -> list[Patient]:
    rows = db.scalars(select(PatientORM).order_by(PatientORM.family_name)).all()
    return [_to_domain(r) for r in rows]


def get_by_id(db: Session, patient_id: str) -> Patient:
    row = db.get(PatientORM, patient_id)
    if row is None:
        raise NotFoundError("Patient", patient_id)
    logger.info(
        "patient_retrieved",
        patient_id=patient_id,
        source_system=row.source_system,
    )
    return _to_domain(row)


def create_patient(db: Session, patient: Patient) -> Patient:
    row = _to_orm(patient)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_domain(row)


def bulk_create(db: Session, patients: list[Patient]) -> int:
    """Insert many patients in one transaction. Returns the count inserted."""
    db.add_all([_to_orm(p) for p in patients])
    db.commit()
    logger.info("patients_bulk_created", count=len(patients))
    return len(patients)
