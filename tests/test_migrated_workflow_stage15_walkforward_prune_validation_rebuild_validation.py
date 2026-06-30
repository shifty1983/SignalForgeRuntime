from __future__ import annotations

from signalforge.backtesting.migrated_workflow_stage15_walkforward_prune_validation_rebuild_validation import (
    build_stage15_walkforward_prune_validation_rebuild_validation,
)


def test_stage15_walkforward_prune_validation_rebuild_validation_builds():
    result = build_stage15_walkforward_prune_validation_rebuild_validation()

    assert result["adapter_type"] == "migrated_workflow_stage15_walkforward_prune_validation_rebuild_validation_builder"
    assert "blockers" in result


def test_stage15_walkforward_prune_validation_rebuild_validation_is_ready():
    result = build_stage15_walkforward_prune_validation_rebuild_validation()

    assert result["is_ready"] is True
    assert result["blocker_count"] == 0
    assert result["all_row_counts_match"] is True
    assert result["all_sample_schemas_match"] is True
    assert result["all_sha256_match"] is True

    labels = {item["label"] for item in result["row_checks"]}
    assert labels == {"results", "skipped_rows"}


