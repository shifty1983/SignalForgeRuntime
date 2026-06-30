from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PriorSymbolRegimeStats:
    prior_count: int
    prior_net_pnl: float
    prior_profit_factor: float | None


def passes_prior_symbol_regime_gate(stats: PriorSymbolRegimeStats | None) -> bool:
    if stats is None:
        return True

    if stats.prior_count < 8:
        return True

    profit_factor = stats.prior_profit_factor
    if profit_factor is None:
        profit_factor = 0.0

    if stats.prior_net_pnl <= 0 and profit_factor <= 0.90:
        return False

    return True


