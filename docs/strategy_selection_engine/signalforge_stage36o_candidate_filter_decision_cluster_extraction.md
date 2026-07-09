# Stage 36O Candidate Filter Decision Cluster Extraction

- is_ready: True
- blocker_count: 0
- source_path: `src\signalforge\backtesting\historical_strategy_candidate_rows_builder.py`
- engine_path: `src\signalforge\engines\strategy_selection\candidate_filter_decision.py`
- backup_path: `docs\strategy_selection_engine\stage36o_backtesting_backups\historical_strategy_candidate_rows_builder.py.before_stage36o.py`
- extracted_function_count: 19
- module_bindings_copied: MISSING_VALUE
- paper_order_created: False
- live_order_created: False
- live_trade_supported: False

## Extracted Functions

- `_normalise_text`
- `_strategy_family_status_aliases`
- `_strategy_family_statuses`
- `_strategy_family_status`
- `_strategy_family_gate_block_reasons`
- `_as_dict`
- `_as_list`
- `_research_context_from_decision_row`
- `_eligibility`
- `_flag_is_true`
- `_nested_state`
- `_normalise_symbol`
- `_parse_option_behavior`
- `_decision_row_block_reasons`
- `_strategy_definition_block_reasons`
- `_has_term_structure_behavior`
- `_has_underlying_position`
- `_strategy_context_block_reasons`
- `_candidate_state`

## Wrapper Verification

| function | backtesting function is wrapper |
|---|---:|
| `_normalise_text` | True |
| `_strategy_family_status_aliases` | True |
| `_strategy_family_statuses` | True |
| `_strategy_family_status` | True |
| `_strategy_family_gate_block_reasons` | True |
| `_as_dict` | True |
| `_as_list` | True |
| `_research_context_from_decision_row` | True |
| `_eligibility` | True |
| `_flag_is_true` | True |
| `_nested_state` | True |
| `_normalise_symbol` | True |
| `_parse_option_behavior` | True |
| `_decision_row_block_reasons` | True |
| `_strategy_definition_block_reasons` | True |
| `_has_term_structure_behavior` | True |
| `_has_underlying_position` | True |
| `_strategy_context_block_reasons` | True |
| `_candidate_state` | True |

## Parity Rows

| function | original vs engine | engine vs patched wrapper |
|---|---:|---:|
| `_normalise_text` | True | True |
| `_strategy_family_status_aliases` | True | True |
| `_strategy_family_statuses` | True | True |
| `_strategy_family_status` | True | True |
| `_strategy_family_gate_block_reasons` | True | True |
| `_as_dict` | True | True |
| `_as_list` | True | True |
| `_research_context_from_decision_row` | True | True |
| `_eligibility` | True | True |
| `_flag_is_true` | True | True |
| `_nested_state` | True | True |
| `_normalise_symbol` | True | True |
| `_parse_option_behavior` | True | True |
| `_decision_row_block_reasons` | True | True |
| `_strategy_definition_block_reasons` | True | True |
| `_has_term_structure_behavior` | True | True |
| `_has_underlying_position` | True | True |
| `_strategy_context_block_reasons` | True | True |
| `_candidate_state` | True | True |

## Warnings

- stage36o_extracts_candidate_filter_decision_logic_only
- historical_candidate_row_builder_remains_in_backtesting
- stage36o_parity_uses_function_fixture_full_replay_parity_should_follow