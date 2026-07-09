# Stage 36N2 Candidate Filter Recursive Dependency Review

- is_ready: True
- blocker_count: 0
- source_path: `src\signalforge\backtesting\historical_strategy_candidate_rows_builder.py`
- proposed_engine_target: `src/signalforge/engines/strategy_selection/candidate_filter_decision.py`
- root_target_count: 6
- dependency_closure_count: 19
- required_function_count: 19
- optional_function_count: 1
- required_import_names: Any, Dict, List, Mapping, Sequence, json
- module_binding_dependencies: MISSING_VALUE
- paper_order_created: False
- live_order_created: False
- live_trade_supported: False

## Required Function Closure

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

## Optional Review Functions

- `_alignment_research_fields`

## Function Dependency Review

| function | action | internal deps | imported deps | module bindings | unresolved |
|---|---|---|---|---|---|
| `_normalise_text` | extract_required_candidate_filter_helper |  | Any | MISSING_VALUE |  |
| `_strategy_family_status_aliases` | extract_required_candidate_filter_helper | _normalise_text | Any, List, Mapping, Sequence | MISSING_VALUE |  |
| `_strategy_family_statuses` | extract_required_candidate_filter_helper | _normalise_text | Any, Dict, Mapping | MISSING_VALUE |  |
| `_strategy_family_status` | extract_required_candidate_filter_helper | _normalise_text, _strategy_family_status_aliases, _strategy_family_statuses | Any, Mapping | MISSING_VALUE |  |
| `_strategy_family_gate_block_reasons` | extract_root_candidate_filter_decision | _normalise_text, _strategy_family_status, _strategy_family_statuses | Any, List, Mapping | MISSING_VALUE |  |
| `_as_dict` | extract_required_candidate_filter_helper |  | Any, Dict, Mapping |  |  |
| `_as_list` | extract_required_candidate_filter_helper |  | Any, List |  |  |
| `_research_context_from_decision_row` | extract_root_candidate_filter_decision | _as_dict, _as_list | Any, Dict, Mapping |  |  |
| `_eligibility` | extract_required_candidate_filter_helper |  | Any, Mapping |  |  |
| `_flag_is_true` | extract_required_candidate_filter_helper | _eligibility | Any, Mapping |  |  |
| `_nested_state` | extract_required_candidate_filter_helper | _normalise_text | Any, Mapping, json |  |  |
| `_normalise_symbol` | extract_required_candidate_filter_helper |  | Any | MISSING_VALUE |  |
| `_parse_option_behavior` | extract_required_candidate_filter_helper |  | Dict | MISSING_VALUE |  |
| `_decision_row_block_reasons` | extract_root_candidate_filter_decision | _flag_is_true, _nested_state, _normalise_symbol, _normalise_text, _parse_option_behavior | Any, List, Mapping | MISSING_VALUE |  |
| `_strategy_definition_block_reasons` | extract_root_candidate_filter_decision | _normalise_text | Any, List, Mapping | MISSING_VALUE |  |
| `_has_term_structure_behavior` | extract_required_candidate_filter_helper |  | Any, Mapping |  |  |
| `_has_underlying_position` | extract_required_candidate_filter_helper | _eligibility | Any, Mapping |  |  |
| `_strategy_context_block_reasons` | extract_root_candidate_filter_decision | _has_term_structure_behavior, _has_underlying_position, _normalise_text, _strategy_family_gate_block_reasons | Any, List, Mapping |  |  |
| `_candidate_state` | manual_review_include_if_candidate_state_is_reusable_decision |  | Sequence |  |  |
| `_alignment_research_fields` | optional_review_helper_not_required_by_root_closure |  | Any, Dict, Mapping |  |  |

## Source Slices

### `_normalise_text`

- action: extract_required_candidate_filter_helper
- lines: 312-316
- signature: `def _normalise_text(value: Any):`

```python
def _normalise_text(value: Any) -> str:
    if value in (None, ""):
        return MISSING_VALUE

    return str(value).strip() or MISSING_VALUE
```

### `_strategy_family_status_aliases`

