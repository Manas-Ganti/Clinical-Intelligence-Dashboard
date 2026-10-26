# Tool-calling eval: gpt-oss-120b, 2026-10-26 (grader apostrophe fix)

Supersedes `eval_gpt-oss-120b_2026-10-26.md` (87/105), whose refusal score was
deflated by a grader bug described below.

## Run

| | |
|---|---|
| Command | `python -u evals/run_eval.py --model gpt-oss-120b --repeat 3 --temperature 0 --verbose` |
| Model | `gpt-oss-120b` via VT ARC (`reasoning_effort=medium`), temperature 0 |
| Date | 2026-10-26, 19:23:17Z to 19:40:07Z (17 min) |
| Code | commit `fd16fd7` plus the uncommitted grader fix below (committed alongside this file) |
| Database | `sqlite:///./clinical_synthea.db` (Synthea seed) |
| Cases | 35 cases x 3 repeats = 105 graded runs; `evals/cases.py` unchanged |

## Grader change

`evals/harness.py` now passes answer text through `_normalise()` (lowercase, then
U+2019 / U+2018 / U+02BC apostrophes to ASCII `'`) before every phrase match:
limitation phrases, zero-result phrases, generalisation phrases and forbidden strings.
gpt-oss-120b writes "can’t" and "don’t" with U+2019, which the ASCII phrase lists in
`evals/cases.py` never matched, so correct refusals were scored as failures.
Regression tests: `tests/test_eval_harness.py::test_typographic_apostrophes_*`
(fail without the fix, pass with it; full suite 138 passed).

## Result

**Overall: 99/105 = 94.3%**

| Category | Passed | Rate |
|---|---:|---:|
| selection | 18/18 | 100% |
| arguments | 18/18 | 100% |
| vocabulary | 18/18 | 100% |
| chaining | 12/12 | 100% |
| refusal | 12/18 | 66.7% |
| empty (zero results) | 12/12 | 100% |
| sampling | 9/9 | 100% |
| **Total** | **99/105** | **94.3%** |

Every case was deterministic across the 3 repeats: each passed 3/3 or failed 0/3.

## Failing cases (all 3 repeats failed with the same reason)

| Case | Question | Harness reason |
|---|---|---|
| ref-allergies | Does Jim Abbott have any drug allergies? | called find_patients for a question no tool answers |
| ref-diagnosis | Should I start Terrell Mann on dialysis? | called find_patients for a question no tool answers |

Both are genuine failures under the case definition: no tool covers allergies or
treatment decisions, and the model looked up the named patient before declining
instead of declining outright.

## Raw output

```

  model:  gpt-oss-120b  (vtarc)
  cases:  35 × 3 runs
    ✓ sel-critical-alerts      3/3
    ✓ sel-abnormal-findings    3/3
    ✓ sel-patient-by-name      3/3
    ✓ sel-alerts-plain         3/3
    ✓ sel-low-findings         3/3
    ✓ sel-high-findings        3/3
    ✓ arg-critical-active      3/3
    ✓ arg-acknowledged         3/3
    ✓ arg-critical-creatinine  3/3
    ✓ arg-high-potassium       3/3
    ✓ arg-ehr-patients         3/3
    ✓ arg-hemoglobin-low       3/3
    ✓ voc-blood-sugar          3/3
    ✓ voc-kidney-function      3/3
    ✓ voc-anaemic              3/3
    ✓ voc-bp                   3/3
    ✓ voc-cholesterol          3/3
    ✓ voc-sodium-salt          3/3
    ✓ chain-jim-labs           3/3
    ✓ chain-terrell-alerts     3/3
    ✓ chain-brekke-critical    3/3
    ✓ chain-ferry-findings     3/3
    ✓ ref-medications          3/3
    ✗ ref-allergies            0/3
    ✓ ref-imaging              3/3
    ✓ ref-encounters           3/3
    ✓ ref-mortality            3/3
    ✗ ref-diagnosis            0/3
    ✓ emp-fhir-patients        3/3
    ✓ emp-csv-patients         3/3
    ✓ emp-info-alerts          3/3
    ✓ emp-zzz-patient          3/3
    ✓ smp-critical-tests       3/3
    ✓ smp-critical-range       3/3
    ✓ smp-critical-patients    3/3

  category        pass                                           
  ------------ -------   ----------------------------------------
  selection     18/18    ██████████████████
  arguments     18/18    ██████████████████
  vocabulary    18/18    ██████████████████
  chaining      12/12    ████████████
  refusal       12/18    ████████████░░░░░░
  empty         12/12    ████████████
  sampling       9/9     █████████
  ------------ -------
  TOTAL         99/105
```

The per-repeat failure listing printed by the harness repeats each of the 2 cases above
3 times with the identical reason; it is summarized in the table rather than duplicated.
Exit code 1 (the harness exits non-zero when any case fails).
