from __future__ import annotations

import importlib
from pathlib import Path


def test_requested_robustness_stress_case_coverage_contract():
    module = importlib.import_module(
        "signalforge.backtesting.v3_2_1_native_quote_pnl_stress_v1"
    )

    coverage = module.REQUESTED_ROBUSTNESS_STRESS_CASE_COVERAGE

    expected_cases = {
        "stress_case_1_25pct_worse_fills",
        "stress_case_2_50pct_worse_fills",
        "stress_case_3_100pct_worse_fills",
        "stress_case_4_no_mid_conservative_bid_ask_fills",
        "stress_case_5_skip_trades_where_spread_exceeds_threshold",
        "stress_case_6_ibkr_like_commissions_and_fees",
    }

    assert set(coverage) == expected_cases

    assert coverage["stress_case_1_25pct_worse_fills"]["quote_cost_multiplier"] == 1.25
    assert coverage["stress_case_2_50pct_worse_fills"]["quote_cost_multiplier"] == 1.50
    assert coverage["stress_case_3_100pct_worse_fills"]["quote_cost_multiplier"] == 2.00
    assert coverage["stress_case_6_ibkr_like_commissions_and_fees"]["commission_per_contract"] == 1.50


def test_stress_engine_contains_native_quote_cases():
    source = Path(
        "src/signalforge/backtesting/v3_2_1_native_quote_pnl_stress_v1.py"
    ).read_text(encoding="utf-8")

    required_terms = [
        "native_quote_1_25x_commission_150",
        "native_quote_1_5x_commission_150",
        "native_quote_2x_commission_150",
        "native_quote_3x_commission_150",
        "round_trip_half_spread_cost_estimate_for_row",
        "signalforge_v3_2_1_spread_guardrail_12_5pct_20230101_20260531",
    ]

    for term in required_terms:
        assert term in source

