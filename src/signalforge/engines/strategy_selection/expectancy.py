# Auto-promoted by Stage 40C4B.
# Core engine for Stage 18 walk_forward_expectancy.
# Backtesting should call this module instead of owning expectancy logic.

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, DefaultDict, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple


DATE_FORMAT = "%Y-%m-%d"
MISSING_VALUE = "__missing__"

DECISION_DATE_FIELDS = (
    "decision_date",
    "as_of_date",
    "signal_date",
    "snapshot_date",
    "date",
)

OUTCOME_DATE_FIELDS = (
    "outcome_date",
    "contract_outcome_date",
    "resolved_date",
    "close_date",
    "exit_date",
    "expiration_date",
)

SYMBOL_FIELDS = (
    "symbol",
    "underlying",
    "underlying_symbol",
    "ticker",
)

STRATEGY_FIELDS = (
    "strategy",
    "strategy_name",
    "candidate_strategy",
    "selected_strategy",
    "option_strategy",
    "trade_strategy",
)

REGIME_FIELDS = (
    "regime_state",
    "regime",
    "market_regime",
    "regime_label",
)

ASSET_BEHAVIOR_FIELDS = (
    "asset_behavior_state",
    "asset_behavior",
    "asset_state",
    "asset_behavior_label",
)

OPTION_BEHAVIOR_FIELDS = (
    "option_behavior_state",
    "option_behavior",
    "option_state",
    "option_behavior_label",
)

RETURN_FIELDS = (
    "strategy_adjusted_return",
    "adjusted_strategy_return",
    "strategy_return",
    "strategy_realized_return",
    "realized_return",
    "outcome_return",
    "contract_return",
    "return",
    "pnl_return",
    "pnl_pct",
    "profit_loss_pct",
)

DATA_STATE_FIELD = "data_state"
COMPLETE_DATA_STATE = "complete"

SCOPE_ORDER = (
    "symbol_strategy_regime_asset_option",
    "symbol_strategy_regime_asset",
    "symbol_strategy_regime",
    "strategy_regime_asset_option",
    "strategy_regime_asset",
    "strategy_regime",
    "strategy_global",
)


@dataclass(frozen=True)
class FieldValues:
    symbol: str
    strategy: str
    regime: str
    asset_behavior: str
    option_behavior: str


@dataclass(frozen=True)
class TrainingExample:
    source_index: int
    decision_date: date
    availability_date: date
    outcome_date_source: str
    return_value: float
    fields: FieldValues


@dataclass
class RunningStats:
    count: int = 0
    win_count: int = 0
    total_return: float = 0.0
    returns: List[float] = field(default_factory=list)
    first_availability_date: Optional[date] = None
    last_availability_date: Optional[date] = None

    def add(self, value: float, availability_date: date) -> None:
        self.count += 1
        if value > 0:
            self.win_count += 1
        self.total_return += value
        self.returns.append(value)

        if self.first_availability_date is None or availability_date < self.first_availability_date:
            self.first_availability_date = availability_date

        if self.last_availability_date is None or availability_date > self.last_availability_date:
            self.last_availability_date = availability_date

    @property
    def average_return(self) -> Optional[float]:
        if self.count == 0:
            return None
        return self.total_return / self.count

    @property
    def median_return(self) -> Optional[float]:
        if self.count == 0:
            return None
        return float(median(self.returns))

    @property
    def win_rate(self) -> Optional[float]:
        if self.count == 0:
            return None
        return self.win_count / self.count


def read_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc

            if not isinstance(value, dict):
                raise ValueError(f"Expected object at line {line_number}, got {type(value).__name__}")

            rows.append(value)

    return rows


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


def _first_present(row: Mapping[str, Any], fields: Sequence[str]) -> Tuple[Optional[Any], Optional[str]]:
    for field_name in fields:
        if field_name in row and row[field_name] not in (None, ""):
            return row[field_name], field_name

    return None, None


def _normalise_component(value: Any) -> str:
    if value in (None, ""):
        return MISSING_VALUE

    return str(value).strip() or MISSING_VALUE


def _parse_date(value: Any) -> Optional[date]:
    if value in (None, ""):
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, (int, float)):
        return None

    text = str(value).strip()
    if not text:
        return None

    for parser in (
        lambda item: datetime.strptime(item[:10], DATE_FORMAT).date(),
        lambda item: datetime.fromisoformat(item.replace("Z", "+00:00")).date(),
    ):
        try:
            return parser(text)
        except ValueError:
            continue

    return None


