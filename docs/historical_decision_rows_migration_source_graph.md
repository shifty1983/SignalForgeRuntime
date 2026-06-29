# Historical Decision Rows Migration Source Graph

## Summary

- Source root: `legacy\source_snapshots\v3_2_2\old_repo\src`
- Targets: `backtesting/historical_decision_rows.py, backtesting/historical_decision_rows_cli.py`
- Node count: 2
- Internal dependency count: 1
- Missing internal dependency count: 0
- External import count: 11
- Is ready: True

## Files in migration cut

### `backtesting/historical_decision_rows.py`

- Module: `backtesting.historical_decision_rows`
- Size bytes: 23234
- SHA-256: `167009b5629fd6450cae3ca79c3d6bf9791d9c8dbbaaaf46c4b06f4e00aefde6`
- Definitions: function:normalize_symbol, function:parse_date, function:iso, function:_first_present, function:_extract_state, function:_records_from_payload, function:load_records, function:load_json, function:_symbols_from_value, function:_get_path, function:_extract_symbols, function:extract_inventory_sets, function:_row_date, function:_row_symbol, function:_extract_state_from_row, function:build_weekly_regime_index, function:lookup_asof_weekly_regime, function:build_symbol_date_index, function:build_market_price_index, function:build_historical_decision_rows, function:write_historical_decision_rows
- Internal dependencies: 0
- Missing internal dependencies: 0

### `backtesting/historical_decision_rows_cli.py`

- Module: `backtesting.historical_decision_rows_cli`
- Size bytes: 3673
- SHA-256: `76d5b54f0236f9a371cbf5106d4d6cb60d6cffb667c6c8620eb21c5b9f7f0d54`
- Definitions: function:_split_symbols, function:main
- Internal dependencies: 1
- Missing internal dependencies: 0

Internal dependencies:
- `backtesting/historical_decision_rows.py`
