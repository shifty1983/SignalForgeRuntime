from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
from collections import Counter
import json

from src.signalforge.data_sources.historical_edge_validation.combined_summary import (
    EXPLICIT_EXCLUSIONS,
)
from src.signalforge.engines.strategy_selection.historical_replay_matrix_metadata_stamp import matrix_metadata_coverage


def read_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    return json.loads(source.read_text(encoding="utf-8-sig"))


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def discover_window_summary_sources(paths: Iterable[str | Path]) -> list[Path]:
    discovered: list[Path] = []

    for raw_path in paths:
        path = Path(raw_path)

        if path.is_file():
            discovered.append(path)
            continue

        if path.is_dir():
            discovered.extend(
                sorted(path.rglob("signalforge_historical_edge_validation_combined_summary.json"))
            )

    return sorted(dict.fromkeys(discovered), key=lambda item: str(item))


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int:
    number = _number(value)
    if number is None:
        return 0
    return int(number)


def _boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "ready"}

    return bool(value)


def _status(record: dict[str, Any]) -> str:
    status = str(record.get("status") or "").strip().lower()
    if status:
        return status

    return "ready" if _boolean(record.get("is_ready")) else "needs_review"


def _weighted_average(
    records: list[dict[str, Any]],
    value_field: str,
    weight_field: str = "contract_outcome_count",
) -> float | None:
    weighted_total = 0.0
    weight_total = 0.0
    fallback_values: list[float] = []

    for record in records:
        value = _number(record.get(value_field))
        if value is None:
            continue

        fallback_values.append(value)

        weight = _number(record.get(weight_field))
        if weight is None or weight <= 0:
            continue

        weighted_total += value * weight
        weight_total += weight

    if weight_total > 0:
        return round(weighted_total / weight_total, 6)

    if fallback_values:
        return round(sum(fallback_values) / len(fallback_values), 6)

    return None


def _simple_average(records: list[dict[str, Any]], value_field: str) -> float | None:
    values = [_number(record.get(value_field)) for record in records]
    values = [value for value in values if value is not None]

    if not values:
        return None

    return round(sum(values) / len(values), 6)


def _collect_unique_values(records: list[dict[str, Any]], field: str) -> list[Any]:
    values: list[Any] = []

    for record in records:
        raw_values = record.get(field) or []
        if not isinstance(raw_values, list):
            raw_values = [raw_values]

        for value in raw_values:
            if value not in values:
                values.append(value)

    return values


def _matrix_metadata_summary_from_record(record: dict[str, Any]) -> dict[str, Any]:
    direct = record.get("matrix_metadata_validation_summary")
    if isinstance(direct, dict):
        return dict(direct)

    nested = record.get("historical_edge_validation_summary")
    if isinstance(nested, dict) and isinstance(nested.get("matrix_metadata_validation_summary"), dict):
        return dict(nested["matrix_metadata_validation_summary"])

    outcome = record.get("contract_outcome_edge_summary")
    if isinstance(outcome, dict) and isinstance(outcome.get("matrix_metadata_summary"), dict):
        return dict(outcome["matrix_metadata_summary"])

    return {}


