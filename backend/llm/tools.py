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
            },
        },
        "cache_control": {"type": "ephemeral"},
    },
]


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
    """Run a tool the model chose, against the service layer. Returns JSON-safe dict."""
    if name == "find_patients":
        fam = (tool_input.get("family_name") or "").lower()
        src = tool_input.get("source_system")
        limit = tool_input.get("limit", 50)
        rows = [
            p
            for p in patient_service.list_patients(db)
            if (not fam or fam in p.family_name.lower())
            and (not src or p.source_system.value == src)
        ]
        return {"patients": [_patient_brief(p) for p in rows[:limit]]}

    if name == "find_findings":
        flag = tool_input.get("abnormal_flag")
        cc = (tool_input.get("code_contains") or "").lower()
        limit = tool_input.get("limit", 100)
        rows = [
            f
            for f in finding_service.list_findings(db, tool_input.get("patient_id"))
            if (not flag or f.abnormal_flag.value == flag)
            and (not cc or cc in f.display.lower() or cc in f.code.lower())
        ]
        return {"findings": [_finding_brief(f) for f in rows[:limit]]}

    if name == "list_alerts":
        sev = tool_input.get("severity")
        st = tool_input.get("status")
        rows = [
            a
            for a in alert_service.list_alerts(db, tool_input.get("patient_id"))
            if (not sev or a.severity.value == sev) and (not st or a.status.value == st)
        ]
        return {"alerts": [_alert_brief(a) for a in rows]}

    return {"error": f"unknown tool: {name}"}
