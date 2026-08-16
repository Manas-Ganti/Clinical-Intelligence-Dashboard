"""The function-calling loop for natural-language queries.

The model maps a plain-English question to tool calls; our code executes them
against the service layer and feeds typed results back until the model produces
a final answer.

The loop is provider-agnostic (see providers.py): the same tool surface runs on
Claude via Anthropic, or on the open models VT ARC hosts (gpt-oss, GLM, Kimi,
DeepSeek) via their OpenAI-compatible endpoint. Which one a query uses is just
the `model` argument — `LLM_MODEL` in the environment, or `--model` in the eval
runner. The client is injectable so tests can run the whole loop with a mock and
no API key.
"""
import structlog
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.llm.models import ModelSpec, default_model, resolve
from backend.llm.providers import ToolUse, provider_for
from backend.llm.tools import execute_tool

logger = structlog.get_logger()


class ToolCall(BaseModel):
    name: str
    input: dict
    result: dict


class QueryResult(BaseModel):
    answer: str
    tool_calls: list[ToolCall]
    # Which model answered. Cheap to carry and hard to reconstruct later — with
    # thirteen models behind one endpoint, "the answer was wrong" is only
    # actionable if you know which model gave it.
    model: str = ""


class QueryEngine:
    def __init__(
        self,
        db: Session,
        client=None,
        model: str | None = None,
        max_turns: int = 6,
        **provider_kwargs,
    ):
        self.db = db
        self.spec: ModelSpec = resolve(model or default_model())
        self.model = self.spec.id
        self.max_turns = max_turns
        self.provider = provider_for(self.spec, client=client, **provider_kwargs)

    def ask(self, question: str) -> QueryResult:
        messages = self.provider.initial_messages(question)
        tool_calls: list[ToolCall] = []
        logger.info("llm_query_started", model=self.model, provider=self.provider.name)

        for _ in range(self.max_turns):
            turn = self.provider.complete(messages)

            if not turn.tool_uses:
                return QueryResult(
                    answer=turn.text, tool_calls=tool_calls, model=self.model
                )

            results: list[tuple[ToolUse, dict]] = []
            for use in turn.tool_uses:
                result = self._run(use)
                tool_calls.append(ToolCall(name=use.name, input=use.input, result=result))
                results.append((use, result))
            self.provider.record(messages, turn, results)

        return QueryResult(
            answer="Stopped after reaching the tool-call limit without a final answer.",
            tool_calls=tool_calls,
            model=self.model,
        )

    def _run(self, use: ToolUse) -> dict:
        """Execute one tool call, or hand back the reason we could not.

        A call whose arguments didn't parse never reaches the service layer —
        running it with silently-empty arguments would answer a different
        question than the one asked, and answer it confidently.
        """
        if use.parse_error:
            logger.warning("llm_tool_call_unparsable", tool=use.name, model=self.model)
            return {"error": use.parse_error}
        result = execute_tool(self.db, use.name, use.input)
        logger.info("llm_tool_executed", tool=use.name, model=self.model)
        return result
