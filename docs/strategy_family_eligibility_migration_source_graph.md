# Legacy Source Migration Graph

## Summary

- Source root: `legacy\source_snapshots\v3_2_2\old_repo\src`
- Targets: `strategy_selection/strategy_family_eligibility.py, strategy_selection/strategy_family_eligibility_cli.py, strategy_selection/strategy_family_eligibility_file_writer.py`
- Node count: 5
- Internal dependency count: 4
- Missing internal dependency count: 0
- External import count: 21
- Is ready: True

## Files in migration cut

### `data_sources/data_source_inventory.py`

- Module: `data_sources.data_source_inventory`
- Size bytes: 21861
- SHA-256: `f6dc485f8170affda71e4071fefcdf93154edac564650d42fca39cf56641af37`
- Definitions: function:build_signalforge_data_source_inventory, function:_module_with_resolution, function:_decision_with_resolution, function:_category_summary, function:_module_summary, function:_adapter_backlog, function:_blocked_result, function:_as_mapping, function:_as_list
- Internal dependencies: 0
- Missing internal dependencies: 0

### `strategy_selection/historical_replay_matrix_metadata_stamp.py`

- Module: `strategy_selection.historical_replay_matrix_metadata_stamp`
- Size bytes: 24913
- SHA-256: `f920a92b3f280d36b12232a00ed1c035b1aa5e8fc92cee66bf4be6f330f9230a`
- Definitions: function:build_signalforge_historical_replay_matrix_metadata_stamping_helpers, function:build_matrix_metadata_envelope, function:stamp_matrix_metadata, function:validate_matrix_metadata_record, function:extract_candidate_matrix_metadata, function:normalize_matrix_metadata, function:normalize_matrix_metadata_value, function:normalize_symbol, function:normalize_horizon_days, function:merge_matrix_metadata, function:build_matrix_cell_key, function:matrix_metadata_coverage, function:summarize_signalforge_historical_replay_matrix_metadata_stamping_helpers, function:_helper_contract, function:_extract_patch_plan, function:_normalize_source_refs, function:_missing_required_fields, function:_stable_token, function:_deep_get, function:_has_value, function:_as_float_or_none, function:_as_int, function:_as_text_list, function:_as_mapping, function:_ordered_unique, function:_stable_id, function:_utc_now_iso
- Internal dependencies: 0
- Missing internal dependencies: 0

### `strategy_selection/strategy_family_eligibility.py`

- Module: `strategy_selection.strategy_family_eligibility`
- Size bytes: 37694
- SHA-256: `e6aa01e34b456b2812845e43dbf8cfac926e50b9ced0ad46d36791482b03e1aa`
- Definitions: class:_MissingType, function:build_signalforge_strategy_family_eligibility, function:_build_eligibility_item, function:_matrix_dimension_metadata_from_alignment, function:_strategy_family_matrix_metadata_items, function:_first_matrix_value, function:_as_mapping, function:_data_review_reasons, function:_risk_review_reasons, function:_is_data_review_reason, function:_is_risk_review_reason, function:_ev_handoff, function:_coverage_status_from_handoff, function:_constraint_flags, function:_favored_families, function:_family_statuses, function:_summary, function:_extract_items, function:_source_artifact_type, function:_looks_like_items, function:_first_value, function:_as_string_list, function:_ordered, function:_clean_symbol, function:_clean_text, function:_blocked_result
- Internal dependencies: 2
- Missing internal dependencies: 0

Internal dependencies:
- `data_sources/data_source_inventory.py`
- `strategy_selection/historical_replay_matrix_metadata_stamp.py`

### `strategy_selection/strategy_family_eligibility_cli.py`

- Module: `strategy_selection.strategy_family_eligibility_cli`
- Size bytes: 1424
- SHA-256: `3e71c125a1f61528f4f9945894ed207c3af1b3b38d1fdba994134aa070122bc4`
- Definitions: function:main, function:_read_json
- Internal dependencies: 2
- Missing internal dependencies: 0

Internal dependencies:
- `strategy_selection/strategy_family_eligibility.py`
- `strategy_selection/strategy_family_eligibility_file_writer.py`

### `strategy_selection/strategy_family_eligibility_file_writer.py`

- Module: `strategy_selection.strategy_family_eligibility_file_writer`
- Size bytes: 5749
- SHA-256: `cc5a229b6ae6471c2dec02c53aba9bf5e09844e9d7d70ee45d2535767e70d8fc`
- Definitions: function:write_strategy_family_eligibility_result, function:build_strategy_family_eligibility_summary
- Internal dependencies: 0
- Missing internal dependencies: 0
