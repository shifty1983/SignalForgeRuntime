from __future__ import annotations

import json
from pathlib import Path
from typing import Any


FIXTURE_DIR = Path("tests/fixtures/v3_2_2_minimal")

CANDIDATE_ID = "signalforge_v3_2_2_symbol_regime_walkforward_prune_20230101_20260531"


def load_json(name: str) -> Any:
    # PowerShell Set-Content commonly writes JSON with a UTF-8 BOM.
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8-sig"))


def iter_dicts(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from iter_dicts(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_dicts(item)


def dicts_with_key(obj: Any, key: str):
    return [d for d in iter_dicts(obj) if key in d]


def approx_equal(actual: float, expected: float, tolerance: float = 1e-6) -> bool:
    return abs(float(actual) - float(expected)) <= tolerance


def test_fixture_manifest_complete():
    manifest = load_json("fixture_manifest.json")

    assert manifest["copied_count"] == 4
    assert manifest["missing_count"] == 0

    copied = set(manifest["copied"])
    assert "v3_2_2_paper_candidate_ruleset_lock.json" in copied
    assert "v3_2_2_pre_broker_audit_pack_summary.json" in copied
    assert "v3_2_2_stress_summary.json" in copied
    assert "project_current_candidate_snapshot.json" in copied


def test_current_candidate_snapshot_locks_v3_2_2():
    snapshot = load_json("project_current_candidate_snapshot.json")
    raw = json.dumps(snapshot)

    assert CANDIDATE_ID in raw
    assert "v3_2_2_locked_as_current_paper_candidate" in raw
    assert "not_live_candidate" in raw


def test_paper_candidate_ruleset_lock():
    lock = load_json("v3_2_2_paper_candidate_ruleset_lock.json")
    raw = json.dumps(lock)

    assert CANDIDATE_ID in raw
    assert "lock_v3_2_2_as_current_paper_candidate_ruleset" in raw
    assert "not_live_candidate" in raw


def test_pre_broker_audit_passed_with_no_blockers():
    summary = load_json("v3_2_2_pre_broker_audit_pack_summary.json")
    raw = json.dumps(summary)

    assert CANDIDATE_ID in raw
    assert "v3_2_2_pre_broker_audits_passed_with_follow_up_flags" in raw

    blocker_dicts = dicts_with_key(summary, "blockers")
    assert blocker_dicts, "Expected at least one blockers field in summary."

    for item in blocker_dicts:
        assert item["blockers"] in ({}, [], None)


def test_no_lookahead_lineage_counts_match_locked_candidate():
    summary = load_json("v3_2_2_pre_broker_audit_pack_summary.json")

    lineage_rows = [
        d for d in iter_dicts(summary)
        if d.get("capital_label") in {"30k", "40k"}
        and "expected_skip_count" in d
        and "actual_v3_2_2_skip_count" in d
    ]

    assert lineage_rows, "No lineage rows found in pre-broker audit summary."

    by_capital = {row["capital_label"]: row for row in lineage_rows}

    assert by_capital["30k"]["expected_skip_count"] == 85
    assert by_capital["30k"]["actual_v3_2_2_skip_count"] == 85
    assert by_capital["30k"].get("false_positive_skip_count", 0) == 0

    assert by_capital["40k"]["expected_skip_count"] == 91
    assert by_capital["40k"]["actual_v3_2_2_skip_count"] == 91
    assert by_capital["40k"].get("false_positive_skip_count", 0) == 0


def test_capacity_spread_guardrail_remains_enforced():
    summary = load_json("v3_2_2_pre_broker_audit_pack_summary.json")

    capacity_rows = [
        d for d in iter_dicts(summary)
        if d.get("capital_label") in {"30k", "40k"}
        and "spread_pct_coverage" in d
        and "spread_pct_max" in d
    ]

    assert capacity_rows, "No capacity/liquidity rows found in pre-broker audit summary."

    by_capital = {row["capital_label"]: row for row in capacity_rows}

    assert approx_equal(by_capital["30k"]["spread_pct_coverage"], 1.0)
    assert approx_equal(by_capital["30k"]["spread_pct_max"], 0.125)

    assert approx_equal(by_capital["40k"]["spread_pct_coverage"], 1.0)
    assert approx_equal(by_capital["40k"]["spread_pct_max"], 0.125)


def test_v3_2_2_locked_baseline_metrics():
    # Use the paper candidate lock for final baseline metrics.
    # The stress summary contains several stress scenarios and should not be
    # reduced by capital_label alone.
    lock = load_json("v3_2_2_paper_candidate_ruleset_lock.json")

    metric_rows = [
        d for d in iter_dicts(lock)
        if d.get("capital_label") in {"30k", "40k"}
        and "total_pnl_dollars" in d
        and "trade_profit_factor" in d
    ]

    assert metric_rows, "No locked V3.2.2 baseline metric rows found."

    by_capital = {row["capital_label"]: row for row in metric_rows}

    assert approx_equal(by_capital["30k"]["total_pnl_dollars"], 730756.16413, tolerance=1e-4)
    assert approx_equal(by_capital["30k"]["max_drawdown_pct"], -0.100569, tolerance=1e-6)
    assert approx_equal(by_capital["30k"]["trade_profit_factor"], 2.646401, tolerance=1e-6)

    assert approx_equal(by_capital["40k"]["total_pnl_dollars"], 736568.165749, tolerance=1e-4)
    assert approx_equal(by_capital["40k"]["max_drawdown_pct"], -0.164075, tolerance=1e-6)
    assert approx_equal(by_capital["40k"]["trade_profit_factor"], 2.633118, tolerance=1e-6)


