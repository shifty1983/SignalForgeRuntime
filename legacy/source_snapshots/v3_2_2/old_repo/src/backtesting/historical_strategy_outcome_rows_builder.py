from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple


DATE_FORMAT = "%Y-%m-%d"
MISSING_VALUE = "__missing__"

SYMBOL_FIELDS = (
    "symbol",
    "underlying",
    "underlying_symbol",
    "ticker",
)

DECISION_DATE_FIELDS = (
    "decision_date",
    "date",
    "as_of_date",
    "signal_date",
    "snapshot_date",
    "entry_date",
    "open_date",
)

OUTCOME_DATE_FIELDS = (
    "outcome_date",
    "contract_outcome_date",
    "resolved_date",
    "close_date",
    "exit_date",
    "expiration_date",
    "expiry",
)

STRATEGY_FIELDS = (
    "strategy",
    "strategy_name",
    "candidate_strategy",
    "selected_strategy",
    "option_strategy",
    "trade_strategy",
    "strategy_type",
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
    "average_strategy_adjusted_return",
)

REGIME_FIELDS = (
    "regime_state",
    "regime",
    "market_regime",
)

ASSET_BEHAVIOR_FIELDS = (
    "asset_behavior_state",
    "asset_behavior",
    "asset_state",
)

OPTION_BEHAVIOR_FIELDS = (
    "option_behavior_state",
    "option_behavior",
    "option_state",
)


@dataclass(frozen=True)
class DecisionContext:
    decision_row_id: str
    symbol: str
    decision_date: str
    regime_state: str
    asset_behavior_state: str
    option_behavior_state: str
    source_data_state: str
    eligibility: Any


@dataclass(frozen=True)
class OutcomeCandidate:
    symbol: str
    decision_date: str
    outcome_date: str
    strategy: str
    strategy_adjusted_return: float
    source_path: str
    source_index: int
    source_container: str


def read_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc

            if not isinstance(payload, dict):
                raise ValueError(f"Expected object at line {line_number}, got {type(payload).__name__}")

            rows.append(payload)

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


def load_json_or_jsonl(path: str | Path) -> Any:
    source_path = Path(path)

    if source_path.suffix.lower() == ".jsonl":
        return read_jsonl(source_path)

    with source_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _first_present(row: Mapping[str, Any], fields: Sequence[str]) -> Tuple[Optional[Any], Optional[str]]:
    for field_name in fields:
        if field_name in row and row[field_name] not in (None, ""):
            return row[field_name], field_name

    return None, None


