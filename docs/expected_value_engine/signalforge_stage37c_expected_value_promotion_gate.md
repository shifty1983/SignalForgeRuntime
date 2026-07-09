# Stage 37C Expected-Value Promotion Gate

- is_ready: True
- blocker_count: 0
- legacy_ev_cluster_symbol_count: 25
- reference_row_count: 181
- non_legacy_reference_row_count: 156
- walk_forward_reference_row_count: 0
- current_strategy_ev_reference_row_count: 0
- active_backtest_uses_legacy_ev_cluster: False
- promotion_gate_decision: `do_not_promote_legacy_expected_value_cluster_without_ab_backtest`
- walk_forward_owner: `src/signalforge/backtesting/walk_forward_expectancy_builder.py`
- expected_value_candidate_status: `research_candidate_only_until_ab_backtested`
- paper_order_created: False
- live_order_created: False
- live_trade_supported: False

## Decision

The legacy expected-value cluster is not promoted into production engines at this stage.
It is classified as research-candidate logic until it is tested through a controlled A/B backtest.

Walk-forward expectancy remains backtesting-owned because it performs historical training-window orchestration, as-of replay, artifact IO, and no-lookahead validation.

## Legacy EV Cluster Symbols

- `normalize`
- `inverse_normalize`
- `score_vega`
- `OpportunityMetrics`
- `ComponentScores`
- `ScoringWeights`
- `OpportunityScoreResult`
- `score_delta`
- `score_expected_return`
- `score_gamma`
- `score_implied_volatility`
- `score_liquidity`
- `score_probability_of_profit`
- `score_reward_risk`
- `score_risk`
- `score_theta`
- `component_scores`
- `validate_weights`
- `total_weight`
- `weighted_score`
- `score_opportunity`
- `rank_opportunities`
- `passes_minimum_thresholds`
- `filter_opportunities`
- `profit_factor`

## References

