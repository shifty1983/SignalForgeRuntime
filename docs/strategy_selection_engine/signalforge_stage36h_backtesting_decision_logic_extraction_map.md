# Stage 36H Backtesting Decision Logic Extraction Map

- is_ready: True
- blocker_count: 0
- function_count: 85
- extraction_candidate_count: 32
- high_confidence_extract_count: 4
- mixed_extract_core_keep_wrapper_count: 5
- paper_order_created: False
- live_order_created: False
- live_trade_supported: False

## Classification Counts

- extract_decision_logic_to_engine: 4
- keep_in_backtesting_cli_or_entrypoint: 2
- keep_in_backtesting_helper_or_io: 36
- keep_in_backtesting_orchestration: 15
- mixed_extract_core_keep_wrapper: 5
- review_possible_embedded_decision_logic: 23

## Target Counts

- none: 17
- signalforge.engines.strategy_selection.allocation: 2
- signalforge.engines.strategy_selection.candidates: 38
- signalforge.engines.strategy_selection.contract_candidate_scoring: 3
- signalforge.engines.strategy_selection.expected_value_scoring: 8
- signalforge.engines.strategy_selection.filters: 8
- signalforge.engines.strategy_selection.ranking: 6
- signalforge.engines.strategy_selection.selector: 3

## Extraction Candidates

| classification | target | file | function | lines | decision score | orchestration score |
|---|---|---|---|---:|---:|---:|
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.filters` | `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_strategy_family_gate_block_reasons` | 484-517 | 2 | 0 |
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.ranking` | `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_as_list` | 526-533 | 1 | 0 |
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.filters` | `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_research_context_from_decision_row` | 536-550 | 2 | 0 |
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.allocation` | `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_alignment_research_fields` | 591-617 | 1 | 1 |
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.filters` | `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_decision_row_block_reasons` | 647-694 | 2 | 1 |
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.candidates` | `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_strategy_definition_block_reasons` | 697-713 | 2 | 1 |
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.filters` | `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_strategy_context_block_reasons` | 716-773 | 2 | 0 |
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.candidates` | `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_candidate_state` | 794-795 | 1 | 1 |
| mixed_extract_core_keep_wrapper | `signalforge.engines.strategy_selection.filters` | `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `build_historical_strategy_candidate_rows` | 798-1217 | 7 | 6 |
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.candidates` | `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `build_historical_strategy_candidate_rows_artifact` | 1220-1250 | 1 | 11 |
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.candidates` | `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `_candidate_id` | 101-107 | 1 | 1 |
| extract_decision_logic_to_engine | `signalforge.engines.strategy_selection.candidates` | `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `_is_selectable` | 110-152 | 5 | 1 |
| extract_decision_logic_to_engine | `signalforge.engines.strategy_selection.expected_value_scoring` | `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `_selection_score` | 155-158 | 3 | 0 |
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.expected_value_scoring` | `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `_sample_confidence_multiplier` | 161-167 | 1 | 0 |
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.candidates` | `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `_scope_confidence_multiplier` | 170-172 | 1 | 0 |
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.candidates` | `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `_confidence_adjusted_selection_score` | 175-180 | 2 | 0 |
| extract_decision_logic_to_engine | `signalforge.engines.strategy_selection.expected_value_scoring` | `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `_rank_tuple` | 183-212 | 4 | 1 |
| mixed_extract_core_keep_wrapper | `signalforge.engines.strategy_selection.expected_value_scoring` | `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `_selection_row` | 216-306 | 9 | 3 |
| mixed_extract_core_keep_wrapper | `signalforge.engines.strategy_selection.filters` | `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `build_historical_strategy_selection_rows_artifact` | 309-441 | 12 | 10 |
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.expected_value_scoring` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `_scope_key` | 294-316 | 1 | 0 |
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.expected_value_scoring` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `_state_for_stats` | 319-335 | 1 | 1 |
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.candidates` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `_select_stats` | 338-360 | 1 | 1 |
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.filters` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `_make_training_examples` | 363-411 | 2 | 1 |
| mixed_extract_core_keep_wrapper | `signalforge.engines.strategy_selection.expected_value_scoring` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `build_walk_forward_expectancy_rows` | 427-622 | 5 | 5 |
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.candidates` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `build_walk_forward_expectancy_artifact` | 625-652 | 1 | 8 |
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.candidates` | `src/signalforge/backtesting/walk_forward_expectancy_cli.py` | `build_parser` | 10-32 | 1 | 5 |
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.contract_candidate_scoring` | `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `_extract_execution_realism_fields` | 348-458 | 2 | 4 |
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.contract_candidate_scoring` | `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `_execution_realism_coverage` | 460-518 | 2 | 3 |
| extract_decision_logic_to_engine | `signalforge.engines.strategy_selection.selector` | `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `_extract_trade` | 520-627 | 4 | 2 |
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.candidates` | `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `_count_source_fields` | 630-638 | 1 | 0 |
| mixed_extract_core_keep_wrapper | `signalforge.engines.strategy_selection.selector` | `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `build_portfolio_selected_trade_sequence` | 641-844 | 6 | 9 |
| review_possible_embedded_decision_logic | `signalforge.engines.strategy_selection.selector` | `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `build_from_paths` | 847-860 | 2 | 6 |

## Warnings

- stage36h_is_read_only_no_logic_moved
- historical_wrappers_should_stay_in_backtesting
- extract_only_reusable_decision_logic_into_engines