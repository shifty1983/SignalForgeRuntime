from __future__ import annotations

from signalforge.backtesting.migrated_workflow_stage8_strategy_leg_selection_rebuild_probe import (
    build_stage8_strategy_leg_selection_rebuild_probe,
)


def test_stage8_strategy_leg_selection_rebuild_probe_builds():
    result = build_stage8_strategy_leg_selection_rebuild_probe()

    assert result["adapter_type"] == "migrated_workflow_stage8_strategy_leg_selection_rebuild_probe_builder"
    assert "detected_flags" in result
    assert "source_leg_selection_rows" in result
    assert "planned_output_dir" in result
