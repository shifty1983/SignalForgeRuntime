# Stage 37A Legacy Expected-Value Domain Inspection

- is_ready: True
- blocker_count: 0
- legacy_dir_count: 2
- file_count: 40
- symbol_count: 583
- legacy_promote_candidate_count: 10
- legacy_keep_orchestration_count: 89
- already_present_candidate_name_count: 0
- missing_engine_candidate_name_count: 10
- walk_forward_owner: `src/signalforge/backtesting/walk_forward_expectancy_builder.py`
- expected_value_engine_target: `src/signalforge/engines/expected_value`
- strategy_selection_ev_scoring_target: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- paper_order_created: False
- live_order_created: False
- live_trade_supported: False

## File Inventory

| source | file | symbols | EV score | selection score | orchestration score |
|---|---|---:|---:|---:|---:|
| legacy_expected_value | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | 0 | 6 | 2 | 1 |
| legacy_expected_value | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/expected_return.py` | 14 | 2 | 0 | 1 |
| legacy_expected_value | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | 25 | 3 | 3 | 1 |
| legacy_expected_value | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/payoff.py` | 16 | 1 | 1 | 1 |
| legacy_expected_value | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/probabilities.py` | 19 | 2 | 0 | 1 |
| legacy_expected_value | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/risk_reward.py` | 25 | 5 | 0 | 0 |
| legacy_expected_value | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/scenarios.py` | 14 | 1 | 0 | 1 |
| legacy_expected_value | `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/__init__.py` | 0 | 6 | 2 | 1 |
| legacy_expected_value | `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/expected_return.py` | 14 | 2 | 0 | 1 |
| legacy_expected_value | `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/opportunity_score.py` | 25 | 3 | 3 | 1 |
| legacy_expected_value | `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/payoff.py` | 16 | 1 | 1 | 1 |
| legacy_expected_value | `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/probabilities.py` | 19 | 2 | 0 | 1 |
| legacy_expected_value | `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/risk_reward.py` | 25 | 5 | 0 | 0 |
| legacy_expected_value | `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/scenarios.py` | 14 | 1 | 0 | 1 |
| current_engine | `src/signalforge/engines/strategy_selection/__init__.py` | 0 | 0 | 0 | 0 |
| current_engine | `src/signalforge/engines/strategy_selection/allocation.py` | 20 | 1 | 5 | 4 |
| current_engine | `src/signalforge/engines/strategy_selection/candidate_filter_decision.py` | 19 | 1 | 4 | 4 |
| current_engine | `src/signalforge/engines/strategy_selection/candidates.py` | 15 | 4 | 5 | 2 |
| current_engine | `src/signalforge/engines/strategy_selection/contract_candidate_scoring.py` | 23 | 4 | 7 | 6 |
| current_engine | `src/signalforge/engines/strategy_selection/evaluator.py` | 7 | 2 | 4 | 2 |
| current_engine | `src/signalforge/engines/strategy_selection/execution_qualified_historical_strategy_candidates_v21.py` | 7 | 1 | 5 | 13 |
| current_engine | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | 21 | 4 | 5 | 5 |
| current_engine | `src/signalforge/engines/strategy_selection/filters.py` | 33 | 4 | 4 | 2 |
| current_engine | `src/signalforge/engines/strategy_selection/historical_replay_matrix_metadata_stamp.py` | 27 | 3 | 3 | 10 |
| current_engine | `src/signalforge/engines/strategy_selection/option_behavior_adapter.py` | 13 | 2 | 4 | 5 |
| current_engine | `src/signalforge/engines/strategy_selection/portfolio_candidate_input.py` | 15 | 4 | 5 | 5 |
| current_engine | `src/signalforge/engines/strategy_selection/ranking.py` | 13 | 3 | 7 | 1 |
| current_engine | `src/signalforge/engines/strategy_selection/repaired_historical_strategy_candidates_v13_v21.py` | 9 | 2 | 3 | 12 |
| current_engine | `src/signalforge/engines/strategy_selection/research_adapter.py` | 15 | 1 | 5 | 3 |
| current_engine | `src/signalforge/engines/strategy_selection/resolved_strategy_execution_rules_v21.py` | 7 | 1 | 3 | 11 |
| current_engine | `src/signalforge/engines/strategy_selection/rules.py` | 19 | 2 | 6 | 2 |
| current_engine | `src/signalforge/engines/strategy_selection/selection_decision.py` | 10 | 7 | 6 | 8 |
| current_engine | `src/signalforge/engines/strategy_selection/selection_report.py` | 7 | 2 | 7 | 3 |
| current_engine | `src/signalforge/engines/strategy_selection/selector.py` | 7 | 3 | 7 | 2 |
| current_engine | `src/signalforge/engines/strategy_selection/strategy_family_eligibility.py` | 26 | 4 | 5 | 8 |
| current_engine | `src/signalforge/engines/strategy_selection/strategy_family_eligibility_cli.py` | 2 | 0 | 3 | 8 |
| current_engine | `src/signalforge/engines/strategy_selection/strategy_family_eligibility_file_writer.py` | 2 | 2 | 2 | 9 |
| current_engine | `src/signalforge/engines/strategy_selection/strategy_structure_availability_v21.py` | 16 | 0 | 3 | 11 |
| backtesting_walk_forward | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | 22 | 5 | 4 | 14 |
| backtesting_walk_forward | `src/signalforge/backtesting/walk_forward_expectancy_cli.py` | 2 | 3 | 1 | 10 |

## Legacy Promote Candidates

| classification | target | file | symbol | kind | reason | EV score | selection score | orchestration score |
|---|---|---|---|---|---|---:|---:|---:|
| promote_candidate_expected_value_engine | `src/signalforge/engines/expected_value` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | `score_vega` | function | pure_or_reusable_expected_value_terms | 3 | 0 | 1 |
| review_for_strategy_selection_expected_value_scoring | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | `rank_opportunities` | function | expected_value_logic_plus_strategy_selection_terms | 3 | 2 | 1 |
| review_for_strategy_selection_expected_value_scoring | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | `passes_minimum_thresholds` | function | expected_value_logic_plus_strategy_selection_terms | 3 | 2 | 1 |
| promote_candidate_expected_value_engine | `src/signalforge/engines/expected_value` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | `filter_opportunities` | function | pure_or_reusable_expected_value_terms | 3 | 0 | 1 |
| promote_candidate_expected_value_engine | `src/signalforge/engines/expected_value` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/risk_reward.py` | `profit_factor` | function | pure_or_reusable_expected_value_terms | 4 | 0 | 1 |
| promote_candidate_expected_value_engine | `src/signalforge/engines/expected_value` | `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/opportunity_score.py` | `score_vega` | function | pure_or_reusable_expected_value_terms | 3 | 0 | 0 |
| review_for_strategy_selection_expected_value_scoring | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/opportunity_score.py` | `rank_opportunities` | function | expected_value_logic_plus_strategy_selection_terms | 3 | 2 | 0 |
| review_for_strategy_selection_expected_value_scoring | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/opportunity_score.py` | `passes_minimum_thresholds` | function | expected_value_logic_plus_strategy_selection_terms | 3 | 2 | 0 |
| promote_candidate_expected_value_engine | `src/signalforge/engines/expected_value` | `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/opportunity_score.py` | `filter_opportunities` | function | pure_or_reusable_expected_value_terms | 3 | 0 | 0 |
| promote_candidate_expected_value_engine | `src/signalforge/engines/expected_value` | `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/risk_reward.py` | `profit_factor` | function | pure_or_reusable_expected_value_terms | 4 | 0 | 0 |

