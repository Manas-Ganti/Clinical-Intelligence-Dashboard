"""Alert service — the only place alert SQL lives.

Phase 3 supports listing/seeding (all seeded alerts are ACTIVE). Phase 4d adds
acknowledge(), which writes an AuditEntry in the same transaction as the status
change (CLAUDE.md rule #5).
"""
from datetime import datetime, timezone

import structlog
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db_models import AlertORM
from backend.services.exceptions import ConflictError, NotFoundError
from domain.models.alert import Alert, AlertStatus, AuditEntry

logger = structlog.get_logger()


def _to_orm(a: Alert) -> AlertORM:
    return AlertORM(
        id=a.id,
        created_at=a.created_at,
        updated_at=a.updated_at,
        source_system=a.source_system.value,
        source_record_id=a.source_record_id,
        data_quality_score=a.data_quality_score,
        patient_id=a.patient_id,
        severity=a.severity.value,
        status=a.status.value,
        message=a.message,
        triggered_at=a.triggered_at,
        finding_id=a.finding_id,
        audit_trail=[e.model_dump(mode="json") for e in a.audit_trail],
    )


def list_alerts(db: Session, patient_id: str | None = None) -> list[Alert]:
    stmt = select(AlertORM).order_by(AlertORM.triggered_at.desc())
    if patient_id:
        stmt = stmt.where(AlertORM.patient_id == patient_id)
    return [Alert.model_validate(r) for r in db.scalars(stmt).all()]


def bulk_create(db: Session, items: list[Alert]) -> int:
    db.add_all([_to_orm(a) for a in items])
    db.commit()
    logger.info("alerts_bulk_created", count=len(items))
    return len(items)


def get_by_id(db: Session, alert_id: str) -> Alert:
    row = db.get(AlertORM, alert_id)
    if row is None:
        raise NotFoundError("Alert", alert_id)
    return Alert.model_validate(row)


def acknowledge(
    db: Session, alert_id: str, acknowledged_by: str, note: str | None = None
) -> Alert:
    """Acknowledge an alert, writing an audit entry in the SAME transaction.

    Enforces CLAUDE.md rule #5: the status change and its audit record commit
    together or not at all, so a silently-acknowledged alert is impossible.
    """
    row = db.get(AlertORM, alert_id)
    if row is None:
        raise NotFoundError("Alert", alert_id)
    if row.status != AlertStatus.ACTIVE.value:
        raise ConflictError(f"Alert {alert_id} is already {row.status}")

    now = datetime.now(timezone.utc)
    entry = AuditEntry(
        acknowledged_by=acknowledged_by,
        acknowledged_at=now,
        prior_status=AlertStatus(row.status),
        new_status=AlertStatus.ACKNOWLEDGED,
        note=note,
    )
    # Apply both changes to the row, then validate the new state against the
    # domain invariant BEFORE committing — if it would violate rule #5, roll back.
    row.status = AlertStatus.ACKNOWLEDGED.value
    row.audit_trail = list(row.audit_trail or []) + [entry.model_dump(mode="json")]
    row.updated_at = now
    try:
        validated = Alert.model_validate(row)
    except ValidationError:
        db.rollback()
        raise

    db.commit()
    db.refresh(row)
    logger.info("alert_acknowledged", alert_id=alert_id, acknowledged_by=acknowledged_by)
    return validated
