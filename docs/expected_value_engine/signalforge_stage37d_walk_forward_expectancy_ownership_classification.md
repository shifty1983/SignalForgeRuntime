# Stage 37D Walk-Forward Expectancy Ownership Classification

- is_ready: True
- blocker_count: 0
- file_count: 3
- symbol_count: 45
- extraction_review_count: 10
- backtesting_keep_count: 20
- walk_forward_owner: `src/signalforge/backtesting/walk_forward_expectancy_builder.py`
- paper_expectancy_consumption_target: `src/signalforge/engines/strategy_selection/expectancy_decision.py`
- legacy_expected_value_status: `research_candidate_only_until_ab_backtested`
- paper_order_created: False
- live_order_created: False
- live_trade_supported: False

## Ownership Decision

Walk-forward expectancy generation remains backtesting-owned.
Paper trading should consume a locked expectancy snapshot produced by the validated backtest workflow.
Only reusable expectancy lookup, confidence handling, and candidate consumption policy should be considered for engine extraction after source-slice review and parity tests.

## File Inventory

| file | symbols | backtesting score | expectancy score | paper engine score |
|---|---:|---:|---:|---:|
| `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | 22 | 16 | 10 | 5 |
| `src/signalforge/backtesting/walk_forward_expectancy_cli.py` | 2 | 11 | 4 | 0 |
| `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | 21 | 6 | 9 | 10 |

## Symbol Classification

