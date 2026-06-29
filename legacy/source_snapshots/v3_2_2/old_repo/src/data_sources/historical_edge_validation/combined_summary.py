from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
import json


EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
    "automatic_close_orders",
    "automatic_roll_orders",
    "automatic_defense_orders",
    "automatic_strategy_changes",
    "automatic_parameter_changes",
    "automatic_pause_actions",
]


def read_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    return json.loads(source.read_text(encoding="utf-8-sig"))


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def discover_edge_validation_sources(paths: Iterable[str | Path]) -> list[Path]:
    discovered: list[Path] = []

    for raw_path in paths:
        path = Path(raw_path)

        if path.is_file():
            discovered.append(path)
            continue

        if path.is_dir():
            discovered.extend(
                sorted(path.rglob("signalforge_historical_edge_validation.json"))
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


def _combined_status(batch_summaries: list[dict[str, Any]]) -> str:
    if not batch_summaries:
        return "blocked"

    ready_count = sum(1 for batch in batch_summaries if batch["is_ready"])
    blocked_count = sum(1 for batch in batch_summaries if batch["status"] == "blocked")

    if ready_count == len(batch_summaries):
        return "ready"

    if blocked_count == len(batch_summaries):
        return "blocked"

    return "needs_review"


def _combined_edge_state(
    status: str,
    historical_edge_score: float | None,
    strategy_adjusted_win_rate: float | None,
    contract_outcome_count: int,
) -> str:
    if status == "blocked" or contract_outcome_count <= 0:
        return "historical_edge_blocked"

    score = historical_edge_score if historical_edge_score is not None else 0.0
    win_rate = strategy_adjusted_win_rate if strategy_adjusted_win_rate is not None else 0.0

    if score >= 0.75 and win_rate >= 0.5:
        return "historical_positive_edge_candidate"

    if score > 0.0 or win_rate >= 0.5:
        return "historical_mixed_edge_candidate"

    return "historical_no_confirmed_edge"


def build_historical_edge_validation_combined_summary(
    edge_validation_records: list[dict[str, Any]],
    *,
    source_paths: list[str | Path] | None = None,
    window_id: str | None = None,
) -> dict[str, Any]:
    source_paths = source_paths or []

    batch_summaries: list[dict[str, Any]] = []

    for index, record in enumerate(edge_validation_records):
        source_path = str(source_paths[index]) if index < len(source_paths) else None
        status = _status(record)
        is_ready = status == "ready" and _boolean(record.get("is_ready"))

        batch_summaries.append(
            {
                "batch_id": record.get("batch_id")
                or record.get("source_batch_id")
                or Path(source_path).parent.name
                if source_path
                else f"batch_{index + 1:04d}",
                "source_path": source_path,
                "status": status,
                "is_ready": is_ready,
                "historical_edge_state": record.get("historical_edge_state"),
                "historical_edge_score": _number(record.get("historical_edge_score")),
                "risk_adjusted_edge_score": _number(record.get("risk_adjusted_edge_score")),
                "symbol_count": _integer(record.get("symbol_count")),
                "contract_outcome_count": _integer(record.get("contract_outcome_count")),
                "filtered_option_row_count": _integer(record.get("filtered_option_row_count")),
                "market_price_snapshot_count": _integer(record.get("market_price_snapshot_count")),
                "portfolio_replay_snapshot_count": _integer(record.get("portfolio_replay_snapshot_count")),
                "maintenance_trigger_snapshot_count": _integer(
                    record.get("maintenance_trigger_snapshot_count")
                    or record.get("maintenance_trigger_count")
                ),
                "strategy_adjusted_win_rate": _number(record.get("strategy_adjusted_win_rate")),
                "average_contract_mark_return": _number(record.get("average_contract_mark_return")),
                "average_strategy_adjusted_return": _number(record.get("average_strategy_adjusted_return")),
                "blocked_reasons": record.get("blocked_reasons") or [],
                "warnings": record.get("warnings") or [],
            }
        )

    status = _combined_status(batch_summaries)
    is_ready = status == "ready"

    contract_outcome_count = sum(batch["contract_outcome_count"] for batch in batch_summaries)
    filtered_option_row_count = sum(batch["filtered_option_row_count"] for batch in batch_summaries)
    market_price_snapshot_count = sum(batch["market_price_snapshot_count"] for batch in batch_summaries)
    portfolio_replay_snapshot_count = sum(batch["portfolio_replay_snapshot_count"] for batch in batch_summaries)
    maintenance_trigger_snapshot_count = sum(
        batch["maintenance_trigger_snapshot_count"] for batch in batch_summaries
    )
    symbol_count = sum(batch["symbol_count"] for batch in batch_summaries)

    historical_edge_score = _weighted_average(edge_validation_records, "historical_edge_score")
    risk_adjusted_edge_score = _weighted_average(edge_validation_records, "risk_adjusted_edge_score")
    strategy_adjusted_win_rate = _weighted_average(
        edge_validation_records,
        "strategy_adjusted_win_rate",
    )
    average_contract_mark_return = _weighted_average(
        edge_validation_records,
        "average_contract_mark_return",
    )
    average_strategy_adjusted_return = _weighted_average(
        edge_validation_records,
        "average_strategy_adjusted_return",
    )

    historical_edge_state = _combined_edge_state(
        status,
        historical_edge_score,
        strategy_adjusted_win_rate,
        contract_outcome_count,
    )

    ready_batch_count = sum(1 for batch in batch_summaries if batch["is_ready"])
    blocked_batch_count = sum(1 for batch in batch_summaries if batch["status"] == "blocked")
    needs_review_batch_count = len(batch_summaries) - ready_batch_count - blocked_batch_count

    return {
        "adapter_type": "historical_edge_validation_combined_summary_builder",
        "artifact_type": "signalforge_historical_edge_validation_combined_summary",
        "schema_version": "signalforge_historical_edge_validation_combined_summary.v1",
        "window_id": window_id,
        "status": status,
        "is_ready": is_ready,
        "historical_edge_state": historical_edge_state,
        "historical_edge_score": historical_edge_score,
        "risk_adjusted_edge_score": risk_adjusted_edge_score,
        "strategy_adjusted_win_rate": strategy_adjusted_win_rate,
        "average_contract_mark_return": average_contract_mark_return,
        "average_strategy_adjusted_return": average_strategy_adjusted_return,
        "symbol_count": symbol_count,
        "contract_outcome_count": contract_outcome_count,
        "filtered_option_row_count": filtered_option_row_count,
        "market_price_snapshot_count": market_price_snapshot_count,
        "portfolio_replay_snapshot_count": portfolio_replay_snapshot_count,
        "maintenance_trigger_snapshot_count": maintenance_trigger_snapshot_count,
        "batch_count": len(batch_summaries),
        "ready_batch_count": ready_batch_count,
        "needs_review_batch_count": needs_review_batch_count,
        "blocked_batch_count": blocked_batch_count,
        "batch_summaries": batch_summaries,
        "blocked_reasons": _collect_unique_values(edge_validation_records, "blocked_reasons"),
        "warnings": _collect_unique_values(edge_validation_records, "warnings"),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "automatic_action": None,
        "automatic_close_order": None,
        "automatic_defense_order": None,
        "automatic_roll_order": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
    }
