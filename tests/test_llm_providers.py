"""The provider layer: one tool surface, two wire formats.

The whole point of the abstraction is that a question answered by Claude and the
same question answered by an ARC-hosted open model produce the *same* typed
QueryResult. So these tests run the full engine loop against a fake
OpenAI-compatible client — no key, no network — and assert on the parts that are
easy to get wrong when translating between the two APIs: the tool schemas, the
tool-result plumbing (`role: "tool"` keyed by call id), and what happens when a
model emits a tool call we cannot read.
"""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.db_models  # noqa: F401
from backend.bootstrap import seed_if_empty
from backend.db import Base, get_db
from backend.llm.models import MODELS, VTARC, default_model, missing_credential, resolve
from backend.llm.providers import openai_tools
from backend.llm.query_engine import QueryEngine
from backend.llm.tools import CLINICAL_TOOLS
from backend.main import app


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


# --- fake OpenAI-compatible client ----------------------------------------- #
class FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class FakeToolCall:
    def __init__(self, id, name, arguments):
        self.id = id
        self.type = "function"
        self.function = FakeFunction(name, arguments)


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class FakeCompletion:
    def __init__(self, message):
        self.choices = [type("Choice", (), {"message": message})()]


class FakeCompletions:
    def __init__(self, messages):
        self._messages = list(messages)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeCompletion(self._messages.pop(0))


class FakeOpenAI:
    def __init__(self, messages):
        self.chat = type("Chat", (), {"completions": FakeCompletions(messages)})()


def _engine(db, messages, model="gpt-oss-120b"):
    return QueryEngine(db, client=FakeOpenAI(messages), model=model)


# --- the registry ----------------------------------------------------------- #
def test_every_arc_model_declares_how_hard_it_should_think():
    """The ARC catalogue lists the same weights under several ids that differ
    only in thinking budget. An id with no parameters would silently run at the
    server default — a different model than the one you asked for."""
    arc = [s for s in MODELS.values() if s.provider == VTARC]
    assert len(arc) == 12
    for spec in arc:
        assert spec.params, f"{spec.id} carries no thinking parameter"
        assert set(spec.params) <= {"reasoning_effort", "enable_thinking"}


def test_deepseek_models_carry_the_larger_context():
    assert resolve("DeepSeek-V4-Flash").max_context == 512_000
    assert resolve("Kimi-K3").max_context == 128_000


def test_unknown_model_is_routed_by_prefix_rather_than_rejected():
    """ARC rotates its catalogue; an id we haven't registered still has to run."""
    assert resolve("Qwen4-42B").provider == VTARC
    assert resolve("claude-something-new").provider == "anthropic"


def test_llm_model_env_selects_the_model(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "GLM-5.2")
    assert default_model() == "GLM-5.2"


