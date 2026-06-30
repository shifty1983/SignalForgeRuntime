from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


SCOPE_SPECIFICITY = {
    "symbol_strategy_regime_asset_option": 7,
    "symbol_strategy_regime_asset": 6,
    "symbol_strategy_regime": 5,
    "strategy_regime_asset_option": 4,
    "strategy_regime_asset": 3,
    "strategy_regime": 2,
    "strategy_global": 1,
}


SCOPE_CONFIDENCE_MULTIPLIER = {
    "symbol_strategy_regime_asset_option": 1.00,
    "symbol_strategy_regime_asset": 0.95,
    "symbol_strategy_regime": 0.90,
    "strategy_regime_asset_option": 0.88,
    "strategy_regime_asset": 0.82,
    "strategy_regime": 0.72,
    "strategy_global": 0.60,
}

DEFAULT_ALLOWED_CONSTRUCTION_QUALITIES: Tuple[str, ...] = ()


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


def _date(value: Any) -> str:
    if value in (None, ""):
        return "missing"
    return str(value)[:10]


def read_jsonl(path: str | Path) -> Iterable[Dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8-sig", errors="ignore") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc
            if isinstance(payload, dict):
                yield payload


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _decision_group_key(row: Mapping[str, Any]) -> Tuple[str, str, str]:
    date = _date(row.get("date") or row.get("decision_date"))
    symbol = str(row.get("symbol") or "missing")
    decision_row_id = str(row.get("decision_row_id") or f"{date}_{symbol}")
    return date, symbol, decision_row_id


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


def build_historical_strategy_selection_rows_artifact(
    *,
    expectancy_rows_path: str | Path,
    output_dir: str | Path,
    minimum_sample_count: int = 20,
    allowed_construction_qualities: Tuple[str, ...] = DEFAULT_ALLOWED_CONSTRUCTION_QUALITIES,
) -> Dict[str, Any]:
    output_path = Path(output_dir)
    rows_path = output_path / "signalforge_historical_strategy_selection_rows.jsonl"
    summary_path = output_path / "signalforge_historical_strategy_selection_rows_summary.json"

    groups: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}

    input_count = 0
    for row in read_jsonl(expectancy_rows_path):
        input_count += 1
        groups.setdefault(_decision_group_key(row), []).append(row)

    output_rows: List[Dict[str, Any]] = []

    selected_count = 0
    no_trade_count = 0

    selected_strategy_counts = Counter()
    selected_expectancy_state_counts = Counter()
    selected_outcome_state_counts = Counter()
    selected_data_state_counts = Counter()
    selected_scope_counts = Counter()
    no_trade_reason_counts = Counter()
    blocked_reason_counts_total = Counter()

    for group_key, candidates in sorted(groups.items()):
        selectable: List[Dict[str, Any]] = []
        rejected_strategy_counts = Counter()
        rejected_expectancy_state_counts = Counter()
        group_blocked_reasons = Counter()

        for candidate in candidates:
            is_selectable, reasons = _is_selectable(
                candidate,
                minimum_sample_count,
                allowed_construction_qualities,
            )
            if is_selectable:
                selectable.append(candidate)
            else:
                rejected_strategy_counts[str(candidate.get("strategy") or "missing")] += 1
                rejected_expectancy_state_counts[str(candidate.get("expectancy_state") or "missing")] += 1

                for reason in reasons:
                    group_blocked_reasons[reason] += 1
                    blocked_reason_counts_total[reason] += 1

        selected = None
        if selectable:
            selected = sorted(selectable, key=_rank_tuple, reverse=True)[0]

        row = _selection_row(
            group_key=group_key,
            selected=selected,
            candidate_count=len(candidates),
            selectable_count=len(selectable),
            rejected_candidate_count=len(candidates) - len(selectable),
            rejected_strategy_counts=rejected_strategy_counts,
            rejected_expectancy_state_counts=rejected_expectancy_state_counts,
            blocked_reason_counts=group_blocked_reasons,
            minimum_sample_count=minimum_sample_count,
            allowed_construction_qualities=allowed_construction_qualities,
        )

        output_rows.append(row)

        if row["selection_state"] == "selected":
            selected_count += 1
            selected_strategy_counts[str(row.get("selected_strategy") or "missing")] += 1
            selected_expectancy_state_counts[str(row.get("selected_expectancy_state") or "missing")] += 1
            selected_outcome_state_counts[str(row.get("selected_outcome_state") or "missing")] += 1
            selected_data_state_counts[str(row.get("selected_data_state") or "missing")] += 1
            selected_scope_counts[str(row.get("selected_expectancy_scope") or "missing")] += 1
        else:
            no_trade_count += 1
            no_trade_reason_counts[str(row.get("selection_reason") or "missing")] += 1

    blockers: List[str] = []
    if not output_rows:
        blockers.append("no_strategy_selection_rows_written")
    if selected_count == 0:
        blockers.append("no_selected_strategy_rows")

    summary = {
        "adapter_type": "historical_strategy_selection_rows_builder",
        "artifact_type": "signalforge_historical_strategy_selection_rows",
        "contract": "historical_strategy_selection_rows",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "input_expectancy_row_count": input_count,
        "decision_group_count": len(groups),
        "output_row_count": len(output_rows),
        "selected_row_count": selected_count,
        "no_trade_row_count": no_trade_count,
        "selection_rate": selected_count / len(output_rows) if output_rows else 0.0,
        "selected_strategy_counts": dict(sorted(selected_strategy_counts.items())),
        "selected_expectancy_state_counts": dict(sorted(selected_expectancy_state_counts.items())),
        "selected_outcome_state_counts": dict(sorted(selected_outcome_state_counts.items())),
        "selected_data_state_counts": dict(sorted(selected_data_state_counts.items())),
        "selected_expectancy_scope_counts": dict(sorted(selected_scope_counts.items())),
        "no_trade_reason_counts": dict(sorted(no_trade_reason_counts.items())),
        "blocked_reason_counts": dict(sorted(blocked_reason_counts_total.items())),
        "selection_policy": {
            "minimum_sample_count": minimum_sample_count,
            "eligible_expectancy_state": "positive_expectancy_candidate",
            "allowed_construction_qualities": list(allowed_construction_qualities),
            "requires_data_state": None,
            "requires_outcome_state": None,
            "ranking_score": "expectancy_average_return_divided_by_holding_period_days",
            "raw_score": "expectancy_average_return_divided_by_holding_period_days",
            "scope_confidence_multipliers": SCOPE_CONFIDENCE_MULTIPLIER,
            "sample_confidence_multiplier": "min(1.0, max(0.50, log10(expectancy_sample_count + 1) / 2.0))",
            "uses_realized_outcome_for_selection": False,
            "allows_partial_future_outcome_rows": True,
        },
        "paths": {
            "expectancy_rows_path": str(expectancy_rows_path),
            "rows_path": str(rows_path),
            "summary_path": str(summary_path),
        },
    }

    write_jsonl(rows_path, output_rows)
    write_json(summary_path, summary)

    return summary


