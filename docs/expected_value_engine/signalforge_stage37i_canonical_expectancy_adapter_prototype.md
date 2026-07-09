# Stage 37I Canonical Expectancy Adapter Prototype

- is_ready: True
- blocker_count: 0
- canonical_summary_is_ready: True
- canonical_total_row_count: 13412
- adapter_item_count: 500
- smoke_row_count: 12
- ready_smoke_count: 0
- acceptable_smoke_count: 12
- paper_order_created: False
- live_order_created: False
- live_trade_supported: False

## Adapter Contract

```json
{
  "adapter_name": "canonical_walk_forward_expectancy_snapshot_adapter",
  "source_owner": "data/canonical/signalforge_pipeline/18_walk_forward_expectancy",
  "source_rows_path": "data\\canonical\\signalforge_pipeline\\18_walk_forward_expectancy\\signalforge_walk_forward_expectancy_rows.jsonl",
  "source_summary_path": "data\\canonical\\signalforge_pipeline\\18_walk_forward_expectancy\\signalforge_walk_forward_expectancy_summary.json",
  "producer_owner": "src/signalforge/backtesting/walk_forward_expectancy_builder.py",
  "consumer_candidate": "signalforge.engines.strategy_selection.expected_value_scoring.build_signalforge_expected_value_scoring",
  "adapter_output_shape": "sequence_of_engine_expected_value_scoring_items",
  "paper_rule": "paper consumes locked canonical expectancy snapshot and does not recompute walk-forward expectancy",
  "required_source_fields": [
    "symbol",
    "strategy_name or strategy",
    "decision_date or date",
    "expectancy_state",
    "expectancy_sample_count",
    "expectancy_minimum_sample_count",
    "expectancy_average_return",
    "expectancy_win_rate",
    "uses_current_row_outcome",
    "uses_future_rows",
    "training_window_end"
  ],
  "required_output_fields": [
    "symbol",
    "strategy_family",
    "strategy_name",
    "decision_date",
    "coverage_status",
    "expected_value_state",
    "favored_families",
    "allowed_families",
    "blocked_families",
    "constraint_flags",
    "blocked_reasons"
  ]
}
```

## Adapter Item Distribution

```json
{
  "coverage_status_counts": {
    "missing_expectancy": 132,
    "sample_limited": 92,
    "covered": 276
  },
  "expected_value_state_counts": {
    "data_review": 132,
    "sample_limited": 92,
    "positive_expectancy_candidate": 80,
    "non_positive_expectancy": 196
  },
  "handoff_status_counts": {
    "data_review": 132,
    "review": 92,
    "candidate": 80,
    "blocked": 196
  },
  "top_strategy_counts": {
    "long_call": 113,
    "long_put": 103,
    "bear_put_debit_spread": 79,
    "bull_call_debit_spread": 67,
    "calendar_spread": 50,
    "diagonal_spread": 38,
    "iron_butterfly": 32,
    "put_credit_spread": 12,
    "iron_condor": 5,
    "call_credit_spread": 1
  }
}
```

## Engine Module Constants

```json
{
  "ELIGIBILITY_ITEM_KEYS": [
    "strategy_family_eligibility_items",
    "eligibility_items",
    "items",
    "data",
    "rows"
  ],
  "EXPECTED_VALUE_SCORING_SCHEMA_VERSION": "signalforge_expected_value_scoring.v1",
  "FAMILY_ORDER": [
    "defined_risk_short_premium",
    "credit_spread",
    "debit_spread",
    "directional_long_premium",
    "long_gamma",
    "protective_put_spread",
    "defined_risk_neutral",
    "defined_risk_only",
    "wait_for_clearer_options_edge",
    "manual_review_only"
  ],
  "NON_EV_FAMILIES": "{'short_premium_without_hedge', 'manual_review_only', 'long_unhedged_premium', 'naked_short_premium'}",
  "COVERED_CAPABILITIES": [
    "expected_value_scoring",
    "risk_adjusted_expected_value_scoring",
    "strategy_family_candidate_scoring",
    "ev_handoff_review_not_trade_selection"
  ],
  "DEPENDS_ON_CAPABILITIES": [
    "strategy_family_eligibility"
  ]
}
```

## Engine Smoke Rows

