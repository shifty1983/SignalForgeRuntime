from __future__ import annotations

from signalforge.backtesting.migrated_workflow_stage2_artifact_parity_replay import (
    build_stage2_artifact_parity_replay,
)


def test_stage2_artifact_parity_replay_builds():
    result = build_stage2_artifact_parity_replay()

    assert result["adapter_type"] == "migrated_workflow_stage2_artifact_parity_replay_builder"
    assert "artifact_results" in result
    assert "blockers" in result
    assert result["compared_artifact_count"] > 0


def test_stage2_artifact_parity_replay_is_ready():
    result = build_stage2_artifact_parity_replay()

    assert result["is_ready"] is True
    assert result["blocker_count"] == 0


def test_stage2_artifact_parity_core_row_counts_match():
    result = build_stage2_artifact_parity_replay()

    core_stages = {
        "historical_decision_rows",
        "historical_strategy_candidate_rows",
        "walk_forward_expectancy",
        "historical_strategy_selection_rows",
        "historical_strategy_leg_selection_rows",
        "portfolio_position_sizing_replay",
        "portfolio_selected_trade_sequence",
    }

    row_results = {
        artifact["stage"]: artifact
        for artifact in result["artifact_results"]
        if artifact.get("artifact_type") == "row_artifact"
    }

    for stage in core_stages:
        assert row_results[stage]["row_count_matches"] is True
        assert row_results[stage]["sha256_matches"] is True
        assert row_results[stage]["source_row_count"] > 0

