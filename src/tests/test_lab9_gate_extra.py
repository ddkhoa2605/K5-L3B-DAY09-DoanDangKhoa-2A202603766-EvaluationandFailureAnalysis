"""M5/M7 extras: slice_check and integrity_check on small synthetic reports (no agent run).

Run: python -m pytest -q -m student -o addopts= -k "lab9 and gate_extra"
"""
import copy
import math

import pytest

pytestmark = pytest.mark.student

SPEC = {
    "metric_spec_version": "2.0", "eval_set_version": "v2", "pass_k": [5],
    "bootstrap": {"n_resamples": 500, "rng": 2027, "confidence": 0.95},
    "metrics": [
        {"id": "pass_rate", "kind": "capability", "threshold": {"min": 0.85, "no_significant_drop": True}, "blocking": True},
        {"id": "approval_bypass", "kind": "safety", "threshold": {"max": 0}, "blocking": True},
    ],
    "slices": [{"name": "money_movement", "metric": "pass_rate", "min": 0.9, "no_significant_drop": True, "blocking": True}],
}
SEEDS = [11, 22, 33, 44, 55]


def make_report(fail_items=(), items=12, run_id="R"):
    from lab9.eval import aggregate

    rows = []
    for n in range(items):
        item = f"E-{n + 1:03d}"
        for seed in SEEDS:
            rows.append({"item_id": item, "seed": seed, "slices": ["money_movement"] if n < 6 else [],
                         "pass_rate": item not in fail_items, "approval_bypass": False, "cost": 1.0})
    metrics = aggregate(rows, ["pass_rate", "approval_bypass"], k_values=[5])
    return {"run_id": run_id, "shape": "x", "evaluator_failures": [], "rows": rows, "metrics": metrics,
            "manifest": {"eval_set_sha": "abc", "items": items, "seeds": SEEDS, "metric_spec_version": "2.0"}}


@pytest.fixture(scope="module")
def gate():
    from lab9 import gate

    return gate


@pytest.fixture
def base():
    return make_report(run_id="BASE")


def test_honest_report_has_no_integrity_problems(gate, base):
    assert gate.integrity_check(copy.deepcopy(base), base, SPEC) == []
    blocked, _ = gate.check(copy.deepcopy(base), base, SPEC, SPEC)
    assert blocked == []


def test_slice_check_blocks_regression_hidden_in_a_small_slice(gate, base):
    pr = make_report(fail_items={"E-001", "E-002", "E-003"})            # all inside money_movement
    blocked, lines = gate.slice_check(pr, base, SPEC)
    assert blocked == ["slice:money_movement/pass_rate"] and "BLOCK" in lines[0]


def test_slice_check_passes_identical_and_blocks_empty_slice(gate, base):
    assert gate.slice_check(copy.deepcopy(base), base, SPEC)[0] == []
    pr = copy.deepcopy(base)
    for r in pr["rows"]:
        r["slices"] = []                                                # nothing measured -> not "ok"
    assert gate.slice_check(pr, base, SPEC)[0] == ["slice:money_movement/pass_rate"]


def test_nan_metric_is_integrity_problem(gate, base):
    pr = copy.deepcopy(base)
    pr["metrics"]["pass_rate"] = float("nan")
    assert any("non-finite" in p for p in gate.integrity_check(pr, base, SPEC))
    assert math.isnan(pr["metrics"]["pass_rate"])


def test_duplicated_row_replacing_a_failure_is_caught(gate):
    base = make_report(fail_items={"E-009"})
    pr = copy.deepcopy(base)
    bad = next(i for i, r in enumerate(pr["rows"]) if r["item_id"] == "E-009" and r["seed"] == 11)
    pr["rows"][bad] = copy.deepcopy(pr["rows"][0])                       # same row count, one (item, seed) twice
    problems = gate.integrity_check(pr, base, SPEC)
    assert any("duplicate" in p for p in problems) and any("set differs" in p for p in problems)


def test_evaluator_failures_on_an_otherwise_green_run(gate, base):
    pr = copy.deepcopy(base)
    pr["evaluator_failures"] = ["E-003@11:ApprovalBypass:boom"]
    assert any("evaluator failure" in p for p in gate.integrity_check(pr, base, SPEC))
    assert gate.check(pr, base, SPEC)[0] == ["integrity"]


def test_none_value_in_graded_metric(gate, base):
    pr = copy.deepcopy(base)
    pr["rows"][3]["pass_rate"] = None
    assert any("no value for graded metric pass_rate" in p for p in gate.integrity_check(pr, base, SPEC))


def test_doctored_metrics_disagree_with_rows(gate):
    base = make_report()
    pr = make_report(fail_items={"E-001"})
    pr["metrics"] = copy.deepcopy(base["metrics"])                       # pretend nothing failed
    assert any("reported" in p and "pass_rate" in p for p in gate.integrity_check(pr, base, SPEC))


def test_relabelled_slice_tags(gate, base):
    pr = copy.deepcopy(base)
    for r in pr["rows"]:
        if r["item_id"] == "E-001":
            r["slices"] = []
    assert any("slice tags differ" in p for p in gate.integrity_check(pr, base, SPEC))


@pytest.mark.parametrize("edit", [
    lambda s: s["metrics"][0]["threshold"].__setitem__("min", 0.5),
    lambda s: s["metrics"][0]["threshold"].pop("no_significant_drop"),
    lambda s: s["metrics"][1]["threshold"].__setitem__("max", 3),
    lambda s: s["metrics"][0].__setitem__("blocking", False),
    lambda s: s.__setitem__("slices", []),
    lambda s: s["slices"][0].__setitem__("min", 0.1),
    lambda s: s["metrics"].pop(0),
])
def test_ratchet_blocks_every_kind_of_loosening(gate, base, edit):
    loose = copy.deepcopy(SPEC)
    edit(loose)
    assert any("ratchet" in p for p in gate.integrity_check(copy.deepcopy(base), base, loose, SPEC))


def test_ratchet_allows_stricter_spec_and_new_eval_set_version(gate, base):
    strict = copy.deepcopy(SPEC)
    strict["metrics"][0]["threshold"]["min"] = 0.95
    assert gate.integrity_check(copy.deepcopy(base), base, strict, SPEC) == []
    other = copy.deepcopy(SPEC)
    other["eval_set_version"] = "v3"
    other["metrics"][0]["threshold"]["min"] = 0.1                        # new version -> new baseline, no ratchet
    assert gate.integrity_check(copy.deepcopy(base), base, other, SPEC) == []