- action: extract_required_candidate_filter_helper
- lines: 415-446
- signature: `def _strategy_family_status_aliases(*, policy: Mapping[str, Any], strategy_family: str):`

```python
def _strategy_family_status_aliases(
    *,
    policy: Mapping[str, Any],
    strategy_family: str,
) -> List[str]:
    family = _normalise_text(strategy_family)
    candidates: List[str] = []

    if family != MISSING_VALUE:
        candidates.append(family)

    aliases = policy.get("strategy_family_eligibility_aliases")
    if not isinstance(aliases, Mapping):
        return candidates

    alias_value = aliases.get(family)
    if alias_value is None:
        alias_value = aliases.get(family.lower())

    if isinstance(alias_value, str):
        alias_items = [alias_value]
    elif isinstance(alias_value, Sequence) and not isinstance(alias_value, (str, bytes)):
        alias_items = list(alias_value)
    else:
        alias_items = []

    for item in alias_items:
        alias = _normalise_text(item)
        if alias != MISSING_VALUE and alias not in candidates:
            candidates.append(alias)

    return candidates
```

### `_strategy_family_statuses`

- action: extract_required_candidate_filter_helper
- lines: 394-412
- signature: `def _strategy_family_statuses(row: Mapping[str, Any]):`

```python
def _strategy_family_statuses(row: Mapping[str, Any]) -> Mapping[str, str]:
    statuses = row.get("strategy_family_statuses")

    if not isinstance(statuses, Mapping):
        eligibility = row.get("strategy_family_eligibility")
        if isinstance(eligibility, Mapping):
            statuses = eligibility.get("strategy_family_statuses")

    if not isinstance(statuses, Mapping):
        return {}

    out: Dict[str, str] = {}
    for key, value in statuses.items():
        family = _normalise_text(key)
        status = _normalise_text(value)
        if family != MISSING_VALUE and status != MISSING_VALUE:
            out[family] = status

    return out
```

### `_strategy_family_status`

- action: extract_required_candidate_filter_helper
- lines: 449-482
- signature: `def _strategy_family_status(row: Mapping[str, Any], strategy_family: str, *, policy: Mapping[str, Any] | None=None):`

```python
def _strategy_family_status(
    row: Mapping[str, Any],
    strategy_family: str,
    *,
    policy: Mapping[str, Any] | None = None,
) -> str:
    family = _normalise_text(strategy_family)
    if family == MISSING_VALUE:
        return MISSING_VALUE

    statuses = _strategy_family_statuses(row)

    lookup = {
        _normalise_text(key).lower(): value
        for key, value in statuses.items()
    }

    candidates = (
        _strategy_family_status_aliases(policy=policy, strategy_family=family)
        if policy is not None
        else [family]
    )

    for candidate in candidates:
        direct = _normalise_text(candidate)

        if direct in statuses:
            return statuses[direct]

        lowered = direct.lower()
        if lowered in lookup:
            return lookup[lowered]

    return MISSING_VALUE
```

### `_strategy_family_gate_block_reasons`

- action: extract_root_candidate_filter_decision
- lines: 484-517
- signature: `def _strategy_family_gate_block_reasons(*, row: Mapping[str, Any], strategy_family: str, policy: Mapping[str, Any]):`

```python
def _strategy_family_gate_block_reasons(
    *,
    row: Mapping[str, Any],
    strategy_family: str,
    policy: Mapping[str, Any],
) -> List[str]:
    if not bool(policy.get("enforce_strategy_family_eligibility", True)):
        return []

    family = _normalise_text(strategy_family)
    if family == MISSING_VALUE:
        return ["missing_strategy_family"]

    statuses = _strategy_family_statuses(row)
    if not statuses:
        return ["missing_strategy_family_statuses"]

    status = _strategy_family_status(row, family, policy=policy)

    if status == MISSING_VALUE:
        return [f"missing_strategy_family_status:{family}"]

    allowed_statuses = set(
        _normalise_text(item)
        for item in (
            policy.get("allowed_strategy_family_statuses")
            or ["favored", "favored_constrained", "allowed", "allowed_constrained"]
        )
    )

    if status not in allowed_statuses:
        return [f"strategy_family_status_not_allowed:{family}:{status}"]

    return []
```

