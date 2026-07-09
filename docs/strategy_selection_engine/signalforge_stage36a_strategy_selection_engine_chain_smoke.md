# Stage 36A Strategy Selection Engine Chain Smoke

- is_ready: True
- blocker_count: 0
- chain_state: engine_chain_import_ready
- expected_stage_count: 14
- ready_stage_count: 14
- live_trade_supported: False
- paper_order_created: False
- live_order_created: False

## Chain

| stage | module | role | compile | import | stale src import |
|---|---|---|---:|---:|---:|
| family_eligibility | `signalforge.engines.strategy_selection.strategy_family_eligibility` | regime_asset_behavior_option_behavior_to_eligible_strategy_families | True | True | False |
| structure_availability | `signalforge.engines.strategy_selection.strategy_structure_availability_v21` | eligible_strategy_families_to_buildable_strategy_structures | True | True | False |
| resolved_execution_rules | `signalforge.engines.strategy_selection.resolved_strategy_execution_rules_v21` | structure_rows_to_allowed_conditional_manual_review_block_execution_state | True | True | False |
| execution_qualified_candidates | `signalforge.engines.strategy_selection.execution_qualified_historical_strategy_candidates_v21` | execution_rule_rows_to_execution_qualified_strategy_candidates | True | True | False |
| repaired_strategy_candidates | `signalforge.engines.strategy_selection.repaired_historical_strategy_candidates_v13_v21` | repair_or_normalize_historical_strategy_candidates | True | True | False |
| candidate_models | `signalforge.engines.strategy_selection.candidates` | candidate_data_models_and_helpers | True | True | False |
| contract_candidate_scoring | `signalforge.engines.strategy_selection.contract_candidate_scoring` | contract_level_candidate_scoring | True | True | False |
| expected_value_scoring | `signalforge.engines.strategy_selection.expected_value_scoring` | expected_value_scoring_support | True | True | False |
| filters | `signalforge.engines.strategy_selection.filters` | post_expectancy_filtering | True | True | False |
| ranking | `signalforge.engines.strategy_selection.ranking` | post_expectancy_candidate_ranking | True | True | False |
| selector | `signalforge.engines.strategy_selection.selector` | grouped_ranked_selection_one_strategy_per_symbol_date | True | True | False |
| portfolio_candidate_input | `signalforge.engines.strategy_selection.portfolio_candidate_input` | selected_candidates_to_portfolio_construction_input | True | True | False |
| allocation | `signalforge.engines.strategy_selection.allocation` | allocation_support_for_selected_candidates | True | True | False |
| selection_report | `signalforge.engines.strategy_selection.selection_report` | selection_reporting_support | True | True | False |

## Warnings

- stage36a_is_import_and_chain_smoke_only_not_backtest_replay
- next_stage_should_compare_backtesting_imports_to_engine_imports_before_deleting_old_paths