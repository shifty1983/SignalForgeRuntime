# Stage 36P4 Non-Empty Historical Candidate Rows Replay Parity

- is_ready: True
- blocker_count: 0
- result_same: True
- expected_candidate_row_count: 54456
- output_file_count: 2
- matching_output_file_count: 2
- paper_order_created: False
- live_order_created: False
- live_trade_supported: False

## Inputs

- decision_rows_path: `artifacts\historical_strategy_family_eligibility_enrichment_local_rebuild_20210601_20260531\signalforge_historical_strategy_family_eligibility_enriched_decision_rows.jsonl`
- strategy_policy_path: `None`

## Output Files

| file | same | original count | current count |
|---|---:|---:|---:|
| `signalforge_historical_strategy_candidate_rows.jsonl` | True | 54456 | 54456 |
| `signalforge_historical_strategy_candidate_rows_summary.json` | True | None | None |

## Warnings

- stage36p4_runs_non_empty_historical_candidate_rows_replay
- historical_candidate_row_builder_remains_in_backtesting_engine_owns_candidate_filter_helpers