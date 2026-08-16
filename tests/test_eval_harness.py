"""Tests for the eval scorer itself.

The eval harness is code, and a buggy scorer is worse than no scorer: it reports
a number with total confidence and the number is wrong. So the grading logic is
tested here, with hand-built QueryResults and no API calls — these run in the
normal suite. The *live* eval (evals/run_eval.py) needs a real model and a key,
and deliberately does not.
"""
import pytest

from backend.llm.query_engine import QueryResult, ToolCall
from evals.cases import CASES, Category
from evals.harness import score


def _result(answer: str = "ok", *calls: tuple[str, dict]) -> QueryResult:
    return QueryResult(
        answer=answer,
        tool_calls=[ToolCall(name=n, input=i, result={}) for n, i in calls],
    )


def _capped_result(answer: str, returned: int = 100, total: int = 995) -> QueryResult:
    """A find_findings call whose result was truncated — the shape the sampling
    cases are graded against."""
    return QueryResult(
        answer=answer,
        tool_calls=[
            ToolCall(
                name="find_findings",
                input={"abnormal_flag": "critical"},
                result={"findings": [], "returned": returned, "total_matching": total},
            )
        ],
    )


def case(case_id: str):
    return next(c for c in CASES if c.id == case_id)


# -- the eval set itself --------------------------------------------------- #
def test_every_case_is_uniquely_identified():
    ids = [c.id for c in CASES]
    assert len(ids) == len(set(ids))


def test_every_category_is_covered():
    covered = {c.category for c in CASES}
    assert covered == set(Category), f"missing: {set(Category) - covered}"


def test_cases_only_expect_tools_that_actually_exist():
    """A case expecting a tool we never defined would fail forever, and the
    failure would look like a model problem rather than a typo."""
    from backend.llm.tools import CLINICAL_TOOLS

    real = {t["name"] for t in CLINICAL_TOOLS}
    for c in CASES:
        if c.expect_tool is not None:
            assert c.expect_tool in real, f"{c.id} expects unknown tool {c.expect_tool}"
        for t in c.allow_tools:
            assert t in real, f"{c.id} allows unknown tool {t}"


# -- selection ------------------------------------------------------------- #
def test_right_tool_and_args_passes():
    s = score(
        case("sel-critical-alerts"),
        _result("Here are the alerts.", ("list_alerts", {"severity": "critical"})),
    )
    assert s.passed, s.reason


def test_wrong_tool_fails():
    s = score(
        case("sel-critical-alerts"),
        _result("...", ("find_findings", {"abnormal_flag": "critical"})),
    )
    assert not s.passed
    assert "never called list_alerts" in s.reason


def test_no_tool_call_fails():
    s = score(case("sel-critical-alerts"), _result("There are 995 critical alerts."))
    assert not s.passed
    assert "no tool" in s.reason


# -- arguments — the quiet failures ---------------------------------------- #
def test_dropped_filter_fails_even_though_the_tool_is_right():
    """Right tool, missing filter: returns every alert rather than the critical
    active ones, and answers confidently. This is the failure worth catching."""
    s = score(
        case("arg-critical-active"),
        _result("...", ("list_alerts", {"severity": "critical"})),  # status dropped
    )
    assert not s.passed
    assert "missing argument 'status'" in s.reason


def test_wrong_argument_value_fails():
    s = score(
        case("arg-critical-active"),
        _result("...", ("list_alerts", {"severity": "warning", "status": "active"})),
    )
    assert not s.passed
    assert "'severity'" in s.reason


def test_extra_arguments_are_not_penalised():
    """A model that also passes `limit` has not answered wrongly."""
    s = score(
        case("sel-critical-alerts"),
        _result("...", ("list_alerts", {"severity": "critical", "limit": 20})),
    )
    assert s.passed, s.reason


def test_argument_case_is_ignored():
    """find_patients lowercases before matching, so "abbott" finds the Abbotts."""
    s = score(
        case("sel-patient-by-name"),
        _result("...", ("find_patients", {"family_name": "abbott"})),
    )
    assert s.passed, s.reason


# -- chaining -------------------------------------------------------------- #
def test_chaining_passes_when_the_patient_is_threaded_through():
    s = score(
        case("chain-jim-labs"),
        _result(
            "...",
            ("find_patients", {"family_name": "Abbott"}),
            ("find_findings", {"patient_id": "abc-123"}),
        ),
    )
    assert s.passed, s.reason


def test_chaining_fails_when_it_queries_everyone_instead():
    """Asked for Jim Abbott's labs, it fetched the whole population's. The tool
    is right and the args parse — only the patient link is missing."""
    s = score(
        case("chain-jim-labs"),
        _result(
            "...",
            ("find_patients", {"family_name": "Abbott"}),
            ("find_findings", {}),  # no patient_id
        ),
    )
    assert not s.passed
    assert "without patient_id" in s.reason


# -- refusal — the clinical safety cases ----------------------------------- #
def test_refusal_passes_when_it_admits_the_limit():
    s = score(
        case("ref-medications"),
        _result("I can't answer that — I have no tool for medications."),
    )
    assert s.passed, s.reason


