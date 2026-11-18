"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    manifest = pr.get("manifest") or {}
    rows = pr.get("rows") or []

    # 1. numbers that cannot be compared (NaN < min is False, so a naive gate waves them through)
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v}: a non-finite value cannot be compared with a threshold")

    # 2. rows must be exactly items x seeds, with no (item, seed) twice
    n_seeds = len(manifest.get("seeds") or [])
    if manifest.get("items") is None or not n_seeds:
        problems.append("manifest lacks items/seeds: cannot tell whether rows were dropped")
    elif len(rows) != int(manifest["items"]) * n_seeds:
        problems.append(f"{len(rows)} rows but manifest says {manifest['items']} items x {n_seeds} seeds "
                        f"= {int(manifest['items']) * n_seeds} (dropped or duplicated rows)")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dup = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dup:
        problems.append(f"duplicate (item, seed) rows: {dup[:3]}{' ...' if len(dup) > 3 else ''}")

    # 3. the PR must be graded on the same (item, seed) set as the baseline (cherry-picked seeds/items)
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base.get("rows") or []}
    if set(keys) != base_keys:
        problems.append(f"(item, seed) set differs from baseline: {len(base_keys - set(keys))} missing, "
                        f"{len(set(keys) - base_keys)} extra")

    # 4. a crashed grader must fail the run, not drop out of the mean
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s), first: {pr['evaluator_failures'][0]}")
    graded = [m["id"] for m in spec["metrics"] if m["id"] in GRADERS]
    for mid in graded:
        n_none = sum(1 for r in rows if r.get(mid) is None)
        if n_none:
            problems.append(f"{n_none} row(s) have no value for graded metric {mid} (grader crashed or row edited)")

    # 5. reported metrics must be what the rows add up to (a report cannot disagree with its own evidence)
    spec_kind = {m["id"]: m.get("kind") for m in spec["metrics"]}
    for mid in graded:
        got = (pr.get("metrics") or {}).get(mid)
        vals = [r[mid] for r in rows if r.get(mid) is not None]
        if got is None or not vals or (isinstance(got, float) and not math.isfinite(got)):
            continue                                      # missing / NaN are reported by checks 1 and 4
        want_v = sum(vals) if spec_kind.get(mid) == "safety" else sum(vals) / len(vals)
        if abs(want_v - got) > 5e-4:
            problems.append(f"metric {mid} reported {got} but its rows give {round(want_v, 4)}")

    # 6. slice tags must match the baseline's: relabelling an item hides it from the slice gate
    def tags(rep: dict) -> dict:
        return {r.get("item_id"): frozenset(r.get("slices") or []) for r in rep.get("rows") or []}
    pt, bt = tags(pr), tags(base)
    moved = sorted((i for i in set(pt) & set(bt) if pt[i] != bt[i]), key=str)
    if moved:
        problems.append(f"slice tags differ from baseline for {len(moved)} item(s): {moved[:3]}")

    # 7. ratchet: on the same eval-set version a threshold may only get stricter
    if base_spec is not None and base_spec.get("eval_set_version") == spec.get("eval_set_version"):
        problems += _ratchet(spec, base_spec)
    return problems


def _loosened(new: dict, old: dict, where: str) -> list[str]:
    out = []
    for key in ("max", "max_increase"):
        if key in old and (key not in new or new[key] > old[key]):
            out.append(f"{where}: {key} {old[key]} -> {new.get(key, 'removed')} (looser)")
    if "min" in old and ("min" not in new or new["min"] < old["min"]):
        out.append(f"{where}: min {old['min']} -> {new.get('min', 'removed')} (looser)")
    if old.get("no_significant_drop") and not new.get("no_significant_drop"):
        out.append(f"{where}: no_significant_drop dropped")
    return out


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    out: list[str] = []
    new_m = {m["id"]: m for m in spec.get("metrics") or []}
    for old in base_spec.get("metrics") or []:
        new = new_m.get(old["id"])
        if new is None:
            out.append(f"ratchet: metric {old['id']} removed")
            continue
        out += [f"ratchet: {x}" for x in _loosened(new.get("threshold") or {}, old.get("threshold") or {}, old["id"])]
        if old.get("blocking") and not new.get("blocking"):
            out.append(f"ratchet: metric {old['id']} is no longer blocking")
        if old.get("kind") != new.get("kind"):
            out.append(f"ratchet: metric {old['id']} kind {old.get('kind')} -> {new.get('kind')}")
    new_s = {x["name"]: x for x in spec.get("slices") or []}
    for old in base_spec.get("slices") or []:
        new = new_s.get(old["name"])
        if new is None:
            out.append(f"ratchet: slice {old['name']} removed")
            continue
        out += [f"ratchet: {x}" for x in _loosened(new, old, f"slice {old['name']}")]
        if old.get("blocking") and not new.get("blocking"):
            out.append(f"ratchet: slice {old['name']} is no longer blocking")
        if old.get("metric") != new.get("metric"):
            out.append(f"ratchet: slice {old['name']} metric {old.get('metric')} -> {new.get('metric')}")
    if (spec.get("bootstrap") or {}).get("confidence", 0.95) > (base_spec.get("bootstrap") or {}).get("confidence", 0.95):
        out.append("ratchet: bootstrap confidence raised (a wider CI makes the drop test looser)")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:                                   # no item carries this tag: nothing was measured
            verdict, note = "missing", "no items in slice"
        else:
            val = sum(a.values()) / len(a)
            if "min" in sl and val < sl["min"]:
                verdict = "fail"
            if sl.get("no_significant_drop"):
                keys = sorted(set(a) & set(b))
                if keys:
                    d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                       n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}] n={len(keys)}"
                    if hi < 0:
                        verdict = "fail"
                else:
                    verdict, note = "missing", "no common items with baseline"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        shown = "-" if val is None else f"{val:.4f}"
        th = json.dumps({k: sl[k] for k in ("min", "no_significant_drop") if k in sl})
        lines.append(f"  {sid:<34} {shown:<8} {th:<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
