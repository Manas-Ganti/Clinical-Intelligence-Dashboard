"""ImagingStudy routes — thin handlers; optional ?patient_id= filter."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.services import imaging_service
from domain.models.imaging_study import ImagingStudy

router = APIRouter(tags=["imaging"])


@router.get("/imaging", response_model=list[ImagingStudy])
def list_imaging(
    patient_id: str | None = None, db: Session = Depends(get_db)
) -> list[ImagingStudy]:
    return imaging_service.list_imaging(db, patient_id)
