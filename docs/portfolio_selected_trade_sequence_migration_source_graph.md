# Legacy Source Migration Graph

## Summary

- Source root: `legacy\source_snapshots\v3_2_2\old_repo\src`
- Targets: `backtesting/portfolio_selected_trade_sequence.py, backtesting/portfolio_selected_trade_sequence_cli.py`
- Node count: 2
- Internal dependency count: 1
- Missing internal dependency count: 0
- External import count: 11
- Is ready: True

## Files in migration cut

### `backtesting/portfolio_selected_trade_sequence.py`

- Module: `backtesting.portfolio_selected_trade_sequence`
- Size bytes: 21768
- SHA-256: `cb3ea8e7d7a92e144ca193bdc58eaf957e1e1d50d1bc2a19c76c4761c42c4948`
- Definitions: class:PortfolioSelectedTradeSequenceResult, function:read_json, function:read_jsonl, function:write_json, function:write_jsonl, function:_get_by_path, function:_first_present_with_path, function:_parse_date, function:_coerce_float, function:_string_or_none, function:_collect_data_states, function:_has_contract_outcome_missing_state, function:_extract_execution_realism_fields, function:_execution_realism_coverage, function:_extract_trade, function:_count_source_fields, function:build_portfolio_selected_trade_sequence, function:build_from_paths
- Internal dependencies: 0
- Missing internal dependencies: 0

### `backtesting/portfolio_selected_trade_sequence_cli.py`

- Module: `backtesting.portfolio_selected_trade_sequence_cli`
- Size bytes: 2240
- SHA-256: `5ef5ad97887e46aa147a444a925ae5520d95cad57a49f0364d759ac8ae8a9c18`
- Definitions: function:parse_args, function:main
- Internal dependencies: 1
- Missing internal dependencies: 0

Internal dependencies:
- `backtesting/portfolio_selected_trade_sequence.py`
