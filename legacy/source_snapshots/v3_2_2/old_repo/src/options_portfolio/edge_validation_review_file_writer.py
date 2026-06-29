from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from os import PathLike
from pathlib import Path
from typing import Any

from src.options_portfolio.edge_validation_review_operation import (
    run_options_edge_validation_review_operation,
)


FILE_WRITER_SCHEMA_VERSION = "options_edge_validation_review_files.v1"
OPERATION_TYPE = "options_edge_validation_review_file_writer"

DEFAULT_FILENAMES = {
    "options_edge_validation_review": "options_edge_validation_review.json",
    "operation_result": "options_edge_validation_review_operation.json",
    "audit_report": "options_edge_validation_review_audit.json",
    "health_report": "options_edge_validation_review_health.json",
    "events": "options_edge_validation_review_events.json",
    "event_log": "options_edge_validation_review_operation.jsonl",
}


def write_options_edge_validation_review_operation_files(
    source: Any,
    *,
    output_dir: str | PathLike[str],
    review_date: str | None = None,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    source_args = _extract_source_args(source, review_date=review_date)

    event_log_path = output_path / DEFAULT_FILENAMES["event_log"]
    operation_result = run_options_edge_validation_review_operation(
        source_args["operation_source"],
        metadata=source_args["metadata"],
        event_log_path=event_log_path,
    )

    edge_review = _as_mapping(operation_result.get("options_edge_validation_review"))
    audit_report = _as_mapping(operation_result.get("audit_report"))
    health_report = _as_mapping(operation_result.get("health_report"))
    events = _as_list(operation_result.get("events"))

    files = {
        "options_edge_validation_review": output_path / DEFAULT_FILENAMES["options_edge_validation_review"],
        "operation_result": output_path / DEFAULT_FILENAMES["operation_result"],
        "audit_report": output_path / DEFAULT_FILENAMES["audit_report"],
        "health_report": output_path / DEFAULT_FILENAMES["health_report"],
        "events": output_path / DEFAULT_FILENAMES["events"],
        "event_log": event_log_path,
    }

    _write_json(files["options_edge_validation_review"], edge_review)
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


def _extract_source_args(source: Any, *, review_date: str | None) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {"operation_source": source, "metadata": {}}

    operation_source = dict(source)

    summaries = _extract_first_list(
        source,
        "options_edge_validation_summaries",
        "edge_validation_summaries",
        "summaries",
    )
    if summaries is not None:
        operation_source["options_edge_validation_summaries"] = summaries

    single_summary = _extract_first_mapping(
        source,
        "options_edge_validation_summary",
        "edge_validation_summary",
        "summary",
    )
    if single_summary is not None:
        operation_source["options_edge_validation_summary"] = single_summary

    thresholds = _extract_first_mapping(source, "review_thresholds", "thresholds")
    if thresholds is not None:
        operation_source["review_thresholds"] = thresholds

    selected_review_date = _string_or_none(review_date) or _string_or_none(
        source.get("review_date") or source.get("summary_date") or source.get("as_of_date")
    )
    if selected_review_date is not None:
        operation_source["review_date"] = selected_review_date

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
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
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
            "review_date": None,
            "has_edge_validation_summary": False,
            "summary_count": 0,
            "single_summary_present": False,
        }

    source_is_summary = source.get("artifact_type") == "options_edge_validation_summary"
    summaries = _as_list(source.get("options_edge_validation_summaries"))
    single_summary = _as_mapping(source.get("options_edge_validation_summary"))
    summary_count = len(summaries) + (1 if single_summary or source_is_summary else 0)

    return {
        "source_shape": "mapping",
        "review_date": _string_or_none(source.get("review_date")),
        "has_edge_validation_summary": summary_count > 0,
        "summary_count": summary_count,
        "single_summary_present": bool(single_summary or source_is_summary),
    }


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