## Legacy Keep-Orchestration Rows

| file | symbol | reason | IO calls |
|---|---|---|---|
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/expected_return.py` | `ScenarioPayoff` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/expected_return.py` | `ExpectedValueResult` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/expected_return.py` | `expected_value` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/expected_return.py` | `scenario_payoff_breakdown` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/expected_return.py` | `expected_value_from_payoffs` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/expected_return.py` | `expected_return` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/expected_return.py` | `annualized_expected_return` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/expected_return.py` | `compounded_annualized_return` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/expected_return.py` | `probability_of_positive_payoff` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/expected_return.py` | `probability_of_negative_payoff` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/expected_return.py` | `average_positive_payoff` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/expected_return.py` | `average_negative_payoff` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/expected_return.py` | `expected_return_from_scenarios` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | `validate_weights` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | `total_weight` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/payoff.py` | `PayoffPoint` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/payoff.py` | `_validate_price` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/payoff.py` | `intrinsic_value` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/payoff.py` | `long_call_payoff` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/payoff.py` | `short_call_payoff` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/payoff.py` | `long_put_payoff` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/payoff.py` | `short_put_payoff` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/payoff.py` | `stock_payoff` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/payoff.py` | `covered_call_payoff` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/payoff.py` | `protective_put_payoff` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/probabilities.py` | `ProbabilityInputs` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/probabilities.py` | `clamp_probability` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/probabilities.py` | `normal_pdf` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/probabilities.py` | `normal_cdf` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/probabilities.py` | `_validate_positive` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/probabilities.py` | `_forward_price` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/probabilities.py` | `expected_move_price` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/probabilities.py` | `probability_above_price` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/probabilities.py` | `probability_below_price` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/probabilities.py` | `probability_between_prices` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/probabilities.py` | `probability_itm_call` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/probabilities.py` | `probability_itm_put` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/probabilities.py` | `probability_otm_call` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/probabilities.py` | `probability_otm_put` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/probabilities.py` | `probability_touch` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/risk_reward.py` | `_absolute_risk` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/risk_reward.py` | `reward_risk_ratio` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/risk_reward.py` | `risk_reward_ratio` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/risk_reward.py` | `max_profit_long_call` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/risk_reward.py` | `max_loss_long_call` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/risk_reward.py` | `max_profit_short_call` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/risk_reward.py` | `max_loss_short_call` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/risk_reward.py` | `max_profit_long_put` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/risk_reward.py` | `max_loss_long_put` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/risk_reward.py` | `max_profit_short_put` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/risk_reward.py` | `max_loss_short_put` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/risk_reward.py` | `max_profit_debit_spread` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/risk_reward.py` | `max_loss_debit_spread` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/risk_reward.py` | `max_profit_credit_spread` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/risk_reward.py` | `max_loss_credit_spread` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/risk_reward.py` | `return_on_risk` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/scenarios.py` | `Scenario` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/scenarios.py` | `ScenarioSet` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/scenarios.py` | `_validate_spot` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/scenarios.py` | `_validate_probability` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/scenarios.py` | `validate_scenarios` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/scenarios.py` | `normalize_scenarios` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/scenarios.py` | `scenario_from_return` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/scenarios.py` | `generate_price_scenarios` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/scenarios.py` | `bull_base_bear_scenarios` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/scenarios.py` | `custom_return_scenarios` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/scenarios.py` | `downside_stress_scenarios` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/scenarios.py` | `weighted_average_price` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/scenarios.py` | `expected_scenario_return` | io_or_walk_forward_artifact_terms_dominate |  |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/scenarios.py` | `scenario_prices` | io_or_walk_forward_artifact_terms_dominate |  |
| `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/expected_return.py` | `expected_value` | io_or_walk_forward_artifact_terms_dominate |  |
| `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/expected_return.py` | `scenario_payoff_breakdown` | io_or_walk_forward_artifact_terms_dominate |  |
| `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/expected_return.py` | `probability_of_positive_payoff` | io_or_walk_forward_artifact_terms_dominate |  |
| `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/expected_return.py` | `probability_of_negative_payoff` | io_or_walk_forward_artifact_terms_dominate |  |
| `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/expected_return.py` | `average_positive_payoff` | io_or_walk_forward_artifact_terms_dominate |  |
| `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/expected_return.py` | `average_negative_payoff` | io_or_walk_forward_artifact_terms_dominate |  |
| `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/payoff.py` | `_validate_price` | io_or_walk_forward_artifact_terms_dominate |  |
| `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/payoff.py` | `intrinsic_value` | io_or_walk_forward_artifact_terms_dominate |  |
| `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/probabilities.py` | `_validate_positive` | io_or_walk_forward_artifact_terms_dominate |  |
| `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/probabilities.py` | `expected_move_price` | io_or_walk_forward_artifact_terms_dominate |  |
| `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/probabilities.py` | `probability_between_prices` | io_or_walk_forward_artifact_terms_dominate |  |
| `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/probabilities.py` | `probability_touch` | io_or_walk_forward_artifact_terms_dominate |  |
| `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/scenarios.py` | `_validate_spot` | io_or_walk_forward_artifact_terms_dominate |  |
| `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/scenarios.py` | `_validate_probability` | io_or_walk_forward_artifact_terms_dominate |  |
| `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/scenarios.py` | `validate_scenarios` | io_or_walk_forward_artifact_terms_dominate |  |
| `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/scenarios.py` | `scenario_from_return` | io_or_walk_forward_artifact_terms_dominate |  |
| `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/scenarios.py` | `custom_return_scenarios` | io_or_walk_forward_artifact_terms_dominate |  |
| `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/scenarios.py` | `weighted_average_price` | io_or_walk_forward_artifact_terms_dominate |  |
| `legacy/source_snapshots/v3_2_2/old_repo/src/expected_value/scenarios.py` | `expected_scenario_return` | io_or_walk_forward_artifact_terms_dominate |  |

## Warnings

- stage37a_is_read_only_no_logic_moved
- walk_forward_expectancy_builder_should_remain_backtesting_orchestration
- promote_only_pure_expected_value_or_strategy_scoring_helpers_after_source_slice_parity_review