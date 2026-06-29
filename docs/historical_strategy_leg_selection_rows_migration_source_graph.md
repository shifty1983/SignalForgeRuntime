# Legacy Source Migration Graph

## Summary

- Source root: `legacy\source_snapshots\v3_2_2\old_repo\src`
- Targets: `backtesting/historical_strategy_leg_selection_rows_builder.py, backtesting/historical_strategy_leg_selection_rows_cli.py`
- Node count: 2
- Internal dependency count: 0
- Missing internal dependency count: 0
- External import count: 15
- Is ready: True

## Files in migration cut

### `backtesting/historical_strategy_leg_selection_rows_builder.py`

- Module: `backtesting.historical_strategy_leg_selection_rows_builder`
- Size bytes: 36674
- SHA-256: `b8c942ca0d136cca59b4e58bbf3fe8edb9f271d72b91a0938b2670ca53d45d9b`
- Definitions: function:_as_float, function:_as_int, function:_as_date, function:_median, function:_norm_symbol, function:read_jsonl, function:write_jsonl, function:write_json, function:_candidate_key, function:_option_key, function:_right, function:_mid, function:_valid_option, function:_dte, function:_strike, function:_delta_abs, function:_atm_score, function:_delta_score, function:_group_by_expiration, function:_expiration_dte, function:_select_expiration_group, function:_filter_right, function:_find_next_higher, function:_find_next_lower, function:_best_atm, function:_best_delta, function:_leg, function:_net_mid_debit, function:_selection_payload, function:_blocked_payload, function:_select_single_long, function:_select_vertical_debit, function:_select_vertical_credit, function:_select_iron_condor, function:_select_iron_butterfly, function:_term_expirations, function:_options_for_expiration, function:_front_back_available_for_exit, function:_select_calendar, function:_select_diagonal, function:select_legs_for_candidate, function:_load_candidate_rows, function:_build_option_index, function:build_historical_strategy_leg_selection_rows, function:build_historical_strategy_leg_selection_rows_artifact
- Internal dependencies: 0
- Missing internal dependencies: 0

### `backtesting/historical_strategy_leg_selection_rows_cli.py`

- Module: `backtesting.historical_strategy_leg_selection_rows_cli`
- Size bytes: 44748
- SHA-256: `3766db36f36480ed0a4b0c974e69fffd91d2cb8d76b7071c054c82e92367acb4`
- Definitions: function:_iter_jsonl, function:_write_json, function:_write_jsonl, function:_write_csv, function:_num, function:_text, function:_date, function:_symbol, function:_right, function:_strike, function:_dte, function:_mid, function:_spread_pct, function:_valid_contract, function:_leg, function:_group_by_expiration, function:_avg_dte, function:_choose_expiration, function:_candidate_expirations, function:_rank_by_delta, function:_contract_score, function:_choose_by_delta, function:_choose_by_strike, function:_choose_wing, function:_target_expiration_dte, function:_front_back_expirations, function:_net_mid, function:_select_long, function:_select_vertical, function:_select_iron_condor, function:_select_iron_butterfly, function:_select_calendar, function:_select_diagonal, function:_select_legs, function:_chain_metrics, function:_net_fields, function:_targeted_delta_specs, function:_iron_body_structure, function:_construction_quality, function:_build_selected_row, function:build_leg_selection_rows, function:main
- Internal dependencies: 0
- Missing internal dependencies: 0
