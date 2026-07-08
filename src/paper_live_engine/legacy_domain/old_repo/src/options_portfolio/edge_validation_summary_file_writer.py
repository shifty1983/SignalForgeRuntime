from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.options_portfolio.edge_validation_summary_operation import (
    run_options_edge_validation_summary_operation,
)


FILE_WRITER_SCHEMA_VERSION = "options_edge_validation_summary_files.v1"
OPERATION_TYPE = "options_edge_validation_summary_file_writer"

DEFAULT_FILENAMES = {
    "options_edge_validation_summary": "options_edge_validation_summary.json",
    "operation_result": "options_edge_validation_summary_operation.json",
    "audit_report": "options_edge_validation_summary_audit.json",
    "health_report": "options_edge_validation_summary_health.json",
    "events": "options_edge_validation_summary_events.json",
    "event_log": "options_edge_validation_summary_operation.jsonl",
}


def write_options_edge_validation_summary_operation_files(
    source: Any,
    *,
    output_dir: str | PathLike[str],
    summary_date: str | None = None,
) -> dict[str, Any]:
    """Write options edge-validation summary artifacts to local files.

    The writer summarizes manual outcome records only. It does not call broker
    APIs, route orders, submit orders, model fills, perform live execution,
    model slippage, or create automatic close/roll/defense orders.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    source_args = _extract_source_args(source, summary_date=summary_date)

    event_log_path = output_path / DEFAULT_FILENAMES["event_log"]
    operation_result = run_options_edge_validation_summary_operation(
        source_args["operation_source"],
        metadata=source_args["metadata"],
        event_log_path=event_log_path,
    )

    edge_summary = _as_mapping(operation_result.get("options_edge_validation_summary"))
    audit_report = _as_mapping(operation_result.get("audit_report"))
    health_report = _as_mapping(operation_result.get("health_report"))
    events = _as_list(operation_result.get("events"))

    files = {
        "options_edge_validation_summary": output_path
        / DEFAULT_FILENAMES["options_edge_validation_summary"],
        "operation_result": output_path / DEFAULT_FILENAMES["operation_result"],
        "audit_report": output_path / DEFAULT_FILENAMES["audit_report"],
        "health_report": output_path / DEFAULT_FILENAMES["health_report"],
        "events": output_path / DEFAULT_FILENAMES["events"],
        "event_log": event_log_path,
    }

    _write_json(files["options_edge_validation_summary"], edge_summary)
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


def _extract_source_args(source: Any, *, summary_date: str | None) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {"operation_source": source, "metadata": {}}

    operation_source = dict(source)

    outcome_records = _extract_first_list(
        source,
        "options_manual_action_outcome_records",
        "manual_action_outcome_records",
        "outcome_records",
    )
    if outcome_records is not None:
        operation_source["options_manual_action_outcome_records"] = outcome_records

    single_outcome_record = _extract_first_mapping(
        source,
        "options_manual_action_outcome_record",
        "manual_action_outcome_record",
        "outcome_record",
    )
    if single_outcome_record is not None:
        operation_source["options_manual_action_outcome_record"] = single_outcome_record

    selected_summary_date = _string_or_none(summary_date) or _string_or_none(
        source.get("summary_date") or source.get("as_of_date") or source.get("plan_date")
    )
    if selected_summary_date is not None:
        operation_source["summary_date"] = selected_summary_date

    return {
        "operation_source": operation_source,
        "metadata": _metadata(source.get("metadata")),
    }


def _extract_first_mapping(source: Mapping[str, Any], *keys: str) -> dict[str, Any] | None:
    for key in keys:
        value = source.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return None


def _extract_first_list(source: Mapping[str, Any], *keys: str) -> list[Any] | None:
    for key in keys:
        value = source.get(key)
        if isinstance(value, list):
            return list(value)
    return None


def _metadata(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_file_summary(files: Mapping[str, Path]) -> dict[str, Any]:
    file_sizes = {key: path.stat().st_size if path.exists() else 0 for key, path in files.items()}
    missing_files = [key for key, path in files.items() if not path.exists()]
    empty_files = [key for key, size in file_sizes.items() if size <= 0]

    return {
        "file_count": len(files),
        "written_file_count": len(files) - len(missing_files),
        "missing_files": missing_files,
        "empty_files": empty_files,
        "file_sizes": file_sizes,
    }


def _build_source_summary(source: Any) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {
            "source_shape": type(source).__name__,
            "summary_date": None,
            "has_outcome_records": False,
            "outcome_record_count": 0,
            "single_outcome_record_present": False,
        }

    outcome_records = _as_list(source.get("options_manual_action_outcome_records"))
    single_outcome_record = _as_mapping(source.get("options_manual_action_outcome_record"))

    return {
        "source_shape": "mapping",
        "summary_date": _string_or_none(source.get("summary_date")),
        "has_outcome_records": bool(outcome_records or single_outcome_record),
        "outcome_record_count": len(outcome_records) + (1 if single_outcome_record else 0),
        "single_outcome_record_present": bool(single_outcome_record),
    }


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    return []


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