def _nested_state(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("state", "source_state", "label", "name", "value"):
            if key in value and value[key] not in (None, ""):
                return str(value[key]).strip() or MISSING_VALUE

        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    if value in (None, ""):
        return MISSING_VALUE

    return str(value).strip() or MISSING_VALUE


def _normalise_symbol(value: Any) -> str:
    if value in (None, ""):
        return MISSING_VALUE

    return str(value).strip().upper() or MISSING_VALUE


def _normalise_text(value: Any) -> str:
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


def _date_text(value: Any) -> Optional[str]:
    parsed = _parse_date(value)
    return parsed.isoformat() if parsed is not None else None


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


def _context_state(row: Mapping[str, Any], fields: Sequence[str]) -> str:
    value, _ = _first_present(row, fields)
    return _nested_state(value)


def _decision_context(row: Mapping[str, Any]) -> Optional[DecisionContext]:
    symbol_value, _ = _first_present(row, SYMBOL_FIELDS)
    date_value, _ = _first_present(row, DECISION_DATE_FIELDS)

    symbol = _normalise_symbol(symbol_value)
    decision_date = _date_text(date_value)

    if symbol == MISSING_VALUE or decision_date is None:
        return None

    decision_row_id = str(row.get("decision_row_id") or f"{decision_date}_{symbol}")

    return DecisionContext(
        decision_row_id=decision_row_id,
        symbol=symbol,
        decision_date=decision_date,
        regime_state=_context_state(row, REGIME_FIELDS),
        asset_behavior_state=_context_state(row, ASSET_BEHAVIOR_FIELDS),
        option_behavior_state=_context_state(row, OPTION_BEHAVIOR_FIELDS),
        source_data_state=str(row.get("data_state") or MISSING_VALUE),
        eligibility=row.get("eligibility"),
    )


def _update_walk_context(context: Dict[str, Any], row: Mapping[str, Any]) -> Dict[str, Any]:
    updated = dict(context)

    for key, fields in (
        ("symbol", SYMBOL_FIELDS),
        ("decision_date", DECISION_DATE_FIELDS),
        ("outcome_date", OUTCOME_DATE_FIELDS),
        ("strategy", STRATEGY_FIELDS),
    ):
        value, _ = _first_present(row, fields)
        if value not in (None, ""):
            updated[key] = value

    return updated


def _iter_candidate_dicts(
    value: Any,
    *,
    context: Optional[Dict[str, Any]] = None,
    container_path: str = "$",
) -> Iterator[Tuple[Mapping[str, Any], Dict[str, Any], str]]:
    inherited = context or {}

    if isinstance(value, Mapping):
        updated_context = _update_walk_context(inherited, value)
        yield value, updated_context, container_path

        for key, child in value.items():
            yield from _iter_candidate_dicts(
                child,
                context=updated_context,
                container_path=f"{container_path}.{key}",
            )

    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_candidate_dicts(
                child,
                context=inherited,
                container_path=f"{container_path}[{index}]",
            )


def _candidate_from_dict(
    row: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    source_path: str,
    source_index: int,
    source_container: str,
) -> Optional[OutcomeCandidate]:
    return_value, _ = _first_present(row, RETURN_FIELDS)
    parsed_return = _parse_float(return_value)

    if parsed_return is None:
        return None

    symbol_value, _ = _first_present(row, SYMBOL_FIELDS)
    date_value, _ = _first_present(row, DECISION_DATE_FIELDS)
    outcome_date_value, _ = _first_present(row, OUTCOME_DATE_FIELDS)
    strategy_value, _ = _first_present(row, STRATEGY_FIELDS)

    symbol = _normalise_symbol(symbol_value if symbol_value not in (None, "") else context.get("symbol"))
    decision_date = _date_text(date_value if date_value not in (None, "") else context.get("decision_date"))
    outcome_date = _date_text(
        outcome_date_value if outcome_date_value not in (None, "") else context.get("outcome_date")
    )
    strategy = _normalise_text(strategy_value if strategy_value not in (None, "") else context.get("strategy"))

    if symbol == MISSING_VALUE or decision_date is None or strategy == MISSING_VALUE:
        return None

    if outcome_date is None:
        outcome_date = decision_date

    return OutcomeCandidate(
        symbol=symbol,
        decision_date=decision_date,
        outcome_date=outcome_date,
        strategy=strategy,
        strategy_adjusted_return=parsed_return,
        source_path=source_path,
        source_index=source_index,
        source_container=source_container,
    )


def extract_outcome_candidates(source_paths: Sequence[str | Path]) -> Tuple[List[OutcomeCandidate], Dict[str, Any]]:
    candidates: List[OutcomeCandidate] = []
    diagnostics: Dict[str, Any] = {
        "source_file_count": len(source_paths),
        "source_files": [str(path) for path in source_paths],
        "scanned_dict_count": 0,
        "outcome_candidate_count": 0,
        "source_candidate_counts": {},
    }

    for source_path in source_paths:
        payload = load_json_or_jsonl(source_path)
        source_count = 0

        for source_index, (candidate_dict, context, container_path) in enumerate(
            _iter_candidate_dicts(payload)
        ):
            diagnostics["scanned_dict_count"] += 1

            candidate = _candidate_from_dict(
                candidate_dict,
                context,
                source_path=str(source_path),
                source_index=source_index,
                source_container=container_path,
            )

            if candidate is None:
                continue

            candidates.append(candidate)
            source_count += 1

        diagnostics["source_candidate_counts"][str(source_path)] = source_count

    diagnostics["outcome_candidate_count"] = len(candidates)

    return candidates, diagnostics


def build_historical_strategy_outcome_rows(
    *,
    decision_rows: Sequence[Mapping[str, Any]],
    outcome_source_paths: Sequence[str | Path],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    decision_index: Dict[Tuple[str, str], DecisionContext] = {}
    duplicate_decision_keys = 0
    rejected_decision_rows = 0
    decision_data_state_counts: Counter[str] = Counter()

    for row in decision_rows:
        decision_data_state_counts[str(row.get("data_state") or MISSING_VALUE)] += 1

        context = _decision_context(row)
        if context is None:
            rejected_decision_rows += 1
            continue

        key = (context.symbol, context.decision_date)
        if key in decision_index:
            duplicate_decision_keys += 1
            continue

        decision_index[key] = context

    outcome_candidates, outcome_diagnostics = extract_outcome_candidates(outcome_source_paths)

    output_rows: List[Dict[str, Any]] = []
    unmatched_outcome_candidates = 0
    matched_decision_keys: set[Tuple[str, str]] = set()
    strategy_counts: Counter[str] = Counter()
    rows_by_decision_key: defaultdict[Tuple[str, str], int] = defaultdict(int)

    for candidate in outcome_candidates:
        key = (candidate.symbol, candidate.decision_date)
        decision = decision_index.get(key)

        if decision is None:
            unmatched_outcome_candidates += 1
            continue

        matched_decision_keys.add(key)
        strategy_counts[candidate.strategy] += 1
        rows_by_decision_key[key] += 1

        output_rows.append(
            {
                "decision_row_id": decision.decision_row_id,
                "symbol": decision.symbol,
                "date": decision.decision_date,
                "decision_date": decision.decision_date,
                "outcome_date": candidate.outcome_date,
                "strategy": candidate.strategy,
                "strategy_adjusted_return": candidate.strategy_adjusted_return,
                "regime_state": decision.regime_state,
                "asset_behavior_state": decision.asset_behavior_state,
                "option_behavior_state": decision.option_behavior_state,
                "data_state": "complete",
                "source_decision_data_state": decision.source_data_state,
                "eligibility": decision.eligibility,
                "outcome_source_path": candidate.source_path,
                "outcome_source_index": candidate.source_index,
                "outcome_source_container": candidate.source_container,
            }
        )

    output_rows.sort(
        key=lambda row: (
            row["decision_date"],
            row["symbol"],
            row["strategy"],
            row["outcome_source_path"],
            row["outcome_source_index"],
        )
    )

    blockers: List[str] = []

    if not decision_index:
        blockers.append("no_valid_decision_context_rows")

    if outcome_diagnostics["outcome_candidate_count"] == 0:
        blockers.append("no_strategy_outcome_candidates_found")

    if not output_rows:
        blockers.append("no_strategy_outcome_rows_joined")

    if duplicate_decision_keys:
        blockers.append("duplicate_decision_context_keys")

    summary: Dict[str, Any] = {
        "adapter_type": "historical_strategy_outcome_rows_builder",
        "artifact_type": "signalforge_historical_strategy_outcome_rows",
        "contract": "historical_strategy_outcome_rows",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "decision_context": {
            "input_decision_row_count": len(decision_rows),
            "valid_decision_context_count": len(decision_index),
            "rejected_decision_row_count": rejected_decision_rows,
            "duplicate_decision_key_count": duplicate_decision_keys,
            "decision_data_state_counts": dict(sorted(decision_data_state_counts.items())),
        },
        "outcome_source": outcome_diagnostics,
        "join": {
            "output_row_count": len(output_rows),
            "matched_decision_count": len(matched_decision_keys),
            "unmatched_outcome_candidate_count": unmatched_outcome_candidates,
            "max_strategy_rows_per_decision": max(rows_by_decision_key.values()) if rows_by_decision_key else 0,
        },
        "strategy_counts": dict(sorted(strategy_counts.items())),
        "paths": {},
    }

    return output_rows, summary


def build_historical_strategy_outcome_rows_artifact(
    *,
    decision_rows_path: str | Path,
    outcome_source_paths: Sequence[str | Path],
    output_dir: str | Path,
) -> Dict[str, Any]:
    output_path = Path(output_dir)

    rows_path = output_path / "signalforge_historical_strategy_outcome_rows.jsonl"
    summary_path = output_path / "signalforge_historical_strategy_outcome_rows_summary.json"

    decision_rows = read_jsonl(decision_rows_path)

    output_rows, summary = build_historical_strategy_outcome_rows(
        decision_rows=decision_rows,
        outcome_source_paths=outcome_source_paths,
    )

    summary["paths"] = {
        "decision_rows_path": str(decision_rows_path),
        "outcome_source_paths": [str(path) for path in outcome_source_paths],
        "rows_path": str(rows_path),
        "summary_path": str(summary_path),
    }

    write_jsonl(rows_path, output_rows)
    write_json(summary_path, summary)

    return summary