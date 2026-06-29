# Legacy Source Migration Graph

## Summary

- Source root: `legacy\source_snapshots\v3_2_2\old_repo\src`
- Targets: `backtesting/portfolio_position_sizing_replay.py, backtesting/portfolio_position_sizing_replay_cli.py`
- Node count: 2
- Internal dependency count: 1
- Missing internal dependency count: 0
- External import count: 11
- Is ready: True

## Files in migration cut

### `backtesting/portfolio_position_sizing_replay.py`

- Module: `backtesting.portfolio_position_sizing_replay`
- Size bytes: 27641
- SHA-256: `97993c38acdb147a09283a35150b4f2ae798b076f2a5e1025b212edf763617b0`
- Definitions: class:PortfolioPositionSizingReplayResult, function:read_json, function:read_jsonl, function:write_json, function:write_jsonl, function:_coerce_float, function:_coerce_int, function:_get_by_path, function:_truthy, function:_extract_execution_realism_fields, function:_execution_realism_coverage, function:_sequence_sort_key, function:_as_list, function:_mean, function:_breakdown_by, function:build_portfolio_position_sizing_replay, function:build_from_paths
- Internal dependencies: 0
- Missing internal dependencies: 0

### `backtesting/portfolio_position_sizing_replay_cli.py`

- Module: `backtesting.portfolio_position_sizing_replay_cli`
- Size bytes: 2576
- SHA-256: `ed1e4b354949ff9f5fdf655eed99d72829b46c48589984a8e4cffe4d6a694df5`
- Definitions: function:parse_args, function:main
- Internal dependencies: 1
- Missing internal dependencies: 0

Internal dependencies:
- `backtesting/portfolio_position_sizing_replay.py`
