# SignalForge Options Execution Map + Adjustment Overlay Implementation Plan

## Purpose

Build a new execution layer between the v1.3 expectancy-driven strategy selector and the raw-leg / portfolio replay layers.

The goal is to turn:

```text
symbol/date/strategy selected by expectancy
```

into:

```text
constructible trade plan with selected legs, entry rules, skip rules, sizing modifiers, defense rules, and exit policy
```

This keeps the core strategy-selection logic general while allowing symbol/date-specific execution behavior through measured metrics rather than hard-coded symbol opinions.

---

## Target Architecture

```text
v1.3 selected strategy candidates
        ↓
base_strategy_execution_map
        ↓
symbol/date execution metrics
        ↓
metric-driven adjustment overlay
        ↓
resolved strategy execution rules
        ↓
contract construction / leg selection
        ↓
quote / liquidity / Greek gate
        ↓
daily action ticket or historical replay row
```

---

## Design Principle

The execution layer should not replace expectancy.

Expectancy answers:

```text
Should this strategy be considered for this symbol/date/setup?
```

The execution map answers:

```text
Can this strategy be expressed as a valid, executable options trade?
```

The raw-leg / v2 option data answers:

```text
Which exact contracts, prices, spreads, Greeks, and liquidity conditions make the trade actionable or untradable?
```

---

## Implementation Tracking Board

| Phase | Name | Status | Owner | Output Artifact | Readiness Gate |
|---|---|---:|---|---|---|
| 1 | Base strategy execution map | Not Started |  | `options_execution_base_map_v1` | Base map validates |
| 2 | Symbol/date execution metrics | Not Started |  | `options_execution_symbol_metrics` | Metrics generated with coverage |
| 3 | Metric-driven adjustment rules | Not Started |  | `execution_adjustment_rules_v1` | Rules validate |
| 4 | Resolved execution rule builder | Not Started |  | `resolved_strategy_execution_rules` | One resolved row per selected candidate |
| 5 | Contract construction | Not Started |  | `options_contract_construction` | Constructed/skipped rows emitted |
| 6 | Daily action plan builder | Not Started |  | `daily_action_plan_<DATE>` | Open/hold/defend/skip actions emitted |
| 7 | Historical replay integration | Not Started |  | `options_execution_replay` | Execution-adjusted selected sequence ready |

Status values:

```text
Not Started
In Progress
Blocked
Ready
Validated
Committed
```

---

# Phase 1 — Base Strategy Execution Map

## Objective

Create a static rulebook defining valid execution parameters for each supported options strategy.

This is the default rule layer before any symbol/date adjustments are applied.

## Proposed Config Path

```text
configs/options_execution/base_strategy_execution_map_v1.json
```

## Initial Supported Strategies

Start with strategies currently active in v1.3:

- [ ] `long_call`
- [ ] `long_put`
- [ ] `call_debit_spread`
- [ ] `put_debit_spread`
- [ ] `put_credit_spread`
- [ ] `call_credit_spread`
- [ ] `iron_condor`

Later expansion candidates:

- [ ] `calendar`
- [ ] `diagonal`
- [ ] `straddle`
- [ ] `strangle`
- [ ] `covered_call`
- [ ] `cash_secured_put`

## Required Fields Per Strategy

Each strategy map should define:

- [ ] Strategy identity
- [ ] Directional bias
- [ ] DTE range
- [ ] Delta / Greek targets
- [ ] Strike / spread-width logic
- [ ] Debit or credit requirements
- [ ] Liquidity requirements
- [ ] Quote quality requirements
- [ ] Entry price rule
- [ ] Risk limits
- [ ] Position sizing defaults
- [ ] Profit-taking rules
- [ ] Loss-stop rules
- [ ] DTE exit rules
- [ ] Defense / maintenance triggers
- [ ] Skip conditions
- [ ] Missing-Greek policy

## Example Base Strategy Map Entry

