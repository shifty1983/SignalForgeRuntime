# Stage 36E Stage 09/10 Entrypoint + Wrapper Parity Inventory

- is_ready: True
- blocker_count: 0
- module_pair_count: 4
- export_row_count: 81
- likely_entrypoint_count: 11
- paper_order_created: False
- live_order_created: False
- live_trade_supported: False

## Likely Entrypoints

| stage | name | kind | signature | same object through wrapper |
|---|---|---|---|---:|
| stage09_structure_availability | `build_strategy_structure_availability` | function | `(contract_features_path: 'Path', output_dir: 'Path', keep_sqlite: 'bool' = False) -> 'dict[str, Any]'` | True |
| stage09_structure_availability | `create_sqlite` | function | `(contract_features_path: 'Path', sqlite_path: 'Path') -> 'dict[str, Any]'` | True |
| stage09_structure_availability | `main` | function | `() -> 'int'` | True |
| stage10_resolved_execution_rules | `build_resolved_rules` | function | `(metric_overlay_path: 'Path', strategy_structure_availability_path: 'Path', output_dir: 'Path') -> 'dict[str, Any]'` | True |
| stage10_resolved_execution_rules | `main` | function | `() -> 'int'` | True |
| stage10_resolved_execution_rules | `resolve_row` | function | `(availability: 'dict[str, Any]', overlay: 'dict[str, Any] | None') -> 'dict[str, Any]'` | True |
| stage11_execution_qualified_candidates | `build_execution_qualified_candidates` | function | `(historical_strategy_selection_rows_path: 'Path', resolved_strategy_execution_rules_path: 'Path', output_dir: 'Path') -> 'dict[str, Any]'` | True |
| stage11_execution_qualified_candidates | `main` | function | `() -> 'int'` | True |
| stage12_repaired_strategy_candidates | `build_repaired_candidates` | function | `(eligibility_rows_path: 'Path', resolved_rules_path: 'Path', output_dir: 'Path') -> 'dict[str, Any]'` | True |
| stage12_repaired_strategy_candidates | `load_rules` | function | `(path: 'Path') -> 'dict[tuple[str, str, str], dict[str, Any]]'` | True |
| stage12_repaired_strategy_candidates | `main` | function | `() -> 'int'` | True |

## Warnings

- stage36e_is_entrypoint_and_wrapper_identity_inventory_not_data_replay
- next_stage_should_use_likely_entrypoints_for_small_fixture_output_parity