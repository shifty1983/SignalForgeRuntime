from __future__ import annotations

SPREAD_GUARDRAIL_MAX = 0.125


def passes_spread_guardrail(spread_pct: float | None) -> bool:
    if spread_pct is None:
        return False
    return float(spread_pct) <= SPREAD_GUARDRAIL_MAX