```json
{
  "strategy": "put_credit_spread",
  "version": "v1",
  "directional_bias": "bullish_to_neutral",
  "entry": {
    "dte_min": 21,
    "dte_max": 60,
    "short_delta_min": 0.15,
    "short_delta_max": 0.35,
    "long_delta_max": 0.15,
    "spread_width_min": 1,
    "spread_width_max": 10,
    "minimum_credit_pct_of_width": 0.25
  },
  "liquidity": {
    "require_bid_ask": true,
    "max_bid_ask_spread_pct": 0.15,
    "min_open_interest": 100,
    "min_volume": 10
  },
  "greeks": {
    "required_for_entry": true,
    "missing_greeks_policy": "reject_contract_or_use_proxy_backtest_only"
  },
  "risk": {
    "max_risk_per_trade_pct": 0.01,
    "position_size_multiplier": 1.0
  },
  "entry_price": {
    "rule": "limit_at_mid_or_better",
    "slippage_buffer_pct": 0.02
  },
  "exit": {
    "profit_take_pct_of_credit": 0.50,
    "loss_stop_multiple_of_credit": 2.0,
    "dte_exit": 7
  },
  "defense": {
    "short_leg_delta_warning": 0.40,
    "short_leg_delta_defense": 0.50,
    "allowed_actions": ["close", "roll_out", "reduce_size"]
  },
  "skip_conditions": [
    "missing_quote",
    "spread_too_wide",
    "credit_too_small",
    "missing_required_greeks",
    "portfolio_risk_cap_exceeded"
  ]
}
```

## Code Deliverables

- [ ] `src/options_execution/base_strategy_execution_map.py`
- [ ] `src/options_execution/base_strategy_execution_map_cli.py`

## Output Artifact

```text
artifacts/options_execution_base_map_v1/
  signalforge_options_execution_base_map_summary.json
```

## Readiness Gate

- [ ] `is_ready = true`
- [ ] All configured strategies parse
- [ ] Required fields exist for each strategy
- [ ] No unknown strategy names
- [ ] No invalid numeric ranges
- [ ] No missing entry / liquidity / risk / exit / defense blocks

---

# Phase 2 — Symbol/Date Execution Metrics

## Objective

Build symbol/date execution metrics from the full option behavior v2 universe.

These metrics drive adjustment rules without hard-coding symbol-specific behavior.

## Input

```text
artifacts/qc_option_behavior_v2_full_decoded/signalforge_qc_option_behavior_v2_final_rows.jsonl
```

## Output

```text
artifacts/options_execution_symbol_metrics_20210601_20260531/
  signalforge_options_execution_symbol_metrics.jsonl
  signalforge_options_execution_symbol_metrics_summary.json
```

## Metric Categories

### Quote Metrics

- [ ] `quote_seen_rate`
- [ ] `bid_ask_complete_rate`
- [ ] `median_spread_pct`
- [ ] `p75_spread_pct`
- [ ] `p90_spread_pct`
- [ ] `quote_quality_state_counts`

### Liquidity Metrics

- [ ] `volume_seen_rate`
- [ ] `open_interest_seen_rate`
- [ ] `median_volume`
- [ ] `median_open_interest`
- [ ] `chain_contract_count`
- [ ] `expiration_count`

### Greek Metrics

- [ ] `greeks_seen_rate`
- [ ] `delta_seen_rate`
- [ ] `median_abs_delta`
- [ ] `delta_bucket_coverage`

### Symbol Behavior Metrics

- [ ] `realized_vol_percentile`
- [ ] `gap_risk_score`
- [ ] `trend_state`
- [ ] `mean_reversion_state`

### Execution Quality Metrics

- [ ] `execution_quality_score`
- [ ] `fill_risk_score`
- [ ] `liquidity_tier`

## Initial Liquidity Tiers

- [ ] `ultra_liquid`
- [ ] `liquid`
- [ ] `normal`
- [ ] `thin`
- [ ] `untradable`

## Code Deliverables

- [ ] `src/options_execution/symbol_execution_metrics.py`
- [ ] `src/options_execution/symbol_execution_metrics_cli.py`

## Readiness Gate

- [ ] Input rows exist
- [ ] Symbol count > 0
- [ ] Date count > 0
- [ ] Spread-pct coverage measured
- [ ] Quote quality coverage measured
- [ ] Greek coverage measured
- [ ] Liquidity tier assigned
- [ ] Summary includes metric coverage rates

---

# Phase 3 — Metric-Driven Adjustment Rules

## Objective

Create a general adjustment overlay based on measured symbol/date metrics.

This file should be general, not symbol-specific.

## Proposed Config Path

```text
configs/options_execution/execution_adjustment_rules_v1.json
```

## Example Adjustment Rules

