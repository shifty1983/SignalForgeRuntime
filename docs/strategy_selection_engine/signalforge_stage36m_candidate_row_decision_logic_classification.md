# Stage 36M Candidate Row Decision Logic Classification

- is_ready: True
- blocker_count: 0
- recommendation: `extract_candidate_filter_decision_cluster_with_parity_test`
- classified_function_count: 10
- extract_with_parity_test_count: 6
- manual_review_before_extract_count: 1
- keep_in_backtesting_count: 3
- paper_order_created: False
- live_order_created: False
- live_trade_supported: False

## Function Classifications

| function | classification | recommendation | target | reason | backtesting score | row shaping score | engine decision score |
|---|---|---|---|---|---:|---:|---:|
| `_strategy_family_gate_block_reasons` | extract_decision_logic_to_engine_candidate_filter | extract_with_parity_test | `signalforge.engines.strategy_selection.candidate_filter_decision` | candidate_filter_or_block_reason_logic | 0 | 2 | 7 |
| `_as_list` | keep_in_backtesting_row_shaping | do_not_extract_now | `none` | row_shaping_terms_dominate_or_match_decision_terms | 0 | 0 | 0 |
| `_research_context_from_decision_row` | extract_decision_logic_to_engine_candidate_filter | extract_with_parity_test | `signalforge.engines.strategy_selection.candidate_filter_decision` | candidate_filter_or_block_reason_logic | 0 | 4 | 8 |
| `_alignment_research_fields` | keep_in_backtesting_row_shaping | do_not_extract_now | `none` | row_shaping_terms_dominate_or_match_decision_terms | 0 | 3 | 1 |
| `_decision_row_block_reasons` | extract_decision_logic_to_engine_candidate_filter | extract_with_parity_test | `signalforge.engines.strategy_selection.candidate_filter_decision` | candidate_filter_or_block_reason_logic | 2 | 4 | 9 |
| `_strategy_definition_block_reasons` | extract_decision_logic_to_engine_candidate_filter | extract_with_parity_test | `signalforge.engines.strategy_selection.candidate_filter_decision` | candidate_filter_or_block_reason_logic | 1 | 3 | 6 |
| `_strategy_context_block_reasons` | extract_decision_logic_to_engine_candidate_filter | extract_with_parity_test | `signalforge.engines.strategy_selection.candidate_filter_decision` | candidate_filter_or_block_reason_logic | 0 | 4 | 7 |
| `_candidate_state` | review_possible_candidate_decision_logic | manual_review_before_extract | `signalforge.engines.strategy_selection.candidate_filter_decision` | possible_reusable_candidate_filter_logic | 1 | 0 | 2 |
| `build_historical_strategy_candidate_rows` | mixed_keep_wrapper_extract_core_decision_logic | manual_review_extract_inner_decisions_only | `signalforge.engines.strategy_selection.filters` | historical_builder_contains_decision_terms_but_must_remain_backtesting_orchestration | 8 | 8 | 14 |
| `build_historical_strategy_candidate_rows_artifact` | keep_in_backtesting_orchestration | do_not_extract_builder | `none` | historical_artifact_builder_or_replay_entrypoint | 13 | 2 | 1 |

## Warnings

- stage36m_is_read_only_no_logic_moved
- historical_candidate_row_builder_remains_in_backtesting
- extract_only_reusable_candidate_filter_or_block_reason_logic