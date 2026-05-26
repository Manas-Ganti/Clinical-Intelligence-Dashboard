"""The Claude function-calling loop for natural-language queries.

The model maps a plain-English question to tool calls; our code executes them
against the service layer and feeds typed results back until the model produces a
final answer. The Anthropic client is injectable so tests can run the whole loop
with a mock and no API key.
"""
import json

import structlog
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.llm.tools import CLINICAL_TOOLS, SYSTEM_PROMPT, execute_tool

logger = structlog.get_logger()

DEFAULT_MODEL = "claude-opus-4-7"


class ToolCall(BaseModel):
    name: str
    input: dict
    result: dict


class QueryResult(BaseModel):
    answer: str
    tool_calls: list[ToolCall]


class QueryEngine:
    def __init__(self, db: Session, client=None, model: str = DEFAULT_MODEL, max_turns: int = 6):
        self.db = db
        self._client = client
        self.model = model
        self.max_turns = max_turns

    @property
    def client(self):
        # Lazy so importing this module never requires the SDK/key until a query runs.
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        return self._client

    def ask(self, question: str) -> QueryResult:
        messages: list[dict] = [{"role": "user", "content": question}]
        tool_calls: list[ToolCall] = []

        for _ in range(self.max_turns):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=CLINICAL_TOOLS,
                messages=messages,
            )

            if response.stop_reason != "tool_use":
                answer = "".join(b.text for b in response.content if b.type == "text")
                return QueryResult(answer=answer.strip(), tool_calls=tool_calls)

            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(self.db, block.name, dict(block.input))
                    tool_calls.append(
                        ToolCall(name=block.name, input=dict(block.input), result=result)
                    )
                    logger.info("llm_tool_executed", tool=block.name)
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, default=str),
                        }
                    )
            messages.append({"role": "user", "content": results})

        return QueryResult(
            answer="Stopped after reaching the tool-call limit without a final answer.",
            tool_calls=tool_calls,
        )
