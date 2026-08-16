"""Run the clinical tool-calling eval against a live model.

    python evals/run_eval.py                       # default model, seeded DB
    python evals/run_eval.py --model claude-sonnet-5
    python evals/run_eval.py --model GLM-5.2       # a VT ARC-hosted open model
    python evals/run_eval.py --list-models         # what's wired up, and reachable
    python evals/run_eval.py --repeat 3            # pass-rate over N runs
    python evals/run_eval.py --only refusal        # one category

Needs the credential the chosen model's provider uses: ANTHROPIC_API_KEY for
Claude (billed), VTARC_API_KEY for the models ARC hosts (free to VT accounts,
key from llm.arc.vt.edu → Settings → Account → API keys). Either way it makes
real requests — which is why it lives here and not in the test suite, where the
client is mocked.

Note on determinism: current Claude models don't accept `temperature`, so you
cannot pin the sampler to 0 there. The ARC models do — `--temperature 0` is
passed through to them and ignored (with a warning) for Claude. Even pinned,
tool-call evals are not perfectly deterministic, so use --repeat when comparing
models and read the pass *rate*, not a single boolean.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import structlog

from backend.db import SessionLocal
from backend.llm.models import MODELS, default_model, missing_credential, resolve
from backend.llm.query_engine import QueryEngine
from evals.cases import CASES, Category
from evals.harness import Score, report, score


def list_models() -> int:
    """The registry, annotated with whether you can actually run each one."""
    print(f"\n  {'model':<34} {'provider':<10} {'context':>8}  parameters")
    print(f"  {'-' * 34} {'-' * 10} {'-' * 8}  {'-' * 34}")
    for spec in MODELS.values():
        missing = missing_credential(spec)
        params = ", ".join(f"{k}={v}" for k, v in spec.params.items()) or "—"
        mark = "" if missing is None else f"  (needs {missing})"
        print(
            f"  {spec.id:<34} {spec.provider:<10} {spec.max_context // 1000:>7}k  {params}{mark}"
        )
    print(f"\n  default (LLM_MODEL): {default_model()}\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None, help="model id (default: LLM_MODEL, else Claude)")
    ap.add_argument("--list-models", action="store_true", help="show the registry and exit")
    ap.add_argument("--temperature", type=float, help="pin the sampler (ARC models only)")
    ap.add_argument("--repeat", type=int, default=1, help="runs per case; report a pass rate")
    ap.add_argument("--only", choices=[c.value for c in Category], help="one category")
    ap.add_argument("--verbose", action="store_true", help="show each case as it runs")
    args = ap.parse_args()

    if args.list_models:
        return list_models()

    # The tool-execution logs are noise here; we care about the verdicts.
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(40))

    spec = resolve(args.model or default_model())
    missing = missing_credential(spec)
    if missing:
        print(f"\n  {spec.id} is served by {spec.provider}, which needs {missing}. Not set.\n")
        return 2

    cases = [c for c in CASES if not args.only or c.category.value == args.only]
    db = SessionLocal()
    kwargs = {} if args.temperature is None else {"temperature": args.temperature}
    engine = QueryEngine(db, model=spec.id, **kwargs)

    print(f"\n  model:  {spec.id}  ({spec.provider})")
    print(f"  cases:  {len(cases)}" + (f" × {args.repeat} runs" if args.repeat > 1 else ""))

    all_scores: list[Score] = []
    passes: Counter[str] = Counter()

    try:
        for case in cases:
            for _ in range(args.repeat):
                try:
                    result = engine.ask(case.question)
                    s = score(case, result)
                except Exception as exc:  # a crashed call is a failed case, not a crashed run
                    from evals.harness import Score as S
                    s = S(case, False, f"request failed: {type(exc).__name__}: {exc}", ())
                all_scores.append(s)
                passes[case.id] += int(s.passed)
            if args.verbose:
                mark = "✓" if passes[case.id] == args.repeat else "✗"
                rate = f"{passes[case.id]}/{args.repeat}" if args.repeat > 1 else ""
                print(f"    {mark} {case.id:<24} {rate}")
    finally:
        db.close()

    print(report(all_scores))

    if args.repeat > 1:
        flaky = [c for c in cases if 0 < passes[c.id] < args.repeat]
        if flaky:
            print("  non-deterministic (passed some runs, failed others):")
            for c in flaky:
                print(f"    {c.id}: {passes[c.id]}/{args.repeat}")
            print()

    failed = sum(1 for s in all_scores if not s.passed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
