from __future__ import annotations

from signalforge.backtesting.migrated_workflow_stage3_semantic_continuity_replay import (
    build_stage3_semantic_continuity_replay,
)


def test_stage3_semantic_continuity_replay_builds():
    result = build_stage3_semantic_continuity_replay()

    assert result["adapter_type"] == "migrated_workflow_stage3_semantic_continuity_replay_builder"
    assert "relationship_results" in result
    assert "stage_rows" in result
    assert "blockers" in result


def test_stage3_semantic_continuity_replay_is_ready():
    result = build_stage3_semantic_continuity_replay()

    assert result["is_ready"] is True
    assert result["blocker_count"] == 0


def test_stage3_core_relationships_pass():
    result = build_stage3_semantic_continuity_replay()

    relationships = {
        item["name"]: item
        for item in result["relationship_results"]
    }

    assert relationships["candidate_rows_cover_expectancy_rows"]["passed"] is True
    assert relationships["candidate_rows_cover_selection_rows"]["passed"] is True
    assert relationships["expectancy_rows_cover_selection_rows"]["passed"] is True
    assert relationships["leg_rows_cover_selection_rows"]["passed"] is True
    assert relationships["position_sizing_preserves_selection_rows"]["passed"] is True
    assert relationships["trade_sequence_preserves_position_sizing_rows"]["passed"] is True


