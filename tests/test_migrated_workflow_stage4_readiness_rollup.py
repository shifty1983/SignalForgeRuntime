from __future__ import annotations

from signalforge.backtesting.migrated_workflow_stage4_readiness_rollup import (
    build_stage4_migrated_workflow_readiness_rollup,
)


def test_stage4_readiness_rollup_builds():
    result = build_stage4_migrated_workflow_readiness_rollup()

    assert result["adapter_type"] == "migrated_workflow_stage4_readiness_rollup_builder"
    assert "input_manifest_statuses" in result
    assert "blockers" in result


def test_stage4_readiness_rollup_is_ready():
    result = build_stage4_migrated_workflow_readiness_rollup()

    assert result["is_ready"] is True
    assert result["blocker_count"] == 0
    assert result["failed_semantic_relationships"] == []


