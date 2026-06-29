from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.position_maintenance.position_risk_monitor_operation import (
    run_options_position_risk_monitor_operation,
)


FILE_WRITER_SCHEMA_VERSION = "options_position_risk_monitor_files.v1"
OPERATION_TYPE = "options_position_risk_monitor_file_writer"

DEFAULT_FILENAMES = {
    "options_position_risk_monitor": "options_position_risk_monitor.json",
    "operation_result": "options_position_risk_monitor_operation.json",
    "audit_report": "options_position_risk_monitor_audit.json",
    "health_report": "options_position_risk_monitor_health.json",
    "events": "options_position_risk_monitor_events.json",
    "event_log": "options_position_risk_monitor_operation.jsonl",
}


def write_options_position_risk_monitor_operation_files(
    source: Any,
    *,
    output_dir: str | PathLike[str],
    evaluation_timestamp: str | None = None,
    plan_date: str | None = None,
    market_regime: str | None = None,
    max_candidates_per_position: int | None = None,
) -> dict[str, Any]:
    """Write scheduled options position risk-monitor artifacts to local files.

    The writer is alert/review only. It does not call broker APIs, route orders,
    submit orders, model fills, perform live execution, model slippage, or create
    automatic close/roll/defense orders.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    source_args = _extract_source_args(
        source,
        evaluation_timestamp=evaluation_timestamp,
        plan_date=plan_date,
        market_regime=market_regime,
        max_candidates_per_position=max_candidates_per_position,
    )

    event_log_path = output_path / DEFAULT_FILENAMES["event_log"]
    operation_result = run_options_position_risk_monitor_operation(
        source_args["operation_source"],
        metadata=source_args["metadata"],
        event_log_path=event_log_path,
    )

    monitor = _as_mapping(operation_result.get("options_position_risk_monitor"))
    audit_report = _as_mapping(operation_result.get("audit_report"))
    health_report = _as_mapping(operation_result.get("health_report"))
    events = _as_list(operation_result.get("events"))

    files = {
        "options_position_risk_monitor": output_path
        / DEFAULT_FILENAMES["options_position_risk_monitor"],
        "operation_result": output_path / DEFAULT_FILENAMES["operation_result"],
        "audit_report": output_path / DEFAULT_FILENAMES["audit_report"],
        "health_report": output_path / DEFAULT_FILENAMES["health_report"],
        "events": output_path / DEFAULT_FILENAMES["events"],
        "event_log": event_log_path,
    }

    _write_json(files["options_position_risk_monitor"], monitor)
    _write_json(files["operation_result"], operation_result)
    _write_json(files["audit_report"], audit_report)
    _write_json(files["health_report"], health_report)
    _write_json(files["events"], events)

    return {
        "schema_version": FILE_WRITER_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": operation_result.get("status", "needs_review"),
        "output_dir": str(output_path),
        "files": {key: str(path) for key, path in files.items()},
        "file_summary": _build_file_summary(files),
        "source_summary": _build_source_summary(source_args["operation_source"]),
        "operation_result": operation_result,
        "explicit_exclusions": list(operation_result.get("explicit_exclusions", [])),
    }


def _extract_source_args(
    source: Any,
    *,
    evaluation_timestamp: str | None,
    plan_date: str | None,
    market_regime: str | None,
    max_candidates_per_position: int | None,
) -> dict[str, Any]:
    source_mapping = source if isinstance(source, Mapping) else {}
    operation_source = dict(source_mapping)

    selected_positions = _extract_positions(source_mapping)
    if selected_positions is not None:
        operation_source["positions"] = selected_positions

    selected_market_data = _extract_market_data(source_mapping)
    if selected_market_data is not None:
        operation_source["latest_market_data"] = selected_market_data

    selected_evaluation_timestamp = _string_or_none(evaluation_timestamp) or _string_or_none(
        source_mapping.get("evaluation_timestamp")
    )
    if selected_evaluation_timestamp is not None:
        operation_source["evaluation_timestamp"] = selected_evaluation_timestamp

    selected_plan_date = _string_or_none(plan_date) or _string_or_none(
        source_mapping.get("plan_date")
    )
    if selected_plan_date is not None:
        operation_source["plan_date"] = selected_plan_date

    selected_market_regime = _string_or_none(market_regime) or _string_or_none(
        source_mapping.get("market_regime")
    )
    if selected_market_regime is not None:
        operation_source["market_regime"] = selected_market_regime

    selected_max_candidates = _optional_non_negative_int(
        max_candidates_per_position,
        fallback=source_mapping.get("max_candidates_per_position"),
    )
    if selected_max_candidates is not None:
        operation_source["max_candidates_per_position"] = selected_max_candidates

    return {
        "operation_source": operation_source,
        "metadata": _metadata(source_mapping.get("metadata")),
    }


def _extract_positions(source: Mapping[str, Any]) -> Any:
    for key in (
        "positions",
        "open_positions",
        "options_positions",
        "existing_positions",
    ):
        if key in source:
            return source.get(key)
    return None


def _extract_market_data(source: Mapping[str, Any]) -> Any:
    for key in (
        "latest_market_data",
        "market_data",
        "latest_quotes",
        "position_market_data",
    ):
        if key in source:
            return source.get(key)
    return None


def _metadata(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _optional_non_negative_int(value: Any, *, fallback: Any) -> int | None:
    selected = value if value is not None else fallback
    if selected is None:
        return None
    try:
        return int(selected)
    except (TypeError, ValueError):
        return selected


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_file_summary(files: Mapping[str, Path]) -> dict[str, Any]:
    return {
        "file_count": len(files),
        "written_files": sorted(files.keys()),
        "missing_files": sorted(
            key for key, path in files.items() if not path.exists()
        ),
        "empty_files": sorted(
            key
            for key, path in files.items()
            if path.exists() and path.stat().st_size == 0
        ),
    }


def _build_source_summary(operation_source: Mapping[str, Any]) -> dict[str, Any]:
    positions = operation_source.get("positions")
    position_count = (
        len(positions)
        if isinstance(positions, Sequence) and not isinstance(positions, (str, bytes))
        else 0
    )
    latest_market_data = operation_source.get("latest_market_data")
    market_data_count = len(latest_market_data) if isinstance(latest_market_data, Mapping) else 0

    return {
        "evaluation_timestamp": _string_or_none(operation_source.get("evaluation_timestamp")),
        "plan_date": _string_or_none(operation_source.get("plan_date")),
        "market_regime": _string_or_none(operation_source.get("market_regime")),
        "position_count": position_count,
        "latest_market_data_count": market_data_count,
        "has_thresholds": isinstance(operation_source.get("thresholds"), Mapping),
        "max_candidates_per_position": operation_source.get("max_candidates_per_position"),
    }


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None

