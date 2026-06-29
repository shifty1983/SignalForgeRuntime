from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeSourceMapping:
    runtime_input_name: str
    runtime_relative_path: str
    seed_source_relative_path: str | None
    generated_by: str
    required_for_paper: bool
    description: str


RUNTIME_SOURCE_MAPPINGS: tuple[RuntimeSourceMapping, ...] = (
    RuntimeSourceMapping(
        runtime_input_name="underlying_market_data",
        runtime_relative_path="data/runtime/market/underlying_daily.jsonl",
        seed_source_relative_path="artifacts/qc_replay_5y_behavior_inputs",
        generated_by="market_data_bootstrap_or_daily_market_refresh",
        required_for_paper=True,
        description="Historical/current underlying market data used by regime, asset behavior, and decision rows.",
    ),
    RuntimeSourceMapping(
        runtime_input_name="regime_latest_snapshot",
        runtime_relative_path="data/runtime/regime/regime_latest_snapshot.json",
        seed_source_relative_path="artifacts/qc_replay_5y_historical_regime_date_map",
        generated_by="regime_layer_builder",
        required_for_paper=True,
        description="Latest as-of market regime state.",
    ),
    RuntimeSourceMapping(
        runtime_input_name="asset_behavior_latest_snapshot",
        runtime_relative_path="data/runtime/asset_behavior/asset_behavior_latest_snapshot.json",
        seed_source_relative_path="artifacts/qc_replay_5y_asset_behavior_decision_export_fred_regime_asset_class_mapped",
        generated_by="asset_behavior_layer_builder",
        required_for_paper=True,
        description="Latest asset behavior state by symbol.",
    ),
    RuntimeSourceMapping(
        runtime_input_name="option_behavior_latest_snapshot",
        runtime_relative_path="data/runtime/option_behavior/option_behavior_latest_snapshot.json",
        seed_source_relative_path="artifacts/qc_replay_5y_partitioned_option_behavior_classifier",
        generated_by="option_behavior_layer_builder",
        required_for_paper=True,
        description="Latest option behavior state by symbol/date.",
    ),
    RuntimeSourceMapping(
        runtime_input_name="option_quote_snapshot",
        runtime_relative_path="data/runtime/option_quotes/option_quote_snapshot.jsonl",
        seed_source_relative_path="artifacts/v3_2_1_native_quote_join_v1_20230101_20260531",
        generated_by="option_quote_refresh_or_native_quote_join",
        required_for_paper=True,
        description="Bid/ask/mid/spread quote snapshot used for spread guardrail and broker order pricing.",
    ),
    RuntimeSourceMapping(
        runtime_input_name="closed_trade_outcomes",
        runtime_relative_path="data/runtime/trade_outcomes/closed_trade_outcomes.jsonl",
        seed_source_relative_path="artifacts/v3_2_2_symbol_regime_walkforward_prune_stress_v1_20230101_20260531",
        generated_by="historical_outcome_bootstrap_plus_paper_fill_capture",
        required_for_paper=True,
        description="Closed outcomes used to build prior symbol/regime state.",
    ),
    RuntimeSourceMapping(
        runtime_input_name="v3_2_2_prior_symbol_regime_state",
        runtime_relative_path="data/runtime/rule_state/v3_2_2_prior_symbol_regime_state.json",
        seed_source_relative_path="artifacts/v3_2_2_pre_broker_audit_pack_v1_20230101_20260531",
        generated_by="prior_symbol_regime_state_builder",
        required_for_paper=True,
        description="Prior symbol/regime state consumed by the V3.2.2 weak-prior gate.",
    ),
)