```json
{
  "adjustment_rules": [
    {
      "rule_id": "wide_spread_tighten_execution",
      "enabled": true,
      "applies_to": {
        "strategies": [
          "put_credit_spread",
          "call_credit_spread",
          "call_debit_spread",
          "put_debit_spread"
        ],
        "metric": "rolling_median_spread_pct",
        "operator": ">",
        "value": 0.12
      },
      "adjustments": {
        "max_bid_ask_spread_pct_multiplier": 0.75,
        "min_open_interest_multiplier": 1.5,
        "position_size_multiplier": 0.5,
        "entry_price_rule": "conservative_limit_only"
      }
    },
    {
      "rule_id": "high_realized_vol_reduce_short_delta",
      "enabled": true,
      "applies_to": {
        "strategies": ["put_credit_spread", "call_credit_spread", "iron_condor"],
        "metric": "realized_vol_percentile_60d",
        "operator": ">=",
        "value": 0.80
      },
      "adjustments": {
        "short_delta_max": 0.25,
        "minimum_credit_pct_of_width": 0.30,
        "position_size_multiplier": 0.5
      }
    },
    {
      "rule_id": "poor_greek_coverage_reject_greek_dependent_strategies",
      "enabled": true,
      "applies_to": {
        "strategies": ["iron_condor", "strangle", "calendar", "diagonal"],
        "metric": "greeks_seen_rate",
        "operator": "<",
        "value": 0.70
      },
      "adjustments": {
        "allow_strategy": false,
        "skip_reason": "insufficient_greek_coverage"
      }
    }
  ]
}
```

## Adjustment Rule Types

- [ ] Tighten spread threshold
- [ ] Increase minimum open interest
- [ ] Increase minimum volume
- [ ] Reduce position size
- [ ] Tighten short-delta target
- [ ] Increase minimum credit requirement
- [ ] Switch to conservative limit pricing
- [ ] Reject Greek-dependent strategies when Greek coverage is poor
- [ ] Reject strategies in untradable liquidity tiers
- [ ] Reduce short-premium exposure under high realized volatility
- [ ] Reduce risk near earnings / event windows if event data is available

## Code Deliverables

- [ ] `src/options_execution/execution_adjustment_rules.py`
- [ ] `src/options_execution/execution_adjustment_rules_cli.py`

## Readiness Gate

- [ ] All rule IDs unique
- [ ] All referenced metrics exist
- [ ] All operators valid
- [ ] All adjustment keys valid
- [ ] All strategy references valid
- [ ] No rule creates impossible numeric ranges
- [ ] Disabled rules are ignored but still parsed

---

# Phase 4 — Resolved Strategy Execution Rule Builder

## Objective

Resolve base strategy rules plus metric-driven adjustments into a final symbol/date/strategy execution rule.

This is the core artifact that bridges v1.3 selection to contract construction.

## Inputs

```text
configs/options_execution/base_strategy_execution_map_v1.json
configs/options_execution/execution_adjustment_rules_v1.json
artifacts/options_execution_symbol_metrics_20210601_20260531/signalforge_options_execution_symbol_metrics.jsonl
v1.3 selected strategy rows
```

## Output

```text
artifacts/resolved_strategy_execution_rules_20210601_20260531/
  signalforge_resolved_strategy_execution_rules.jsonl
  signalforge_resolved_strategy_execution_rules_summary.json
```

## Example Resolved Row

```json
{
  "adapter_type": "resolved_strategy_execution_rule_builder",
  "artifact_type": "signalforge_resolved_strategy_execution_rule",
  "symbol": "AAPL",
  "asof_date": "2024-03-15",
  "strategy": "put_credit_spread",
  "base_map_id": "put_credit_spread_v1",
  "metrics_snapshot": {
    "rolling_median_spread_pct": 0.08,
    "greeks_seen_rate": 0.92,
    "liquidity_tier": "liquid",
    "realized_vol_percentile_60d": 0.74
  },
  "applied_adjustments": [
    "normal_liquidity_base_size"
  ],
  "resolved_execution": {
    "dte_min": 21,
    "dte_max": 60,
    "short_delta_min": 0.15,
    "short_delta_max": 0.35,
    "minimum_credit_pct_of_width": 0.25,
    "max_bid_ask_spread_pct": 0.15,
    "position_size_multiplier": 1.0,
    "entry_price_rule": "limit_at_mid_or_better"
  },
  "constructibility_precheck_state": "candidate_constructible",
  "skip_reasons": []
}
```

## Code Deliverables

- [ ] `src/options_execution/resolved_strategy_execution_rules.py`
- [ ] `src/options_execution/resolved_strategy_execution_rules_cli.py`

