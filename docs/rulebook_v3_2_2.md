# V3.2.2 Rulebook

V3.2.2 is the current locked paper candidate.

Rules:

## Spread Guardrail

Skip trade when:

spread_pct > 0.125

This rule is applied after leg selection because it requires option bid/ask/spread data.

## Prior Symbol/Regime Weak-Prior Gate

Scope:

symbol + regime_state

Use only closed outcomes where:

close_date < current_entry_date

Skip trade when all are true:

- prior closed trade count >= 8
- prior net PnL <= 0
- prior profit factor <= 0.90

This rule is a pre-trade risk gate. It must not feed expectancy or strategy selection directly.
