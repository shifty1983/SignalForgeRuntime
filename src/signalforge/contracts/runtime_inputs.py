from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeInputContract:
    name: str
    relative_path: str
    required: bool
    max_age_days: int | None
    description: str


RUNTIME_INPUT_CONTRACTS: tuple[RuntimeInputContract, ...] = (
    RuntimeInputContract(
        name="underlying_market_data",
        relative_path="data/runtime/market/underlying_daily.jsonl",
        required=True,
        max_age_days=5,
        description="Current underlying OHLCV / market behavior input.",
    ),
    RuntimeInputContract(
        name="regime_latest_snapshot",
        relative_path="data/runtime/regime/regime_latest_snapshot.json",
        required=True,
        max_age_days=5,
        description="Latest as-of regime state.",
    ),
    RuntimeInputContract(
        name="asset_behavior_latest_snapshot",
        relative_path="data/runtime/asset_behavior/asset_behavior_latest_snapshot.json",
        required=True,
        max_age_days=5,
        description="Latest asset behavior state per tradable symbol.",
    ),
    RuntimeInputContract(
        name="option_behavior_latest_snapshot",
        relative_path="data/runtime/option_behavior/option_behavior_latest_snapshot.json",
        required=True,
        max_age_days=5,
        description="Latest option behavior classifications.",
    ),
    RuntimeInputContract(
        name="option_quote_snapshot",
        relative_path="data/runtime/option_quotes/option_quote_snapshot.jsonl",
        required=True,
        max_age_days=2,
        description="Latest option bid/ask/mid/spread data used for leg selection and execution guardrails.",
    ),
    RuntimeInputContract(
        name="closed_trade_outcomes",
        relative_path="data/runtime/trade_outcomes/closed_trade_outcomes.jsonl",
        required=True,
        max_age_days=None,
        description="Closed historical/paper/live outcomes used for prior-state calculations.",
    ),
    RuntimeInputContract(
        name="v3_2_2_prior_symbol_regime_state",
        relative_path="data/runtime/rule_state/v3_2_2_prior_symbol_regime_state.json",
        required=True,
        max_age_days=5,
        description="Prior symbol/regime state for the V3.2.2 weak-prior gate.",
    ),
)
