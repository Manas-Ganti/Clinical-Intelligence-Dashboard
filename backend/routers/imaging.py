"""ImagingStudy routes — thin handlers; optional ?patient_id= filter, always paged."""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.pagination import DEFAULT_LIMIT, Limit, Offset, set_total
from backend.services import imaging_service
from domain.models.imaging_study import ImagingStudy

router = APIRouter(tags=["imaging"])


@router.get("/imaging", response_model=list[ImagingStudy])
def list_imaging(
    response: Response,
    patient_id: str | None = None,
    limit: Limit = DEFAULT_LIMIT,
    offset: Offset = 0,
    db: Session = Depends(get_db),
) -> list[ImagingStudy]:
    set_total(response, imaging_service.count_imaging(db, patient_id))
    return imaging_service.list_imaging(db, patient_id, limit=limit, offset=offset)