| symbol | path | legacy source | walk-forward backtest | current EV scoring engine |
|---|---|---:|---:|---:|
| `profit_factor` | `src/signalforge/backtesting/cohort_gate_v1_2_robustness_validation_cli.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/cohort_risk_rejection_gate_v1_1_cli.py` | False | False | False |
| `normalize` | `src/signalforge/backtesting/historical_behavior_row_normalizer.py` | False | False | False |
| `normalize` | `src/signalforge/backtesting/historical_behavior_row_normalizer_cli.py` | False | False | False |
| `normalize` | `src/signalforge/backtesting/historical_decision_rows.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/historical_strategy_selection_cohort_risk_cli.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/phase6_portfolio_reconstruction_qc_manifest.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/portfolio_capital_sufficiency_cli.py` | False | False | False |
| `normalize` | `src/signalforge/backtesting/portfolio_construction_rule_sensitivity_cli.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/portfolio_construction_rule_sensitivity_cli.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/portfolio_construction_rule_sensitivity_qc_manifest_cli.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/portfolio_equity_reconstruction.py` | False | False | False |
| `normalize` | `src/signalforge/backtesting/portfolio_exposure_constraint_sensitivity_cli.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/portfolio_exposure_constraint_sensitivity_cli.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/portfolio_exposure_constraint_sensitivity_qc_manifest_cli.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/portfolio_loss_pattern_attribution_cli.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/portfolio_loss_pocket_rule_sweep_cli.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/portfolio_loss_pocket_split_validation_cli.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/portfolio_metrics_report.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/portfolio_position_sizing_replay.py` | False | False | False |
| `normalize` | `src/signalforge/backtesting/portfolio_robustness_qc_manifest_cli.py` | False | False | False |
| `normalize` | `src/signalforge/backtesting/portfolio_robustness_stress_validation_cli.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/portfolio_robustness_stress_validation_cli.py` | False | False | False |
| `normalize` | `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/portfolio_value_ranked_allocator_v2.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/portfolio_value_ranked_allocator_v2_1_cli.py` | False | False | False |
| `normalize` | `src/signalforge/backtesting/qc_5y_data_inventory.py` | False | False | False |
| `normalize` | `src/signalforge/backtesting/qc_5y_data_inventory_gate.py` | False | False | False |
| `normalize` | `src/signalforge/backtesting/qc_5y_data_inventory_symbol_policy_from_split.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/v3_2_1_native_quote_attribution_v1.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/v3_2_1_native_quote_pnl_stress_v1.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/v3_2_1_native_quote_walkforward_prune_validation_v1.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/v3_2_2_iron_butterfly_dependence_v1.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/v3_2_2_native_quote_attribution_v1.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/v3_2_2_pre_broker_audit_pack_v1.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/v3_2_2_symbol_regime_walkforward_prune_stress_v1.py` | False | False | False |
| `profit_factor` | `src/signalforge/backtesting/v3_2_reconciled_canonical_from_v2_locked_actions.py` | False | False | False |
| `normalize` | `src/signalforge/bootstrap/asset_behavior_bootstrap.py` | False | False | False |
| `normalize` | `src/signalforge/bootstrap/closed_outcomes_bootstrap.py` | False | False | False |
| `normalize` | `src/signalforge/bootstrap/option_behavior_bootstrap.py` | False | False | False |
| `normalize` | `src/signalforge/bootstrap/portfolio_construction_bootstrap.py` | False | False | False |
| `profit_factor` | `src/signalforge/bootstrap/portfolio_construction_bootstrap.py` | False | False | False |
| `profit_factor` | `src/signalforge/bootstrap/prior_gate_asof_parity.py` | False | False | False |
| `normalize` | `src/signalforge/bootstrap/prior_gate_evaluation_outcomes_bootstrap.py` | False | False | False |
| `profit_factor` | `src/signalforge/bootstrap/prior_gate_skipped_row_parity.py` | False | False | False |
| `profit_factor` | `src/signalforge/bootstrap/prior_symbol_regime_state_builder.py` | False | False | False |
| `normalize` | `src/signalforge/bootstrap/strategy_selection_bootstrap.py` | False | False | False |
| `profit_factor` | `src/signalforge/bootstrap/v3_2_2_pre_trade_decisions_bootstrap.py` | False | False | False |
| `profit_factor` | `src/signalforge/bootstrap/v3_2_2_runtime_readiness_audit.py` | False | False | False |
| `normalize` | `src/signalforge/data/canonical_contract_outcomes_from_resolution_cli.py` | False | False | False |
| `normalize` | `src/signalforge/data/canonical_options_bootstrap_cli.py` | False | False | False |
| `normalize` | `src/signalforge/data/canonical_options_data_backfill_merge_cli.py` | False | False | False |
| `normalize` | `src/signalforge/data_sources/data_source_inventory.py` | False | False | False |
| `normalize` | `src/signalforge/engines/alignment/historical_regime_asset_options_alignment_cli.py` | False | False | False |
| `normalize` | `src/signalforge/engines/alignment/regime_asset_options_alignment.py` | False | False | False |
| `normalize` | `src/signalforge/engines/behavior/asset_behavior_selection.py` | False | False | False |
| `normalize` | `src/signalforge/engines/behavior/asset_multi_horizon_behavior.py` | False | False | False |
| `normalize` | `src/signalforge/engines/behavior/behavior_classifier.py` | False | False | False |
| `normalize` | `src/signalforge/engines/behavior/behavior_score.py` | False | False | False |
| `component_scores` | `src/signalforge/engines/behavior/behavior_score.py` | False | False | False |
| `total_weight` | `src/signalforge/engines/behavior/behavior_score.py` | False | False | False |
| `normalize` | `src/signalforge/engines/behavior/benchmark_symbol.py` | False | False | False |
| `normalize` | `src/signalforge/engines/behavior/diagnostics.py` | False | False | False |
| `normalize` | `src/signalforge/engines/behavior/market_price_behavior.py` | False | False | False |
| `normalize` | `src/signalforge/engines/behavior/options_setup_policy.py` | False | False | False |
| `normalize` | `src/signalforge/engines/options/options_behavior_orats_gap_review.py` | False | False | False |
| `normalize` | `src/signalforge/engines/options_behavior/options_strategy_policy.py` | False | False | False |
| `normalize` | `src/signalforge/engines/options_strategy/catalog.py` | False | False | False |
| `normalize` | `src/signalforge/engines/options_strategy/policy_alignment.py` | False | False | False |
| `normalize` | `src/signalforge/engines/regime/asset_class_policy.py` | False | False | False |
| `normalize` | `src/signalforge/engines/regime/fred_regime_pipeline_cli.py` | False | False | False |
| `normalize` | `src/signalforge/engines/regime/fred_source_builder.py` | False | False | False |
| `normalize` | `src/signalforge/engines/regime/fred_weekly_pipeline.py` | False | False | False |
| `normalize` | `src/signalforge/engines/regime/fred_weekly_regime_pipeline_cli.py` | False | False | False |
| `normalize` | `src/signalforge/engines/regime/market_proxy_overlay.py` | False | False | False |
| `weighted_score` | `src/signalforge/engines/regime/market_proxy_overlay.py` | False | False | False |
| `normalize` | `src/signalforge/engines/regime/options_policy.py` | False | False | False |
| `normalize` | `src/signalforge/engines/regime/options_strategy_fit.py` | False | False | False |
| `normalize` | `src/signalforge/engines/strategy_selection/allocation.py` | False | False | False |
| `total_weight` | `src/signalforge/engines/strategy_selection/allocation.py` | False | False | False |
| `normalize` | `src/signalforge/engines/strategy_selection/candidates.py` | False | False | False |
| `normalize` | `src/signalforge/engines/strategy_selection/contract_candidate_scoring.py` | False | False | False |
| `normalize` | `src/signalforge/engines/strategy_selection/execution_qualified_historical_strategy_candidates_v21.py` | False | False | False |
| `normalize` | `src/signalforge/engines/strategy_selection/filters.py` | False | False | False |
| `normalize` | `src/signalforge/engines/strategy_selection/historical_replay_matrix_metadata_stamp.py` | False | False | False |
| `normalize` | `src/signalforge/engines/strategy_selection/option_behavior_adapter.py` | False | False | False |
| `normalize` | `src/signalforge/engines/strategy_selection/ranking.py` | False | False | False |
| `total_weight` | `src/signalforge/engines/strategy_selection/ranking.py` | False | False | False |
| `weighted_score` | `src/signalforge/engines/strategy_selection/ranking.py` | False | False | False |
| `normalize` | `src/signalforge/engines/strategy_selection/research_adapter.py` | False | False | False |
| `normalize` | `src/signalforge/engines/strategy_selection/rules.py` | False | False | False |
| `normalize` | `src/signalforge/engines/strategy_selection/selector.py` | False | False | False |
| `total_weight` | `src/signalforge/engines/strategy_selection/selector.py` | False | False | False |
| `weighted_score` | `src/signalforge/engines/strategy_selection/selector.py` | False | False | False |
| `normalize` | `src/signalforge/options_execution/option_contract_execution_features_v21.py` | False | False | False |
| `profit_factor` | `src/signalforge/rulebooks/prior_symbol_regime_state.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `inverse_normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `score_vega` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `OpportunityMetrics` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `ComponentScores` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `ScoringWeights` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `OpportunityScoreResult` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `score_delta` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `score_expected_return` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `score_gamma` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `score_implied_volatility` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `score_liquidity` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `score_probability_of_profit` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `score_reward_risk` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `score_risk` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `score_theta` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `component_scores` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `validate_weights` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `total_weight` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `weighted_score` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `score_opportunity` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `rank_opportunities` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `passes_minimum_thresholds` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `filter_opportunities` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `profit_factor` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/__init__.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `inverse_normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `score_vega` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `OpportunityMetrics` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `ComponentScores` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `ScoringWeights` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `OpportunityScoreResult` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `score_delta` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `score_expected_return` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `score_gamma` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `score_implied_volatility` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `score_liquidity` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `score_probability_of_profit` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `score_reward_risk` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `score_risk` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `score_theta` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `component_scores` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `validate_weights` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `total_weight` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `weighted_score` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `score_opportunity` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `rank_opportunities` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `passes_minimum_thresholds` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `filter_opportunities` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | True | False | False |
| `profit_factor` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/risk_reward.py` | True | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/scenarios.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/hardening/reproducibility.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/optimizer/constraints.py` | False | False | False |
| `total_weight` | `src/paper_live_engine/legacy_domain/old_repo/src/optimizer/constraints.py` | False | False | False |
| `total_weight` | `src/paper_live_engine/legacy_domain/old_repo/src/optimizer/objective.py` | False | False | False |
| `weighted_score` | `src/paper_live_engine/legacy_domain/old_repo/src/optimizer/objective.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/optimizer/portfolio.py` | False | False | False |
| `total_weight` | `src/paper_live_engine/legacy_domain/old_repo/src/optimizer/portfolio.py` | False | False | False |
| `weighted_score` | `src/paper_live_engine/legacy_domain/old_repo/src/optimizer/portfolio.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/optimizer/rebalance.py` | False | False | False |
| `total_weight` | `src/paper_live_engine/legacy_domain/old_repo/src/optimizer/rebalance.py` | False | False | False |
| `total_weight` | `src/paper_live_engine/legacy_domain/old_repo/src/optimizer/solver.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/action_execution_record.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/action_execution_record_operation.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/action_outcome_record.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/action_outcome_record_operation.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/action_queue_operation.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/action_review.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/action_review_operation.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/control_report.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/control_report_manifest_builder_operation.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/control_report_operation.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/control_report_pipeline_operation.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/control_report_source_assembler.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/control_report_source_assembler_operation.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/edge_validation_review.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/edge_validation_review_operation.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/edge_validation_summary.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/edge_validation_summary_operation.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/strategy_decision_log.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/strategy_decision_log_operation.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/strategy_improvement_queue.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/strategy_improvement_queue_operation.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/strategy_improvement_review.py` | False | False | False |
| `normalize` | `src/paper_live_engine/legacy_domain/old_repo/src/options_portfolio/strategy_improvement_review_operation.py` | False | False | False |

## Warnings

- stage37c_is_read_only_no_logic_moved
- legacy_expected_value_cluster_is_research_candidate_until_backtested
- walk_forward_expectancy_builder_remains_backtesting_owned