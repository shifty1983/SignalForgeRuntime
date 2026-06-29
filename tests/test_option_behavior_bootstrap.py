from __future__ import annotations

import json
from pathlib import Path

from signalforge.runtime.option_behavior_bootstrap import (
    CLASSIFIER_SOURCE_RELATIVE_PATH,
    SOURCE_READINESS_RELATIVE_PATH,
    SYMBOL_READINESS_RELATIVE_PATH,
    build_option_behavior_bootstrap,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_option_behavior_bootstrap_blocks_when_seed_missing(tmp_path: Path):
    summary = build_option_behavior_bootstrap(
        seed_bundle=tmp_path / "missing",
        output_path=tmp_path / "option_behavior_latest_snapshot.json",
    )

    assert not summary.is_ready
    assert "seed_bundle_missing" in summary.blockers


def test_option_behavior_bootstrap_writes_snapshot(tmp_path: Path):
    seed = tmp_path / "seed"

    write_json(
        seed / CLASSIFIER_SOURCE_RELATIVE_PATH,
        {
            "artifact_type": "signalforge_partitioned_option_behavior_classifier",
            "schema_version": "test",
            "is_ready": True,
            "status": "ready",
            "macro_regime_label": "late_cycle_overheating",
            "policy_regime_label": "late_cycle_overheating",
            "weekly_planning_label": "late_cycle_overheating_with_rates_review",
            "ready_symbols": ["SPY"],
            "review_required_symbols": ["TLT"],
            "blocked_symbols": ["XYZ"],
            "symbol_count": 3,
            "total_option_row_count": 100,
            "symbol_behavior_items": [
                {
                    "symbol": "SPY",
                    "option_behavior_state": "iv_low_liquid",
                    "iv_level": "low",
                    "liquidity_state": "liquid",
                    "option_behavior_gate": "ready",
                }
            ],
        },
    )

    write_json(
        seed / SOURCE_READINESS_RELATIVE_PATH,
        {
            "artifact_type": "signalforge_partitioned_option_behavior_source_readiness",
            "schema_version": "test",
            "is_ready": True,
            "status": "ready",
            "combined_ready_symbols": ["SPY"],
            "combined_review_required_symbols": ["TLT"],
            "combined_blocked_symbols": ["XYZ"],
        },
    )

    write_json(
        seed / SYMBOL_READINESS_RELATIVE_PATH,
        {
            "artifact_type": "signalforge_option_source_symbol_readiness_consolidation",
            "schema_version": "test",
            "is_ready": True,
            "status": "ready",
            "macro_regime_label": "late_cycle_overheating",
            "policy_regime_label": "late_cycle_overheating",
            "weekly_planning_label": "late_cycle_overheating_with_rates_review",
            "symbol_count": 3,
            "usable_symbol_count": 1,
            "usable_symbols": ["SPY"],
            "review_required_symbols": ["TLT"],
            "blocked_symbols": ["XYZ"],
            "symbol_items": [
                {
                    "symbol": "SPY",
                    "downstream_gate": "ready",
                    "global_state": "ready",
                    "ready_partition_count": 2,
                    "review_required_partition_count": 0,
                    "blocked_partition_count": 0,
                    "total_state_record_count": 2,
                },
                {
                    "symbol": "TLT",
                    "downstream_gate": "review_required",
                    "global_state": "review_required_only",
                    "ready_partition_count": 0,
                    "review_required_partition_count": 1,
                    "blocked_partition_count": 0,
                    "total_state_record_count": 1,
                },
            ],
        },
    )

    output = tmp_path / "option_behavior_latest_snapshot.json"

    summary = build_option_behavior_bootstrap(seed_bundle=seed, output_path=output)

    assert summary.is_ready
    assert summary.symbol_count == 3
    assert summary.usable_symbol_count == 1
    assert summary.ready_symbol_count == 1
    assert summary.review_required_symbol_count == 1
    assert summary.blocked_symbol_count == 1
    assert summary.total_option_row_count == 100

    snapshot = json.loads(output.read_text(encoding="utf-8"))

    assert snapshot["contract"] == "option_behavior_latest_snapshot"
    assert snapshot["items_by_symbol"]["SPY"]["is_usable"] is True
    assert snapshot["items_by_symbol"]["TLT"]["downstream_gate"] == "review_required"
    assert snapshot["items_by_symbol"]["XYZ"]["membership_gate"] == "blocked"


def test_option_behavior_bootstrap_blocks_when_source_not_ready(tmp_path: Path):
    seed = tmp_path / "seed"

    write_json(seed / CLASSIFIER_SOURCE_RELATIVE_PATH, {"is_ready": False, "status": "blocked"})
    write_json(seed / SOURCE_READINESS_RELATIVE_PATH, {"is_ready": True, "status": "ready"})
    write_json(
        seed / SYMBOL_READINESS_RELATIVE_PATH,
        {
            "is_ready": True,
            "status": "ready",
            "symbol_items": [{"symbol": "SPY"}],
        },
    )

    summary = build_option_behavior_bootstrap(
        seed_bundle=seed,
        output_path=tmp_path / "option_behavior_latest_snapshot.json",
    )

    assert not summary.is_ready
    assert "classifier_not_ready" in summary.blockers
    assert "classifier_status_not_ready" in summary.blockers