def _parse_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None

    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(parsed) or math.isinf(parsed):
        return None

    return parsed


def _decision_date_for_row(row: Mapping[str, Any]) -> Optional[date]:
    value, _ = _first_present(row, DECISION_DATE_FIELDS)
    return _parse_date(value)


def _field_values(row: Mapping[str, Any]) -> FieldValues:
    symbol, _ = _first_present(row, SYMBOL_FIELDS)
    strategy, _ = _first_present(row, STRATEGY_FIELDS)
    regime, _ = _first_present(row, REGIME_FIELDS)
    asset_behavior, _ = _first_present(row, ASSET_BEHAVIOR_FIELDS)
    option_behavior, _ = _first_present(row, OPTION_BEHAVIOR_FIELDS)

    return FieldValues(
        symbol=_normalise_component(symbol),
        strategy=_normalise_component(strategy),
        regime=_normalise_component(regime),
        asset_behavior=_normalise_component(asset_behavior),
        option_behavior=_normalise_component(option_behavior),
    )


def _return_value_for_row(row: Mapping[str, Any]) -> Optional[float]:
    value, _ = _first_present(row, RETURN_FIELDS)
    return _parse_float(value)


def _availability_date_for_row(row: Mapping[str, Any], decision_date: date) -> Tuple[date, str]:
    value, field_name = _first_present(row, OUTCOME_DATE_FIELDS)
    parsed = _parse_date(value)

    if parsed is not None:
        return parsed, field_name or "outcome_date"

    return decision_date, "decision_date_fallback"


def _scope_key(scope: str, fields: FieldValues) -> Tuple[str, ...]:
    if scope == "symbol_strategy_regime_asset_option":
        return (fields.symbol, fields.strategy, fields.regime, fields.asset_behavior, fields.option_behavior)

    if scope == "symbol_strategy_regime_asset":
        return (fields.symbol, fields.strategy, fields.regime, fields.asset_behavior)

    if scope == "symbol_strategy_regime":
        return (fields.symbol, fields.strategy, fields.regime)

    if scope == "strategy_regime_asset_option":
        return (fields.strategy, fields.regime, fields.asset_behavior, fields.option_behavior)

    if scope == "strategy_regime_asset":
        return (fields.strategy, fields.regime, fields.asset_behavior)

    if scope == "strategy_regime":
        return (fields.strategy, fields.regime)

    if scope == "strategy_global":
        return (fields.strategy,)

    raise ValueError(f"Unsupported expectancy scope: {scope}")


def _state_for_stats(stats: Optional[RunningStats], minimum_sample_count: int) -> str:
    if stats is None or stats.count == 0:
        return "no_prior_sample"

    if stats.count < minimum_sample_count:
        return "sample_limited"

    average_return = stats.average_return or 0.0
    win_rate = stats.win_rate or 0.0

    if average_return > 0 and win_rate >= 0.50:
        return "positive_expectancy_candidate"

    if average_return < 0 and win_rate < 0.50:
        return "negative_expectancy_candidate"

    return "mixed_expectancy"


def _select_stats(
    aggregators: Mapping[Tuple[str, Tuple[str, ...]], RunningStats],
    fields: FieldValues,
    minimum_sample_count: int,
) -> Tuple[str, Optional[RunningStats]]:
    candidates: List[Tuple[int, str, RunningStats]] = []

    for order_index, scope in enumerate(SCOPE_ORDER):
        stats = aggregators.get((scope, _scope_key(scope, fields)))

        if stats is None or stats.count == 0:
            continue

        candidates.append((order_index, scope, stats))

        if stats.count >= minimum_sample_count:
            return scope, stats

    if not candidates:
        return SCOPE_ORDER[0], None

    _, scope, stats = max(candidates, key=lambda item: (item[2].count, -item[0]))
    return scope, stats


