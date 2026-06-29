# Historical Decision Rows Migration Source Graph

## Summary

- Source root: `legacy\source_snapshots\v3_2_2\old_repo\src`
- Targets: `backtesting/historical_strategy_candidate_rows_builder.py, backtesting/historical_strategy_candidate_rows_cli.py`
- Node count: 2
- Internal dependency count: 1
- Missing internal dependency count: 0
- External import count: 9
- Is ready: True

## Files in migration cut

### `backtesting/historical_strategy_candidate_rows_builder.py`

- Module: `backtesting.historical_strategy_candidate_rows_builder`
- Size bytes: 41286
- SHA-256: `91fab4e431b5e73db64730b6376b980bf217705424cc8e7e4e7882f15f0da2f9`
- Definitions: function:read_jsonl, function:write_jsonl, function:write_json, function:load_strategy_policy, function:_normalise_symbol, function:_normalise_text, function:_nested_state, function:_nested_source_date, function:_eligibility, function:_flag_is_true, function:_has_underlying_position, function:_has_term_structure_behavior, function:_parse_option_behavior, function:_decision_row_block_reasons, function:_strategy_definition_block_reasons, function:_strategy_context_block_reasons, function:_candidate_id, function:_strategy_instance, function:_candidate_state, function:build_historical_strategy_candidate_rows, function:build_historical_strategy_candidate_rows_artifact
- Internal dependencies: 0
- Missing internal dependencies: 0

### `backtesting/historical_strategy_candidate_rows_cli.py`

- Module: `backtesting.historical_strategy_candidate_rows_cli`
- Size bytes: 1461
- SHA-256: `1be7a362731bdb7c5aa8e7c91c006da37dcfddb75b808f3c05c8ab29c5f7edf6`
- Definitions: function:build_parser, function:main
- Internal dependencies: 1
- Missing internal dependencies: 0

Internal dependencies:
- `backtesting/historical_strategy_candidate_rows_builder.py`