| symbol | file | classification | recommendation | target | reason | backtesting | expectancy | paper engine | IO calls |
|---|---|---|---|---|---|---:|---:|---:|---|
| `FieldValues` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | keep_in_backtesting_walk_forward_orchestration | do_not_extract_builder_or_training_window_logic | `none` | walk_forward_training_or_historical_replay_terms_dominate | 1 | 1 | 1 |  |
| `TrainingExample` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | keep_in_backtesting_walk_forward_orchestration | do_not_extract_builder_or_training_window_logic | `none` | walk_forward_training_or_historical_replay_terms_dominate | 4 | 1 | 0 |  |
| `RunningStats` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | keep_or_review_low_confidence | manual_review | `manual_review` | low_signal_or_mixed_terms | 2 | 3 | 0 |  |
| `read_jsonl` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | keep_in_backtesting_artifact_io | do_not_extract | `none` | contains_file_or_artifact_io | 6 | 1 | 0 | loads, open |
| `write_jsonl` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | keep_in_backtesting_artifact_io | do_not_extract | `none` | contains_file_or_artifact_io | 6 | 1 | 0 | dumps, mkdir, open |
| `write_json` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | keep_in_backtesting_artifact_io | do_not_extract | `none` | contains_file_or_artifact_io | 5 | 1 | 0 | mkdir, open |
| `_first_present` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | keep_in_backtesting_walk_forward_orchestration | do_not_extract_builder_or_training_window_logic | `none` | walk_forward_training_or_historical_replay_terms_dominate | 1 | 1 | 0 |  |
| `_normalise_component` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | keep_or_review_low_confidence | manual_review | `manual_review` | low_signal_or_mixed_terms | 1 | 2 | 0 |  |
| `_parse_date` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | keep_in_backtesting_walk_forward_orchestration | do_not_extract_builder_or_training_window_logic | `none` | walk_forward_training_or_historical_replay_terms_dominate | 2 | 1 | 0 |  |
| `_parse_float` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | keep_in_backtesting_walk_forward_orchestration | do_not_extract_builder_or_training_window_logic | `none` | walk_forward_training_or_historical_replay_terms_dominate | 1 | 1 | 0 |  |
| `_decision_date_for_row` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | keep_in_backtesting_walk_forward_orchestration | do_not_extract_builder_or_training_window_logic | `none` | walk_forward_training_or_historical_replay_terms_dominate | 2 | 1 | 0 |  |
| `_field_values` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | keep_in_backtesting_walk_forward_orchestration | do_not_extract_builder_or_training_window_logic | `none` | walk_forward_training_or_historical_replay_terms_dominate | 1 | 1 | 1 |  |
| `_return_value_for_row` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | keep_in_backtesting_walk_forward_orchestration | do_not_extract_builder_or_training_window_logic | `none` | walk_forward_training_or_historical_replay_terms_dominate | 1 | 1 | 0 |  |
| `_availability_date_for_row` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | keep_in_backtesting_walk_forward_orchestration | do_not_extract_builder_or_training_window_logic | `none` | walk_forward_training_or_historical_replay_terms_dominate | 2 | 2 | 0 |  |
| `_scope_key` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | keep_in_backtesting_walk_forward_orchestration | do_not_extract_builder_or_training_window_logic | `none` | walk_forward_training_or_historical_replay_terms_dominate | 2 | 1 | 1 |  |
| `_state_for_stats` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | review_extract_expectancy_consumption_policy | source_slice_review_before_extract | `src/signalforge/engines/strategy_selection/expectancy_decision.py` | expectancy_policy_plus_candidate_consumption_terms | 2 | 7 | 2 |  |
| `_select_stats` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | keep_or_review_low_confidence | manual_review | `manual_review` | low_signal_or_mixed_terms | 2 | 3 | 1 |  |
| `_make_training_examples` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | keep_in_backtesting_walk_forward_orchestration | do_not_extract_builder_or_training_window_logic | `none` | walk_forward_training_or_historical_replay_terms_dominate | 5 | 3 | 1 |  |
| `_add_example_to_aggregators` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | keep_in_backtesting_walk_forward_orchestration | do_not_extract_builder_or_training_window_logic | `none` | walk_forward_training_or_historical_replay_terms_dominate | 4 | 1 | 0 |  |
| `_iso` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | keep_in_backtesting_walk_forward_orchestration | do_not_extract_builder_or_training_window_logic | `none` | walk_forward_training_or_historical_replay_terms_dominate | 2 | 1 | 0 |  |
| `build_walk_forward_expectancy_rows` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | keep_in_backtesting_walk_forward_orchestration | do_not_extract_builder_or_training_window_logic | `none` | walk_forward_training_or_historical_replay_terms_dominate | 9 | 9 | 4 |  |
| `build_walk_forward_expectancy_artifact` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | keep_in_backtesting_walk_forward_orchestration | do_not_extract_builder_or_training_window_logic | `none` | walk_forward_training_or_historical_replay_terms_dominate | 9 | 3 | 0 |  |
| `build_parser` | `src/signalforge/backtesting/walk_forward_expectancy_cli.py` | keep_in_backtesting_cli | do_not_extract | `none` | cli_entrypoint | 9 | 3 | 0 |  |
| `main` | `src/signalforge/backtesting/walk_forward_expectancy_cli.py` | keep_in_backtesting_cli | do_not_extract | `none` | cli_entrypoint | 9 | 3 | 0 | dumps, parse_args, print |
| `build_signalforge_expected_value_scoring` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | review_extract_expectancy_consumption_policy | source_slice_review_before_extract | `src/signalforge/engines/strategy_selection/expectancy_decision.py` | expectancy_policy_plus_candidate_consumption_terms | 4 | 6 | 8 |  |
| `_build_ev_item` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | review_extract_expectancy_consumption_policy | source_slice_review_before_extract | `src/signalforge/engines/strategy_selection/expectancy_decision.py` | expectancy_policy_plus_candidate_consumption_terms | 3 | 4 | 9 |  |
| `_candidate_families` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | review_extract_strategy_candidate_policy | source_slice_review_before_extract | `src/signalforge/engines/strategy_selection/expectancy_decision.py` | candidate_policy_terms_without_strong_backtesting_io | 1 | 3 | 4 |  |
| `_score_family_candidate` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | review_extract_expectancy_consumption_policy | source_slice_review_before_extract | `src/signalforge/engines/strategy_selection/expectancy_decision.py` | expectancy_policy_plus_candidate_consumption_terms | 2 | 4 | 6 |  |
| `_premium_alignment_adjustment` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | keep_or_review_low_confidence | manual_review | `manual_review` | low_signal_or_mixed_terms | 0 | 2 | 2 |  |
| `_risk_penalty` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | keep_or_review_low_confidence | manual_review | `manual_review` | low_signal_or_mixed_terms | 0 | 2 | 1 |  |
| `_constraint_penalty` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | keep_or_review_low_confidence | manual_review | `manual_review` | low_signal_or_mixed_terms | 1 | 2 | 1 |  |
| `_candidate_ev_state` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | review_extract_expectancy_consumption_policy | source_slice_review_before_extract | `src/signalforge/engines/strategy_selection/expectancy_decision.py` | expectancy_policy_plus_candidate_consumption_terms | 1 | 6 | 3 |  |
| `_item_ev_state` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | review_extract_expectancy_consumption_policy | source_slice_review_before_extract | `src/signalforge/engines/strategy_selection/expectancy_decision.py` | expectancy_policy_plus_candidate_consumption_terms | 1 | 4 | 4 |  |
| `_candidate_handoff_status` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | review_extract_expectancy_consumption_policy | source_slice_review_before_extract | `src/signalforge/engines/strategy_selection/expectancy_decision.py` | expectancy_policy_plus_candidate_consumption_terms | 2 | 4 | 5 |  |
| `_summary` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | review_extract_expectancy_consumption_policy | source_slice_review_before_extract | `src/signalforge/engines/strategy_selection/expectancy_decision.py` | expectancy_policy_plus_candidate_consumption_terms | 3 | 5 | 7 |  |
| `_extract_items` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | keep_or_review_low_confidence | manual_review | `manual_review` | low_signal_or_mixed_terms | 1 | 2 | 1 |  |
| `_source_artifact_type` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | keep_or_review_low_confidence | manual_review | `manual_review` | low_signal_or_mixed_terms | 1 | 3 | 1 |  |
| `_looks_like_items` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | keep_or_review_low_confidence | manual_review | `manual_review` | low_signal_or_mixed_terms | 0 | 2 | 1 |  |
| `_first_value` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | keep_or_review_low_confidence | manual_review | `manual_review` | low_signal_or_mixed_terms | 0 | 2 | 1 |  |
| `_as_string_list` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | keep_or_review_low_confidence | manual_review | `manual_review` | low_signal_or_mixed_terms | 0 | 2 | 1 |  |
| `_ordered` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | keep_or_review_low_confidence | manual_review | `manual_review` | low_signal_or_mixed_terms | 0 | 2 | 2 |  |
| `_clamp_score` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | keep_or_review_low_confidence | manual_review | `manual_review` | low_signal_or_mixed_terms | 0 | 3 | 1 |  |
| `_clean_symbol` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | keep_or_review_low_confidence | manual_review | `manual_review` | low_signal_or_mixed_terms | 0 | 2 | 1 |  |
| `_clean_text` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | keep_or_review_low_confidence | manual_review | `manual_review` | low_signal_or_mixed_terms | 0 | 2 | 1 |  |
| `_blocked_result` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | review_extract_expectancy_consumption_policy | source_slice_review_before_extract | `src/signalforge/engines/strategy_selection/expectancy_decision.py` | expectancy_policy_plus_candidate_consumption_terms | 4 | 5 | 7 |  |

## Warnings

- stage37d_is_read_only_no_logic_moved
- walk_forward_expectancy_generation_remains_backtesting_owned
- paper_engine_should_consume_locked_expectancy_snapshot_not_recompute_walk_forward