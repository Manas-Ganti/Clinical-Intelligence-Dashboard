"""Alert domain model and its audit trail.

Per the project's accountability rule (CLAUDE.md #5), any Alert that has moved
past ACTIVE must carry at least one AuditEntry explaining who changed it and when.
That invariant is enforced here, at the contract level, so no layer above can
produce a silently-acknowledged alert.
"""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from domain.models.base import DomainBase


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AuditEntry(BaseModel):
    """Record of a single change to an alert's status.

    A typed nested model, never a raw dict — so the audit trail is as structured
    and validated as the alert it belongs to.
    """

    acknowledged_by: str
    acknowledged_at: datetime
    prior_status: AlertStatus
    new_status: AlertStatus
    note: str | None = None

    model_config = ConfigDict(from_attributes=True)


class Alert(DomainBase):
    patient_id: str
    severity: AlertSeverity
    status: AlertStatus = AlertStatus.ACTIVE
    message: str
    triggered_at: datetime
    finding_id: str | None = None  # typed link to the Finding that triggered it
    audit_trail: list[AuditEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def status_change_requires_audit(self) -> "Alert":
        # A status change away from ACTIVE cannot exist without an audit entry
        # recording who made it — this is CLAUDE.md rule #5 as a hard invariant.
        if self.status != AlertStatus.ACTIVE and not self.audit_trail:
            raise ValueError(
                f"alert in status '{self.status.value}' requires at least one "
                "audit entry"
            )
        return self
