from __future__ import annotations

from signalforge.runtime.execution.readiness_contract import (
    build_runtime_execution_readiness_contract,
    validate_runtime_execution_readiness_contract,
)


def test_runtime_execution_contract_supports_paper_not_live():
    contract = build_runtime_execution_readiness_contract()

    assert contract["paper_trade_supported"] is True
    assert contract["live_trade_supported"] is False
    assert contract["requires_manual_approval"] is True
    assert contract["supported_execution_modes"] == ["paper"]
    assert "live" in contract["blocked_execution_modes"]


def test_runtime_execution_contract_finds_migrated_execution_module():
    contract = build_runtime_execution_readiness_contract()

    assert contract["migrated_execution_module_count"] > 0
    assert contract["migrated_execution_modules"]


def test_runtime_execution_contract_validates_ready_for_paper_only():
    validation = validate_runtime_execution_readiness_contract()

    assert validation["is_ready_for_paper"] is True
    assert validation["is_ready_for_live"] is False
    assert validation["blocker_count"] == 0
    assert validation["live_blockers"]
