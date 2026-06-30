from __future__ import annotations

from signalforge.backtesting.migrated_workflow_stage0_artifact_contract_replay import (
    build_stage0_artifact_contract_replay,
)


def test_stage0_artifact_contract_replay_builds():
    result = build_stage0_artifact_contract_replay()

    assert result["adapter_type"] == "migrated_workflow_stage0_artifact_contract_replay_builder"
    assert "stage_results" in result
    assert "blockers" in result


def test_stage0_artifact_contract_replay_core_rows_parse():
    result = build_stage0_artifact_contract_replay()

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

    for stage in core_stages:
        assert stages[stage]["row_exists"] is True
        assert stages[stage]["row_count"] > 0
        assert stages[stage]["sample"]["sample_parse_ready"] is True


