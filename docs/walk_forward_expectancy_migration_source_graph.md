# Legacy Source Migration Graph

## Summary

- Source root: `legacy\source_snapshots\v3_2_2\old_repo\src`
- Targets: `backtesting/walk_forward_expectancy_builder.py, backtesting/walk_forward_expectancy_cli.py, backtesting/walk_forward_expectancy_availability_safe_builder.py, backtesting/walk_forward_expectancy_availability_safe_cli.py`
- Node count: 4
- Internal dependency count: 2
- Missing internal dependency count: 0
- External import count: 24
- Is ready: True

## Files in migration cut

### `backtesting/walk_forward_expectancy_availability_safe_builder.py`

- Module: `backtesting.walk_forward_expectancy_availability_safe_builder`
- Size bytes: 16727
- SHA-256: `a67899364f620a9cac024175ee8ad77cc3ed69f59fc00783eb2f36460bbfad1c`
- Definitions: function:_as_float, function:_as_date, function:_parse_date, function:_date_text, function:read_jsonl, function:write_jsonl, function:write_json, function:_field_any, function:_field, function:_strategy_key, function:_scope_keys, function:_row_id, function:_training_sample, function:_valid_samples, function:_metrics, function:_classify, function:_choose_scope, function:build_walk_forward_expectancy_rows
- Internal dependencies: 0
- Missing internal dependencies: 0

### `backtesting/walk_forward_expectancy_availability_safe_cli.py`

- Module: `backtesting.walk_forward_expectancy_availability_safe_cli`
- Size bytes: 934
- SHA-256: `6201b8e7955fa1b548482719d3e3585ad675e4ef030237576cad7e0180db1cb4`
- Definitions: function:main
- Internal dependencies: 1
- Missing internal dependencies: 0

Internal dependencies:
- `backtesting/walk_forward_expectancy_availability_safe_builder.py`

### `backtesting/walk_forward_expectancy_builder.py`

- Module: `backtesting.walk_forward_expectancy_builder`
- Size bytes: 21217
- SHA-256: `cf22e5b75f3592f5f08feb033792cdd7be230f84169c5fc1761deabc216baee0`
- Definitions: class:FieldValues, class:TrainingExample, class:RunningStats, function:read_jsonl, function:write_jsonl, function:write_json, function:_first_present, function:_normalise_component, function:_parse_date, function:_parse_float, function:_decision_date_for_row, function:_field_values, function:_return_value_for_row, function:_availability_date_for_row, function:_scope_key, function:_state_for_stats, function:_select_stats, function:_make_training_examples, function:_add_example_to_aggregators, function:_iso, function:build_walk_forward_expectancy_rows, function:build_walk_forward_expectancy_artifact
- Internal dependencies: 0
- Missing internal dependencies: 0

### `backtesting/walk_forward_expectancy_cli.py`

- Module: `backtesting.walk_forward_expectancy_cli`
- Size bytes: 1358
- SHA-256: `960e1e710d165b0a396d75a2febe0359ec1d006d6a9bd76de87941fcd1d0d4ed`
- Definitions: function:build_parser, function:main
- Internal dependencies: 1
- Missing internal dependencies: 0

Internal dependencies:
- `backtesting/walk_forward_expectancy_builder.py`