| variant | source items | ok | ready | blockers | warnings | count fields | summary | error |
|---|---:|---:|---:|---|---|---|---|---|
| items_list | 500 | True | False | None | None | {} | None | None |
| items_key | 500 | True | False | None | None | {} | None | None |
| rows_key | None | True | False | None | None | {} | None | None |
| eligibility_items_key | None | True | False | None | None | {} | None | None |
| expected_value_items_key | None | True | False | None | None | {} | None | None |
| strategy_selection_items_key | None | True | False | None | None | {} | None | None |
| artifact_wrapped_items | 500 | True | False | None | None | {} | None | None |
| module_declared_key_strategy_family_eligibility_items | None | True | False | None | None | {} | None | None |
| module_declared_key_eligibility_items | None | True | False | None | None | {} | None | None |
| module_declared_key_items | 500 | True | False | None | None | {} | None | None |
| module_declared_key_data | None | True | False | None | None | {} | None | None |
| module_declared_key_rows | None | True | False | None | None | {} | None | None |

## Adapter Sample Rows

```json
[
  {
    "symbol": "DIA",
    "underlying_symbol": "DIA",
    "strategy_family": "bear_put_debit_spread",
    "strategy_name": "bear_put_debit_spread",
    "candidate_strategy": "bear_put_debit_spread",
    "candidate_id": "2021-06-07_DIA_bear_put_debit_spread_10d",
    "strategy_candidate_id": "2021-06-07_DIA_bear_put_debit_spread_10d",
    "decision_date": "2021-06-07",
    "date": "2021-06-07",
    "coverage_status": "missing_expectancy",
    "expected_value_state": "data_review",
    "expected_value_handoff_status": "data_review",
    "handoff_status": "data_review",
    "favored_families": [],
    "allowed_families": [],
    "blocked_families": [],
    "risk_flags": [],
    "constraint_flags": [
      "missing_expectancy"
    ],
    "blocked_reasons": [
      "missing_or_no_prior_expectancy_sample"
    ],
    "premium_bias": "long_premium_bias",
    "expectancy_state": "no_prior_sample",
    "expectancy_scope": "symbol_strategy_regime_asset_option",
    "expectancy_sample_count": 0,
    "expectancy_minimum_sample_count": 20,
    "expectancy_average_return": null,
    "expectancy_median_return": null,
    "expectancy_win_rate": null,
    "is_sample_limited": false,
    "uses_current_row_outcome": false,
    "uses_future_rows": false,
    "training_window_start": null,
    "training_window_end": "2021-06-06",
    "source_expectancy_contract": "walk_forward_expectancy",
    "source_expectancy_artifact": "data/canonical/signalforge_pipeline/18_walk_forward_expectancy"
  },
  {
    "symbol": "DIA",
    "underlying_symbol": "DIA",
    "strategy_family": "bull_call_debit_spread",
    "strategy_name": "bull_call_debit_spread",
    "candidate_strategy": "bull_call_debit_spread",
    "candidate_id": "2021-06-07_DIA_bull_call_debit_spread_10d",
    "strategy_candidate_id": "2021-06-07_DIA_bull_call_debit_spread_10d",
    "decision_date": "2021-06-07",
    "date": "2021-06-07",
    "coverage_status": "missing_expectancy",
    "expected_value_state": "data_review",
    "expected_value_handoff_status": "data_review",
    "handoff_status": "data_review",
    "favored_families": [],
    "allowed_families": [],
    "blocked_families": [],
    "risk_flags": [],
    "constraint_flags": [
      "missing_expectancy"
    ],
    "blocked_reasons": [
      "missing_or_no_prior_expectancy_sample"
    ],
    "premium_bias": "long_premium_bias",
    "expectancy_state": "no_prior_sample",
    "expectancy_scope": "symbol_strategy_regime_asset_option",
    "expectancy_sample_count": 0,
    "expectancy_minimum_sample_count": 20,
    "expectancy_average_return": null,
    "expectancy_median_return": null,
    "expectancy_win_rate": null,
    "is_sample_limited": false,
    "uses_current_row_outcome": false,
    "uses_future_rows": false,
    "training_window_start": null,
    "training_window_end": "2021-06-06",
    "source_expectancy_contract": "walk_forward_expectancy",
    "source_expectancy_artifact": "data/canonical/signalforge_pipeline/18_walk_forward_expectancy"
  },
  {
    "symbol": "DIA",
    "underlying_symbol": "DIA",
    "strategy_family": "long_call",
    "strategy_name": "long_call",
    "candidate_strategy": "long_call",
    "candidate_id": "2021-06-07_DIA_long_call_10d",
    "strategy_candidate_id": "2021-06-07_DIA_long_call_10d",
    "decision_date": "2021-06-07",
    "date": "2021-06-07",
    "coverage_status": "missing_expectancy",
    "expected_value_state": "data_review",
    "expected_value_handoff_status": "data_review",
    "handoff_status": "data_review",
    "favored_families": [],
    "allowed_families": [],
    "blocked_families": [],
    "risk_flags": [],
    "constraint_flags": [
      "missing_expectancy"
    ],
    "blocked_reasons": [
      "missing_or_no_prior_expectancy_sample"
    ],
    "premium_bias": "long_premium_bias",
    "expectancy_state": "no_prior_sample",
    "expectancy_scope": "symbol_strategy_regime_asset_option",
    "expectancy_sample_count": 0,
    "expectancy_minimum_sample_count": 20,
    "expectancy_average_return": null,
    "expectancy_median_return": null,
    "expectancy_win_rate": null,
    "is_sample_limited": false,
    "uses_current_row_outcome": false,
    "uses_future_rows": false,
    "training_window_start": null,
    "training_window_end": "2021-06-06",
    "source_expectancy_contract": "walk_forward_expectancy",
    "source_expectancy_artifact": "data/canonical/signalforge_pipeline/18_walk_forward_expectancy"
  },
  {
    "symbol": "DIA",
    "underlying_symbol": "DIA",
    "strategy_family": "long_put",
    "strategy_name": "long_put",
    "candidate_strategy": "long_put",
    "candidate_id": "2021-06-07_DIA_long_put_10d",
    "strategy_candidate_id": "2021-06-07_DIA_long_put_10d",
    "decision_date": "2021-06-07",
    "date": "2021-06-07",
    "coverage_status": "missing_expectancy",
    "expected_value_state": "data_review",
    "expected_value_handoff_status": "data_review",
    "handoff_status": "data_review",
    "favored_families": [],
    "allowed_families": [],
    "blocked_families": [],
    "risk_flags": [],
    "constraint_flags": [
      "missing_expectancy"
    ],
    "blocked_reasons": [
      "missing_or_no_prior_expectancy_sample"
    ],
    "premium_bias": "long_premium_bias",
    "expectancy_state": "no_prior_sample",
    "expectancy_scope": "symbol_strategy_regime_asset_option",
    "expectancy_sample_count": 0,
    "expectancy_minimum_sample_count": 20,
    "expectancy_average_return": null,
    "expectancy_median_return": null,
    "expectancy_win_rate": null,
    "is_sample_limited": false,
    "uses_current_row_outcome": false,
    "uses_future_rows": false,
    "training_window_start": null,
    "training_window_end": "2021-06-06",
    "source_expectancy_contract": "walk_forward_expectancy",
    "source_expectancy_artifact": "data/canonical/signalforge_pipeline/18_walk_forward_expectancy"
  },
  {
    "symbol": "EEM",
    "underlying_symbol": "EEM",
    "strategy_family": "bear_put_debit_spread",
    "strategy_name": "bear_put_debit_spread",
    "candidate_strategy": "bear_put_debit_spread",
    "candidate_id": "2021-06-07_EEM_bear_put_debit_spread_10d",
    "strategy_candidate_id": "2021-06-07_EEM_bear_put_debit_spread_10d",
    "decision_date": "2021-06-07",
    "date": "2021-06-07",
    "coverage_status": "missing_expectancy",
    "expected_value_state": "data_review",
    "expected_value_handoff_status": "data_review",
    "handoff_status": "data_review",
    "favored_families": [],
    "allowed_families": [],
    "blocked_families": [],
    "risk_flags": [],
    "constraint_flags": [
      "missing_expectancy"
    ],
    "blocked_reasons": [
      "missing_or_no_prior_expectancy_sample"
    ],
    "premium_bias": "long_premium_bias",
    "expectancy_state": "no_prior_sample",
    "expectancy_scope": "symbol_strategy_regime_asset_option",
    "expectancy_sample_count": 0,
    "expectancy_minimum_sample_count": 20,
    "expectancy_average_return": null,
    "expectancy_median_return": null,
    "expectancy_win_rate": null,
    "is_sample_limited": false,
    "uses_current_row_outcome": false,
    "uses_future_rows": false,
    "training_window_start": null,
    "training_window_end": "2021-06-06",
    "source_expectancy_contract": "walk_forward_expectancy",
    "source_expectancy_artifact": "data/canonical/signalforge_pipeline/18_walk_forward_expectancy"
  }
]
```

## Warnings

- adapter_items_built_but_current_engine_did_not_return_ready_true_for_any_variant
- next_stage_should_inspect_expected_value_scoring_readiness_contract_before_wiring
- stage37i_is_docs_only_no_production_logic_moved
- canonical_expectancy_snapshot_is_selected_source_of_truth
- legacy_expected_value_domain_remains_research_only_until_ab_backtested