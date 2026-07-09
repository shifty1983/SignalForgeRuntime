# Stage 36K Historical Strategy Selection Replay Parity

- is_ready: True
- blocker_count: 0
- result_same: True
- output_file_count: 2
- matching_output_file_count: 2
- paper_order_created: False
- live_order_created: False
- live_trade_supported: False

## Resolved Inputs

### Original

- expectancy_rows_path: `artifacts\sf18_walk_forward_expectancy\signalforge_walk_forward_expectancy_rows.jsonl`
- output_dir: `docs\strategy_selection_engine\stage36k_original_selection_replay_output`

### Current

- expectancy_rows_path: `artifacts\sf18_walk_forward_expectancy\signalforge_walk_forward_expectancy_rows.jsonl`
- output_dir: `docs\strategy_selection_engine\stage36k_current_selection_replay_output`

## Output Files

| file | same | original count | current count |
|---|---:|---:|---:|
| `signalforge_historical_strategy_selection_rows.jsonl` | True | 5218 | 5218 |
| `signalforge_historical_strategy_selection_rows_summary.json` | True | None | None |

## Warnings

- stage36k_runs_historical_selection_replay_only
- historical_wrapper_remains_in_backtesting_engine_owns_selection_decision_helpers