# Stage 37L Canonical Expectancy Snapshot Adapter Promotion

- is_ready: True
- blocker_count: 0
- adapter_path: `src\signalforge\engines\strategy_selection\canonical_expectancy_snapshot_adapter.py`
- canonical_summary_is_ready: True
- adapter_artifact_is_ready: True
- adapter_input_row_count: 13412
- adapter_output_item_count: 13412
- expected_value_scoring_status: needs_review
- expected_value_scoring_is_ready: False
- expected_value_scoring_requires_manual_approval: True
- expected_value_scoring_item_count: 13412
- paper_order_created: False
- live_order_created: False
- live_trade_supported: False

## Adapter Summary

```json
{
  "input_row_count": 13412,
  "output_item_count": 13412,
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

## Expected-Value Scoring Result

```json
{
  "artifact_type": "signalforge_expected_value_scoring",
  "contract": "expected_value_scoring",
  "status": "needs_review",
  "is_ready": false,
  "requires_manual_approval": true,
  "review_scope": "risk_adjusted_expected_value_scoring_not_trade_selection_or_execution",
  "expected_value_item_count": 13412,
  "ev_item_count": 13412,
  "order_intent": null,
  "broker_order_id": null,
  "automatic_action": null
}
```

## Parity Rows

| group | same | expected | actual |
|---|---:|---|---|
| coverage_status_counts | True | `{'missing_expectancy': 132, 'sample_limited': 165, 'covered': 13115}` | `{'missing_expectancy': 132, 'sample_limited': 165, 'covered': 13115}` |
| expected_value_state_counts | True | `{'data_review': 132, 'sample_limited': 165, 'positive_expectancy_candidate': 9405, 'non_positive_expectancy': 3710}` | `{'data_review': 132, 'sample_limited': 165, 'positive_expectancy_candidate': 9405, 'non_positive_expectancy': 3710}` |
| handoff_status_counts | True | `{'data_review': 132, 'review': 165, 'candidate': 9405, 'blocked': 3710}` | `{'data_review': 132, 'review': 165, 'candidate': 9405, 'blocked': 3710}` |

## Warnings

- stage37l_promotes_adapter_only_no_order_logic
- expected_value_scoring_remains_review_handoff_not_trade_authorization
- legacy_expected_value_domain_not_used
- data_canonical_runtime_files_should_not_be_force_added_to_git