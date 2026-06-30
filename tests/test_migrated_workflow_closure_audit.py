from __future__ import annotations

from signalforge.backtesting.migrated_workflow_closure_audit import (
    build_migrated_workflow_closure_audit,
)


def test_migrated_workflow_closure_audit_builds():
    result = build_migrated_workflow_closure_audit()

    assert result["adapter_type"] == "migrated_workflow_closure_audit_builder"
    assert result["artifact_type"] == "signalforge_migrated_workflow_closure_audit"
    assert "stage_results" in result
    assert "blockers" in result
    assert "warnings" in result


def test_migrated_workflow_closure_audit_is_closed_through_v3_2_2_lock():
    result = build_migrated_workflow_closure_audit()

    assert result["is_ready"] is True
    assert result["closure_state"] == "closed_through_v3_2_2_paper_candidate_lock"
    assert result["blocker_count"] == 0
    assert result["expected_stage_count"] == 16
    assert result["ready_stage_count"] == 16

    stages = {row["stage"]: row for row in result["stage_results"]}
    assert set(stages) == set(range(5, 21))

    for stage in range(5, 21):
        assert stages[stage]["stage_ready"] is True

    lock_core = result["paper_candidate_lock_core"]
    assert lock_core["decision"] == "lock_v3_2_2_as_current_paper_candidate_ruleset"
    assert lock_core["paper_candidate_state"] == "locked_for_paper_candidate_review"
    assert lock_core["live_candidate_state"] == "not_live_candidate"
    assert lock_core["paper_candidate_id"] == "signalforge_v3_2_2_symbol_regime_walkforward_prune_20230101_20260531"


def test_migrated_workflow_closure_audit_records_expected_warnings_only():
    result = build_migrated_workflow_closure_audit()

    assert "stage5_generated_dir_missing_but_validation_ready" in result["warnings"]
    assert any(
        "Legacy post-lock/runtime candidate artifacts still exist" in warning
        for warning in result["warnings"]
    )