def _make_training_examples(rows: Sequence[Mapping[str, Any]]) -> Tuple[List[TrainingExample], Dict[str, int]]:
    examples: List[TrainingExample] = []

    diagnostics = {
        "complete_rows_seen": 0,
        "training_rows_accepted": 0,
        "training_rows_rejected_non_complete": 0,
        "training_rows_rejected_missing_decision_date": 0,
        "training_rows_rejected_missing_return": 0,
        "training_rows_using_decision_date_fallback": 0,
    }

    for source_index, row in enumerate(rows):
        if row.get(DATA_STATE_FIELD) != COMPLETE_DATA_STATE:
            diagnostics["training_rows_rejected_non_complete"] += 1
            continue

        diagnostics["complete_rows_seen"] += 1

        decision_date = _decision_date_for_row(row)
        if decision_date is None:
            diagnostics["training_rows_rejected_missing_decision_date"] += 1
            continue

        return_value = _return_value_for_row(row)
        if return_value is None:
            diagnostics["training_rows_rejected_missing_return"] += 1
            continue

        availability_date, source = _availability_date_for_row(row, decision_date)

        if source == "decision_date_fallback":
            diagnostics["training_rows_using_decision_date_fallback"] += 1

        examples.append(
            TrainingExample(
                source_index=source_index,
                decision_date=decision_date,
                availability_date=availability_date,
                outcome_date_source=source,
                return_value=return_value,
                fields=_field_values(row),
            )
        )

        diagnostics["training_rows_accepted"] += 1

    examples.sort(key=lambda item: (item.availability_date, item.source_index))
    return examples, diagnostics


def _add_example_to_aggregators(
    aggregators: MutableMapping[Tuple[str, Tuple[str, ...]], RunningStats],
    example: TrainingExample,
) -> None:
    for scope in SCOPE_ORDER:
        key = (scope, _scope_key(scope, example.fields))
        aggregators.setdefault(key, RunningStats()).add(example.return_value, example.availability_date)


