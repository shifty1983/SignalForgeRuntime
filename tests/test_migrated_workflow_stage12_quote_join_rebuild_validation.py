from __future__ import annotations

from signalforge.backtesting.migrated_workflow_stage12_quote_join_rebuild_validation import (
    build_stage12_quote_join_rebuild_validation,
)


def test_stage12_quote_join_rebuild_validation_builds():
    result = build_stage12_quote_join_rebuild_validation()

    assert result["adapter_type"] == "migrated_workflow_stage12_quote_join_rebuild_validation_builder"
    assert "blockers" in result


def test_stage12_quote_join_rebuild_validation_is_ready():
    result = build_stage12_quote_join_rebuild_validation()

    assert result["is_ready"] is True
    assert result["blocker_count"] == 0
    assert result["row_count_matches"] is True
    assert result["sample_schema_matches"] is True
    assert result["sha256_matches"] is True