## Readiness Gate

- [ ] One resolved rule per selected strategy candidate
- [ ] Base map found for every selected strategy
- [ ] Metrics snapshot joined
- [ ] Adjustment rules evaluated deterministically
- [ ] Applied adjustments listed
- [ ] Resolved numeric ranges valid
- [ ] Skip reasons emitted when blocked
- [ ] Summary includes constructible / skipped counts

---

# Phase 5 — Contract Construction

## Objective

Use resolved strategy execution rules and option behavior v2 rows to select actual option legs.

This is where strategy-level expectancy becomes an actionable options structure.

## Inputs

```text
artifacts/resolved_strategy_execution_rules_20210601_20260531/signalforge_resolved_strategy_execution_rules.jsonl
artifacts/qc_option_behavior_v2_full_decoded/signalforge_qc_option_behavior_v2_final_rows.jsonl
v1.3 selected strategy rows
```

## Output

```text
artifacts/options_contract_construction_20210601_20260531/
  signalforge_options_contract_construction_rows.jsonl
  signalforge_options_contract_construction_summary.json
```

## Contract Construction Examples

### Long Call

- [ ] Choose call within DTE range
- [ ] Match target delta range
- [ ] Require quote quality pass
- [ ] Rank by spread_pct, liquidity, delta fit, and DTE fit

### Long Put

- [ ] Choose put within DTE range
- [ ] Match target delta range
- [ ] Require quote quality pass
- [ ] Rank by spread_pct, liquidity, delta fit, and DTE fit

### Call Debit Spread

- [ ] Choose long call by higher target delta
- [ ] Choose short call by lower target delta or width rule
- [ ] Require same expiration
- [ ] Require max debit pct of width
- [ ] Require both legs pass quote/liquidity gate

### Put Debit Spread

- [ ] Choose long put by higher absolute target delta
- [ ] Choose short put by lower absolute target delta or width rule
- [ ] Require same expiration
- [ ] Require max debit pct of width
- [ ] Require both legs pass quote/liquidity gate

### Put Credit Spread

- [ ] Choose short put by target delta
- [ ] Choose long put below short strike by width rule
- [ ] Require same expiration
- [ ] Require minimum credit pct of width
- [ ] Require both legs pass quote/liquidity gate

### Call Credit Spread

- [ ] Choose short call by target delta
- [ ] Choose long call above short strike by width rule
- [ ] Require same expiration
- [ ] Require minimum credit pct of width
- [ ] Require both legs pass quote/liquidity gate

### Iron Condor

- [ ] Choose short put and short call by target delta
- [ ] Choose protective wings by width rule
- [ ] Require same expiration
- [ ] Enforce balanced risk / credit rules
- [ ] Require all legs pass quote/liquidity gate

## Example Construction Row

```json
{
  "symbol": "AAPL",
  "asof_date": "2024-03-15",
  "strategy": "put_credit_spread",
  "construction_state": "constructed",
  "selected_legs": [
    {
      "leg_role": "short_put",
      "option_symbol": "...",
      "expiration": "2024-04-19",
      "strike": 170,
      "delta": -0.28,
      "bid": 2.10,
      "ask": 2.25,
      "mid": 2.175
    },
    {
      "leg_role": "long_put",
      "option_symbol": "...",
      "expiration": "2024-04-19",
      "strike": 165,
      "delta": -0.14,
      "bid": 1.05,
      "ask": 1.15,
      "mid": 1.10
    }
  ],
  "estimated_credit": 1.075,
  "spread_width": 5,
  "credit_pct_of_width": 0.215,
  "entry_price_rule": "limit_at_mid_or_better",
  "skip_reasons": []
}
```

## Code Deliverables

- [ ] `src/options_execution/contract_construction.py`
- [ ] `src/options_execution/contract_construction_cli.py`

## Readiness Gate

- [ ] Constructed count > 0
- [ ] Not-constructed count reported
- [ ] Skip reason counts reported
- [ ] Quote quality pass rate reported
- [ ] Greek coverage pass rate reported
- [ ] Strategy construction coverage by strategy reported
- [ ] No constructed trade violates resolved execution map

---

# Phase 6 — Daily Action Plan Builder

## Objective

Create the production-facing daily decision artifact.

This turns constructed trades and existing positions into next-day action tickets.

## Inputs

```text
constructed trades
portfolio state
existing positions
resolved execution rules
```

