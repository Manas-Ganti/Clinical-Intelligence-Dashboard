"""Finding routes — thin handlers; optional ?patient_id= filter."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.services import finding_service
from domain.models.finding import Finding

router = APIRouter(tags=["findings"])


@router.get("/findings", response_model=list[Finding])
def list_findings(
    patient_id: str | None = None, db: Session = Depends(get_db)
) -> list[Finding]:
    return finding_service.list_findings(db, patient_id)
