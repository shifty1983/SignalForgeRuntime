from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
from signalforge.engines.strategy_selection import selection_decision as _selection_decision_engine


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


def _as_float(value: Any):
    return _selection_decision_engine._as_float(value)


def _as_int(value: Any):
    return _selection_decision_engine._as_int(value)


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


def _candidate_id(row: Mapping[str, Any]):
    return _selection_decision_engine._candidate_id(row)


def _is_selectable(row: Mapping[str, Any], minimum_sample_count: int, allowed_construction_qualities: Tuple[str, ...]):
    return _selection_decision_engine._is_selectable(row, minimum_sample_count, allowed_construction_qualities)


def _selection_score(row: Mapping[str, Any]):
    return _selection_decision_engine._selection_score(row)


def _sample_confidence_multiplier(row: Mapping[str, Any]):
    return _selection_decision_engine._sample_confidence_multiplier(row)


def _scope_confidence_multiplier(row: Mapping[str, Any]):
    return _selection_decision_engine._scope_confidence_multiplier(row)


def _confidence_adjusted_selection_score(row: Mapping[str, Any]):
    return _selection_decision_engine._confidence_adjusted_selection_score(row)


def _rank_tuple(row: Mapping[str, Any]):
    return _selection_decision_engine._rank_tuple(row)



def _selection_row(*, group_key: Tuple[str, str, str], selected: Optional[Mapping[str, Any]], candidate_count: int, selectable_count: int, rejected_candidate_count: int, rejected_strategy_counts: Counter, rejected_expectancy_state_counts: Counter, blocked_reason_counts: Counter, minimum_sample_count: int, allowed_construction_qualities: Tuple[str, ...]):
    return _selection_decision_engine._selection_row(group_key=group_key, selected=selected, candidate_count=candidate_count, selectable_count=selectable_count, rejected_candidate_count=rejected_candidate_count, rejected_strategy_counts=rejected_strategy_counts, rejected_expectancy_state_counts=rejected_expectancy_state_counts, blocked_reason_counts=blocked_reason_counts, minimum_sample_count=minimum_sample_count, allowed_construction_qualities=allowed_construction_qualities)


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




