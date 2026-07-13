"""Patient routes — thin handlers that call the service and return domain models.

No SQL and no business logic here (CLAUDE.md rule #2); FastAPI serializes the
returned Pydantic objects via ``response_model``.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.pagination import DEFAULT_LIMIT, Limit, Offset, set_total
from backend.services import patient_service
from backend.services.exceptions import NotFoundError
from domain.models.patient import Patient

router = APIRouter(tags=["patients"])


@router.get("/patients", response_model=list[Patient])
def list_patients(
    response: Response,
    limit: Limit = DEFAULT_LIMIT,
    offset: Offset = 0,
    db: Session = Depends(get_db),
) -> list[Patient]:
    set_total(response, patient_service.count_patients(db))
    return patient_service.list_patients(db, limit=limit, offset=offset)


@router.get("/patients/{patient_id}", response_model=Patient)
def get_patient(patient_id: str, db: Session = Depends(get_db)) -> Patient:
    try:
        return patient_service.get_by_id(db, patient_id)
    except NotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Patient {patient_id} not found"
        )
