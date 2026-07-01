from signalforge.backtesting.historical_strategy_candidate_rows_builder import (
    build_historical_strategy_candidate_rows,
)


def test_candidate_rows_carry_research_context_objects_and_term_fields():
    decision_row = {
        "decision_row_id": "2024-01-05_AAPL",
        "decision_date": "2024-01-05",
        "symbol": "AAPL",
        "data_state": "complete",
        "regime": {"state": "risk_on", "source_state": "available"},
        "asset_behavior": {"state": "constructive", "source_state": "available", "trend_quality": "strong"},
        "option_behavior": {
            "state": "iv_moderate_liquid",
            "source_state": "available",
            "term_structure_state": "available",
            "term_structure_shape": "flat",
            "front_iv": 0.22,
            "back_iv": 0.20,
            "front_back_iv_spread": -0.02,
            "front_back_iv_spread_pct": -0.10,
            "front_dte": 17,
            "back_dte": 45,
        },
        "eligibility": {
            "is_tradable": True,
            "eligible_for_strategy_selection": True,
            "eligible_for_option_strategy_selection": True,
        },
        "regime_asset_options_alignment": {
            "term_structure_state": "available",
            "premium_bias": "balanced_premium_bias",
        },
        "strategy_family_eligibility": {
            "strategy_family_eligibility_handoff": "ready_for_expected_value_scoring",
        },
        "strategy_family_statuses": {
            "long_premium": "allowed",
        },
    }

    policy = {
        "policy_name": "test_policy",
        "policy_version": "1.0",
        "required_eligibility_flags": [
            "is_tradable",
            "eligible_for_strategy_selection",
            "eligible_for_option_strategy_selection",
        ],
        "eligible_data_states": ["complete"],
        "enforce_strategy_family_eligibility": True,
        "allowed_strategy_family_statuses": ["allowed"],
        "blocked_option_liquidity_states": [],
        "risk_overlays": [{"risk_overlay": "defined_risk_cap_m1_p1", "risk_overlay_rank": 1}],
        "holding_period_days": [21],
        "excluded_strategies": [],
        "excluded_strategy_reasons": {},
        "strategies": [
            {
                "strategy": "long_call",
                "strategy_family": "long_premium",
                "strategy_structure": "single_leg_option",
                "strategy_direction": "bullish",
                "premium_profile": "debit",
                "defined_risk": True,
                "requires_term_structure": False,
                "requires_underlying_position": False,
                "allowed_asset_behavior_states": ["constructive"],
                "allowed_option_iv_levels": ["moderate"],
                "allowed_option_liquidity_states": ["liquid"],
                "allowed_holding_period_days": [21],
                "candidate_rank": 1,
            }
        ],
    }

    rows, summary = build_historical_strategy_candidate_rows(
        decision_rows=[decision_row],
        strategy_policy=policy,
    )

    assert summary["is_ready"] is True
    assert len(rows) == 1

    row = rows[0]
    assert row["strategy_candidate_state"] == "available"

    assert row["asset_behavior"]["trend_quality"] == "strong"
    assert row["option_behavior"]["term_structure_shape"] == "flat"
    assert row["regime_asset_options_alignment"]["term_structure_state"] == "available"
    assert row["strategy_family_eligibility"]["strategy_family_eligibility_handoff"] == "ready_for_expected_value_scoring"
    assert row["strategy_family_statuses"]["long_premium"] == "allowed"

    assert row["research_context"]["asset_behavior"]["trend_quality"] == "strong"
    assert row["research_context"]["option_behavior"]["front_iv"] == 0.22

    assert row["term_structure_state"] == "available"
    assert row["term_structure_shape"] == "flat"
    assert row["front_iv"] == 0.22
    assert row["back_iv"] == 0.20
    assert row["front_back_iv_spread"] == -0.02
    assert row["front_back_iv_spread_pct"] == -0.10
    assert row["front_dte"] == 17
    assert row["back_dte"] == 45