### `_as_dict`

- action: extract_required_candidate_filter_helper
- lines: 520-523
- signature: `def _as_dict(value: Any):`

```python
def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}
```

### `_as_list`

- action: extract_required_candidate_filter_helper
- lines: 526-533
- signature: `def _as_list(value: Any):`

```python
def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return []
```

### `_research_context_from_decision_row`

- action: extract_root_candidate_filter_decision
- lines: 536-550
- signature: `def _research_context_from_decision_row(row: Mapping[str, Any]):`

```python
def _research_context_from_decision_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "regime": _as_dict(row.get("regime")),
        "asset_behavior": _as_dict(row.get("asset_behavior")),
        "option_behavior": _as_dict(row.get("option_behavior")),
        "regime_asset_options_alignment": _as_dict(row.get("regime_asset_options_alignment")),
        "strategy_family_eligibility": _as_dict(row.get("strategy_family_eligibility")),
        "strategy_family_statuses": _as_dict(row.get("strategy_family_statuses")),
        "favored_strategy_families": _as_list(row.get("favored_strategy_families")),
        "allowed_strategy_families": _as_list(row.get("allowed_strategy_families")),
        "discouraged_strategy_families": _as_list(row.get("discouraged_strategy_families")),
        "blocked_strategy_families": _as_list(row.get("blocked_strategy_families")),
        "review_required_strategy_families": _as_list(row.get("review_required_strategy_families")),
        "strategy_family_eligibility_handoff": row.get("strategy_family_eligibility_handoff"),
    }
```

### `_eligibility`

- action: extract_required_candidate_filter_helper
- lines: 343-345
- signature: `def _eligibility(row: Mapping[str, Any]):`

```python
def _eligibility(row: Mapping[str, Any]) -> Mapping[str, Any]:
    eligibility = row.get("eligibility")
    return eligibility if isinstance(eligibility, Mapping) else {}
```

### `_flag_is_true`

- action: extract_required_candidate_filter_helper
- lines: 348-349
- signature: `def _flag_is_true(row: Mapping[str, Any], flag_name: str):`

```python
def _flag_is_true(row: Mapping[str, Any], flag_name: str) -> bool:
    return bool(_eligibility(row).get(flag_name))
```

### `_nested_state`

- action: extract_required_candidate_filter_helper
- lines: 319-331
- signature: `def _nested_state(value: Any):`

```python
def _nested_state(value: Any) -> str:
    if isinstance(value, Mapping):
        state = value.get("state")
        if state not in (None, ""):
            return _normalise_text(state)

        source_state = value.get("source_state")
        if source_state not in (None, ""):
            return _normalise_text(source_state)

        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    return _normalise_text(value)
```

### `_normalise_symbol`

- action: extract_required_candidate_filter_helper
- lines: 305-309
- signature: `def _normalise_symbol(value: Any):`

```python
def _normalise_symbol(value: Any) -> str:
    if value in (None, ""):
        return MISSING_VALUE

    return str(value).strip().upper() or MISSING_VALUE
```

### `_parse_option_behavior`

- action: extract_required_candidate_filter_helper
- lines: 620-644
- signature: `def _parse_option_behavior(option_behavior_state: str):`

```python
def _parse_option_behavior(option_behavior_state: str) -> Dict[str, str]:
    lowered = option_behavior_state.lower()

    if lowered.startswith("iv_low"):
        iv_level = "low"
    elif lowered.startswith("iv_moderate"):
        iv_level = "moderate"
    elif lowered.startswith("iv_high"):
        iv_level = "high"
    else:
        iv_level = MISSING_VALUE

    if "illiquid_or_sparse" in lowered:
        liquidity_state = "illiquid_or_sparse"
    elif "moderate_liquidity" in lowered:
        liquidity_state = "moderate_liquidity"
    elif lowered.endswith("_liquid") or "_liquid" in lowered:
        liquidity_state = "liquid"
    else:
        liquidity_state = MISSING_VALUE

    return {
        "option_iv_level": iv_level,
        "option_liquidity_state": liquidity_state,
    }
```

