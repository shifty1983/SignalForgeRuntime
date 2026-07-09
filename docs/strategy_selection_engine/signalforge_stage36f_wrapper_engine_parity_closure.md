# Stage 36F Wrapper/Engine Parity Closure

- is_ready: True
- blocker_count: 0
- parity_state: wrapper_and_engine_entrypoints_identical
- module_pair_count: 4
- entrypoint_count: 11
- same_object_count: 11
- expected_same_object_count: 11
- paper_order_created: False
- live_order_created: False
- live_trade_supported: False

## Entrypoints

| stage | entrypoint | same object | signature |
|---|---|---:|---|
| stage09_structure_availability | `build_strategy_structure_availability` | True | `(contract_features_path: 'Path', output_dir: 'Path', keep_sqlite: 'bool' = False) -> 'dict[str, Any]'` |
| stage09_structure_availability | `create_sqlite` | True | `(contract_features_path: 'Path', sqlite_path: 'Path') -> 'dict[str, Any]'` |
| stage09_structure_availability | `main` | True | `() -> 'int'` |
| stage10_resolved_execution_rules | `build_resolved_rules` | True | `(metric_overlay_path: 'Path', strategy_structure_availability_path: 'Path', output_dir: 'Path') -> 'dict[str, Any]'` |
| stage10_resolved_execution_rules | `resolve_row` | True | `(availability: 'dict[str, Any]', overlay: 'dict[str, Any] | None') -> 'dict[str, Any]'` |
| stage10_resolved_execution_rules | `main` | True | `() -> 'int'` |
| stage11_execution_qualified_candidates | `build_execution_qualified_candidates` | True | `(historical_strategy_selection_rows_path: 'Path', resolved_strategy_execution_rules_path: 'Path', output_dir: 'Path') -> 'dict[str, Any]'` |
| stage11_execution_qualified_candidates | `main` | True | `() -> 'int'` |
| stage12_repaired_strategy_candidates | `build_repaired_candidates` | True | `(eligibility_rows_path: 'Path', resolved_rules_path: 'Path', output_dir: 'Path') -> 'dict[str, Any]'` |
| stage12_repaired_strategy_candidates | `load_rules` | True | `(path: 'Path') -> 'dict[tuple[str, str, str], dict[str, Any]]'` |
| stage12_repaired_strategy_candidates | `main` | True | `() -> 'int'` |

## Warnings

- stage36f_does_not_run_full_historical_replay
- same_object_wrapper_identity_guarantees_same_entrypoint_execution_path