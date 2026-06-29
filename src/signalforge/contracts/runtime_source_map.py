from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeSourceMapping:
    runtime_input_name: str
    runtime_input_path: str
    seed_source_path: str | None
    builder_module: str
    description: str
    required_for_paper: bool = True

    @property
    def seed_source_relative_path(self) -> str | None:
        return self.seed_source_path

    @property
    def runtime_input_relative_path(self) -> str:
        return self.runtime_input_path

    @property
    def runtime_relative_path(self) -> str:
        return self.runtime_input_path

    @property
    def generated_by(self) -> str:
        return self.builder_module


RUNTIME_SOURCE_MAPPINGS: tuple[RuntimeSourceMapping, ...] = (
    RuntimeSourceMapping(
        runtime_input_name="underlying_market_data",
        runtime_input_path="data/runtime/market/underlying_daily.jsonl",
        seed_source_path="artifacts/qc_replay_5y_behavior_inputs",
        builder_module="pending_market_bootstrap",
        description="Market data runtime bootstrap source.",
    ),
    RuntimeSourceMapping(
        runtime_input_name="regime_latest_snapshot",
        runtime_input_path="data/runtime/regime/regime_latest_snapshot.json",
        seed_source_path="artifacts/qc_replay_5y_historical_regime_date_map",
        builder_module="pending_regime_bootstrap",
        description="Regime snapshot runtime bootstrap source.",
    ),
    RuntimeSourceMapping(
        runtime_input_name="asset_behavior_latest_snapshot",
        runtime_input_path="data/runtime/asset_behavior/asset_behavior_latest_snapshot.json",
        seed_source_path="artifacts/qc_replay_5y_asset_behavior_decision_export_fred_regime_asset_class_mapped",
        builder_module="signalforge.runtime.asset_behavior_bootstrap",
        description="Asset behavior runtime bootstrap source.",
    ),
    RuntimeSourceMapping(
        runtime_input_name="option_behavior_latest_snapshot",
        runtime_input_path="data/runtime/option_behavior/option_behavior_latest_snapshot.json",
        seed_source_path="artifacts/qc_replay_5y_partitioned_option_behavior_classifier",
        builder_module="signalforge.runtime.option_behavior_bootstrap",
        description="Option behavior runtime bootstrap source.",
    ),
    RuntimeSourceMapping(
        runtime_input_name="option_quote_snapshot",
        runtime_input_path="data/runtime/option_quotes/option_quote_snapshot.jsonl",
        seed_source_path="artifacts/v3_2_1_native_quote_join_v1_20230101_20260531",
        builder_module="pending_option_quote_bootstrap",
        description="Native quote snapshot source for spread and execution checks.",
    ),
    RuntimeSourceMapping(
        runtime_input_name="closed_trade_outcomes",
        runtime_input_path="data/runtime/trade_outcomes/closed_trade_outcomes.jsonl",
        seed_source_path="artifacts/v3_2_2_symbol_regime_walkforward_prune_stress_v1_20230101_20260531",
        builder_module="signalforge.runtime.closed_outcomes_bootstrap",
        description="Executed V3.2.2 closed trade outcomes only.",
    ),
    RuntimeSourceMapping(
        runtime_input_name="v3_2_2_prior_gate_evaluation_outcomes",
        runtime_input_path="data/runtime/rule_state/v3_2_2_prior_gate_evaluation_outcomes.jsonl",
        seed_source_path="artifacts/v3_2_2_symbol_regime_walkforward_prune_stress_v1_20230101_20260531",
        builder_module="signalforge.runtime.prior_gate_evaluation_outcomes_bootstrap",
        description="Executed outcomes plus shadow skipped outcomes used for prior-gate as-of evaluation.",
    ),
    RuntimeSourceMapping(
        runtime_input_name="v3_2_2_prior_symbol_regime_state",
        runtime_input_path="data/runtime/rule_state/v3_2_2_prior_symbol_regime_state.json",
        seed_source_path="artifacts/v3_2_2_symbol_regime_walkforward_prune_stress_v1_20230101_20260531",
        builder_module="signalforge.runtime.prior_symbol_regime_state_builder",
        description="Generated V3.2.2 prior symbol/regime state from prior-gate evaluation outcomes.",
    ),
)


RUNTIME_SOURCE_MAPPINGS_BY_INPUT: dict[str, RuntimeSourceMapping] = {
    mapping.runtime_input_name: mapping for mapping in RUNTIME_SOURCE_MAPPINGS
}


