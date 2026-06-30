from __future__ import annotations

from signalforge.backtesting.legacy_post_lock_disposition_audit import (
    build_legacy_post_lock_disposition_audit,
)


def test_legacy_post_lock_disposition_audit_builds():
    result = build_legacy_post_lock_disposition_audit()

    assert result["adapter_type"] == "legacy_post_lock_disposition_audit_builder"
    assert result["artifact_type"] == "signalforge_legacy_post_lock_disposition_audit"
    assert "legacy_post_lock_artifacts" in result
    assert "runtime_candidates" in result
    assert "deployment_candidates" in result


def test_legacy_post_lock_disposition_audit_is_ready():
    result = build_legacy_post_lock_disposition_audit()

    assert result["is_ready"] is True
    assert result["blocker_count"] == 0
    assert result["legacy_post_lock_artifact_count"] >= 1


def test_legacy_post_lock_disposition_audit_identifies_runtime_and_deployment_candidates():
    result = build_legacy_post_lock_disposition_audit()

    assert result["runtime_candidate_count"] >= 1
    assert result["deployment_candidate_count"] >= 1

    runtime_names = {row["name"] for row in result["runtime_candidates"]}
    deployment_names = {row["name"] for row in result["deployment_candidates"]}

    assert "ibkr_paper_connection_smoke_test_20210601_20260531_21d" in runtime_names
    assert "portfolio_execution_translation_rulebook_20210601_20260531" in deployment_names


def test_legacy_post_lock_disposition_audit_keeps_deployment_after_runtime():
    result = build_legacy_post_lock_disposition_audit()

    action_counts = result["recommended_action_counts"]

    assert action_counts["review_for_runtime_or_paper_trading_migration"] >= 1
    assert action_counts["review_after_runtime_paper_trade_design"] >= 1
