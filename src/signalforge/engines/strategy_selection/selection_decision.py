"""Reusable post-expectancy selection decision helpers.



Backtesting owns historical replay orchestration.

This module owns reusable selection decision logic used by historical replay,

paper candidate evaluation, and future live candidate evaluation.

"""



from __future__ import annotations



from math import log10

from typing import Any




# Extracted module-level bindings required by selection decision helpers.
import math

from collections import Counter

from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

SCOPE_CONFIDENCE_MULTIPLIER = {
    "symbol_strategy_regime_asset_option": 1.00,
    "symbol_strategy_regime_asset": 0.95,
    "symbol_strategy_regime": 0.90,
    "strategy_regime_asset_option": 0.88,
    "strategy_regime_asset": 0.82,
    "strategy_regime": 0.72,
    "strategy_global": 0.60,
}

def _as_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        value = float(value)
        if math.isnan(value):
            return None
        return value
    except Exception:
        return None

def _as_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except Exception:
        return None

def _candidate_id(row: Mapping[str, Any]) -> str:
    return str(
        row.get("quote_outcome_id")
        or row.get("leg_selection_id")
        or row.get("strategy_candidate_id")
        or f"{row.get('date')}_{row.get('symbol')}_{row.get('strategy_instance')}"
    )

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

def _selection_score(row: Mapping[str, Any]) -> float:
    avg_return = _as_float(row.get("expectancy_average_return")) or 0.0
    holding_period = _as_int(row.get("holding_period_days")) or 1
    return avg_return / max(holding_period, 1)

def _sample_confidence_multiplier(row: Mapping[str, Any]) -> float:
    sample_count = _as_int(row.get("expectancy_sample_count")) or 0
    if sample_count <= 0:
        return 0.0

    # 20 samples should be usable but not equal in confidence to several hundred samples.
    return min(1.0, max(0.50, math.log10(sample_count + 1) / 2.0))

def _scope_confidence_multiplier(row: Mapping[str, Any]) -> float:
    scope = str(row.get("expectancy_scope") or "missing")
    return SCOPE_CONFIDENCE_MULTIPLIER.get(scope, 0.50)

def _confidence_adjusted_selection_score(row: Mapping[str, Any]) -> float:
    return (
        _selection_score(row)
        * _scope_confidence_multiplier(row)
        * _sample_confidence_multiplier(row)
    )

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

