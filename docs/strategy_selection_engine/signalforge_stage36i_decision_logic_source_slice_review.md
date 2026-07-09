# Stage 36I Decision Logic Source Slice Review

- is_ready: True
- blocker_count: 0
- function_slice_count: 8
- paper_order_created: False
- live_order_created: False
- live_trade_supported: False

## `_is_selectable`

- source: `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py`
- lines: 110-152
- proposed target: `src/signalforge/engines/strategy_selection/selection_decision.py`
- calls: _as_float, _as_int, append, get, len
- external names: Any, List, Mapping, Tuple, _as_float, _as_int, bool, int, len, str

```python
def _is_selectable(
    row: Mapping[str, Any],
    minimum_sample_count: int,
    allowed_construction_qualities: Tuple[str, ...],
) -> Tuple[bool, List[str]]:
    reasons: List[str] = []

    if row.get("leg_selection_state") != "selected":
        reasons.append("leg_selection_not_selected")

    if row.get("strategy_candidate_state") not in (None, "available"):
        reasons.append("strategy_candidate_not_available")

    if False and row.get("data_state") != "complete":

        reasons.append("data_state_not_complete")

    if False and row.get("outcome_state") != "complete":

        reasons.append("outcome_state_not_complete")

    construction_quality = row.get("construction_quality")
    if allowed_construction_qualities and construction_quality not in allowed_construction_qualities:
        reasons.append("construction_quality_not_allowed")

    if row.get("expectancy_state") != "positive_expectancy_candidate":
        reasons.append("expectancy_not_positive")

    avg_return = _as_float(row.get("expectancy_average_return"))
    if avg_return is None or avg_return <= 0:
        reasons.append("expectancy_average_return_not_positive")

    sample_count = _as_int(row.get("expectancy_sample_count")) or 0
    if sample_count < minimum_sample_count:
        reasons.append("expectancy_sample_below_minimum")

    if row.get("uses_current_row_outcome") is True:
        reasons.append("uses_current_row_outcome")

    if row.get("uses_future_rows") is True:
        reasons.append("uses_future_rows")

    return len(reasons) == 0, reasons
```

## `_selection_score`

- source: `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py`
- lines: 155-158
- proposed target: `src/signalforge/engines/strategy_selection/selection_decision.py`
- calls: _as_float, _as_int, get, max
- external names: Any, Mapping, _as_float, _as_int, float, max, str

```python
def _selection_score(row: Mapping[str, Any]) -> float:
    avg_return = _as_float(row.get("expectancy_average_return")) or 0.0
    holding_period = _as_int(row.get("holding_period_days")) or 1
    return avg_return / max(holding_period, 1)
```

## `_sample_confidence_multiplier`

- source: `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py`
- lines: 161-167
- proposed target: `src/signalforge/engines/strategy_selection/selection_decision.py`
- calls: _as_int, get, log10, max, min
- external names: Any, Mapping, _as_int, float, math, max, min, str

```python
def _sample_confidence_multiplier(row: Mapping[str, Any]) -> float:
    sample_count = _as_int(row.get("expectancy_sample_count")) or 0
    if sample_count <= 0:
        return 0.0

    # 20 samples should be usable but not equal in confidence to several hundred samples.
    return min(1.0, max(0.50, math.log10(sample_count + 1) / 2.0))
```

## `_scope_confidence_multiplier`

- source: `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py`
- lines: 170-172
- proposed target: `src/signalforge/engines/strategy_selection/selection_decision.py`
- calls: get, str
- external names: Any, Mapping, SCOPE_CONFIDENCE_MULTIPLIER, float, str

```python
def _scope_confidence_multiplier(row: Mapping[str, Any]) -> float:
    scope = str(row.get("expectancy_scope") or "missing")
    return SCOPE_CONFIDENCE_MULTIPLIER.get(scope, 0.50)
```

## `_confidence_adjusted_selection_score`

- source: `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py`
- lines: 175-180
- proposed target: `src/signalforge/engines/strategy_selection/selection_decision.py`
- calls: _sample_confidence_multiplier, _scope_confidence_multiplier, _selection_score
- external names: Any, Mapping, _sample_confidence_multiplier, _scope_confidence_multiplier, _selection_score, float, str

```python
def _confidence_adjusted_selection_score(row: Mapping[str, Any]) -> float:
    return (
        _selection_score(row)
        * _scope_confidence_multiplier(row)
        * _sample_confidence_multiplier(row)
    )
```

## `_rank_tuple`

- source: `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py`
- lines: 183-212
- proposed target: `src/signalforge/engines/strategy_selection/selection_decision.py`
- calls: _as_float, _as_int, _selection_score, get, str
- external names: Any, Mapping, Tuple, _as_float, _as_int, _selection_score, float, int, str

