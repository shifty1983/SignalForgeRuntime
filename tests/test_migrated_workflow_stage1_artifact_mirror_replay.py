from __future__ import annotations

from signalforge.backtesting.migrated_workflow_stage1_artifact_mirror_replay import (
    build_stage1_artifact_mirror_replay,
)


def test_stage1_artifact_mirror_replay_builds_without_copying():
    result = build_stage1_artifact_mirror_replay(copy_files=False)

    assert result["adapter_type"] == "migrated_workflow_stage1_artifact_mirror_replay_builder"
    assert result["copy_files"] is False
    assert "stage_results" in result
    assert "blockers" in result


def test_stage1_artifact_mirror_replay_core_sources_are_non_empty():
    result = build_stage1_artifact_mirror_replay(copy_files=False)

    stages = {stage["stage"]: stage for stage in result["stage_results"]}

    core_stages = {
        "historical_decision_rows",
        "historical_strategy_candidate_rows",
        "walk_forward_expectancy",
        "historical_strategy_selection_rows",
        "historical_strategy_leg_selection_rows",
        "portfolio_position_sizing_replay",
        "portfolio_selected_trade_sequence",
    }

    for stage_name in core_stages:
        row_artifact = stages[stage_name]["row_artifact"]
        assert row_artifact is not None
        assert row_artifact["row_count"] > 0
        assert row_artifact["source_sha256"]