## Output

```text
artifacts/daily_action_plan_<DATE>/
  signalforge_daily_action_plan.json
  signalforge_daily_action_plan_orders.csv
  signalforge_daily_action_plan_summary.json
```

## Daily Action Types

- [ ] `open`
- [ ] `hold`
- [ ] `close`
- [ ] `defend`
- [ ] `roll`
- [ ] `reduce_size`
- [ ] `skip`

## Example Daily Action Row

```json
{
  "action_type": "open",
  "generated_asof_date": "2026-07-03",
  "intended_action_date": "2026-07-06",
  "symbol": "AAPL",
  "strategy": "put_credit_spread",
  "decision": "open_candidate",
  "selected_legs": [],
  "entry_order": {
    "order_type": "limit",
    "limit_price_rule": "mid_or_better_with_slippage_buffer",
    "time_in_force": "day"
  },
  "risk": {
    "max_loss": 500,
    "position_size_multiplier": 0.5
  },
  "skip_conditions": [
    "do_not_enter_if_spread_pct_above_0.10",
    "do_not_enter_if_quote_missing",
    "do_not_enter_if_credit_below_minimum"
  ],
  "applied_adjustments": [
    "wide_spread_tighten_execution"
  ]
}
```

## Code Deliverables

- [ ] `src/options_execution/daily_action_plan.py`
- [ ] `src/options_execution/daily_action_plan_cli.py`

## Readiness Gate

- [ ] Action plan generated for target date
- [ ] Open candidates listed
- [ ] Existing-position actions listed
- [ ] Skip candidates listed with reasons
- [ ] Orders CSV produced
- [ ] Summary counts by action type produced

---

# Phase 7 — Historical Replay Integration

## Objective

Integrate the execution map, adjustments, and construction layer into the historical backtest.

This measures how much expectancy-driven edge survives realistic execution rules.

## New Historical Flow

```text
historical decision rows
→ strategy eligibility
→ expectancy-driven v1.3 selector
→ resolved execution rules
→ contract construction
→ execution replay
→ defense / maintenance replay
→ portfolio construction
→ equity reconstruction
```

## Comparative Backtest Tracks

Track A:

```text
v1.3 original selected trade sequence
```

Track B:

```text
v1.3 + execution map + contract construction + realistic execution
```

Track C, optional diagnostic:

```text
pure raw-leg discovery / raw-leg challenger
```

## Output Artifacts

```text
artifacts/options_execution_replay_20210601_20260531/
artifacts/options_defense_maintenance_replay_20210601_20260531/
artifacts/options_execution_adjusted_selected_trade_sequence_20210601_20260531/
```

## Comparison Metrics

- [ ] Selected candidate count
- [ ] Constructible count
- [ ] Skipped count
- [ ] Skip reason counts
- [ ] Average spread_pct
- [ ] Estimated slippage
- [ ] Win rate
- [ ] Average return
- [ ] Median return
- [ ] Drawdown
- [ ] Tail loss
- [ ] Profit factor
- [ ] Sharpe, if daily equity is reconstructed
- [ ] Sortino, if daily equity is reconstructed

## Readiness Gate

- [ ] Execution-adjusted selected trade sequence generated
- [ ] Portfolio reconstruction completes
- [ ] Metrics report generated
- [ ] Comparison versus original v1.3 generated
- [ ] Slippage / spread / skip impacts summarized

---

# Recommended Build Order

Build in this order:

1. [ ] Base strategy execution map validator
2. [ ] Symbol/date execution metrics builder
3. [ ] Adjustment rule validator
4. [ ] Resolver
5. [ ] Contract construction
6. [ ] Daily action plan builder
7. [ ] Historical replay integration

Do not start with contract construction. Start with the map and resolver first.

---

# First Implementation Target

The first implementation should only support strategies currently active in v1.3.

Initial target:

- [ ] `long_call`
- [ ] `long_put`
- [ ] `call_debit_spread`
- [ ] `put_debit_spread`
- [ ] `put_credit_spread`
- [ ] `call_credit_spread`
- [ ] `iron_condor`

A strategy should not enter production until it has:

- [ ] Base execution map
- [ ] Adjustment rule coverage
- [ ] Contract construction logic
- [ ] Quote/liquidity gate
- [ ] Greek policy
- [ ] Entry price rule
- [ ] Exit rule
- [ ] Defense rule
- [ ] Readiness tests

