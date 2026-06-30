from __future__ import annotations

from signalforge.backtesting.migrated_workflow_dry_run_plan import (
    ORDERED_STAGES,
    build_migrated_workflow_dry_run_plan,
)


def test_migrated_workflow_dry_run_plan_builds():
    plan = build_migrated_workflow_dry_run_plan()

    assert plan["adapter_type"] == "migrated_workflow_dry_run_plan_builder"
    assert plan["stage_count"] == len(ORDERED_STAGES)
    assert "stages" in plan
    assert "blockers" in plan


def test_migrated_workflow_dry_run_plan_resolves_core_rows():
    plan = build_migrated_workflow_dry_run_plan()

    core_stages = {
        "historical_decision_rows",
        "historical_strategy_candidate_rows",
        "walk_forward_expectancy",
        "historical_strategy_selection_rows",
        "historical_strategy_leg_selection_rows",
        "portfolio_position_sizing_replay",
        "portfolio_selected_trade_sequence",
    }

    stages = {stage["stage"]: stage for stage in plan["stages"]}

    for stage in core_stages:
        assert stages[stage]["selected_row_path"]


