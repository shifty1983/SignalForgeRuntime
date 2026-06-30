from __future__ import annotations

from signalforge.rulebooks.prior_symbol_regime_state import (
    PriorSymbolRegimeStats,
    passes_prior_symbol_regime_gate,
)
from signalforge.rulebooks.spread_guardrail import passes_spread_guardrail


def passes_v3_2_2_pre_trade_gates(
    *,
    spread_pct: float | None,
    prior_symbol_regime_stats: PriorSymbolRegimeStats | None,
) -> bool:
    if not passes_spread_guardrail(spread_pct):
        return False

    if not passes_prior_symbol_regime_gate(prior_symbol_regime_stats):
        return False

    return True




