# Stage 36J Selection Decision Cluster Extraction

- is_ready: True
- blocker_count: 0
- source_path: `src\signalforge\backtesting\historical_strategy_selection_rows_builder.py`
- engine_path: `src\signalforge\engines\strategy_selection\selection_decision.py`
- backup_path: `docs\strategy_selection_engine\stage36j_backtesting_backups\historical_strategy_selection_rows_builder.py.before_stage36j`
- extracted_function_count: 10
- parity_function_count: 8
- copied_binding_names: Any, Counter, Dict, Iterable, List, Mapping, Optional, SCOPE_CONFIDENCE_MULTIPLIER, Tuple, math
- paper_order_created: False
- live_order_created: False
- live_trade_supported: False

## Wrapper Verification

| function | backtesting function is wrapper |
|---|---:|
| `_as_float` | True |
| `_as_int` | True |
| `_candidate_id` | True |
| `_is_selectable` | True |
| `_selection_score` | True |
| `_sample_confidence_multiplier` | True |
| `_scope_confidence_multiplier` | True |
| `_confidence_adjusted_selection_score` | True |
| `_rank_tuple` | True |
| `_selection_row` | True |

## Parity Rows

| function | original vs engine | engine vs patched wrapper |
|---|---:|---:|
| `_candidate_id` | True | True |
| `_is_selectable` | True | True |
| `_selection_score` | True | True |
| `_sample_confidence_multiplier` | True | True |
| `_scope_confidence_multiplier` | True | True |
| `_confidence_adjusted_selection_score` | True | True |
| `_rank_tuple` | True | True |
| `_selection_row` | True | True |

## Warnings

- stage36j_repaired_missing_engine_constants_after_initial_extraction
- historical_backtesting_wrapper_remains_in_backtesting
- selection_decision_logic_now_owned_by_engine
- parity_uses_small_fixture_not_full_historical_replay