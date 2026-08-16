"""Tool results must be bounded, and must still tell the truth about totals.

Every tool result is fed straight back into the model's context, so an unbounded
one is a context-window and cost bug, not merely a slow query. Before this,
`list_alerts(severity="critical")` returned all 995 alerts — ~58k tokens of JSON
on every call, on every turn.

Capping the rows creates a second, subtler hazard: a model that can only see 50
rows will happily report "there are 50 critical alerts" when there are 995. So
the cap and the count are tested together — one without the other is a bug.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.db_models  # noqa: F401  register tables
from backend.bootstrap import seed_if_empty
from backend.db import Base
from backend.llm.tools import MAX_TOOL_ROWS, execute_tool


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    seed_if_empty(session, source="sample")
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# -- the cap --------------------------------------------------------------- #
@pytest.mark.parametrize(
    "tool,key",
    [
        ("find_patients", "patients"),
        ("find_findings", "findings"),
        ("list_alerts", "alerts"),
    ],
)
def test_no_tool_can_be_made_to_return_more_than_the_cap(db, tool, key):
    """A model asking for limit=10000 isn't malicious, it's optimistic — and
    honouring it would blow the context window of the small local models we want
    to be able to run this on."""
    result = execute_tool(db, tool, {"limit": 10_000})
    assert len(result[key]) <= MAX_TOOL_ROWS


@pytest.mark.parametrize("bad", [0, -5, "fifty", None, 1.5])
def test_a_nonsense_limit_does_not_crash_the_tool(db, bad):
    """The limit comes from a language model, so it can be anything at all."""
    result = execute_tool(db, "list_alerts", {"limit": bad})
    assert 0 <= len(result["alerts"]) <= MAX_TOOL_ROWS


# -- the count: the other half of the cap ---------------------------------- #
@pytest.mark.parametrize(
    "tool,key",
    [
        ("find_patients", "patients"),
        ("find_findings", "findings"),
        ("list_alerts", "alerts"),
    ],
)
def test_every_result_reports_the_true_total_not_just_the_page(db, tool, key):
    """Without this the model counts the rows it can see and is confidently wrong."""
    capped = execute_tool(db, tool, {"limit": 1})
    full = execute_tool(db, tool, {"limit": MAX_TOOL_ROWS})

    assert len(capped[key]) <= 1
    # The page shrank; the reported total must not.
    assert capped["total_matching"] == full["total_matching"]
    assert capped["total_matching"] >= len(full[key])


def test_total_matching_respects_the_filter(db):
    """The total must be the total *of the filtered set*, not of the whole table —
    otherwise "how many critical alerts?" gets answered with the alert count."""
    critical = execute_tool(db, "list_alerts", {"severity": "critical"})
    everything = execute_tool(db, "list_alerts", {})

    assert critical["total_matching"] <= everything["total_matching"]
    assert all(a["severity"] == "critical" for a in critical["alerts"])


# -- filters now run in SQL; they must still behave ------------------------ #
def test_family_name_is_a_case_insensitive_substring(db):
    lower = execute_tool(db, "find_patients", {"family_name": "lovelace"})
    upper = execute_tool(db, "find_patients", {"family_name": "LOVELACE"})

    assert lower["total_matching"] >= 1
    assert lower["total_matching"] == upper["total_matching"]


def test_code_contains_matches_either_the_name_or_the_loinc_code(db):
    """Clinicians type "hemoglobin"; the data also carries LOINC 718-7. Both work."""
    by_name = execute_tool(db, "find_findings", {"code_contains": "hemoglobin"})
    by_code = execute_tool(db, "find_findings", {"code_contains": "718-7"})

    assert by_name["total_matching"] >= 1
    assert by_code["total_matching"] >= 1


def test_filters_combine_rather_than_override(db):
    """Right tool, one filter silently dropped, wrong set of rows, confident
    answer — the quiet failure this guards."""
    both = execute_tool(
        db, "find_findings", {"abnormal_flag": "low", "code_contains": "hemoglobin"}
    )
    for f in both["findings"]:
        assert f["abnormal_flag"] == "low"
        assert "hemoglobin" in f["display"].lower()


# -- the empty result: the fabrication trap -------------------------------- #
def test_an_empty_result_is_explicitly_empty(db):
    """No patient came from PACS. The model must see a zero, not an absence."""
    result = execute_tool(db, "find_patients", {"source_system": "pacs"})

    assert result["patients"] == []
    assert result["total_matching"] == 0
    assert result["returned"] == 0