### `_decision_row_block_reasons`

- action: extract_root_candidate_filter_decision
- lines: 647-694
- signature: `def _decision_row_block_reasons(row: Mapping[str, Any], *, strategy_policy: Mapping[str, Any]):`

```python
def _decision_row_block_reasons(
    row: Mapping[str, Any],
    *,
    strategy_policy: Mapping[str, Any],
) -> List[str]:
    reasons: List[str] = []

    symbol = _normalise_symbol(row.get("symbol"))
    decision_date = _normalise_text(row.get("date") or row.get("decision_date"))

    if symbol == MISSING_VALUE:
        reasons.append("missing_symbol")

    if decision_date == MISSING_VALUE:
        reasons.append("missing_decision_date")

    eligible_data_states = set(strategy_policy.get("eligible_data_states") or ["complete"])
    source_data_state = str(row.get("data_state") or MISSING_VALUE)

    if source_data_state not in eligible_data_states:
        reasons.append(f"source_data_state_not_eligible:{source_data_state}")

    for required_flag in strategy_policy.get("required_eligibility_flags") or []:
        if not _flag_is_true(row, str(required_flag)):
            reasons.append(f"eligibility_flag_false:{required_flag}")

    regime_state = _nested_state(row.get("regime"))
    asset_behavior_state = _nested_state(row.get("asset_behavior"))
    option_behavior_state = _nested_state(row.get("option_behavior"))

    if regime_state == MISSING_VALUE:
        reasons.append("missing_regime_state")

    if asset_behavior_state == MISSING_VALUE:
        reasons.append("missing_asset_behavior_state")

    if option_behavior_state == MISSING_VALUE:
        reasons.append("missing_option_behavior_state")

    parsed_option_behavior = _parse_option_behavior(option_behavior_state)

    if parsed_option_behavior["option_iv_level"] == MISSING_VALUE:
        reasons.append("missing_option_iv_level")

    if parsed_option_behavior["option_liquidity_state"] == MISSING_VALUE:
        reasons.append("missing_option_liquidity_state")

    return reasons
```

### `_strategy_definition_block_reasons`

- action: extract_root_candidate_filter_decision
- lines: 697-713
- signature: `def _strategy_definition_block_reasons(strategy: Mapping[str, Any]):`

```python
def _strategy_definition_block_reasons(strategy: Mapping[str, Any]) -> List[str]:
    reasons: List[str] = []

    required_fields = [
        "strategy",
        "strategy_family",
        "strategy_structure",
        "strategy_direction",
        "premium_profile",
        "candidate_rank",
    ]

    for field_name in required_fields:
        if _normalise_text(strategy.get(field_name)) == MISSING_VALUE:
            reasons.append(f"missing_{field_name}")

    return reasons
```

### `_has_term_structure_behavior`

- action: extract_required_candidate_filter_helper
- lines: 367-389
- signature: `def _has_term_structure_behavior(row: Mapping[str, Any]):`

```python
def _has_term_structure_behavior(row: Mapping[str, Any]) -> bool:
    option_behavior = row.get("option_behavior")

    if isinstance(option_behavior, Mapping):
        for key in (
            "term_structure_state",
            "term_structure",
            "term_structure_behavior",
            "front_back_iv_spread",
        ):
            if option_behavior.get(key) not in (None, ""):
                return True

    for key in (
        "term_structure_state",
        "term_structure",
        "term_structure_behavior",
        "front_back_iv_spread",
    ):
        if row.get(key) not in (None, ""):
            return True

    return False
```

### `_has_underlying_position`

- action: extract_required_candidate_filter_helper
- lines: 352-364
- signature: `def _has_underlying_position(row: Mapping[str, Any]):`

```python
def _has_underlying_position(row: Mapping[str, Any]) -> bool:
    if bool(row.get("has_underlying_position")):
        return True

    eligibility = _eligibility(row)
    if bool(eligibility.get("has_underlying_position")):
        return True

    position = row.get("position")
    if isinstance(position, Mapping):
        return bool(position.get("has_underlying_position"))

    return False
```

