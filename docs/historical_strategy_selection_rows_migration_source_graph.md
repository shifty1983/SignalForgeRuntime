# Legacy Source Migration Graph

## Summary

- Source root: `legacy\source_snapshots\v3_2_2\old_repo\src`
- Targets: `backtesting/historical_strategy_selection_rows_builder.py, backtesting/historical_strategy_selection_rows_cli.py`
- Node count: 2
- Internal dependency count: 1
- Missing internal dependency count: 0
- External import count: 9
- Is ready: True

## Files in migration cut

### `backtesting/historical_strategy_selection_rows_builder.py`

- Module: `backtesting.historical_strategy_selection_rows_builder`
- Size bytes: 17868
- SHA-256: `ca11a15d14eebd0c3d67000e809955052a0b0c91184db0f0fb23a645546d4115`
- Definitions: function:_as_float, function:_as_int, function:_date, function:read_jsonl, function:write_jsonl, function:write_json, function:_decision_group_key, function:_candidate_id, function:_is_selectable, function:_selection_score, function:_sample_confidence_multiplier, function:_scope_confidence_multiplier, function:_confidence_adjusted_selection_score, function:_rank_tuple, function:_selection_row, function:build_historical_strategy_selection_rows_artifact
- Internal dependencies: 0
- Missing internal dependencies: 0

### `backtesting/historical_strategy_selection_rows_cli.py`

- Module: `backtesting.historical_strategy_selection_rows_cli`
- Size bytes: 1388
- SHA-256: `b0a7b57de24c3db9e8db0202648eb4f49cf231074ef036d7de822e6335efbd10`
- Definitions: function:main
- Internal dependencies: 1
- Missing internal dependencies: 0

Internal dependencies:
- `backtesting/historical_strategy_selection_rows_builder.py`