def _iso(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def build_walk_forward_expectancy_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    minimum_sample_count: int = 20,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if minimum_sample_count < 1:
        raise ValueError("minimum_sample_count must be >= 1")

    indexed_rows: List[Tuple[int, Mapping[str, Any], Optional[date]]] = [
        (index, row, _decision_date_for_row(row)) for index, row in enumerate(rows)
    ]

    rows_missing_decision_date = sum(1 for _, _, decision_date in indexed_rows if decision_date is None)

    sortable_rows = sorted(
        indexed_rows,
        key=lambda item: (item[2] or date.max, item[0]),
    )

    training_examples, training_diagnostics = _make_training_examples(rows)

    aggregators: Dict[Tuple[str, Tuple[str, ...]], RunningStats] = {}
    next_example_index = 0
    output_by_source_index: Dict[int, Dict[str, Any]] = {}

    state_counts: DefaultDict[str, int] = defaultdict(int)
    scope_counts: DefaultDict[str, int] = defaultdict(int)
    data_state_counts: DefaultDict[str, int] = defaultdict(int)
    missing_component_counts: DefaultDict[str, int] = defaultdict(int)

    rows_using_current_row_outcome = 0
    rows_using_future_rows = 0
    rows_missing_training_window_end = 0
    scored_rows = 0

    for source_index, row, current_decision_date in sortable_rows:
        data_state_counts[str(row.get(DATA_STATE_FIELD, MISSING_VALUE))] += 1

        enriched = dict(row)
        fields = _field_values(row)

        for component_name, component_value in (
            ("symbol", fields.symbol),
            ("strategy", fields.strategy),
            ("regime", fields.regime),
            ("asset_behavior", fields.asset_behavior),
            ("option_behavior", fields.option_behavior),
        ):
            if component_value == MISSING_VALUE:
                missing_component_counts[f"rows_missing_{component_name}"] += 1

        if current_decision_date is None:
            state = "invalid_missing_decision_date"
            state_counts[state] += 1
            rows_missing_training_window_end += 1

            enriched.update(
                {
                    "expectancy_scope": None,
                    "expectancy_sample_count": 0,
                    "expectancy_win_rate": None,
                    "expectancy_average_return": None,
                    "expectancy_median_return": None,
                    "expectancy_state": state,
                    "training_window_start": None,
                    "training_window_end": None,
                    "uses_current_row_outcome": False,
                    "uses_future_rows": False,
                    "is_sample_limited": False,
                    "expectancy_minimum_sample_count": minimum_sample_count,
                }
            )

            output_by_source_index[source_index] = enriched
            continue

        while (
            next_example_index < len(training_examples)
            and training_examples[next_example_index].availability_date < current_decision_date
        ):
            _add_example_to_aggregators(aggregators, training_examples[next_example_index])
            next_example_index += 1

        scope, stats = _select_stats(aggregators, fields, minimum_sample_count)
        state = _state_for_stats(stats, minimum_sample_count)

        state_counts[state] += 1
        scope_counts[scope] += 1
        scored_rows += 1

        sample_count = stats.count if stats is not None else 0
        win_rate = stats.win_rate if stats is not None else None
        average_return = stats.average_return if stats is not None else None
        median_return = stats.median_return if stats is not None else None

        training_window_start = stats.first_availability_date if stats is not None else None

        if stats is not None and stats.last_availability_date is not None:
            training_window_end = stats.last_availability_date
        else:
            training_window_end = current_decision_date - timedelta(days=1)

        uses_future_rows = bool(training_window_end and training_window_end >= current_decision_date)

        if uses_future_rows:
            rows_using_future_rows += 1

        if training_window_end is None:
            rows_missing_training_window_end += 1

        enriched.update(
            {
                "expectancy_scope": scope,
                "expectancy_sample_count": sample_count,
                "expectancy_win_rate": win_rate,
                "expectancy_average_return": average_return,
                "expectancy_median_return": median_return,
                "expectancy_state": state,
                "training_window_start": _iso(training_window_start),
                "training_window_end": _iso(training_window_end),
                "uses_current_row_outcome": False,
                "uses_future_rows": uses_future_rows,
                "is_sample_limited": state == "sample_limited",
                "expectancy_minimum_sample_count": minimum_sample_count,
            }
        )

        output_by_source_index[source_index] = enriched

    output_rows = [output_by_source_index[index] for index in range(len(rows))]

    blockers: List[str] = []

    if len(output_rows) != len(rows):
        blockers.append("output_row_count_does_not_match_input_row_count")

    if rows_missing_decision_date:
        blockers.append("rows_missing_decision_date")

    if rows_using_current_row_outcome:
        blockers.append("rows_using_current_row_outcome")

    if rows_using_future_rows:
        blockers.append("rows_using_future_rows")

    if rows_missing_training_window_end:
        blockers.append("rows_missing_training_window_end")

    if state_counts.get("sample_limited", 0) == 0:
        blockers.append("sample_limited_state_not_observed")

    if state_counts.get("no_prior_sample", 0) == 0:
        blockers.append("no_prior_sample_state_not_observed")

    if missing_component_counts.get("rows_missing_strategy", 0):
        blockers.append("rows_missing_strategy")

    summary: Dict[str, Any] = {
        "adapter_type": "walk_forward_expectancy_builder",
        "artifact_type": "signalforge_walk_forward_expectancy",
        "contract": "walk_forward_expectancy",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "input_row_count": len(rows),
        "output_row_count": len(output_rows),
        "scored_row_count": scored_rows,
        "expectancy_state_counts": {
            state: state_counts.get(state, 0)
            for state in (
                "no_prior_sample",
                "sample_limited",
                "positive_expectancy_candidate",
                "negative_expectancy_candidate",
                "mixed_expectancy",
                "invalid_missing_decision_date",
            )
        },
        "expectancy_scope_counts": {scope: scope_counts.get(scope, 0) for scope in SCOPE_ORDER},
        "data_state_counts": dict(sorted(data_state_counts.items())),
        "missing_component_counts": dict(sorted(missing_component_counts.items())),
        "training_pool": training_diagnostics,
        "leakage_checks": {
            "rows_using_current_row_outcome": rows_using_current_row_outcome,
            "rows_using_future_rows": rows_using_future_rows,
            "rows_missing_training_window_end": rows_missing_training_window_end,
        },
        "sample_policy": {
            "minimum_sample_count": minimum_sample_count,
            "sample_limited_is_terminal_state": True,
            "training_data_state_required": COMPLETE_DATA_STATE,
        },
        "paths": {},
    }

    return output_rows, summary


def build_walk_forward_expectancy_artifact(
    *,
    decision_rows_path: str | Path,
    output_dir: str | Path,
    minimum_sample_count: int = 20,
) -> Dict[str, Any]:
    output_path = Path(output_dir)

    rows_path = output_path / "signalforge_walk_forward_expectancy_rows.jsonl"
    summary_path = output_path / "signalforge_walk_forward_expectancy_summary.json"

    rows = read_jsonl(decision_rows_path)

    output_rows, summary = build_walk_forward_expectancy_rows(
        rows,
        minimum_sample_count=minimum_sample_count,
    )

    summary["paths"] = {
        "decision_rows_path": str(decision_rows_path),
        "rows_path": str(rows_path),
        "summary_path": str(summary_path),
    }

    write_jsonl(rows_path, output_rows)
    write_json(summary_path, summary)

    return summary