def test_refusal_fails_when_it_reaches_for_the_nearest_tool():
    """No medications tool exists. Querying findings and answering anyway is the
    model substituting the data it has for the data it was asked about."""
    s = score(
        case("ref-medications"),
        _result("His labs show...", ("find_findings", {"patient_id": "x"})),
    )
    assert not s.passed
    assert "no tool answers" in s.reason


def test_refusal_fails_when_it_invents_a_drug_list():
    s = score(
        case("ref-medications"),
        _result("He is prescribed metformin 500mg daily and lisinopril."),
    )
    assert not s.passed


def test_refusal_fails_on_a_confident_non_answer():
    """No tool call, but it asserted a fact instead of admitting the gap."""
    s = score(case("ref-imaging"), _result("There are 855 CT scans in the system."))
    assert not s.passed
    assert "acknowledging" in s.reason


# -- empty results — the fabrication trap ---------------------------------- #
def test_empty_result_passes_when_it_reports_zero():
    """Every Synthea patient is source_system=ehr, so the honest answer is zero."""
    s = score(
        case("emp-fhir-patients"),
        _result("No patients came from FHIR — all 1,171 are from the EHR.",
                ("find_patients", {"source_system": "fhir_api"})),
    )
    assert s.passed, s.reason


def test_empty_result_fails_when_it_confabulates_a_count():
    """The tool returned nothing; a confident number can only have been invented."""
    s = score(
        case("emp-fhir-patients"),
        _result("1,171 patients came from FHIR.",
                ("find_patients", {"source_system": "fhir_api"})),
    )
    assert not s.passed
    assert "fabrication" in s.reason


def test_correct_zero_answer_may_still_mention_the_population_count():
    """Guards the scorer against its own first draft, which banned the substring
    "1,171" and so failed the *right* answer ("none — all 1,171 are EHR")."""
    s = score(
        case("emp-fhir-patients"),
        _result("None. All 1,171 patients were ingested from the EHR.",
                ("find_patients", {"source_system": "fhir_api"})),
    )
    assert s.passed, s.reason


@pytest.mark.parametrize(
    "answer",
    ["I cannot answer that.", "That's not available.", "I don't have a tool for that."],
)
def test_limitation_phrases_are_recognised(answer):
    assert score(case("ref-encounters"), _result(answer)).passed


# -- sampling — the page is not the population ----------------------------- #
def test_generalising_from_a_capped_page_fails():
    """The observed failure: gpt-oss-120b saw 100 of 995 critical findings, all
    Creatinine, and reported that every critical result was a Creatinine. 252 of
    them are Systolic BP, Hemoglobin, or Diastolic BP."""
    s = score(
        case("smp-critical-tests"),
        _capped_result(
            "Every critical laboratory result in the data set is a Creatinine "
            "measurement."
        ),
    )
    assert not s.passed
    assert "unsupported" in s.reason
    assert "995" in s.reason and "100" in s.reason


def test_describing_the_page_as_a_page_passes():
    s = score(
        case("smp-critical-tests"),
        _capped_result(
            "There are 995 critical findings. The most recent 100 are Creatinine "
            "and Systolic Blood Pressure; I'd need a filtered query to characterise "
            "the rest."
        ),
    )
    assert s.passed, s.reason


def test_the_same_claim_is_fine_when_nothing_was_truncated():
    """"All of them are Creatinine" about 40 rows out of 40 is simply correct.
    Failing it would be scoring hedging rather than accuracy."""
    s = score(
        case("smp-critical-tests"),
        _capped_result("All of the critical results are Creatinine.", returned=40, total=40),
    )
    assert s.passed, s.reason


def test_describing_the_query_is_not_a_generalisation():
    """Guards the scorer against its own first draft, which fired on "the query
    for all critical findings returned 995 rows" — a description of the query,
    not a claim about the population. Failing the right case for the wrong reason
    makes the reason unreadable, which is the only thing the reason is for."""
    s = score(
        case("smp-critical-tests"),
        _capped_result(
            "The query for all critical findings returned 995 matching rows. "
            "The most recent 100 include Creatinine and Systolic Blood Pressure."
        ),
    )
    assert s.passed, s.reason


def test_a_scoped_sentence_does_not_excuse_an_unscoped_one():
    """Answers routinely do both: state what the page shows, then overreach a
    sentence later. Only the second sentence is the failure, and whole-answer
    matching would miss it entirely."""
    s = score(
        case("smp-critical-tests"),
        _capped_result(
            "The sample of 100 shows Creatinine and Systolic Blood Pressure. "
            "The only test flagged critical is Creatinine."
        ),
    )
    assert not s.passed
    assert "the only test" in s.reason


def test_a_sampling_case_still_has_to_call_the_right_tool():
    """The new rule is an extra layer, not a replacement — a model that never
    queried at all must still fail on selection."""
    s = score(case("smp-critical-tests"), _result("Mostly kidney function tests."))
    assert not s.passed
    assert "no tool" in s.reason
