from __future__ import annotations

from signalforge.backtesting.migrated_workflow_manifest import (
    ORDERED_WORKFLOW_STEPS,
    build_migrated_workflow_manifest,
)


def test_migrated_workflow_manifest_is_ready():
    manifest = build_migrated_workflow_manifest()

    assert manifest["is_ready"] is True
    assert manifest["blocker_count"] == 0


def test_migrated_workflow_manifest_has_core_ordered_steps():
    manifest = build_migrated_workflow_manifest()

    observed = [step["step"] for step in manifest["workflow_steps"]]

    assert observed == ORDERED_WORKFLOW_STEPS
    assert "historical_decision_rows" in observed
    assert "walk_forward_expectancy" in observed
    assert "portfolio_value_ranked_allocator_v2" in observed
    assert "v3_2_2_pruning" in observed
    assert "v3_2_2_ruleset_lock" in observed
    assert "runtime_execution_readiness_contract" in observed


def test_migrated_workflow_manifest_discovers_execution_modules():
    manifest = build_migrated_workflow_manifest()

    assert manifest["runtime_execution_modules"]
    assert "readiness_contract" in manifest["runtime_execution_modules"]

