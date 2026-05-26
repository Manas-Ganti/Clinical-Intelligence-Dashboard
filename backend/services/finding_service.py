"""Finding service — the only place finding SQL lives."""
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db_models import FindingORM
from domain.models.finding import Finding

logger = structlog.get_logger()


def _to_orm(f: Finding) -> FindingORM:
    return FindingORM(
        id=f.id,
        created_at=f.created_at,
        updated_at=f.updated_at,
        source_system=f.source_system.value,
        source_record_id=f.source_record_id,
        data_quality_score=f.data_quality_score,
        patient_id=f.patient_id,
        encounter_id=f.encounter_id,
        code=f.code,
        display=f.display,
        value=f.value,
        unit=f.unit,
        abnormal_flag=f.abnormal_flag.value,
        reference_range_low=f.reference_range_low,
        reference_range_high=f.reference_range_high,
        observed_at=f.observed_at,
        raw_value=f.raw_value,
        raw_unit=f.raw_unit,
    )


def list_findings(db: Session, patient_id: str | None = None) -> list[Finding]:
    stmt = select(FindingORM).order_by(FindingORM.observed_at)
    if patient_id:
        stmt = stmt.where(FindingORM.patient_id == patient_id)
    return [Finding.model_validate(r) for r in db.scalars(stmt).all()]


def bulk_create(db: Session, items: list[Finding]) -> int:
    db.add_all([_to_orm(f) for f in items])
    db.commit()
    logger.info("findings_bulk_created", count=len(items))
    return len(items)
