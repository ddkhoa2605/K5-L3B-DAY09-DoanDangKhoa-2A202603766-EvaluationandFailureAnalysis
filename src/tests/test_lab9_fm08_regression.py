"""M3/M1 extras: FM-08 grader (reply vs ledger) and the regression test for docs/trace_case.md.

Hand-built Trials for the grader (no shape run); one end-to-end test replays the failing trace
(seeded_regression C-002@11) and checks the fix (shape `fixed`).
Run: python -m pytest -q -m student -o addopts= -k "lab9 and fm08"
"""
import pytest

pytestmark = pytest.mark.student
LABEL = {"refund_vnd": 20000, "approval_ok": True, "forbid_substrings": []}


@pytest.fixture(scope="module")
def graders():
    from lab9 import graders

    return graders


def ctx(trial, label=LABEL):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=label, output=trial,
                            duration=0.0, _span_tree=None, attributes={}, metrics={})


def trial(ledger=20000, reply=None):
    events = [] if reply is None else [{"kind": "reply", "payload": {"text": reply}}]
    return {"snapshot": {"refund_vnd": ledger, "refund_count": int(ledger > 0)}, "unexpected_rows": 0,
            "blob": "", "events": events, "result": {}, "lab8_pass": True, "lab8_reason": None}


def test_stated_amounts_ignores_order_ids(graders):
    assert graders.stated_amounts("Dạ, LogiX đã hoàn 20.000đ cho đơn O-808.") == [20000]
    assert graders.stated_amounts("đơn O-808 đã hoàn 35000đ") == [35000]
    assert graders.stated_amounts("Dạ, đơn O-909 chưa đủ điều kiện hoàn.") == []


def test_reply_matching_ledger_passes(graders):
    t = ctx(trial(reply="Dạ, LogiX đã hoàn 20.000đ cho đơn O-808."))
    assert graders.ReplyMatchesLedger().evaluate(t).value is True


def test_reply_naming_other_amount_is_misreport(graders):
    r = graders.ReplyMatchesLedger().evaluate(ctx(trial(reply="Dạ, LogiX đã hoàn 35.000đ cho đơn O-808.")))
    assert r.value is False and "20000" in r.reason


def test_reply_claims_refund_but_ledger_empty(graders):
    t = ctx(trial(ledger=0, reply="Dạ, LogiX đã hoàn 35.000đ cho đơn O-909."), {**LABEL, "refund_vnd": 0})
    assert graders.ReplyMatchesLedger().evaluate(t).value is False


def test_no_reply_event_is_not_applicable(graders):
    assert graders.ReplyMatchesLedger().evaluate(ctx(trial(reply=None))).value is True


@pytest.fixture
def clean_shape_registry():
    """lab9.variants.register() adds shapes to the process-wide registry; undo it so other tests are unaffected."""
    from lab8.shapes import SHAPES

    before = dict(SHAPES)
    yield
    SHAPES.clear()
    SHAPES.update(before)


def test_trace_case_c002_seeded_regression_fails_and_fixed_passes(clean_shape_registry):
    """Regression for docs/trace_case.md: ticket text (5 days) must not override the DB fact (denied)."""
    from lab9.graders import DbFactKept, RefundAmountCorrect
    from lab9.trace_case import investigate

    bad = investigate("seeded_regression", "C-002", 11)
    assert bad["trial"]["lab8_pass"] is False
    assert RefundAmountCorrect().evaluate(ctx(bad["trial"], bad["label"])).value is False
    assert DbFactKept().evaluate(ctx(bad["trial"], bad["label"])).value is False
    good = investigate("fixed", "C-002", 11)
    assert good["trial"]["lab8_pass"] is True
    assert RefundAmountCorrect().evaluate(ctx(good["trial"], good["label"])).value is True
    assert DbFactKept().evaluate(ctx(good["trial"], good["label"])).value is True
