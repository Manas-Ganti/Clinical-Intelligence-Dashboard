"""Encounter routes — thin handlers; optional ?patient_id= filter."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.services import encounter_service
from domain.models.encounter import Encounter

router = APIRouter(tags=["encounters"])


@router.get("/encounters", response_model=list[Encounter])
def list_encounters(
    patient_id: str | None = None, db: Session = Depends(get_db)
) -> list[Encounter]:
    return encounter_service.list_encounters(db, patient_id)