def test_each_provider_asks_for_its_own_credential(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("VTARC_API_KEY", "vt-key")
    assert missing_credential(resolve("Kimi-K3")) is None
    assert missing_credential(resolve("claude-opus-4-8")) == "ANTHROPIC_API_KEY"


# --- schema translation ----------------------------------------------------- #
def test_openai_tools_mirror_the_anthropic_ones_exactly():
    """Same names, same JSON Schema — otherwise the eval would be comparing two
    different tool surfaces and calling the difference a model difference."""
    converted = openai_tools()
    assert [t["function"]["name"] for t in converted] == [t["name"] for t in CLINICAL_TOOLS]
    for tool, original in zip(converted, CLINICAL_TOOLS):
        assert tool["type"] == "function"
        assert tool["function"]["parameters"] == original["input_schema"]
        # cache_control is an Anthropic-only field; sending it here is a 400.
        assert "cache_control" not in json.dumps(tool)


# --- the loop --------------------------------------------------------------- #
def test_engine_runs_tool_then_answers_on_an_openai_model(db):
    engine = _engine(
        db,
        [
            FakeMessage(
                tool_calls=[
                    FakeToolCall("call_1", "find_patients", '{"source_system": "fhir_api"}')
                ]
            ),
            FakeMessage(content="Two patients came from FHIR: Marie Curie and Rosalind Franklin."),
        ],
    )
    result = engine.ask("Which patients came from FHIR?")

    assert "Marie" in result.answer
    assert result.model == "gpt-oss-120b"
    assert result.tool_calls[0].name == "find_patients"
    assert {p["mrn"] for p in result.tool_calls[0].result["patients"]} == {"7007", "8008"}


def test_thinking_parameters_ride_in_extra_body(db):
    engine = _engine(db, [FakeMessage(content="ok")], model="GLM-5.2-non-thinking")
    engine.ask("hello")
    sent = engine.provider.client.chat.completions.calls[0]
    assert sent["model"] == "GLM-5.2-non-thinking"
    assert sent["extra_body"] == {"enable_thinking": False}
    assert sent["messages"][0]["role"] == "system"  # no top-level system field here


def test_tool_results_are_paired_back_to_their_call_id(db):
    """A tool message the server cannot pair with a call fails the whole
    request, so the id has to survive the round trip."""
    engine = _engine(
        db,
        [
            FakeMessage(tool_calls=[FakeToolCall("call_abc", "list_alerts", '{"severity": "critical"}')]),
            FakeMessage(content="Two critical alerts."),
        ],
    )
    engine.ask("Which alerts are critical?")

    second_request = engine.provider.client.chat.completions.calls[1]["messages"]
    assistant, tool_result = second_request[-2], second_request[-1]
    assert assistant["role"] == "assistant"
    assert assistant["tool_calls"][0]["id"] == "call_abc"
    assert tool_result["role"] == "tool"
    assert tool_result["tool_call_id"] == "call_abc"
    assert json.loads(tool_result["content"])["total_matching"] >= 1


def test_unparsable_arguments_are_reported_not_executed(db):
    """A model that emits invalid JSON for its arguments is a real failure mode
    for smaller open models. Running the tool anyway with empty arguments would
    answer a different question than the one asked — confidently."""
    engine = _engine(
        db,
        [
            FakeMessage(tool_calls=[FakeToolCall("call_1", "find_patients", "{not json")]),
            FakeMessage(content="I couldn't complete that."),
        ],
    )
    result = engine.ask("Which patients came from FHIR?")

    assert "error" in result.tool_calls[0].result
    assert result.tool_calls[0].input == {}
    # The turn still has to be answerable: a tool message must come back for the
    # call, or the next request is malformed.
    tool_msg = engine.provider.client.chat.completions.calls[1]["messages"][-1]
    assert tool_msg["tool_call_id"] == "call_1"


def test_engine_stops_at_the_turn_limit(db):
    """A model that keeps calling tools forever is a cost bug, not a query."""
    calls = [
        FakeMessage(tool_calls=[FakeToolCall(f"c{i}", "find_patients", "{}")]) for i in range(4)
    ]
    engine = QueryEngine(db, client=FakeOpenAI(calls), model="Kimi-K3", max_turns=3)
    result = engine.ask("loop forever")
    assert "tool-call limit" in result.answer
    assert len(result.tool_calls) == 3


# --- the route -------------------------------------------------------------- #
def test_query_503_names_the_credential_the_configured_model_needs(db, monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gpt-oss-120b")
    monkeypatch.delenv("VTARC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-irrelevant-here")
    app.dependency_overrides[get_db] = lambda: db
    try:
        r = TestClient(app).post("/query", json={"question": "anything"})
        assert r.status_code == 503
        assert "VTARC_API_KEY" in r.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_model_endpoint_reports_what_the_ask_bar_is_wired_to(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "DeepSeek-V4-Flash")
    monkeypatch.setenv("VTARC_API_KEY", "vt-key")
    body = TestClient(app).get("/query/model").json()
    assert body == {
        "model": "DeepSeek-V4-Flash",
        "provider": "vtarc",
        "max_context": 512_000,
        "available": True,
        "missing_credential": None,
    }
