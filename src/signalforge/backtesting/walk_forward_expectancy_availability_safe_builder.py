from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


Sample = Dict[str, Any]


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


def _as_date(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value)
    if len(text) >= 10:
        return text[:10]
    return None


def _parse_date(value: Any) -> Optional[datetime]:
    text = _as_date(value)
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except Exception:
        return None


def _date_text(date_value: datetime) -> str:
    return date_value.strftime("%Y-%m-%d")


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


def _field_any(row: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return str(value)
    return "missing"


def _field(row: Mapping[str, Any], name: str) -> str:
    return _field_any(row, name)


def _strategy_key(row: Mapping[str, Any]) -> str:
    strategy = _field_any(row, "strategy_instance", "strategy")
    holding_period = _field_any(row, "holding_period_days", "holding_period")

    # Expectancy should not mix 5/10/21/45-day outcomes for the same strategy.
    # Encode holding period into the cohort key while preserving the original row fields.
    if holding_period != "missing":
        return f"{strategy}__holding_{holding_period}"

    return strategy


def _scope_keys(row: Mapping[str, Any]) -> List[Tuple[str, Tuple[str, ...]]]:
    symbol = _field_any(row, "symbol", "underlying", "underlying_symbol")
    strategy_key = _strategy_key(row)
    regime = _field_any(row, "regime_state", "macro_regime", "regime")
    asset = _field_any(row, "asset_behavior_state", "asset_behavior", "asset_state")
    option = _field_any(row, "options_behavior_state", "option_behavior_state", "option_behavior", "option_state")

    return [
        ("symbol_strategy_regime_asset_option", (symbol, strategy_key, regime, asset, option)),
        ("symbol_strategy_regime_asset", (symbol, strategy_key, regime, asset)),
        ("symbol_strategy_regime", (symbol, strategy_key, regime)),
        ("strategy_regime_asset_option", (strategy_key, regime, asset, option)),
        ("strategy_regime_asset", (strategy_key, regime, asset)),
        ("strategy_regime", (strategy_key, regime)),
        ("strategy_global", (strategy_key,)),
    ]


def _row_id(row: Mapping[str, Any]) -> str:
    return str(
        row.get("quote_outcome_id")
        or row.get("leg_selection_id")
        or row.get("strategy_candidate_id")
        or f"{row.get('date')}_{row.get('symbol')}_{row.get('strategy_instance')}"
    )


def _training_sample(row: Mapping[str, Any]) -> Optional[Sample]:
    if row.get("data_state") != "complete":
        return None

    realized_return = _as_float(row.get("strategy_adjusted_return"))
    decision_date = _as_date(row.get("date") or row.get("decision_date"))
    availability_date = _as_date(row.get("outcome_availability_date") or row.get("outcome_date"))

    if realized_return is None or decision_date is None or availability_date is None:
        return None

    return {
        "row_id": _row_id(row),
        "return": realized_return,
        "decision_date": decision_date,
        "availability_date": availability_date,
        "scope_keys": _scope_keys(row),
    }


def _valid_samples(
    samples: List[Sample],
    *,
    current_row_id: str,
    current_decision_date: str,
    training_window_end: str,
) -> List[Sample]:
    valid = []

    for sample in samples:
        if sample["row_id"] == current_row_id:
            continue
        if sample["availability_date"] > training_window_end:
            continue
        if sample["decision_date"] >= current_decision_date:
            continue
        valid.append(sample)

    return valid


def _metrics(samples: List[Sample]) -> Dict[str, Any]:
    returns = [float(sample["return"]) for sample in samples]
    count = len(returns)

    if count == 0:
        return {
            "expectancy_sample_count": 0,
            "expectancy_average_return": None,
            "expectancy_median_return": None,
            "expectancy_win_rate": None,
            "expectancy_min_return": None,
            "expectancy_max_return": None,
        }

    return {
        "expectancy_sample_count": count,
        "expectancy_average_return": sum(returns) / count,
        "expectancy_median_return": statistics.median(returns),
        "expectancy_win_rate": sum(1 for value in returns if value > 0) / count,
        "expectancy_min_return": min(returns),
        "expectancy_max_return": max(returns),
    }


def _classify(metrics: Mapping[str, Any], minimum_sample_count: int) -> str:
    sample_count = int(metrics.get("expectancy_sample_count") or 0)

    if sample_count == 0:
        return "no_prior_sample"

    if sample_count < minimum_sample_count:
        return "sample_limited"

    avg = _as_float(metrics.get("expectancy_average_return"))
    median = _as_float(metrics.get("expectancy_median_return"))
    win_rate = _as_float(metrics.get("expectancy_win_rate"))

    if avg is None or median is None or win_rate is None:
        return "mixed_expectancy"

    if avg > 0 and (median > 0 or win_rate >= 0.5):
        return "positive_expectancy_candidate"

    if avg < 0 and (median < 0 or win_rate <= 0.5):
        return "negative_expectancy_candidate"

    return "mixed_expectancy"


def _choose_scope(
    row: Mapping[str, Any],
    pools: Mapping[Tuple[str, Tuple[str, ...]], List[Sample]],
    *,
    minimum_sample_count: int,
    current_row_id: str,
    current_decision_date: str,
    training_window_end: str,
) -> Tuple[str, List[Sample]]:
    best_scope_name = "symbol_strategy_regime_asset_option"
    best_samples: List[Sample] = []

    for scope_name, key in _scope_keys(row):
        raw_samples = pools.get((scope_name, key), [])
        valid_samples = _valid_samples(
            raw_samples,
            current_row_id=current_row_id,
            current_decision_date=current_decision_date,
            training_window_end=training_window_end,
        )

        if len(valid_samples) >= minimum_sample_count:
            return scope_name, valid_samples

        if len(valid_samples) > len(best_samples):
            best_scope_name = scope_name
            best_samples = valid_samples

    return best_scope_name, best_samples


def build_walk_forward_expectancy_rows(
    *,
    decision_rows_path: str | Path,
    output_dir: str | Path,
    minimum_sample_count: int = 20,
) -> Dict[str, Any]:
    rows = list(read_jsonl(decision_rows_path))

    output_path = Path(output_dir)
    rows_path = output_path / "signalforge_walk_forward_expectancy_rows.jsonl"
    summary_path = output_path / "signalforge_walk_forward_expectancy_summary.json"

    rows_sorted = sorted(
        rows,
        key=lambda row: (
            _as_date(row.get("date") or row.get("decision_date")) or "9999-99-99",
            _field(row, "symbol"),
            _strategy_key(row),
            str(row.get("leg_selection_id") or row.get("strategy_candidate_id") or ""),
        ),
    )

    training_samples = []
    rejected_counts = Counter()

    for row in rows_sorted:
        sample = _training_sample(row)
        if sample is None:
            if row.get("data_state") != "complete":
                rejected_counts["non_complete"] += 1
            elif _as_float(row.get("strategy_adjusted_return")) is None:
                rejected_counts["missing_return"] += 1
            elif not _as_date(row.get("outcome_availability_date") or row.get("outcome_date")):
                rejected_counts["missing_outcome_availability_date"] += 1
            else:
                rejected_counts["invalid_training_sample"] += 1
            continue
        training_samples.append(sample)

    training_samples.sort(key=lambda sample: (sample["availability_date"], sample["decision_date"], sample["row_id"]))

    pools: Dict[Tuple[str, Tuple[str, ...]], List[Sample]] = defaultdict(list)
    training_index = 0

    output_rows: List[Dict[str, Any]] = []

    expectancy_state_counts = Counter()
    expectancy_scope_counts = Counter()
    sample_count_counts = Counter()
    data_state_counts = Counter()

    rows_using_current_row_outcome = 0
    rows_using_future_rows = 0
    rows_missing_training_window_end = 0
    invalid_missing_decision_date = 0

    for row in rows_sorted:
        output_row = dict(row)

        current_decision_date = _as_date(row.get("date") or row.get("decision_date"))
        current_decision_dt = _parse_date(current_decision_date)
        current_row_id = _row_id(row)

        if current_decision_dt is None:
            invalid_missing_decision_date += 1
            output_row.update(
                {
                    "adapter_type": "walk_forward_expectancy_availability_safe_builder",
                    "artifact_type": "signalforge_walk_forward_expectancy_row",
                    "contract": "walk_forward_expectancy",
                    "expectancy_state": "invalid_missing_decision_date",
                    "expectancy_scope": "none",
                    "expectancy_sample_count": 0,
                    "expectancy_average_return": None,
                    "expectancy_median_return": None,
                    "expectancy_win_rate": None,
                    "expectancy_minimum_sample_count": minimum_sample_count,
                    "training_window_start": None,
                    "training_window_end": None,
                    "uses_current_row_outcome": False,
                    "uses_future_rows": False,
                    "is_sample_limited": False,
                }
            )
            output_rows.append(output_row)
            expectancy_state_counts["invalid_missing_decision_date"] += 1
            data_state_counts[str(output_row.get("data_state") or "missing")] += 1
            continue

        training_window_end = _date_text(current_decision_dt - timedelta(days=1))

        while (
            training_index < len(training_samples)
            and training_samples[training_index]["availability_date"] <= training_window_end
        ):
            sample = training_samples[training_index]
            for scope_name, key in sample["scope_keys"]:
                pools[(scope_name, key)].append(sample)
            training_index += 1

        scope_name, selected_samples = _choose_scope(
            row,
            pools,
            minimum_sample_count=minimum_sample_count,
            current_row_id=current_row_id,
            current_decision_date=current_decision_date,
            training_window_end=training_window_end,
        )

        metrics = _metrics(selected_samples)
        expectancy_state = _classify(metrics, minimum_sample_count)

        uses_current = any(sample["row_id"] == current_row_id for sample in selected_samples)
        uses_future = any(
            sample["availability_date"] > training_window_end
            or sample["decision_date"] >= current_decision_date
            for sample in selected_samples
        )

        if uses_current:
            rows_using_current_row_outcome += 1
        if uses_future:
            rows_using_future_rows += 1
        if not training_window_end:
            rows_missing_training_window_end += 1

        training_window_start = None
        if selected_samples:
            training_window_start = min(sample["availability_date"] for sample in selected_samples)

        output_row.update(
            {
                "adapter_type": "walk_forward_expectancy_availability_safe_builder",
                "artifact_type": "signalforge_walk_forward_expectancy_row",
                "contract": "walk_forward_expectancy",
                "expectancy_state": expectancy_state,
                "expectancy_scope": scope_name,
                "expectancy_minimum_sample_count": minimum_sample_count,
                "training_window_start": training_window_start,
                "training_window_end": training_window_end,
                "uses_current_row_outcome": uses_current,
                "uses_future_rows": uses_future,
                "is_sample_limited": expectancy_state == "sample_limited",
            }
        )
        output_row.update(metrics)

        output_rows.append(output_row)

        expectancy_state_counts[expectancy_state] += 1
        expectancy_scope_counts[scope_name] += 1
        sample_count_counts[str(metrics["expectancy_sample_count"])] += 1
        data_state_counts[str(output_row.get("data_state") or "missing")] += 1

    blockers = []
    if not output_rows:
        blockers.append("no_walk_forward_expectancy_rows_written")
    if rows_using_current_row_outcome:
        blockers.append("uses_current_row_outcome")
    if rows_using_future_rows:
        blockers.append("uses_future_rows")

    summary = {
        "adapter_type": "walk_forward_expectancy_availability_safe_builder",
        "artifact_type": "signalforge_walk_forward_expectancy",
        "contract": "walk_forward_expectancy",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "input_row_count": len(rows),
        "output_row_count": len(output_rows),
        "scored_row_count": len(output_rows),
        "data_state_counts": dict(sorted(data_state_counts.items())),
        "expectancy_state_counts": dict(sorted(expectancy_state_counts.items())),
        "expectancy_scope_counts": dict(sorted(expectancy_scope_counts.items())),
        "expectancy_sample_count_counts": dict(sorted(sample_count_counts.items(), key=lambda item: int(item[0]))),
        "sample_policy": {
            "minimum_sample_count": minimum_sample_count,
            "sample_limited_is_terminal_state": True,
            "training_data_state_required": "complete",
            "training_availability_rule": "outcome_availability_date_lte_decision_date_minus_1_day",
            "strategy_key_rule": "strategy_plus_holding_period_days",
            "option_behavior_field_preference": "options_behavior_state_then_option_behavior_state",
        },
        "training_pool": {
            "complete_rows_seen": len(rows),
            "training_rows_accepted": len(training_samples),
            "training_rows_rejected": sum(rejected_counts.values()),
            "training_rows_rejected_counts": dict(sorted(rejected_counts.items())),
        },
        "leakage_checks": {
            "rows_missing_training_window_end": rows_missing_training_window_end,
            "rows_using_current_row_outcome": rows_using_current_row_outcome,
            "rows_using_future_rows": rows_using_future_rows,
            "invalid_missing_decision_date": invalid_missing_decision_date,
        },
        "paths": {
            "decision_rows_path": str(decision_rows_path),
            "rows_path": str(rows_path),
            "summary_path": str(summary_path),
        },
    }

    write_jsonl(rows_path, output_rows)
    write_json(summary_path, summary)

    return summary