### `_strategy_context_block_reasons`

- action: extract_root_candidate_filter_decision
- lines: 716-773
- signature: `def _strategy_context_block_reasons(*, row: Mapping[str, Any], strategy: Mapping[str, Any], asset_behavior_state: str, option_iv_level: str, option_liquidity_state: str, holding_period_days: int, policy: Mapping[str, Any]):`

```python
def _strategy_context_block_reasons(
    *,
    row: Mapping[str, Any],
    strategy: Mapping[str, Any],
    asset_behavior_state: str,
    option_iv_level: str,
    option_liquidity_state: str,
    holding_period_days: int,
    policy: Mapping[str, Any],
) -> List[str]:
    reasons: List[str] = []

    strategy_name = strategy.get("strategy")
    strategy_family = _normalise_text(strategy.get("strategy_family"))

    reasons.extend(
        _strategy_family_gate_block_reasons(
            row=row,
            strategy_family=strategy_family,
            policy=policy,
        )
    )

    blocked_liquidity_states = set(policy.get("blocked_option_liquidity_states") or [])
    if option_liquidity_state in blocked_liquidity_states:
        reasons.append(f"blocked_option_liquidity_state:{option_liquidity_state}")

    allowed_asset_states = set(strategy.get("allowed_asset_behavior_states") or [])
    if allowed_asset_states and asset_behavior_state not in allowed_asset_states:
        reasons.append(
            f"strategy_asset_behavior_not_allowed:{strategy_name}:{asset_behavior_state}"
        )

    allowed_iv_levels = set(strategy.get("allowed_option_iv_levels") or [])
    if allowed_iv_levels and option_iv_level not in allowed_iv_levels:
        reasons.append(
            f"strategy_option_iv_not_allowed:{strategy_name}:{option_iv_level}"
        )

    allowed_liquidity_states = set(strategy.get("allowed_option_liquidity_states") or [])
    if allowed_liquidity_states and option_liquidity_state not in allowed_liquidity_states:
        reasons.append(
            f"strategy_option_liquidity_not_allowed:{strategy_name}:{option_liquidity_state}"
        )

    allowed_holding_periods = set(strategy.get("allowed_holding_period_days") or [])
    if allowed_holding_periods and holding_period_days not in allowed_holding_periods:
        reasons.append(
            f"strategy_horizon_not_allowed:{strategy_name}:{holding_period_days}"
        )

    if bool(strategy.get("requires_underlying_position")) and not _has_underlying_position(row):
        reasons.append(f"requires_underlying_position:{strategy_name}")

    if bool(strategy.get("requires_term_structure")) and not _has_term_structure_behavior(row):
        reasons.append(f"requires_term_structure_behavior:{strategy_name}")

    return reasons
```

### `_candidate_state`

- action: manual_review_include_if_candidate_state_is_reusable_decision
- lines: 794-795
- signature: `def _candidate_state(reasons: Sequence[str]):`

```python
def _candidate_state(reasons: Sequence[str]) -> str:
    return "available" if not reasons else "blocked"
```

### `_alignment_research_fields`

- action: optional_review_helper_not_required_by_root_closure
- lines: 591-617
- signature: `def _alignment_research_fields(alignment: Any):`

```python
def _alignment_research_fields(alignment: Any) -> Dict[str, Any]:
    if not isinstance(alignment, Mapping):
        return {}

    keys = (
        "regime_options_alignment",
        "asset_options_alignment",
        "strategy_environment_bias",
        "premium_bias",
        "coverage_status",
        "matrix_dimension_state",
        "matrix_metadata_state",
        "strategy_selection_handoff",
        "term_structure_state",
        "theta_sensitivity_state",
        "spread_state",
        "skew_state",
        "iv_expansion_state",
        "gamma_concentration_state",
        "volatility_risk_premium_state",
    )

    return {
        key: alignment.get(key)
        for key in keys
        if alignment.get(key) not in (None, "")
    }
```


## Warnings

- stage36n2_is_read_only_no_logic_moved
- historical_candidate_row_builder_remains_in_backtesting
- candidate_filter_extraction_must_include_full_dependency_closure