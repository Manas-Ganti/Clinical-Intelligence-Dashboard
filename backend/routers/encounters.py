"""Encounter routes — thin handlers; optional ?patient_id= filter, always paged."""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.pagination import DEFAULT_LIMIT, Limit, Offset, set_total
from backend.services import encounter_service
from domain.models.encounter import Encounter

router = APIRouter(tags=["encounters"])


@router.get("/encounters", response_model=list[Encounter])
def list_encounters(
    response: Response,
    patient_id: str | None = None,
    limit: Limit = DEFAULT_LIMIT,
    offset: Offset = 0,
    db: Session = Depends(get_db),
) -> list[Encounter]:
    set_total(response, encounter_service.count_encounters(db, patient_id))
    return encounter_service.list_encounters(db, patient_id, limit=limit, offset=offset)
