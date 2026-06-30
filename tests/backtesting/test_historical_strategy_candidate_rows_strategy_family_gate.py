from signalforge.backtesting.historical_strategy_candidate_rows_builder import (
    build_historical_strategy_candidate_rows,
)


def _decision_row(strategy_family_statuses):
    return {
        "decision_row_id": "2024-01-05_AAPL",
        "decision_date": "2024-01-05",
        "symbol": "AAPL",
        "data_state": "complete",
        "regime": {"state": "risk_on", "source_state": "available"},
        "asset_behavior": {"state": "constructive", "source_state": "available"},
        "option_behavior": {"state": "iv_moderate_liquid", "source_state": "available"},
        "eligibility": {
            "is_tradable": True,
            "eligible_for_strategy_selection": True,
            "eligible_for_option_strategy_selection": True,
        },
        "strategy_family_statuses": strategy_family_statuses,
    }


def _policy():
    return {
        "policy_name": "test_strategy_family_gate_policy",
        "policy_version": "1.0",
        "eligible_data_states": ["complete"],
        "required_eligibility_flags": [
            "is_tradable",
            "eligible_for_strategy_selection",
            "eligible_for_option_strategy_selection",
        ],
        "enforce_strategy_family_eligibility": True,
        "allowed_strategy_family_statuses": ["allowed"],
        "blocked_option_liquidity_states": [],
        "holding_period_days": [5],
        "risk_overlays": [{"risk_overlay": "test_overlay", "risk_overlay_rank": 1}],
        "strategies": [
            {
                "strategy": "test_allowed_strategy",
                "strategy_family": "allowed_family",
                "strategy_structure": "single_leg_option",
                "strategy_direction": "bullish",
                "premium_profile": "debit",
                "defined_risk": True,
                "requires_underlying_position": False,
                "requires_term_structure": False,
                "candidate_rank": 1,
                "allowed_holding_period_days": [5],
            },
            {
                "strategy": "test_blocked_strategy",
                "strategy_family": "blocked_family",
                "strategy_structure": "single_leg_option",
                "strategy_direction": "bullish",
                "premium_profile": "debit",
                "defined_risk": True,
                "requires_underlying_position": False,
                "requires_term_structure": False,
                "candidate_rank": 2,
                "allowed_holding_period_days": [5],
            },
        ],
    }


def test_candidate_rows_apply_strategy_family_eligibility_gate() -> None:
    rows, summary = build_historical_strategy_candidate_rows(
        decision_rows=[_decision_row({"allowed_family": "allowed", "blocked_family": "blocked"})],
        strategy_policy=_policy(),
        emit_blocked_rows=True,
    )

    by_strategy = {row["strategy"]: row for row in rows}

    assert by_strategy["test_allowed_strategy"]["strategy_candidate_state"] == "available"
    assert by_strategy["test_allowed_strategy"]["strategy_family_status"] == "allowed"

    assert by_strategy["test_blocked_strategy"]["strategy_candidate_state"] == "blocked"
    assert by_strategy["test_blocked_strategy"]["strategy_family_status"] == "blocked"
    assert (
        "strategy_family_status_not_allowed:blocked_family:blocked"
        in by_strategy["test_blocked_strategy"]["strategy_candidate_block_reasons"]
    )

    assert summary["strategy_family_status_counts"]["allowed"] == 1
    assert summary["strategy_family_status_counts"]["blocked"] == 1


def test_candidate_rows_block_when_strategy_family_statuses_missing() -> None:
    rows, summary = build_historical_strategy_candidate_rows(
        decision_rows=[_decision_row({})],
        strategy_policy=_policy(),
        emit_blocked_rows=True,
    )

    assert rows
    assert all(row["strategy_candidate_state"] == "blocked" for row in rows)
    assert summary["strategy_family_status_counts"]["__missing__"] == len(rows)


