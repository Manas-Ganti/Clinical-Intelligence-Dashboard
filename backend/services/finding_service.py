"""Finding service — the only place finding SQL lives."""
import structlog
from sqlalchemy import func, select
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


def list_findings(
    db: Session,
    patient_id: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[Finding]:
    """List findings, newest-ordered, optionally filtered and paged.

    ``limit=None`` is unbounded and exists for internal callers (seeding,
    analytics) that legitimately want every row. The API layer never passes None
    — a real Synthea load is ~150k findings, and serializing that into one
    response would be a denial of service on our own frontend.
    """
    stmt = select(FindingORM).order_by(FindingORM.observed_at)
    if patient_id:
        stmt = stmt.where(FindingORM.patient_id == patient_id)
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return [Finding.model_validate(r) for r in db.scalars(stmt).all()]


def count_findings(db: Session, patient_id: str | None = None) -> int:
    """Total matching findings, so a paged client knows how many there are."""
    stmt = select(func.count()).select_from(FindingORM)
    if patient_id:
        stmt = stmt.where(FindingORM.patient_id == patient_id)
    return db.scalar(stmt) or 0


def bulk_create(db: Session, items: list[Finding]) -> int:
    db.add_all([_to_orm(f) for f in items])
    db.commit()
    logger.info("findings_bulk_created", count=len(items))
    return len(items)