---

# Key Design Constraints

## Avoid Symbol-Specific Overfitting

Do not create hard-coded custom execution maps for every symbol.

Preferred:

```text
If symbol metrics show wide spreads, reduce size or tighten liquidity rules.
```

Avoid:

```text
AAPL always uses these custom parameters because it improved the backtest.
```

## Use Symbol-Specific Overrides Sparingly

Allowed only when:

- [ ] Symbol has persistent structural behavior
- [ ] Override is explainable
- [ ] Override is stable across windows
- [ ] Override is documented
- [ ] Override improves robustness, not just headline return

## Always Store Resolution Provenance

Every resolved execution row should show:

- [ ] Base strategy map used
- [ ] Metrics snapshot used
- [ ] Adjustment rules triggered
- [ ] Final resolved parameters
- [ ] Skip reasons, if any
- [ ] Construction result
- [ ] Selected legs, if constructed

---

# Success Criteria

This layer is successful when every v1.3 selected strategy candidate can be traced through the execution system:

```text
selected by expectancy
→ base execution map found
→ symbol/date metrics joined
→ adjustment rules evaluated
→ final resolved execution rule produced
→ trade constructed or skipped with clear reason
```

The system should answer:

- [ ] Why did we trade this?
- [ ] Why did we skip this?
- [ ] Why was size reduced?
- [ ] Why was delta tightened?
- [ ] Why was spread threshold changed?
- [ ] Which metrics triggered the adjustment?
- [ ] Which legs were selected?
- [ ] Which rule would trigger defense or exit?

---

# Open Questions

## Strategy Coverage

- [ ] Which strategies are currently active in v1.3 and must be included in v1?
- [ ] Are any legacy strategies no longer used and safe to exclude?

## Greek Policy

- [ ] Should Greek-dependent strategies reject missing Greeks outright?
- [ ] Should backtests allow moneyness proxy fallback when Greeks are missing?
- [ ] Should daily production reject all missing-Greek contracts?

## Execution Timing

- [ ] Should historical replay use same-day entry or next-day entry?
- [ ] Should daily action tickets always assume T+1 execution?

## Event Risk

- [ ] Do we have earnings/event data available?
- [ ] Should single-name strategies be blocked through earnings?
- [ ] Should ETFs be exempt from single-name event filters?

## Portfolio Greeks

- [ ] Should net delta limits be enforced in v1?
- [ ] Should vega/gamma exposure be portfolio-level constraints in v1?
- [ ] Should position sizing be adjusted by marginal Greek contribution?

## Fill Modeling

- [ ] Should entry default to mid?
- [ ] Should entry use mid plus slippage buffer?
- [ ] Should wide-spread names require conservative limit-only pricing?
- [ ] Should fill quality be learned by symbol/strategy over time?

---

# Milestone Definition

## Milestone 1 — Rulebook Ready

- [ ] Base strategy execution map created
- [ ] Base map validator passes
- [ ] Strategy coverage confirmed

## Milestone 2 — Metrics Ready

- [ ] Full option behavior v2 rows decoded
- [ ] Symbol/date metrics generated
- [ ] Liquidity tiers assigned
- [ ] Greek coverage measured

## Milestone 3 — Adjustment Overlay Ready

- [ ] Adjustment rules created
- [ ] Adjustment validator passes
- [ ] Rule coverage documented

## Milestone 4 — Resolver Ready

- [ ] Resolved execution rows generated
- [ ] Applied adjustments auditable
- [ ] Skip reasons emitted

## Milestone 5 — Construction Ready

- [ ] Selected legs emitted
- [ ] Constructible / skipped counts valid
- [ ] No construction violates resolved execution map

## Milestone 6 — Daily Action Ready

- [ ] Daily action plan JSON produced
- [ ] Daily action orders CSV produced
- [ ] Open / hold / defend / skip actions supported

## Milestone 7 — Historical Replay Ready

- [ ] Execution-adjusted sequence generated
- [ ] Portfolio reconstruction completes
- [ ] Comparison versus original v1.3 produced

---

# Final Target State

The system should operate as a daily options decision engine:

```text
Update data after market close
→ run regime / behavior / option behavior / expectancy
→ select strategy candidates
→ resolve execution rules
→ construct valid option trades
→ generate next-day action plan
→ reconcile fills
→ update metrics
→ repeat
```

The execution map and adjustment overlay are the bridge between research edge and actionable trading discipline.
