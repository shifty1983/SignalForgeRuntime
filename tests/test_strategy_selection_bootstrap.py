from __future__ import annotations

import json
from pathlib import Path

from signalforge.bootstrap.strategy_selection_bootstrap import (
    DECISION_ROWS_SOURCE_RELATIVE_PATH,
    STRATEGY_SELECTION_SOURCE_RELATIVE_PATH,
    STRATEGY_SELECTION_SUMMARY_RELATIVE_PATH,
    build_strategy_selection_bootstrap,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_strategy_selection_bootstrap_blocks_when_seed_missing(tmp_path: Path):
    summary = build_strategy_selection_bootstrap(
        seed_bundle=tmp_path / "missing",
        output_path=tmp_path / "strategy_selection_latest_snapshot.json",
    )

    assert not summary.is_ready
    assert "seed_bundle_missing" in summary.blockers


def test_strategy_selection_bootstrap_writes_joined_snapshot(tmp_path: Path):
    seed = tmp_path / "seed"

    write_json(seed / STRATEGY_SELECTION_SUMMARY_RELATIVE_PATH, {"is_ready": True, "artifact_type": "summary"})

    write_jsonl(
        seed / DECISION_ROWS_SOURCE_RELATIVE_PATH,
        [
            {
                "decision_row_id": "2026-01-01_SPY",
                "date": "2026-01-01",
                "symbol": "SPY",
                "regime": {"state": "risk_on", "source_date": "2025-12-31", "source_state": "available"},
                "asset_behavior": {"state": "constructive", "source_date": "2026-01-01", "source_state": "available"},
                "option_behavior": {"state": "iv_low_liquid", "source_date": "2026-01-01", "source_state": "available"},
                "eligibility": {
                    "eligible_for_strategy_selection": True,
                    "eligible_for_option_strategy_selection": True,
                    "eligible_for_option_decision": True,
                    "is_tradable": True,
                },
                "data_state": "complete",
                "blocks": [],
            }
        ],
    )

    write_jsonl(
        seed / STRATEGY_SELECTION_SOURCE_RELATIVE_PATH,
        [
            {
                "decision_row_id": "2026-01-01_SPY",
                "decision_date": "2026-01-01",
                "symbol": "SPY",
                "selection_state": "selected",
                "selection_reason": "positive_expectancy_candidate",
                "candidate_count": 3,
                "selectable_candidate_count": 1,
                "rejected_candidate_count": 2,
                "minimum_sample_count": 20,
                "selected_strategy": "long_call",
                "selected_expectancy_score": 0.25,
                "selected_expectancy_average_return": 0.15,
                "selected_expectancy_sample_count": 42,
                "selected_expectancy_state": "positive_expectancy_candidate",
                "selected_outcome_state": "complete",
                "selection_uses_current_row_outcome": False,
                "selection_uses_future_rows": False,
                "selection_uses_realized_outcome": False,
            }
        ],
    )

    output = tmp_path / "strategy_selection_latest_snapshot.json"
    summary = build_strategy_selection_bootstrap(seed_bundle=seed, output_path=output)

    assert summary.is_ready
    assert summary.source_row_count == 1
    assert summary.decision_row_count == 1
    assert summary.joined_row_count == 1
    assert summary.latest_decision_date == "2026-01-01"
    assert summary.selected_row_count == 1
    assert summary.selected_strategy_count == 1

    snapshot = json.loads(output.read_text(encoding="utf-8"))
    spy = snapshot["latest_rows_by_symbol"]["SPY"]

    assert snapshot["contract"] == "strategy_selection_latest_snapshot"
    assert spy["selected_strategy"] == "long_call"
    assert spy["regime_state"] == "risk_on"
    assert spy["asset_behavior_state"] == "constructive"
    assert spy["option_behavior_state"] == "iv_low_liquid"


def test_strategy_selection_bootstrap_blocks_on_missing_decision_join(tmp_path: Path):
    seed = tmp_path / "seed"

    write_json(seed / STRATEGY_SELECTION_SUMMARY_RELATIVE_PATH, {"is_ready": True})
    write_jsonl(seed / DECISION_ROWS_SOURCE_RELATIVE_PATH, [])
    write_jsonl(
        seed / STRATEGY_SELECTION_SOURCE_RELATIVE_PATH,
        [
            {
                "decision_row_id": "2026-01-01_SPY",
                "decision_date": "2026-01-01",
                "symbol": "SPY",
                "selection_state": "no_trade",
            }
        ],
    )

    summary = build_strategy_selection_bootstrap(
        seed_bundle=seed,
        output_path=tmp_path / "strategy_selection_latest_snapshot.json",
    )

    assert not summary.is_ready
    assert "one_or_more_strategy_rows_missing_decision_join" in summary.blockers
