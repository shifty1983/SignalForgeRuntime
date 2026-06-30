from __future__ import annotations

from signalforge.backtesting.migrated_workflow_stage20_v3_2_2_paper_candidate_ruleset_lock_rebuild_validation import (
    build_stage20_v3_2_2_paper_candidate_ruleset_lock_rebuild_validation,
)


def test_stage20
@'
from __future__ import annotations

from signalforge.backtesting.migrated_workflow_stage20_v3_2_2_paper_v3_2_2_paper_candidate_ruleset_lock_rebuild_validation_builds():
    result = build_stage20_v3_2_2_paper_candidate_ruleset_lock_rebuild_validation()

    assert result["adapter_type"] == "migrated_workflow_stage20_v3_2_2_paper_candidate_ruleset_lock_rebuild_validation_builder"
    assert "blockers" in result


def test_stage20_v3_2_2_paper_candidate_ruleset_lock_rebuild_validation_is_ready():
    result = build_stage20_v3_2_2_paper_candidate_ruleset_lock_rebuild_validation()

    assert result["is_ready"] is True
    assert result["blocker_count"] == 0
    assert result["all_byte_counts_match"] is True
    assert result["all_sha256_match"] is True

    labels = {item["label"] for item in result["file_checks"]}
    assert labels == {"lock_json", "lock_md"}

    core = result["generated_lock_core"]
    assert core["decision"] == "lock_v3_2_2_as_current_paper_candidate_ruleset"
    assert core["paper_candidate_state"] == "locked_for_paper_candidate_review"
    assert core["live_candidate_state"] == "not_live_candidate"