```python
def _rank_tuple(row: Mapping[str, Any]) -> Tuple[float, float, float, float, int, int, int, int]:
    score = _selection_score(row)
    avg_return = _as_float(row.get("expectancy_average_return")) or 0.0
    median_return = _as_float(row.get("expectancy_median_return")) or 0.0
    win_rate = _as_float(row.get("expectancy_win_rate")) or 0.0
    sample_count = _as_int(row.get("expectancy_sample_count")) or 0
    candidate_rank = _as_int(row.get("candidate_rank")) or 999_999
    holding_period = _as_int(row.get("holding_period_days")) or 999_999

    scope_specificity_order = {
        "strategy_global": 1,
        "strategy_regime": 2,
        "strategy_regime_asset": 3,
        "strategy_regime_asset_option": 4,
        "symbol_strategy_regime": 5,
        "symbol_strategy_regime_asset": 6,
        "symbol_strategy_regime_asset_option": 7,
    }
    scope_specificity = scope_specificity_order.get(str(row.get("expectancy_scope") or ""), 0)

    return (
        score,
        avg_return,
        median_return,
        win_rate,
        sample_count,
        scope_specificity,
        -candidate_rank,
        -holding_period,
    )
```

## `_selection_row`

- source: `src/signalforge/backtesting/historical_strategy_selection_rows_builder.py`
- lines: 216-306
- proposed target: `src/signalforge/engines/strategy_selection/selection_decision.py`
- calls: _candidate_id, _selection_score, dict, get, items, sorted, update
- external names: Any, Counter, Dict, Mapping, Optional, Tuple, _candidate_id, _selection_score, dict, int, sorted, str

```python
def _selection_row(
    *,
    group_key: Tuple[str, str, str],
    selected: Optional[Mapping[str, Any]],
    candidate_count: int,
    selectable_count: int,
    rejected_candidate_count: int,
    rejected_strategy_counts: Counter,
    rejected_expectancy_state_counts: Counter,
    blocked_reason_counts: Counter,
    minimum_sample_count: int,
    allowed_construction_qualities: Tuple[str, ...],
) -> Dict[str, Any]:
    date, symbol, decision_row_id = group_key

    base: Dict[str, Any] = {
        "adapter_type": "historical_strategy_selection_rows_builder",
        "artifact_type": "signalforge_historical_strategy_selection_row",
        "contract": "historical_strategy_selection_rows",
        "date": date,
        "decision_date": date,
        "symbol": symbol,
        "decision_row_id": decision_row_id,
        "candidate_count": candidate_count,
        "selectable_candidate_count": selectable_count,
        "rejected_candidate_count": rejected_candidate_count,
        "rejected_strategy_counts": dict(sorted(rejected_strategy_counts.items())),
        "rejected_expectancy_state_counts": dict(sorted(rejected_expectancy_state_counts.items())),
        "minimum_sample_count": minimum_sample_count,
        "selection_uses_realized_outcome": False,
        "selection_uses_current_row_outcome": False,
        "selection_uses_future_rows": False,
        "blocked_reason_counts": dict(sorted(blocked_reason_counts.items())),
    }

    if selected is None:
        base.update(
            {
                "selection_state": "no_trade",
                "selected_strategy": None,
                "selected_strategy_instance": None,
                "selected_expectancy_state": None,
                "selected_expectancy_score": None,
                "selected_expectancy_average_return": None,
                "selected_expectancy_sample_count": None,
                "selected_outcome_state": None,
                "selected_candidate_id": None,
                "selection_reason": "no_positive_expectancy_candidate",
            }
        )
        return base

    base.update(
        {
            "selection_state": "selected",
            "selection_reason": "highest_positive_walk_forward_expectancy_score",
            "selected_candidate_id": _candidate_id(selected),
            "selected_strategy": selected.get("strategy"),
            "selected_strategy_instance": selected.get("strategy_instance"),
            "selected_strategy_family": selected.get("strategy_family"),
            "selected_strategy_structure": selected.get("strategy_structure"),
            "selected_holding_period_days": selected.get("holding_period_days"),
            "selected_risk_overlay": selected.get("risk_overlay"),
            "selected_premium_profile": selected.get("premium_profile"),
            "selected_expectancy_state": selected.get("expectancy_state"),
            "selected_expectancy_scope": selected.get("expectancy_scope"),
            "selected_expectancy_score": _selection_score(selected),
            "selected_expectancy_average_return": selected.get("expectancy_average_return"),
            "selected_expectancy_median_return": selected.get("expectancy_median_return"),
            "selected_expectancy_win_rate": selected.get("expectancy_win_rate"),
            "selected_expectancy_sample_count": selected.get("expectancy_sample_count"),
            "selected_training_window_start": selected.get("training_window_start"),
            "selected_training_window_end": selected.get("training_window_end"),
            "selected_outcome_state": selected.get("outcome_state"),
            "selected_data_state": selected.get("data_state"),
            "selected_strategy_adjusted_return": selected.get("strategy_adjusted_return"),
            "selected_outcome_availability_date": selected.get("outcome_availability_date"),
            "selected_leg_selection_id": selected.get("leg_selection_id"),
            "selected_quote_outcome_id": selected.get("quote_outcome_id"),
            "regime_state": selected.get("regime_state"),
            "asset_behavior_state": selected.get("asset_behavior_state"),
            "option_behavior_state": selected.get("option_behavior_state"),
            "option_iv_level": selected.get("option_iv_level"),
            "option_liquidity_state": selected.get("option_liquidity_state"),
            "term_structure_state": selected.get("term_structure_state"),
            "term_structure_shape": selected.get("term_structure_shape"),
            "source_candidate": dict(selected),
        }
    )

    return base
```

