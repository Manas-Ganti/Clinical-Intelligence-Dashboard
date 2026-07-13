"""Finding routes — thin handlers; optional ?patient_id= filter, always paged."""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.pagination import DEFAULT_LIMIT, Limit, Offset, set_total
from backend.services import finding_service
from domain.models.finding import Finding

router = APIRouter(tags=["findings"])


@router.get("/findings", response_model=list[Finding])
def list_findings(
    response: Response,
    patient_id: str | None = None,
    limit: Limit = DEFAULT_LIMIT,
    offset: Offset = 0,
    db: Session = Depends(get_db),
) -> list[Finding]:
    set_total(response, finding_service.count_findings(db, patient_id))
    return finding_service.list_findings(db, patient_id, limit=limit, offset=offset)
