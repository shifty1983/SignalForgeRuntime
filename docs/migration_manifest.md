# SignalForge Runtime Migration Manifest

Purpose:

Migrate only the logic required to operate the locked V3.2.2 paper candidate.
The research repo remains the proof archive. The runtime repo remains clean.

## Current Runtime Baseline

- V3.2.2 paper candidate rulebook started
- Golden fixture parity tests present
- External seed bundle preserved outside Git
- Runtime data/source contracts present
- Generated artifacts ignored
- Large historical data not tracked

## Migration Rules

1. Do not copy entire legacy folders.
2. Migrate one layer at a time.
3. Every migrated layer must have a parity or contract test.
4. No generated artifacts are committed.
5. No optimization or failed-candidate research logic enters runtime.
6. Backtest-only scripts do not enter runtime unless converted into reusable modules.

## Migration Queue

### 1. Rulebook

Status: started.

Runtime modules:

- src/signalforge/rulebooks/spread_guardrail.py
- src/signalforge/rulebooks/prior_symbol_regime_state.py
- src/signalforge/rulebooks/v3_2_2.py

Proof:

- spread guardrail tests
- prior symbol/regime tests
- V3.2.2 fixture parity tests

### 2. Closed Outcomes / Prior State

Status: next.

Research sources to inspect:

- artifacts/v3_2_2_symbol_regime_walkforward_prune_stress_v1_20230101_20260531
- artifacts/qc_replay_5y_matrix_enriched_contract_outcomes
- artifacts/historical_decision_rows_20210601_20260531

Runtime outputs:

- data/runtime/trade_outcomes/closed_trade_outcomes.jsonl
- data/runtime/rule_state/v3_2_2_prior_symbol_regime_state.json

Required tests:

- closed outcomes schema test
- prior state calculation test
- V3.2.2 skip-count parity test

### 3. Market Data Loader

Status: migrate after prior-state logic.

Seed sources:

- artifacts/qc_replay_5y_behavior_inputs
- artifacts/qc_replay_5y_market_price_behavior
- data/manual

Runtime output:

- data/runtime/market/underlying_daily.jsonl

### 4. Regime Layer

Status: migrate after market loader.

Seed sources:

- artifacts/qc_replay_5y_historical_regime_date_map

Runtime output:

- data/runtime/regime/regime_latest_snapshot.json

### 5. Asset Behavior Layer

Status: migrate after regime layer.

Seed sources:

- artifacts/qc_replay_5y_asset_behavior_decision_export_fred_regime_asset_class_mapped

Runtime output:

- data/runtime/asset_behavior/asset_behavior_latest_snapshot.json

### 6. Option Behavior Layer

Status: migrate after asset behavior.

Seed sources:

- artifacts/qc_replay_5y_partitioned_option_behavior_classifier
- artifacts/qc_replay_5y_partitioned_option_behavior_source_readiness
- artifacts/qc_replay_5y_option_source_symbol_readiness_consolidation

Runtime output:

- data/runtime/option_behavior/option_behavior_latest_snapshot.json
- data/runtime/option_quotes/option_quote_snapshot.jsonl

### 7. Strategy Selection / Expectancy

Status: migrate later.

Seed sources:

- artifacts/historical_strategy_selection_rows_20210601_20260531
- artifacts/strategy_matrix_edge_inventory_20210601_20260531
- artifacts/strategy_eligibility_native_family_gate_position_sizing_replay_v1_20210601_20260531

Runtime output:

- selected strategy candidate rows

### 8. Portfolio Allocator

Status: migrate later.

Seed sources:

- artifacts/portfolio_value_ranked_allocator_v2_20210601_20260531
- artifacts/portfolio_value_ranked_allocator_v2_canonical_ledgers_20230101_20260531

Runtime output:

- sized trade candidates

### 9. Broker Execution Rehearsal

Status: last.

Runtime output:

- broker-safe paper order tickets
- rejection report
- fill reconciliation report
