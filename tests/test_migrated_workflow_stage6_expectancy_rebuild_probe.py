from __future__ import annotations

from signalforge.backtesting.migrated_workflow_stage6_expectancy_rebuild_probe import (
    build_stage6_expectancy_rebuild_probe,
)


def test_stage6_expectancy_rebuild_probe_builds():
    result = build_stage6_expectancy_rebuild_probe()

    assert result["adapter_type"] == "migrated_workflow_stage6_expectancy_rebuild_probe_builder"
    assert "source_strategy_outcome_rows" in result
    assert "detected_flags" in result


def test_stage6_expectancy_rebuild_probe_detects_decision_rows_contract():
    result = build_stage6_expectancy_rebuild_probe()

    assert "--decision-rows" in result["detected_flags"]
    assert "--output-dir" in result["detected_flags"]


