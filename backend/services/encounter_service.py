"""Encounter service — the only place encounter SQL lives."""
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db_models import EncounterORM
from domain.models.encounter import Encounter

logger = structlog.get_logger()


def _to_orm(e: Encounter) -> EncounterORM:
    return EncounterORM(
        id=e.id,
        created_at=e.created_at,
        updated_at=e.updated_at,
        source_system=e.source_system.value,
        source_record_id=e.source_record_id,
        data_quality_score=e.data_quality_score,
        patient_id=e.patient_id,
        encounter_class=e.encounter_class.value,
        status=e.status.value,
        period_start=e.period_start,
        period_end=e.period_end,
        reason=e.reason,
    )


def list_encounters(db: Session, patient_id: str | None = None) -> list[Encounter]:
    stmt = select(EncounterORM).order_by(EncounterORM.period_start)
    if patient_id:
        stmt = stmt.where(EncounterORM.patient_id == patient_id)
    return [Encounter.model_validate(r) for r in db.scalars(stmt).all()]


def bulk_create(db: Session, items: list[Encounter]) -> int:
    db.add_all([_to_orm(e) for e in items])
    db.commit()
    logger.info("encounters_bulk_created", count=len(items))
    return len(items)
