# Tool-result token cost, before and after the row cap

Measured 2026-10-26 at commit `0083722c6028786b854d3aa242420fc95eac1e0f`
(measurement script uncommitted at the time of the run).

## Command

```
python scripts/measure_tool_tokens.py
```

- Database: `sqlite:///./clinical_synthea.db` (Synthea seed, 995 alerts, all severity `critical`)
- Tool call: `list_alerts {"severity": "critical"}`, the call behind eval case
  `sel-critical-alerts` ("Show me all the critical alerts.")
- Serialization: `json.dumps(result, default=str)`, the exact string both providers put in
  the tool-result message (`backend/llm/providers.py:142` and `:244`)
- Cap: `MAX_TOOL_ROWS = 100` in `backend/llm/tools.py`; `list_alerts` defaults to 50 rows
  when the model passes no `limit`; every result carries `returned` and `total_matching`
- Tokenizers: tiktoken 0.14.0. `o200k_harmony` is the tokenizer of gpt-oss-120b, this
  project's default `LLM_MODEL`. `cl100k_base` is included as a common reference.
  Claude's tokenizer is not publicly available, so no Claude count is given.
- No LLM call is made. Counts cover the tool-result content string only, not the message
  wrapper, system prompt or tool schemas.

## Results

| Variant | Rows sent | total_matching | Chars | Tokens (o200k_harmony) | Tokens (cl100k_base) |
|---|---:|---:|---:|---:|---:|
| Pre-cap, code as of `aaaf578` | 995 | n/a | 233,580 | **98,551** | 98,713 |
| Cap disabled in-process, current code | 995 | 995 | 233,620 | 98,564 | 98,726 |
| Cap on, default limit (model passes no limit) | 50 | 995 | 11,790 | **5,037** | 5,060 |
| Cap on, max limit (model asks for more than 100) | 100 | 995 | 23,569 | 10,006 | 10,041 |

Two runs gave identical numbers.

Reduction (o200k_harmony): 98,551 to 5,037 tokens at the default limit (19.6x, 94.9% fewer);
98,551 to 10,006 at the cap ceiling (9.8x, 89.8% fewer). The added `returned` and
`total_matching` fields cost 13 tokens.

## How the variants are built

- **Pre-cap** reproduces `execute_tool`'s `list_alerts` branch from commit `aaaf578`: every
  alert, filtered by severity, returned as `{"alerts": [...]}`. `_alert_brief` is unchanged
  between that commit and HEAD (verified by diff).
- **Cap disabled** calls the current `execute_tool` with `tools.MAX_TOOL_ROWS` patched to
  10^9 inside the script's own process only. Application code is not modified.
- **Cap on** calls the current `execute_tool` unmodified.

## Against the previously cited "58k to 2.9k tokens"

- **58k does not hold.** The 995-row result measures 98.6k tokens. 58k matches the
  chars/4 rule of thumb (233,580 / 4 = 58.4k), not a tokenizer count.
- **2.9k does not hold.** It equals 58k x 50/995 = 2.92k, a hand scaling of an estimate.
  The measured capped result is 5.0k tokens at the default 50 rows and 10.0k at the
  100-row ceiling.
- Supported claim: **~98.6k to ~5.0k tokens per call (about 20x smaller) for the
  995-alert query at the default limit, ~10.0k at the 100-row ceiling**, measured with
  gpt-oss-120b's tokenizer.
