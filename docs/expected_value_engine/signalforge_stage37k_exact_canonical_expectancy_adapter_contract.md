# Stage 37K Exact Canonical Expectancy Adapter Contract

- is_ready: True
- blocker_count: 0
- canonical_summary_is_ready: True
- canonical_row_count: 13412
- adapter_target: `src/signalforge/engines/strategy_selection/canonical_expectancy_snapshot_adapter.py`
- engine_consumer: `signalforge.engines.strategy_selection.expected_value_scoring.build_signalforge_expected_value_scoring`
- paper_rule: paper consumes canonical locked walk-forward expectancy snapshot; paper does not recompute walk-forward expectancy
- paper_order_created: False
- live_order_created: False
- live_trade_supported: False

## Contract Rows

| section | field | value | requirement |
|---|---|---|---|
| ownership | source_owner | `data/canonical/signalforge_pipeline/18_walk_forward_expectancy` | canonical snapshot is the active source of truth |
| ownership | producer_owner | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | walk-forward generation remains backtesting-owned |
| ownership | adapter_target | `src/signalforge/engines/strategy_selection/canonical_expectancy_snapshot_adapter.py` | adapter may be promoted only after parity tests |
| ownership | consumer | `signalforge.engines.strategy_selection.expected_value_scoring.build_signalforge_expected_value_scoring` | engine consumes adapted items as review/handoff scoring, not direct execution |
| paper_rule | locked_expectancy | `paper consumes canonical locked walk-forward expectancy snapshot; paper does not recompute walk-forward expectancy` | no expectancy recomputation inside paper decision loop |
| safety | lookahead_guard | `uses_current_row_outcome=False and uses_future_rows=False` | required for every row consumed by paper snapshot adapter |
| safety | manual_review_state | `expected_value_scoring output may remain is_ready=False with requires_manual_approval=True` | EV scoring does not authorize trades by itself |
| legacy | legacy_expected_value_domain | `research_candidate_only` | legacy EV logic cannot be promoted without A/B backtest proof |

## Validation

```json
{
  "required_source_fields": [
    "symbol",
    "decision_date",
    "expectancy_state",
    "expectancy_sample_count",
    "expectancy_minimum_sample_count",
    "uses_current_row_outcome",
    "uses_future_rows",
    "training_window_end"
  ],
  "missing_field_counts": {},
  "no_lookahead_violation_count": 0,
  "empty_strategy_count": 0,
  "empty_symbol_count": 0,
  "coverage_status_counts": {
    "missing_expectancy": 132,
    "sample_limited": 165,
    "covered": 13115
  },
  "expected_value_state_counts": {
    "data_review": 132,
    "sample_limited": 165,
    "positive_expectancy_candidate": 9405,
    "non_positive_expectancy": 3710
  },
  "handoff_status_counts": {
    "data_review": 132,
    "review": 165,
    "candidate": 9405,
    "blocked": 3710
  },
  "reason_counts": {
    "missing_or_no_prior_expectancy_sample": 132,
    "sample_limited_expectancy": 165,
    "positive_expectancy_evidence": 9405,
    "non_positive_expectancy": 3710
  },
  "top_strategy_counts": {
    "long_put": 2859,
    "long_call": 2717,
    "bear_put_debit_spread": 2127,
    "bull_call_debit_spread": 1647,
    "calendar_spread": 1377,
    "iron_butterfly": 1117,
    "diagonal_spread": 817,
    "put_credit_spread": 339,
    "iron_condor": 273,
    "call_credit_spread": 139
  },
  "expectancy_scope_counts": {
    "symbol_strategy_regime_asset_option": 2998,
    "strategy_regime_asset_option": 6321,
    "strategy_global": 3565,
    "strategy_regime_asset": 289,
    "symbol_strategy_regime_asset": 239
  }
}
```

## Warnings

- stage37k_is_contract_only_no_production_logic_moved
- expected_value_scoring_is_review_handoff_not_trade_authorization
- legacy_expected_value_domain_remains_research_only_until_ab_backtested
- data_canonical_runtime_files_should_not_be_force_added_to_git