## `_extract_trade`

- source: `src/signalforge/backtesting/portfolio_selected_trade_sequence.py`
- lines: 520-627
- proposed target: `src/signalforge/engines/strategy_selection/selected_trade_sequence_decision.py`
- calls: _coerce_float, _extract_execution_realism_fields, _first_present_with_path, _has_contract_outcome_missing_state, _parse_date, _string_or_none, append, get, isoformat, join, len
- external names: Any, DATE_FIELDS, EXPECTANCY_ASOF_FIELDS, REALIZED_RETURN_FIELDS, STRATEGY_FIELDS, SYMBOL_FIELDS, _coerce_float, _extract_execution_realism_fields, _first_present_with_path, _has_contract_outcome_missing_state, _parse_date, _string_or_none, dict, int, len, list, str

```python
def _extract_trade(row: dict[str, Any], original_index: int) -> dict[str, Any]:
    raw_date, date_source_field = _first_present_with_path(row, DATE_FIELDS)
    parsed_date = _parse_date(raw_date)

    raw_symbol, symbol_source_field = _first_present_with_path(row, SYMBOL_FIELDS)
    symbol = _string_or_none(raw_symbol)

    raw_strategy, strategy_source_field = _first_present_with_path(row, STRATEGY_FIELDS)
    strategy = _string_or_none(raw_strategy)

    raw_return, realized_return_source_field = _first_present_with_path(
        row,
        REALIZED_RETURN_FIELDS,
    )
    realized_return = _coerce_float(raw_return)

    expectancy_asof_raw, expectancy_asof_source_field = _first_present_with_path(
        row,
        EXPECTANCY_ASOF_FIELDS,
    )
    expectancy_asof_date = _parse_date(expectancy_asof_raw)

    skip_reasons: list[str] = []

    selection_state = _string_or_none(row.get("selection_state"))
    data_state = _string_or_none(row.get("data_state"))
    outcome_state = _string_or_none(row.get("outcome_state"))
    is_selected_trade = row.get("is_selected_trade")
    is_portfolio_reconstructable = row.get("is_portfolio_reconstructable")

    is_no_trade = (
        selection_state == "no_trade"
        or is_selected_trade is False
        or data_state == "no_trade"
        or outcome_state == "no_trade"
    )

    if parsed_date is None:
        skip_reasons.append("missing_or_invalid_decision_date")

    if symbol is None:
        skip_reasons.append("missing_symbol")

    if is_no_trade:
        skip_reasons.append("no_trade")
    else:
        if strategy is None:
            skip_reasons.append("missing_selected_strategy")

        if realized_return is None:
            skip_reasons.append("missing_realized_return")

        if is_portfolio_reconstructable is False:
            skip_reasons.append("portfolio_not_reconstructable")

        if data_state not in (None, "complete"):
            skip_reasons.append("data_state_not_complete")

        if outcome_state not in (None, "complete"):
            skip_reasons.append("outcome_state_not_complete")

        if _has_contract_outcome_missing_state(row):
            skip_reasons.append("contract_outcome_missing")

    if (
        parsed_date is not None
        and expectancy_asof_date is not None
        and expectancy_asof_date > parsed_date
    ):
        skip_reasons.append("future_expectancy_asof_date")

    trade_key = "|".join(
        [
            parsed_date.isoformat() if parsed_date else "UNKNOWN_DATE",
            symbol or "UNKNOWN_SYMBOL",
            strategy or "UNKNOWN_STRATEGY",
        ]
    )

    execution_realism = _extract_execution_realism_fields(row)

    return {
        "original_index": original_index,
        "decision_date": parsed_date.isoformat() if parsed_date else None,
        "symbol": symbol,
        "selected_strategy": strategy,
        "realized_return": realized_return,
        "expectancy_asof_date": expectancy_asof_date.isoformat()
        if expectancy_asof_date
        else None,
        "trade_key": trade_key,
        "selection_state": selection_state,
        "data_state": data_state,
        "outcome_state": outcome_state,
        "is_selected_trade": is_selected_trade,
        "is_portfolio_reconstructable": is_portfolio_reconstructable,
        "portfolio_usable": len(skip_reasons) == 0,
        "portfolio_skip_reasons": skip_reasons,
        "source_fields": {
            "decision_date": date_source_field,
            "symbol": symbol_source_field,
            "selected_strategy": strategy_source_field,
            "realized_return": realized_return_source_field,
            "expectancy_asof_date": expectancy_asof_source_field,
        },
        "source_row": row,
        **execution_realism,
    }
```

## Warnings

- stage36i_is_read_only_source_slice_review
- do_not_move_historical_wrappers_out_of_backtesting
- next_stage_should_extract_first_selection_decision_cluster_with_parity_test