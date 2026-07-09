# Stage 36B Backtesting-to-Engine Import Boundary Map

- is_ready: True
- blocker_count: 0
- matched_file_count: 75
- old_owner_reference_file_count: 6
- backtesting_boundary_file_count: 37
- live_trade_supported: False
- paper_order_created: False
- live_order_created: False

## Bucket Counts

- backtesting_consumer_or_legacy_owner: 37
- bootstrap_consumer: 2
- engine_strategy_selection: 17
- legacy_options_execution_owner_or_wrapper_candidate: 4
- other_consumer: 10
- paper_live_engine_consumer: 5

## Action Counts

- already_points_to_engine_review_only: 1
- inspect_for_embedded_strategy_selection_logic: 30
- keep_engine_source: 17
- replace_logic_or_imports_with_engine_module_after_boundary_review: 6
- review_reference: 21

## Boundary Rows

| bucket | action | path | old refs | engine refs | terms |
|---|---|---|---|---|---|
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/historical_decision_rows.py` |  |  | strategy_selection |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py` |  |  | historical_strategy_candidate_rows, strategy_selection |
| backtesting_consumer_or_legacy_owner | replace_logic_or_imports_with_engine_module_after_boundary_review | `src/signalforge/backtesting/historical_strategy_candidate_rows_cli.py` | signalforge.backtesting.historical_strategy_candidate_rows_builder |  | historical_strategy_candidate_rows |
| backtesting_consumer_or_legacy_owner | already_points_to_engine_review_only | `src/signalforge/backtesting/historical_strategy_family_eligibility_enrichment.py` |  | signalforge.engines.strategy_selection.strategy_family_eligibility | strategy_selection |
| backtesting_consumer_or_legacy_owner | replace_logic_or_imports_with_engine_module_after_boundary_review | `src/signalforge/backtesting/historical_strategy_leg_selection_rows_cli.py` | signalforge.backtesting.historical_strategy_leg_selection_rows_builder |  |  |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/historical_strategy_selection_cohort_risk_cli.py` |  |  | historical_strategy_selection_rows, strategy_selection |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py` |  |  | historical_strategy_selection_rows, ranking, strategy_selection, walk_forward_expectancy |
| backtesting_consumer_or_legacy_owner | replace_logic_or_imports_with_engine_module_after_boundary_review | `src/signalforge/backtesting/historical_strategy_selection_rows_cli.py` | signalforge.backtesting.historical_strategy_selection_rows_builder |  | historical_strategy_selection_rows, strategy_selection |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/layer_field_carry_forward_enrichment_v2.py` |  |  | historical_strategy_selection_rows, strategy_selection |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/legacy_post_lock_disposition_audit.py` |  |  | historical_strategy_candidate_rows |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/migrated_workflow_artifact_paths.py` |  |  | historical_strategy_candidate_rows, historical_strategy_selection_rows, strategy_selection, walk_forward_expectancy |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/migrated_workflow_closure_audit.py` |  |  | historical_strategy_candidate_rows, strategy_selection, walk_forward_expectancy |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/migrated_workflow_dry_run_inputs.py` |  |  | historical_strategy_candidate_rows, historical_strategy_selection_rows, strategy_selection, walk_forward_expectancy |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/migrated_workflow_dry_run_plan.py` |  |  | historical_strategy_candidate_rows, historical_strategy_selection_rows, strategy_selection, walk_forward_expectancy |
| backtesting_consumer_or_legacy_owner | replace_logic_or_imports_with_engine_module_after_boundary_review | `src/signalforge/backtesting/migrated_workflow_manifest.py` | signalforge.backtesting.historical_strategy_candidate_rows_builder, signalforge.backtesting.historical_strategy_leg_selection_rows_builder, signalforge.backtesting.historical_strategy_selection_rows_builder, signalforge.backtesting.walk_forward_expectancy_availability_safe_builder, signalforge.backtesting.walk_forward_expectancy_builder | signalforge.engines.strategy_selection.strategy_family_eligibility | historical_strategy_candidate_rows, historical_strategy_selection_rows, strategy_selection, walk_forward_expectancy |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/migrated_workflow_stage0_artifact_contract_replay.py` |  |  | historical_strategy_candidate_rows, historical_strategy_selection_rows, strategy_selection, walk_forward_expectancy |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/migrated_workflow_stage10_selected_trade_sequence_rebuild_probe.py` |  |  | historical_strategy_selection_rows, strategy_selection |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/migrated_workflow_stage3_semantic_continuity_replay.py` |  |  | historical_strategy_candidate_rows, historical_strategy_selection_rows, strategy_selection, walk_forward_expectancy |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/migrated_workflow_stage5_candidate_rebuild_probe.py` |  |  | historical_strategy_candidate_rows |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/migrated_workflow_stage5_candidate_rebuild_validation.py` |  |  | historical_strategy_candidate_rows |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/migrated_workflow_stage6_expectancy_rebuild_probe.py` |  |  | walk_forward_expectancy |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/migrated_workflow_stage6_expectancy_rebuild_validation.py` |  |  | walk_forward_expectancy |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/migrated_workflow_stage7_strategy_selection_rebuild_probe.py` |  |  | historical_strategy_selection_rows, strategy_selection, walk_forward_expectancy |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/migrated_workflow_stage7_strategy_selection_rebuild_validation.py` |  |  | historical_strategy_selection_rows, strategy_selection |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/migrated_workflow_stage8_strategy_leg_selection_rebuild_probe.py` |  |  | historical_strategy_candidate_rows, historical_strategy_selection_rows, strategy_selection, walk_forward_expectancy |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/migrated_workflow_stage9_position_sizing_rebuild_probe.py` |  |  | historical_strategy_selection_rows, strategy_selection |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/phase6_portfolio_reconstruction_qc_manifest.py` |  |  | strategy_selection |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/portfolio_construction_rule_sensitivity_cli.py` |  |  | ranking |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/portfolio_equity_reconstruction.py` |  |  | strategy_selection |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/portfolio_metrics_report.py` |  |  | strategy_selection |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/portfolio_position_sizing_replay.py` |  |  | strategy_selection |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/portfolio_selected_trade_sequence.py` |  |  | strategy_selection |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/portfolio_selected_trade_sequence_cli.py` |  |  | strategy_selection |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/walk_forward_expectancy_availability_safe_builder.py` |  |  | ranking, walk_forward_expectancy |
| backtesting_consumer_or_legacy_owner | replace_logic_or_imports_with_engine_module_after_boundary_review | `src/signalforge/backtesting/walk_forward_expectancy_availability_safe_cli.py` | signalforge.backtesting.walk_forward_expectancy_availability_safe_builder |  | walk_forward_expectancy |
| backtesting_consumer_or_legacy_owner | inspect_for_embedded_strategy_selection_logic | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` |  |  | walk_forward_expectancy |
| backtesting_consumer_or_legacy_owner | replace_logic_or_imports_with_engine_module_after_boundary_review | `src/signalforge/backtesting/walk_forward_expectancy_cli.py` | signalforge.backtesting.walk_forward_expectancy_builder |  | walk_forward_expectancy |
| bootstrap_consumer | review_reference | `src/signalforge/bootstrap/bootstrap_sequence.py` |  |  | strategy_selection |
| bootstrap_consumer | review_reference | `src/signalforge/bootstrap/strategy_selection_bootstrap.py` |  |  | historical_strategy_selection_rows, strategy_selection |
| engine_strategy_selection | keep_engine_source | `src/signalforge/engines/strategy_selection/allocation.py` |  | signalforge.engines.strategy_selection.candidates | strategy_selection |
| engine_strategy_selection | keep_engine_source | `src/signalforge/engines/strategy_selection/contract_candidate_scoring.py` |  |  | ranking |
| engine_strategy_selection | keep_engine_source | `src/signalforge/engines/strategy_selection/evaluator.py` |  |  | strategy_selection |
| engine_strategy_selection | keep_engine_source | `src/signalforge/engines/strategy_selection/execution_qualified_historical_strategy_candidates_v21.py` |  |  | execution_qualified_historical_strategy_candidates, historical_strategy_selection_rows, resolved_strategy_execution_rules, strategy_selection |
| engine_strategy_selection | keep_engine_source | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` |  |  | expected_value_scoring |
| engine_strategy_selection | keep_engine_source | `src/signalforge/engines/strategy_selection/filters.py` |  | signalforge.engines.strategy_selection.candidates | strategy_selection |
| engine_strategy_selection | keep_engine_source | `src/signalforge/engines/strategy_selection/option_behavior_adapter.py` |  |  | strategy_selection |
| engine_strategy_selection | keep_engine_source | `src/signalforge/engines/strategy_selection/portfolio_candidate_input.py` |  |  | portfolio_candidate_input |
| engine_strategy_selection | keep_engine_source | `src/signalforge/engines/strategy_selection/ranking.py` |  | signalforge.engines.strategy_selection.candidates | ranking, strategy_selection |
| engine_strategy_selection | keep_engine_source | `src/signalforge/engines/strategy_selection/repaired_historical_strategy_candidates_v13_v21.py` |  |  | execution_qualified_historical_strategy_candidates, repaired_historical_strategy_candidates, resolved_strategy_execution_rules |
| engine_strategy_selection | keep_engine_source | `src/signalforge/engines/strategy_selection/resolved_strategy_execution_rules_v21.py` |  |  | resolved_strategy_execution_rules, strategy_structure_availability |
| engine_strategy_selection | keep_engine_source | `src/signalforge/engines/strategy_selection/rules.py` |  | signalforge.engines.strategy_selection.candidates | strategy_selection |
| engine_strategy_selection | keep_engine_source | `src/signalforge/engines/strategy_selection/selection_report.py` |  |  | ranking, strategy_selection |
| engine_strategy_selection | keep_engine_source | `src/signalforge/engines/strategy_selection/selector.py` |  | signalforge.engines.strategy_selection.candidates, signalforge.engines.strategy_selection.filters, signalforge.engines.strategy_selection.ranking | ranking, selector, strategy_selection |
| engine_strategy_selection | keep_engine_source | `src/signalforge/engines/strategy_selection/strategy_family_eligibility.py` |  |  | expected_value_scoring, strategy_selection |
| engine_strategy_selection | keep_engine_source | `src/signalforge/engines/strategy_selection/strategy_family_eligibility_cli.py` |  | signalforge.engines.strategy_selection.strategy_family_eligibility | strategy_selection |
| engine_strategy_selection | keep_engine_source | `src/signalforge/engines/strategy_selection/strategy_structure_availability_v21.py` |  |  | strategy_structure_availability |
| legacy_options_execution_owner_or_wrapper_candidate | review_reference | `src/signalforge/options_execution/execution_qualified_historical_strategy_candidates_v21.py` |  |  | execution_qualified_historical_strategy_candidates, historical_strategy_selection_rows, resolved_strategy_execution_rules, strategy_selection |
| legacy_options_execution_owner_or_wrapper_candidate | review_reference | `src/signalforge/options_execution/repaired_historical_strategy_candidates_v13_v21.py` |  |  | execution_qualified_historical_strategy_candidates, repaired_historical_strategy_candidates, resolved_strategy_execution_rules |
| legacy_options_execution_owner_or_wrapper_candidate | review_reference | `src/signalforge/options_execution/resolved_strategy_execution_rules_v21.py` |  |  | resolved_strategy_execution_rules, strategy_structure_availability |
| legacy_options_execution_owner_or_wrapper_candidate | review_reference | `src/signalforge/options_execution/strategy_structure_availability_v21.py` |  |  | strategy_structure_availability |
| other_consumer | review_reference | `src/signalforge/contracts/runtime_inputs.py` |  |  | strategy_selection |
| other_consumer | review_reference | `src/signalforge/contracts/runtime_source_map.py` |  |  | historical_strategy_selection_rows, strategy_selection |
| other_consumer | review_reference | `src/signalforge/data/seed_bundle.py` |  |  | historical_strategy_selection_rows, strategy_selection |
| other_consumer | review_reference | `src/signalforge/engines/alignment/historical_regime_asset_options_alignment_cli.py` |  |  | strategy_selection |
| other_consumer | review_reference | `src/signalforge/engines/alignment/regime_asset_options_alignment.py` |  |  | strategy_selection |
| other_consumer | review_reference | `src/signalforge/engines/behavior/options_setup_policy.py` |  |  | strategy_selection |
| other_consumer | review_reference | `src/signalforge/engines/options/options_behavior_integration.py` |  |  | strategy_selection |
| other_consumer | review_reference | `src/signalforge/engines/options/options_behavior_orats_gap_review.py` |  |  | strategy_selection |
| other_consumer | review_reference | `src/signalforge/engines/options_strategy/setup_matcher.py` |  |  | strategy_selection |
| other_consumer | review_reference | `src/signalforge/migration/legacy_source_graph.py` |  |  | strategy_selection |
| paper_live_engine_consumer | review_reference | `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` |  |  | ranking |
| paper_live_engine_consumer | review_reference | `src/paper_live_engine/legacy_domain/old_repo/src/optimizer/objective.py` |  |  | ranking |
| paper_live_engine_consumer | review_reference | `src/paper_live_engine/legacy_domain/old_repo/src/optimizer/solver.py` |  |  | ranking |
| paper_live_engine_consumer | review_reference | `src/paper_live_engine/legacy_domain/old_repo/src/portfolio_construction/operation_runner.py` |  |  | strategy_selection |
| paper_live_engine_consumer | review_reference | `src/paper_live_engine/legacy_domain/old_repo/src/portfolio_construction/strategy_adapter.py` |  |  | strategy_selection |

## Warnings

- old_owner_references_detected_expected_before_wrapper_migration
- stage36b_is_read_only_no_imports_modified
- next_stage_should_create_wrappers_or_update_backtesting_imports_one_group_at_a_time