def _aggregate_matrix_metadata_window_summary(window_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    mapped_counts: Counter[str] = Counter()
    missing_counts: Counter[str] = Counter()
    cell_counts: Counter[str] = Counter()
    total_record_count = 0
    ready_record_count = 0
    needs_review_record_count = 0
    window_with_metadata_count = 0

    for window in window_summaries:
        summary = window.get("matrix_metadata_validation_summary")
        if not isinstance(summary, dict) or not summary:
            continue
        window_with_metadata_count += 1
        total_record_count += _integer(summary.get("contract_outcome_count"))
        ready_record_count += _integer(summary.get("exact_matrix_cell_ready_record_count"))
        needs_review_record_count += _integer(summary.get("needs_review_record_count"))
        for field, count in (summary.get("mapped_required_field_counts") or {}).items():
            mapped_counts[str(field)] += _integer(count)
        for field, count in (summary.get("missing_required_field_counts") or {}).items():
            missing_counts[str(field)] += _integer(count)
        for cell_key, count in (summary.get("matrix_cell_counts") or {}).items():
            cell_counts[str(cell_key)] += _integer(count)

    ready_to_build = total_record_count > 0 and ready_record_count == total_record_count and needs_review_record_count == 0
    if not window_summaries:
        state = "blocked"
    elif ready_to_build:
        state = "ready"
    elif window_with_metadata_count:
        state = "needs_review"
    else:
        state = "needs_review"

    return {
        "matrix_metadata_state": state,
        "window_count": len(window_summaries),
        "window_with_matrix_metadata_summary_count": window_with_metadata_count,
        "contract_outcome_count": total_record_count,
        "exact_matrix_cell_ready_record_count": ready_record_count,
        "needs_review_record_count": needs_review_record_count,
        "mapped_required_field_counts": dict(sorted(mapped_counts.items())),
        "missing_required_field_counts": dict(sorted(missing_counts.items())),
        "matrix_cell_count": len(cell_counts),
        "matrix_cell_counts": dict(sorted(cell_counts.items())),
        "source_window_matrix_metadata_coverage": matrix_metadata_coverage(window_summaries),
        "ready_to_build_exact_matrix_edge_summary": ready_to_build,
        "recommended_next_step": (
            "patch_historical_edge_validation_edge_diagnostics_matrix_metadata"
            if ready_to_build
            else "ensure_all_historical_edge_validation_windows_include_matrix_metadata_summary"
        ),
    }


def _combined_status(window_summaries: list[dict[str, Any]]) -> str:
    if not window_summaries:
        return "blocked"

    ready_count = sum(1 for window in window_summaries if window["is_ready"])
    blocked_count = sum(1 for window in window_summaries if window["status"] == "blocked")

    if ready_count == len(window_summaries):
        return "ready"

    if blocked_count == len(window_summaries):
        return "blocked"

    return "needs_review"


def _edge_state_counts(window_summaries: list[dict[str, Any]]) -> dict[str, int]:
    states = [str(window.get("historical_edge_state") or "") for window in window_summaries]

    return {
        "positive_window_count": sum(
            1 for state in states if state == "historical_positive_edge_candidate"
        ),
        "mixed_window_count": sum(
            1 for state in states if state == "historical_mixed_edge_candidate"
        ),
        "no_confirmed_edge_window_count": sum(
            1 for state in states if state == "historical_no_confirmed_edge"
        ),
        "edge_blocked_window_count": sum(
            1 for state in states if state == "historical_edge_blocked"
        ),
    }


def _multi_window_edge_state(
    *,
    status: str,
    window_count: int,
    positive_window_count: int,
    mixed_window_count: int,
    historical_edge_score: float | None,
    strategy_adjusted_win_rate: float | None,
    contract_outcome_count: int,
) -> str:
    if status == "blocked" or window_count <= 0 or contract_outcome_count <= 0:
        return "historical_edge_blocked"

    score = historical_edge_score if historical_edge_score is not None else 0.0
    win_rate = strategy_adjusted_win_rate if strategy_adjusted_win_rate is not None else 0.0

    positive_ratio = positive_window_count / window_count
    mixed_or_positive_ratio = (positive_window_count + mixed_window_count) / window_count

    if positive_ratio >= 0.70 and score >= 0.75 and win_rate >= 0.50:
        return "historical_positive_edge_candidate"

    if mixed_or_positive_ratio >= 0.70 and (score > 0.0 or win_rate >= 0.50):
        return "historical_mixed_edge_candidate"

    return "historical_no_confirmed_edge"


def build_historical_edge_validation_multi_window_summary(
    window_records: list[dict[str, Any]],
    *,
    source_paths: list[str | Path] | None = None,
    period_id: str | None = None,
) -> dict[str, Any]:
    source_paths = source_paths or []

    window_summaries: list[dict[str, Any]] = []

    for index, record in enumerate(window_records):
        source_path = str(source_paths[index]) if index < len(source_paths) else None
        status = _status(record)
        is_ready = status == "ready" and _boolean(record.get("is_ready"))

        inferred_window_id = record.get("window_id")
        if not inferred_window_id and source_path:
            parent_name = Path(source_path).parent.name
            inferred_window_id = parent_name.replace(
                "historical_edge_validation_research_export_", ""
            ).replace("_combined", "")

        window_summaries.append(
            {
                "window_id": inferred_window_id or f"window_{index + 1:04d}",
                "source_path": source_path,
                "status": status,
                "is_ready": is_ready,
                "historical_edge_state": record.get("historical_edge_state"),
                "historical_edge_score": _number(record.get("historical_edge_score")),
                "risk_adjusted_edge_score": _number(record.get("risk_adjusted_edge_score")),
                "strategy_adjusted_win_rate": _number(record.get("strategy_adjusted_win_rate")),
                "average_contract_mark_return": _number(record.get("average_contract_mark_return")),
                "average_strategy_adjusted_return": _number(
                    record.get("average_strategy_adjusted_return")
                ),
                "batch_count": _integer(record.get("batch_count")),
                "ready_batch_count": _integer(record.get("ready_batch_count")),
                "needs_review_batch_count": _integer(record.get("needs_review_batch_count")),
                "blocked_batch_count": _integer(record.get("blocked_batch_count")),
                "outcome_symbol_count": _integer(record.get("symbol_count")),
                "contract_outcome_count": _integer(record.get("contract_outcome_count")),
                "filtered_option_row_count": _integer(record.get("filtered_option_row_count")),
                "market_price_snapshot_count": _integer(record.get("market_price_snapshot_count")),
                "portfolio_replay_snapshot_count": _integer(
                    record.get("portfolio_replay_snapshot_count")
                ),
                "maintenance_trigger_snapshot_count": _integer(
                    record.get("maintenance_trigger_snapshot_count")
                ),
                "blocked_reasons": record.get("blocked_reasons") or [],
                "warnings": record.get("warnings") or [],
                "matrix_metadata_validation_summary": _matrix_metadata_summary_from_record(record),
            }
        )

    status = _combined_status(window_summaries)
    is_ready = status == "ready"

    edge_state_counts = _edge_state_counts(window_summaries)

    window_count = len(window_summaries)
    ready_window_count = sum(1 for window in window_summaries if window["is_ready"])
    blocked_window_count = sum(1 for window in window_summaries if window["status"] == "blocked")
    needs_review_window_count = window_count - ready_window_count - blocked_window_count

    batch_count = sum(window["batch_count"] for window in window_summaries)
    ready_batch_count = sum(window["ready_batch_count"] for window in window_summaries)
    needs_review_batch_count = sum(
        window["needs_review_batch_count"] for window in window_summaries
    )
    blocked_batch_count = sum(window["blocked_batch_count"] for window in window_summaries)

    outcome_symbol_window_count = sum(
        window["outcome_symbol_count"] for window in window_summaries
    )
    contract_outcome_count = sum(
        window["contract_outcome_count"] for window in window_summaries
    )
    filtered_option_row_count = sum(
        window["filtered_option_row_count"] for window in window_summaries
    )
    market_price_snapshot_count = sum(
        window["market_price_snapshot_count"] for window in window_summaries
    )
    portfolio_replay_snapshot_count = sum(
        window["portfolio_replay_snapshot_count"] for window in window_summaries
    )
    maintenance_trigger_snapshot_count = sum(
        window["maintenance_trigger_snapshot_count"] for window in window_summaries
    )

    historical_edge_score = _weighted_average(window_records, "historical_edge_score")
    risk_adjusted_edge_score = _weighted_average(window_records, "risk_adjusted_edge_score")
    strategy_adjusted_win_rate = _weighted_average(
        window_records,
        "strategy_adjusted_win_rate",
    )
    average_contract_mark_return = _weighted_average(
        window_records,
        "average_contract_mark_return",
    )
    average_strategy_adjusted_return = _weighted_average(
        window_records,
        "average_strategy_adjusted_return",
    )

    matrix_metadata_multi_window_summary = _aggregate_matrix_metadata_window_summary(window_summaries)

    historical_edge_state = _multi_window_edge_state(
        status=status,
        window_count=window_count,
        positive_window_count=edge_state_counts["positive_window_count"],
        mixed_window_count=edge_state_counts["mixed_window_count"],
        historical_edge_score=historical_edge_score,
        strategy_adjusted_win_rate=strategy_adjusted_win_rate,
        contract_outcome_count=contract_outcome_count,
    )

    positive_window_ratio = (
        round(edge_state_counts["positive_window_count"] / window_count, 6)
        if window_count
        else None
    )
    mixed_or_positive_window_ratio = (
        round(
            (
                edge_state_counts["positive_window_count"]
                + edge_state_counts["mixed_window_count"]
            )
            / window_count,
            6,
        )
        if window_count
        else None
    )

    return {
        "adapter_type": "historical_edge_validation_multi_window_summary_builder",
        "artifact_type": "signalforge_historical_edge_validation_multi_window_summary",
        "schema_version": "signalforge_historical_edge_validation_multi_window_summary.v1",
        "period_id": period_id,
        "status": status,
        "is_ready": is_ready,
        "historical_edge_state": historical_edge_state,
        "multi_window_edge_state": historical_edge_state,
        "historical_edge_score": historical_edge_score,
        "risk_adjusted_edge_score": risk_adjusted_edge_score,
        "strategy_adjusted_win_rate": strategy_adjusted_win_rate,
        "average_contract_mark_return": average_contract_mark_return,
        "average_strategy_adjusted_return": average_strategy_adjusted_return,
        "window_average_historical_edge_score": _simple_average(
            window_records,
            "historical_edge_score",
        ),
        "window_average_strategy_adjusted_win_rate": _simple_average(
            window_records,
            "strategy_adjusted_win_rate",
        ),
        "window_average_strategy_adjusted_return": _simple_average(
            window_records,
            "average_strategy_adjusted_return",
        ),
        "window_count": window_count,
        "ready_window_count": ready_window_count,
        "needs_review_window_count": needs_review_window_count,
        "blocked_window_count": blocked_window_count,
        **edge_state_counts,
        "positive_window_ratio": positive_window_ratio,
        "mixed_or_positive_window_ratio": mixed_or_positive_window_ratio,
        "batch_count": batch_count,
        "ready_batch_count": ready_batch_count,
        "needs_review_batch_count": needs_review_batch_count,
        "blocked_batch_count": blocked_batch_count,
        "outcome_symbol_window_count": outcome_symbol_window_count,
        "symbol_count": outcome_symbol_window_count,
        "symbol_count_interpretation": (
            "Sum of outcome-symbol appearances across windows, not unique symbols."
        ),
        "contract_outcome_count": contract_outcome_count,
        "filtered_option_row_count": filtered_option_row_count,
        "market_price_snapshot_count": market_price_snapshot_count,
        "portfolio_replay_snapshot_count": portfolio_replay_snapshot_count,
        "maintenance_trigger_snapshot_count": maintenance_trigger_snapshot_count,
        "window_summaries": window_summaries,
        "matrix_metadata_multi_window_summary": matrix_metadata_multi_window_summary,
        "ready_to_build_exact_matrix_edge_summary": matrix_metadata_multi_window_summary.get("ready_to_build_exact_matrix_edge_summary", False),
        "exact_matrix_cell_ready_record_count": matrix_metadata_multi_window_summary.get("exact_matrix_cell_ready_record_count", 0),
        "matrix_metadata_needs_review_record_count": matrix_metadata_multi_window_summary.get("needs_review_record_count", 0),
        "blocked_reasons": _collect_unique_values(window_records, "blocked_reasons"),
        "warnings": _collect_unique_values(window_records, "warnings"),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "automatic_action": None,
        "automatic_close_order": None,
        "automatic_defense_order": None,
        "automatic_roll_order": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
    }
