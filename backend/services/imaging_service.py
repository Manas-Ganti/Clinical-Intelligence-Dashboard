"""ImagingStudy service — the only place imaging SQL lives.

Stores metadata only; the pixel bytes live in object storage referenced by
image_uri (Phase 4b wires the actual blob store and binary ingestion).
"""
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db_models import ImagingStudyORM
from domain.models.imaging_study import ImagingStudy

logger = structlog.get_logger()


def _to_orm(s: ImagingStudy) -> ImagingStudyORM:
    return ImagingStudyORM(
        id=s.id,
        created_at=s.created_at,
        updated_at=s.updated_at,
        source_system=s.source_system.value,
        source_record_id=s.source_record_id,
        data_quality_score=s.data_quality_score,
        patient_id=s.patient_id,
        encounter_id=s.encounter_id,
        modality=s.modality.value,
        body_part=s.body_part,
        study_date=s.study_date,
        series_count=s.series_count,
        image_uri=s.image_uri,
        source_format=s.source_format.value,
    )


def list_imaging(db: Session, patient_id: str | None = None) -> list[ImagingStudy]:
    stmt = select(ImagingStudyORM).order_by(ImagingStudyORM.study_date)
    if patient_id:
        stmt = stmt.where(ImagingStudyORM.patient_id == patient_id)
    return [ImagingStudy.model_validate(r) for r in db.scalars(stmt).all()]


def bulk_create(db: Session, items: list[ImagingStudy]) -> int:
    db.add_all([_to_orm(s) for s in items])
    db.commit()
    logger.info("imaging_bulk_created", count=len(items))
    return len(items)
