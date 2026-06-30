from __future__ import annotations

from signalforge.backtesting.migrated_workflow_stage7_strategy_selection_rebuild_probe import (
    build_stage7_strategy_selection_rebuild_probe,
)


def test_stage7_strategy_selection_rebuild_probe_builds():
    result = build_stage7_strategy_selection_rebuild_probe()

    assert result["adapter_type"] == "migrated_workflow_stage7_strategy_selection_rebuild_probe_builder"
    assert "generated_expectancy_rows" in result
    assert "detected_flags" in result


def test_stage7_strategy_selection_rebuild_probe_detects_expectancy_contract():
    result = build_stage7_strategy_selection_rebuild_probe()

    assert "--expectancy-rows" in result["detected_flags"]
    assert "--output-dir" in result["detected_flags"]


