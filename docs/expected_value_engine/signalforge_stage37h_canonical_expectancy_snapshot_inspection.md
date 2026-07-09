# Stage 37H Canonical Expectancy Snapshot Inspection

- is_ready: True
- blocker_count: 0
- canonical_dir: `data\canonical\signalforge_pipeline\18_walk_forward_expectancy`
- canonical_artifact_count: 1
- non_empty_canonical_artifact_count: 1
- ready_canonical_artifact_count: 1
- paper_snapshot_selection_rule: prefer data/canonical/signalforge_pipeline/18_walk_forward_expectancy when it is ready, no-lookahead safe, and matches the locked paper candidate scope
- paper_order_created: False
- live_order_created: False
- live_trade_supported: False

## Preferred Canonical Snapshot

```json
{
  "source_group": "canonical_pipeline",
  "root": "data\\canonical\\signalforge_pipeline\\18_walk_forward_expectancy",
  "rows_path": "data\\canonical\\signalforge_pipeline\\18_walk_forward_expectancy\\signalforge_walk_forward_expectancy_rows.jsonl",
  "row_count": 13412,
  "summary_path": "data\\canonical\\signalforge_pipeline\\18_walk_forward_expectancy\\signalforge_walk_forward_expectancy_summary.json",
  "summary_exists": true,
  "summary_is_ready": true,
  "summary_artifact_type": "signalforge_walk_forward_expectancy",
  "summary_contract": "walk_forward_expectancy",
  "sample_key_count": 123,
  "has_expectancy_fields": true,
  "has_no_lookahead_fields": true,
  "sample_compact_row": {
    "symbol": "DIA",
    "strategy": "bear_put_debit_spread",
    "strategy_name": "bear_put_debit_spread",
    "candidate_strategy": "bear_put_debit_spread",
    "strategy_candidate_id": "2021-06-07_DIA_bear_put_debit_spread_10d",
    "candidate_id": "2021-06-07_DIA_bear_put_debit_spread_10d",
    "decision_date": "2021-06-07",
    "date": "2021-06-07",
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
    "training_window_end": "2021-06-06"
  }
}
```

## Artifact Rows

| source | row count | ready | artifact type | expectancy fields | no-lookahead fields | rows path | summary path |
|---|---:|---:|---|---:|---:|---|---|
| canonical_pipeline | 13412 | True | signalforge_walk_forward_expectancy | True | True | `data\canonical\signalforge_pipeline\18_walk_forward_expectancy\signalforge_walk_forward_expectancy_rows.jsonl` | `data\canonical\signalforge_pipeline\18_walk_forward_expectancy\signalforge_walk_forward_expectancy_summary.json` |
| artifact_comparison | 13412 | True | signalforge_walk_forward_expectancy | True | True | `artifacts\sf18_walk_forward_expectancy\signalforge_walk_forward_expectancy_rows.jsonl` | `artifacts\sf18_walk_forward_expectancy\signalforge_walk_forward_expectancy_summary.json` |
| artifact_comparison | 8220 | True | signalforge_pruned_walk_forward_expectancy_rows | True | True | `artifacts\sf20_pruned_expectancy_core_plus_credit\signalforge_walk_forward_expectancy_rows_pruned_core_plus_credit.jsonl` | `artifacts\sf20_pruned_expectancy_core_plus_credit\signalforge_walk_forward_expectancy_rows_pruned_core_plus_credit_summary.json` |
| artifact_comparison | 13412 | True | signalforge_walk_forward_expectancy | True | True | `artifacts\walk_forward_expectancy_v13_v21_primary_term_hpd5_exit10_20210601_20260531\signalforge_walk_forward_expectancy_rows.jsonl` | `artifacts\walk_forward_expectancy_v13_v21_primary_term_hpd5_exit10_20210601_20260531\signalforge_walk_forward_expectancy_summary.json` |
| artifact_comparison | 8220 | True | signalforge_pruned_walk_forward_expectancy_rows | True | True | `artifacts\walk_forward_expectancy_v13_v21_primary_term_hpd5_exit10_pruned_core_plus_credit_20210601_20260531\signalforge_walk_forward_expectancy_rows_pruned_core_plus_credit.jsonl` | `artifacts\walk_forward_expectancy_v13_v21_primary_term_hpd5_exit10_pruned_core_plus_credit_20210601_20260531\signalforge_walk_forward_expectancy_rows_pruned_core_plus_credit_summary.json` |

## Warnings

- stage37h_is_read_only_no_logic_moved
- canonical_pipeline_expectancy_should_be_preferred_for_locked_snapshot_if_ready
- data_canonical_is_runtime_source_and_should_not_be_force_added_to_git