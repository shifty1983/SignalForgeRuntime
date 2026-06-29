from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeInputContract:
    name: str
    path: str
    required: bool
    max_age_days: int | None
    description: str

    @property
    def relative_path(self) -> str:
        return self.path


RUNTIME_INPUT_CONTRACTS: tuple[RuntimeInputContract, ...] = (
    RuntimeInputContract(
        name="underlying_market_data",
        path="data/runtime/market/underlying_daily.jsonl",
        required=True,
        max_age_days=5,
        description="Current underlying market data used by the runtime decision process.",
    ),
    RuntimeInputContract(
        name="regime_latest_snapshot",
        path="data/runtime/regime/regime_latest_snapshot.json",
        required=True,
        max_age_days=5,
        description="Latest regime snapshot available to the runtime engine.",
    ),
    RuntimeInputContract(
        name="asset_behavior_latest_snapshot",
        path="data/runtime/asset_behavior/asset_behavior_latest_snapshot.json",
        required=True,
        max_age_days=5,
        description="Latest asset behavior snapshot available to the runtime engine.",
    ),
    RuntimeInputContract(
        name="option_behavior_latest_snapshot",
        path="data/runtime/option_behavior/option_behavior_latest_snapshot.json",
        required=True,
        max_age_days=5,
        description="Latest option behavior snapshot available to the runtime engine.",
    ),
    RuntimeInputContract(
        name="option_quote_snapshot",
        path="data/runtime/option_quotes/option_quote_snapshot.jsonl",
        required=True,
        max_age_days=2,
        description="Current option quote snapshot used for spread and execution checks.",
    ),
    RuntimeInputContract(
        name="closed_trade_outcomes",
        path="data/runtime/trade_outcomes/closed_trade_outcomes.jsonl",
        required=True,
        max_age_days=None,
        description="Executed V3.2.2 closed trade outcomes only.",
    ),
    RuntimeInputContract(
        name="v3_2_2_prior_gate_evaluation_outcomes",
        path="data/runtime/rule_state/v3_2_2_prior_gate_evaluation_outcomes.jsonl",
        required=True,
        max_age_days=None,
        description=(
            "Evaluation-history outcomes used by the V3.2.2 prior symbol/regime gate. "
            "Includes executed closed trades plus shadow outcomes for prior-gate skipped rows."
        ),
    ),
    RuntimeInputContract(
        name="v3_2_2_prior_symbol_regime_state",
        path="data/runtime/rule_state/v3_2_2_prior_symbol_regime_state.json",
        required=True,
        max_age_days=None,
        description="Current V3.2.2 prior symbol/regime state generated from evaluation outcomes.",
    ),
)


RUNTIME_INPUT_CONTRACTS_BY_NAME: dict[str, RuntimeInputContract] = {
    contract.name: contract for contract in RUNTIME_INPUT_CONTRACTS
}
