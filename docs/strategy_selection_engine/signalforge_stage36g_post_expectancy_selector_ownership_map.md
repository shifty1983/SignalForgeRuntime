# Stage 36G Post-Expectancy Selector Ownership Map

- is_ready: True
- blocker_count: 0
- backtesting_file_count: 6
- engine_module_count: 9
- engine_export_count: 114
- high_priority_backtesting_file_count: 6
- paper_order_created: False
- live_order_created: False
- live_trade_supported: False

## High Priority Backtesting Files

- `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py`
- `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py`
- `src/signalforge/backtesting/historical_strategy_selection_rows_cli.py`
- `src/signalforge/backtesting/walk_forward_expectancy_builder.py`
- `src/signalforge/backtesting/walk_forward_expectancy_cli.py`
- `src/signalforge/backtesting/portfolio_selected_trade_sequence.py`

## Backtesting Files

| path | functions | engine imports | terms |
|---|---:|---|---|
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | 30 |  | candidate, expectancy, rank, select, strategy_selection, symbol |
| `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | 16 |  | candidate, expectancy, rank, ranking, score, select, strategy_selection, symbol |
| `src/signalforge/backtesting/historical_strategy_selection_rows_cli.py` | 1 |  | expectancy, select, strategy_selection |
| `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | 19 |  | candidate, expectancy, score, select, symbol |
| `src/signalforge/backtesting/walk_forward_expectancy_cli.py` | 2 |  | expectancy |
| `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | 17 |  | candidate, expectancy, select, strategy_selection, symbol, trade_sequence |

## Best Overlaps

| backtesting file | function | best score | best engine candidates |
|---|---|---:|---|
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `read_jsonl` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `write_jsonl` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `write_json` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `load_strategy_policy` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_normalise_symbol` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_normalise_text` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_nested_state` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_nested_source_date` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_eligibility` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_flag_is_true` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_has_underlying_position` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_has_term_structure_behavior` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_strategy_family_statuses` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_strategy_family_status_aliases` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_strategy_family_status` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_strategy_family_gate_block_reasons` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_as_dict` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_as_list` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_research_context_from_decision_row` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_option_behavior_research_fields` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_alignment_research_fields` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_parse_option_behavior` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_decision_row_block_reasons` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_strategy_definition_block_reasons` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_strategy_context_block_reasons` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_candidate_id` | 1 | signalforge.engines.strategy_selection.allocation.CandidateAllocationConfig; signalforge.engines.strategy_selection.allocation.allocate_selected_candidates; signalforge.engines.strategy_selection.allocation.validate_candidate_data |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_strategy_instance` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `_candidate_state` | 1 | signalforge.engines.strategy_selection.allocation.CandidateAllocationConfig; signalforge.engines.strategy_selection.allocation.allocate_selected_candidates; signalforge.engines.strategy_selection.allocation.validate_candidate_data |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `build_historical_strategy_candidate_rows` | 1 | signalforge.engines.strategy_selection.allocation.CandidateAllocationConfig; signalforge.engines.strategy_selection.allocation.allocate_selected_candidates; signalforge.engines.strategy_selection.allocation.validate_candidate_data |
| `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` | `build_historical_strategy_candidate_rows_artifact` | 1 | signalforge.engines.strategy_selection.allocation.CandidateAllocationConfig; signalforge.engines.strategy_selection.allocation.allocate_selected_candidates; signalforge.engines.strategy_selection.allocation.validate_candidate_data |
| `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `_as_float` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `_as_int` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `_date` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `read_jsonl` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `write_jsonl` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `write_json` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `_decision_group_key` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `_candidate_id` | 1 | signalforge.engines.strategy_selection.allocation.CandidateAllocationConfig; signalforge.engines.strategy_selection.allocation.allocate_selected_candidates; signalforge.engines.strategy_selection.allocation.validate_candidate_data |
| `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `_is_selectable` | 1 | signalforge.engines.strategy_selection.allocation.allocate_selected_candidates; signalforge.engines.strategy_selection.filters.filter_by_selection_eligible; signalforge.engines.strategy_selection.ranking.rank_selection_pipeline |
| `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `_selection_score` | 2 | signalforge.engines.strategy_selection.filters.filter_by_selection_eligible; signalforge.engines.strategy_selection.ranking.rank_selection_pipeline; signalforge.engines.strategy_selection.selection_report.StrategySelectionCandidateSummary |
| `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `_sample_confidence_multiplier` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `_scope_confidence_multiplier` | 0 |  |
| `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `_confidence_adjusted_selection_score` | 2 | signalforge.engines.strategy_selection.filters.filter_by_selection_eligible; signalforge.engines.strategy_selection.ranking.rank_selection_pipeline; signalforge.engines.strategy_selection.selection_report.StrategySelectionCandidateSummary |
| `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `_rank_tuple` | 1 | signalforge.engines.strategy_selection.allocation.rank_weighted_allocation; signalforge.engines.strategy_selection.ranking.CandidateRankingConfig; signalforge.engines.strategy_selection.ranking.add_group_rank |
| `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `_selection_row` | 2 | signalforge.engines.strategy_selection.filters.filter_by_selection_eligible; signalforge.engines.strategy_selection.ranking.rank_selection_pipeline; signalforge.engines.strategy_selection.selection_report.StrategySelectionCandidateSummary |
| `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` | `build_historical_strategy_selection_rows_artifact` | 2 | signalforge.engines.strategy_selection.filters.filter_by_selection_eligible; signalforge.engines.strategy_selection.ranking.rank_selection_pipeline; signalforge.engines.strategy_selection.selection_report.StrategySelectionCandidateSummary |
| `src/signalforge/backtesting/historical_strategy_selection_rows_cli.py` | `main` | 0 |  |
| `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `read_jsonl` | 0 |  |
| `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `write_jsonl` | 0 |  |
| `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `write_json` | 0 |  |
| `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `_first_present` | 0 |  |
| `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `_normalise_component` | 0 |  |
| `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `_parse_date` | 0 |  |
| `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `_parse_float` | 0 |  |
| `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `_decision_date_for_row` | 0 |  |
| `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `_field_values` | 0 |  |
| `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `_return_value_for_row` | 0 |  |
| `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `_availability_date_for_row` | 0 |  |
| `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `_scope_key` | 0 |  |
| `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `_state_for_stats` | 0 |  |
| `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `_select_stats` | 1 | signalforge.engines.strategy_selection.allocation.allocate_selected_candidates; signalforge.engines.strategy_selection.filters.filter_by_selection_eligible; signalforge.engines.strategy_selection.ranking.rank_selection_pipeline |
| `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `_make_training_examples` | 0 |  |
| `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `_add_example_to_aggregators` | 0 |  |
| `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `_iso` | 0 |  |
| `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `build_walk_forward_expectancy_rows` | 0 |  |
| `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | `build_walk_forward_expectancy_artifact` | 0 |  |
| `src/signalforge/backtesting/walk_forward_expectancy_cli.py` | `build_parser` | 0 |  |
| `src/signalforge/backtesting/walk_forward_expectancy_cli.py` | `main` | 0 |  |
| `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `read_json` | 0 |  |
| `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `read_jsonl` | 0 |  |
| `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `write_json` | 0 |  |
| `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `write_jsonl` | 0 |  |
| `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `_get_by_path` | 0 |  |
| `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `_first_present_with_path` | 0 |  |
| `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `_parse_date` | 0 |  |
| `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `_coerce_float` | 0 |  |
| `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `_string_or_none` | 0 |  |
| `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `_collect_data_states` | 0 |  |
| `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `_has_contract_outcome_missing_state` | 0 |  |
| `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `_extract_execution_realism_fields` | 0 |  |
| `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `_execution_realism_coverage` | 0 |  |
| `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `_extract_trade` | 0 |  |
| `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `_count_source_fields` | 0 |  |
| `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `build_portfolio_selected_trade_sequence` | 1 | signalforge.engines.strategy_selection.allocation.allocate_selected_candidates; signalforge.engines.strategy_selection.filters.filter_by_selection_eligible; signalforge.engines.strategy_selection.portfolio_candidate_input.build_signalforge_portfolio_candidate_input |
| `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | `build_from_paths` | 0 |  |

## Warnings

- stage36g_is_read_only_no_backtesting_logic_modified
- next_stage_should_migrate_one_backtesting_builder_to_engine_call_or_create_wrapper_parity_test