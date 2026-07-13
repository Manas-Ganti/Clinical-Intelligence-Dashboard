"""Alert routes — list (optional ?patient_id=) and the audited acknowledge action."""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.pagination import DEFAULT_LIMIT, Limit, Offset, set_total
from backend.services import alert_service
from backend.services.exceptions import ConflictError, NotFoundError
from domain.models.alert import Alert

router = APIRouter(tags=["alerts"])


class AcknowledgeRequest(BaseModel):
    acknowledged_by: str
    note: str | None = None


@router.get("/alerts", response_model=list[Alert])
def list_alerts(
    response: Response,
    patient_id: str | None = None,
    limit: Limit = DEFAULT_LIMIT,
    offset: Offset = 0,
    db: Session = Depends(get_db),
) -> list[Alert]:
    set_total(response, alert_service.count_alerts(db, patient_id))
    return alert_service.list_alerts(db, patient_id, limit=limit, offset=offset)


@router.post("/alerts/{alert_id}/acknowledge", response_model=Alert)
def acknowledge_alert(
    alert_id: str, body: AcknowledgeRequest, db: Session = Depends(get_db)
) -> Alert:
    try:
        return alert_service.acknowledge(db, alert_id, body.acknowledged_by, body.note)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
