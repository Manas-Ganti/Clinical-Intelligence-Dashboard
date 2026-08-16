"""Tool definitions and dispatch for the natural-language query layer.

Claude only ever *chooses* these tools and their arguments; OUR code executes
them against the service layer and returns typed results (CLAUDE.md #4). The model
never writes SQL and never sees the database — it can only invoke the operations
defined here, which is what makes the surface safe.
"""
from sqlalchemy.orm import Session

from backend.services import alert_service, finding_service, patient_service
from domain.models.alert import Alert
from domain.models.finding import Finding
from domain.models.patient import Patient

SYSTEM_PROMPT = """You are a clinical data query assistant for the Clinical \
Intelligence Dashboard. Answer questions ONLY by calling the provided tools — \
never invent patients, values, or counts. The dataset is small and synthetic.

Domain objects: Patient, Encounter, Finding (a lab/observation), ImagingStudy, \
Alert. Each Patient carries a data_quality_score and a source_system (one of \
csv_upload, fhir_api, ehr, pacs). Findings have an abnormal_flag (normal/high/\
low/critical). Alerts have a severity (info/warning/critical) and a status.

Tool results are CAPPED: each returns at most a page of rows plus a \
"total_matching" field giving the true number of rows that matched. When asked \
"how many", answer from "total_matching" — never from the number of rows you can \
see, which is only a sample. If "total_matching" is 0, say plainly that there are \
none; do not infer a number.

The same applies to DESCRIBING a result set, and it is the easier mistake to \
make. When "returned" is less than "total_matching", the rows you can see are \
the most recent page — not the population. Never state what is true of ALL \
matching rows from that page: which tests appear, what the value range is, which \
patients are involved, whether anything is unique or universal. Say what the \
sample shows and label it as a sample ("the most recent 100 of 995 are…"), or \
narrow the query with a filter and read "total_matching" again. Claiming every \
critical result is a Creatinine because the visible page happens to be Creatinine \
is exactly the error to avoid.

When a question cannot be answered with the available tools, say so plainly. \
After gathering data, give a concise answer grounded only in the tool results."""

# input_schema follows JSON Schema; the model fills these in. cache_control on the
# last tool marks the (static) tool prefix cacheable — a no-op until the prefix
# exceeds the model's minimum, but correct as the surface grows.
CLINICAL_TOOLS = [
    {
        "name": "find_patients",
        "description": (
            "Find patients, optionally filtered by family name (substring) or "
            "source system. Use for questions about patient populations or provenance."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "family_name": {"type": "string", "description": "Case-insensitive substring of the family name"},
                "source_system": {
                    "type": "string",
                    "enum": ["csv_upload", "fhir_api", "ehr", "pacs"],
                    "description": "Which source the patient was ingested from",
                },
                "limit": {"type": "integer", "default": 50},
            },
        },
    },
    {
        "name": "find_findings",
        "description": (
            "Search clinical findings/labs, optionally by abnormal flag, patient, "
            "or code/name substring. Use for questions about lab results or "
            "abnormal values across patients."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "abnormal_flag": {
                    "type": "string",
                    "enum": ["normal", "high", "low", "critical"],
                },
                "patient_id": {"type": "string"},
                "code_contains": {"type": "string", "description": "Substring of the finding name or code"},
                "limit": {"type": "integer", "default": 100},
            },
        },
    },
    {
        "name": "list_alerts",
        "description": "List alerts, optionally filtered by patient, severity, or status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "severity": {"type": "string", "enum": ["info", "warning", "critical"]},
                "status": {"type": "string", "enum": ["active", "acknowledged", "resolved"]},
                "limit": {"type": "integer", "default": 50},
            },
        },
        "cache_control": {"type": "ephemeral"},
    },
]

# Every tool result is fed straight back into the model's context, so an
# unbounded one is a context-window and cost bug, not just a slow query. This
# tool surface had no cap on list_alerts at all: "show me the critical alerts"
# returned all 995, ~58k tokens of JSON, on every call. The model does not need
# 995 rows to answer a question about them — it needs enough to summarise and
# count, and `total_matching` below tells it how many there really are.
MAX_TOOL_ROWS = 100


def _bounded(limit: object, default: int = 50) -> int:
    """Clamp whatever the model asked for into something we can afford to send.

    A model that asks for limit=10000 is not malicious, it is optimistic — and
    honouring it would blow the context window of exactly the small local models
    we want to be able to run this on.
    """
    try:
        requested = int(limit)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(1, min(requested, MAX_TOOL_ROWS))


def _patient_brief(p: Patient) -> dict:
    return {
        "id": p.id,
        "mrn": p.mrn,
        "name": f"{p.given_name} {p.family_name}",
        "sex": p.sex.value,
        "source_system": p.source_system.value,
        "data_quality_score": p.data_quality_score,
    }


def _finding_brief(f: Finding) -> dict:
    return {
        "patient_id": f.patient_id,
        "display": f.display,
        "value": f.value,
        "unit": f.unit,
        "abnormal_flag": f.abnormal_flag.value,
        "observed_at": f.observed_at.isoformat(),
    }


def _alert_brief(a: Alert) -> dict:
    return {
        "id": a.id,
        "patient_id": a.patient_id,
        "severity": a.severity.value,
        "status": a.status.value,
        "message": a.message,
    }


def execute_tool(db: Session, name: str, tool_input: dict) -> dict:
    """Run a tool the model chose, against the service layer. Returns JSON-safe dict.

    Every filter runs in SQL. This used to load the whole table and filter the
    list in Python — fine against ten synthetic rows, a 150k-row table scan
    against real data, and on every turn of every question.

    Each result carries ``total_matching`` alongside the rows. Without it, a
    truncated result is indistinguishable from a complete one, and the model
    would confidently report "there are 50 critical alerts" when there are 995.
    """
    if name == "find_patients":
        limit = _bounded(tool_input.get("limit"), 50)
        filters = {
            "family_name": tool_input.get("family_name"),
            "source_system": tool_input.get("source_system"),
        }
        rows = patient_service.list_patients(db, limit=limit, **filters)
        total = patient_service.count_patients(db, **filters)
        return {
            "patients": [_patient_brief(p) for p in rows],
            "returned": len(rows),
            "total_matching": total,
        }

    if name == "find_findings":
        limit = _bounded(tool_input.get("limit"), 100)
        patient_id = tool_input.get("patient_id")
        filters = {
            "abnormal_flag": tool_input.get("abnormal_flag"),
            "code_contains": tool_input.get("code_contains"),
        }
        rows = finding_service.list_findings(db, patient_id, limit=limit, **filters)
        total = finding_service.count_findings(db, patient_id, **filters)
        return {
            "findings": [_finding_brief(f) for f in rows],
            "returned": len(rows),
            "total_matching": total,
        }

    if name == "list_alerts":
        limit = _bounded(tool_input.get("limit"), 50)
        patient_id = tool_input.get("patient_id")
        filters = {
            "severity": tool_input.get("severity"),
            "status": tool_input.get("status"),
        }
        rows = alert_service.list_alerts(db, patient_id, limit=limit, **filters)
        total = alert_service.count_alerts(db, patient_id, **filters)
        return {
            "alerts": [_alert_brief(a) for a in rows],
            "returned": len(rows),
            "total_matching": total,
        }

    return {"error": f"unknown tool: {name}"}
