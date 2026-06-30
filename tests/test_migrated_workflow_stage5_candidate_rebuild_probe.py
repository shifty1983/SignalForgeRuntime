from __future__ import annotations

from signalforge.backtesting.migrated_workflow_stage5_candidate_rebuild_probe import (
    build_stage5_candidate_rebuild_probe,
)


def test_stage5_candidate_rebuild_probe_builds():
    result = build_stage5_candidate_rebuild_probe()

    assert result["adapter_type"] == "migrated_workflow_stage5_candidate_rebuild_probe_builder"
    assert result["decision_rows_path"]
    assert "cli_help" in result
    assert "detected_flags" in result

