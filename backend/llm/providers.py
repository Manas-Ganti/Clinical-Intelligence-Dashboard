"""Provider adapters: the same tool surface, spoken to two different APIs.

`QueryEngine` runs one loop — ask, execute the tools the model chose, feed the
typed results back. Everything *below* that loop is provider-shaped: Anthropic
returns content blocks and takes tool results as a user turn; OpenAI-compatible
servers return `tool_calls` on an assistant message and take tool results as
`role: "tool"` messages. A provider owns those three jobs:

    initial_messages(question)      → the transcript to start from
    complete(messages)              → a normalised Turn (text + tool uses)
    record(messages, turn, results) → append the turn and its results, natively

so the engine never branches on which model it is talking to.

Why native OpenAI rather than ARC's Anthropic-compatible route: the open models
are *served* in OpenAI shape, and their thinking controls (`reasoning_effort`,
`enable_thinking`) are extra body params on that route. Translating through a
compatibility shim would put a lossy layer between us and exactly the behaviour
the eval is trying to measure.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import structlog

from backend.llm.models import ANTHROPIC, ModelSpec, vtarc_base_url
from backend.llm.tools import CLINICAL_TOOLS, SYSTEM_PROMPT

logger = structlog.get_logger()

MAX_TOKENS = 1024


@dataclass(frozen=True)
class ToolUse:
    id: str
    name: str
    input: dict
    # Set when the model emitted a tool call we could not read (OpenAI-shaped
    # arguments arrive as a JSON *string*, and a model that hasn't been trained
    # or constrained for tool use can emit something that isn't JSON). Kept as a
    # value rather than raised: a malformed call is a result the eval should
    # grade, not a crash that loses the run.
    parse_error: str | None = None


@dataclass
class Turn:
    text: str
    tool_uses: list[ToolUse] = field(default_factory=list)
    raw: Any = None


def openai_tools() -> list[dict]:
    """CLINICAL_TOOLS in OpenAI function shape — same names, same JSON Schema.

    Only the envelope differs, so the tool surface stays defined in one place
    (tools.py) and no model sees a different set of operations than another.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        }
        for tool in CLINICAL_TOOLS
    ]


class AnthropicProvider:
    """Claude via the Anthropic SDK."""

    name = ANTHROPIC

    def __init__(
        self,
        spec: ModelSpec,
        client: Any = None,
        max_tokens: int = MAX_TOKENS,
        temperature: float | None = None,
    ):
        self.spec = spec
        self._client = client
        self.max_tokens = max_tokens
        # Accepted and dropped: current Claude models reject `temperature`, and a
        # cross-model eval that pins it for the open models should not therefore
        # fail to run against Claude at all.
        if temperature is not None:
            logger.warning("llm_temperature_ignored", model=spec.id, provider=self.name)

    @property
    def client(self) -> Any:
        # Lazy so importing this module never requires the SDK/key until a query runs.
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        return self._client

    def initial_messages(self, question: str) -> list[dict]:
        return [{"role": "user", "content": question}]

    def complete(self, messages: list[dict]) -> Turn:
        response = self.client.messages.create(
            model=self.spec.id,
            max_tokens=self.max_tokens,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=CLINICAL_TOOLS,
            messages=messages,
            **self.spec.params,
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        tool_uses = [
            ToolUse(id=b.id, name=b.name, input=dict(b.input))
            for b in response.content
            if b.type == "tool_use"
        ]
        return Turn(text=text.strip(), tool_uses=tool_uses, raw=response)

    def record(self, messages: list[dict], turn: Turn, results: list[tuple[ToolUse, dict]]) -> None:
        messages.append({"role": "assistant", "content": turn.raw.content})
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": use.id,
                        "content": json.dumps(result, default=str),
                    }
                    for use, result in results
                ],
            }
        )


class OpenAICompatProvider:
    """VT ARC's hosted open models (and any other OpenAI-compatible server).

    The system prompt rides as the first message rather than a top-level field,
    and there is no prompt caching to declare — vLLM-style servers cache the
    shared prefix themselves, so the cache_control marks Claude needs are simply
    absent here rather than translated.
    """

    name = "vtarc"

    def __init__(
        self,
        spec: ModelSpec,
        client: Any = None,
        max_tokens: int = MAX_TOKENS,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float | None = None,
    ):
        self.spec = spec
        self._client = client
        self.max_tokens = max_tokens
        self.base_url = base_url or vtarc_base_url()
        self._api_key = api_key
        self.temperature = temperature

    @property
    def client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                base_url=self.base_url,
                # "EMPTY" is the conventional placeholder for a local vLLM with
                # auth disabled; ARC's gateway requires a real key.
                api_key=self._api_key or os.getenv("VTARC_API_KEY") or "EMPTY",
            )
        return self._client

    def initial_messages(self, question: str) -> list[dict]:
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]

    def complete(self, messages: list[dict]) -> Turn:
        kwargs: dict = {
            "model": self.spec.id,
            "max_tokens": self.max_tokens,
            "tools": openai_tools(),
            "messages": messages,
        }
        if self.spec.params:
            kwargs["extra_body"] = dict(self.spec.params)
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature

        response = self.client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        return Turn(
            text=(message.content or "").strip(),
            tool_uses=[_parse_openai_tool_call(tc) for tc in (message.tool_calls or [])],
            raw=message,
        )

    def record(self, messages: list[dict], turn: Turn, results: list[tuple[ToolUse, dict]]) -> None:
        # Rebuilt by hand rather than echoed with model_dump(): responses from
        # these servers carry extra fields (reasoning_content, refusal, …) that
        # some of them then reject on the way back in. The assistant turn only
        # has to carry what the next turn needs — the text and the calls.
        assistant: dict = {"role": "assistant", "content": turn.raw.content or ""}
        if turn.raw.tool_calls:
            assistant["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments or "{}",
                    },
                }
                for tc in turn.raw.tool_calls
            ]
        messages.append(assistant)

        # One tool message per call, keyed by id. A server that gets a tool
        # result it cannot pair with a call errors the whole request, so this
        # must stay 1:1 with the tool_calls above, malformed ones included.
        for use, result in results:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": use.id,
                    "content": json.dumps(result, default=str),
                }
            )


def _parse_openai_tool_call(call: Any) -> ToolUse:
    raw_args = call.function.arguments or "{}"
    try:
        parsed = json.loads(raw_args)
    except json.JSONDecodeError as exc:
        return ToolUse(id=call.id, name=call.function.name, input={}, parse_error=f"arguments were not valid JSON: {exc}")
    if not isinstance(parsed, dict):
        return ToolUse(
            id=call.id,
            name=call.function.name,
            input={},
            parse_error=f"arguments were {type(parsed).__name__}, expected a JSON object",
        )
    return ToolUse(id=call.id, name=call.function.name, input=parsed)


def provider_for(spec: ModelSpec, client: Any = None, **kwargs: Any) -> Any:
    """The adapter for a model. `client` is injectable so tests run the whole
    loop against a fake — for either provider — with no key and no network."""
    if spec.provider == ANTHROPIC:
        return AnthropicProvider(spec, client=client, **kwargs)
    return OpenAICompatProvider(spec, client=client, **kwargs)
