"""Phase 4c tests: the LLM query layer's tool dispatch and function-calling loop.

The Anthropic client is faked, so the full engine loop runs with no API key — we
verify our code executes the right tool and threads results back to a final answer.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.db_models  # noqa: F401
from backend.bootstrap import seed_if_empty
from backend.db import Base, get_db
from backend.llm.query_engine import QueryEngine
from backend.llm.tools import execute_tool
from backend.main import app


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    seed_if_empty(session)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# --- fake Anthropic client ------------------------------------------------- #
class FakeBlock:
    def __init__(self, type, text=None, name=None, input=None, id=None):
        self.type = type
        self.text = text
        self.name = name
        self.input = input
        self.id = id


class FakeResp:
    def __init__(self, content, stop_reason):
        self.content = content
        self.stop_reason = stop_reason


class FakeMessages:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.messages = FakeMessages(responses)


# --- tool dispatch (no LLM) ------------------------------------------------ #
def test_execute_find_patients_by_source(db):
    out = execute_tool(db, "find_patients", {"source_system": "fhir_api"})
    assert {p["mrn"] for p in out["patients"]} == {"7007", "8008"}


def test_execute_find_findings_critical(db):
    out = execute_tool(db, "find_findings", {"abnormal_flag": "critical"})
    assert len(out["findings"]) == 2  # Grace Hopper's two critical hemoglobins
    assert all(f["abnormal_flag"] == "critical" for f in out["findings"])


def test_unknown_tool_returns_error(db):
    assert "error" in execute_tool(db, "nope", {})


# --- full engine loop with a faked model ----------------------------------- #
def test_engine_runs_tool_then_answers(db):
    responses = [
        FakeResp(
            [FakeBlock("tool_use", name="find_patients", input={"source_system": "fhir_api"}, id="t1")],
            "tool_use",
        ),
        FakeResp(
            [FakeBlock("text", text="Two patients came from FHIR: Marie Curie and Rosalind Franklin.")],
            "end_turn",
        ),
    ]
    engine = QueryEngine(db, client=FakeClient(responses))
    result = engine.ask("Which patients came from FHIR?")

    assert "Marie" in result.answer
    assert result.tool_calls[0].name == "find_patients"
    assert {p["mrn"] for p in result.tool_calls[0].result["patients"]} == {"7007", "8008"}


def test_query_endpoint_requires_api_key(db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app.dependency_overrides[get_db] = lambda: db
    try:
        r = TestClient(app).post("/query", json={"question": "anything"})
        assert r.status_code == 503
    finally:
        app.dependency_overrides.clear()
