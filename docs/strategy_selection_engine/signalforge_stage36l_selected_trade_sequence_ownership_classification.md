# Stage 36L Selected Trade Sequence Ownership Classification

- is_ready: True
- blocker_count: 0
- recommendation: `keep_portfolio_selected_trade_sequence_in_backtesting`
- classified_function_count: 6
- keep_in_backtesting_count: 6
- manual_review_before_extract_count: 0
- paper_order_created: False
- live_order_created: False
- live_trade_supported: False

## Function Classifications

| function | classification | recommendation | reason | backtesting score | row shaping score | engine decision score |
|---|---|---|---|---:|---:|---:|
| `_extract_execution_realism_fields` | keep_in_backtesting_row_shaping | do_not_extract_now | row_shaping_terms_dominate_or_match_decision_terms | 7 | 7 | 1 |
| `_execution_realism_coverage` | keep_in_backtesting_row_shaping | do_not_extract_now | row_shaping_terms_dominate_or_match_decision_terms | 4 | 3 | 1 |
| `_extract_trade` | keep_in_backtesting_row_shaping | do_not_extract_now | row_shaping_terms_dominate_or_match_decision_terms | 7 | 13 | 2 |
| `_count_source_fields` | keep_in_backtesting_row_shaping | do_not_extract_now | row_shaping_terms_dominate_or_match_decision_terms | 5 | 4 | 0 |
| `build_portfolio_selected_trade_sequence` | keep_in_backtesting_orchestration | do_not_extract_builder | top_level_historical_artifact_builder_or_path_entrypoint | 19 | 7 | 3 |
| `build_from_paths` | keep_in_backtesting_orchestration | do_not_extract_builder | top_level_historical_artifact_builder_or_path_entrypoint | 10 | 1 | 1 |

## Warnings

- stage36l_is_read_only_no_logic_moved
- portfolio_selected_trade_sequence_remains_backtesting_owned_unless_manual_review_finds_core_decision_logic
- do_not_extract_row_shaping_or_artifact_contract_logic_to_core_engines