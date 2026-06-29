from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.options_portfolio.action_review_operation import (
    run_options_manual_action_review_operation,
)


FILE_WRITER_SCHEMA_VERSION = "options_manual_action_review_files.v1"
OPERATION_TYPE = "options_manual_action_review_file_writer"

DEFAULT_FILENAMES = {
    "options_manual_action_review": "options_manual_action_review.json",
    "operation_result": "options_manual_action_review_operation.json",
    "audit_report": "options_manual_action_review_audit.json",
    "health_report": "options_manual_action_review_health.json",
    "events": "options_manual_action_review_events.json",
    "event_log": "options_manual_action_review_operation.jsonl",
}


def write_options_manual_action_review_operation_files(
    source: Any,
    *,
    output_dir: str | PathLike[str],
    reviewed_at: str | None = None,
    reviewer: str | None = None,
) -> dict[str, Any]:
    """Write options manual action-review artifacts to local files.

    The writer records human review decisions only. It does not call broker APIs,
    route orders, submit orders, model fills, perform live execution, model
    slippage, or create automatic close/roll/defense orders.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    source_args = _extract_source_args(
        source,
        reviewed_at=reviewed_at,
        reviewer=reviewer,
    )

    event_log_path = output_path / DEFAULT_FILENAMES["event_log"]
    operation_result = run_options_manual_action_review_operation(
        source_args["operation_source"],
        metadata=source_args["metadata"],
        event_log_path=event_log_path,
    )

    action_review = _as_mapping(operation_result.get("options_manual_action_review"))
    audit_report = _as_mapping(operation_result.get("audit_report"))
    health_report = _as_mapping(operation_result.get("health_report"))
    events = _as_list(operation_result.get("events"))

    files = {
        "options_manual_action_review": output_path
        / DEFAULT_FILENAMES["options_manual_action_review"],
        "operation_result": output_path / DEFAULT_FILENAMES["operation_result"],
        "audit_report": output_path / DEFAULT_FILENAMES["audit_report"],
        "health_report": output_path / DEFAULT_FILENAMES["health_report"],
        "events": output_path / DEFAULT_FILENAMES["events"],
        "event_log": event_log_path,
    }

    _write_json(files["options_manual_action_review"], action_review)
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
    reviewed_at: str | None,
    reviewer: str | None,
) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {"operation_source": source, "metadata": {}}

    operation_source = dict(source)

    queue = _extract_first_mapping(
        source,
        "options_manual_action_queue",
        "manual_action_queue",
        "action_queue",
    )
    if queue is not None:
        operation_source["options_manual_action_queue"] = queue

    decisions = _extract_first_list(
        source,
        "review_decisions",
        "manual_review_decisions",
        "decisions",
    )
    if decisions is not None:
        operation_source["review_decisions"] = decisions

    selected_reviewed_at = _string_or_none(reviewed_at) or _string_or_none(
        source.get("reviewed_at") or source.get("evaluation_timestamp")
    )
    if selected_reviewed_at is not None:
        operation_source["reviewed_at"] = selected_reviewed_at

    selected_reviewer = _string_or_none(reviewer) or _string_or_none(source.get("reviewer"))
    if selected_reviewer is not None:
        operation_source["reviewer"] = selected_reviewer

    selected_queue_date = _string_or_none(source.get("queue_date") or source.get("plan_date"))
    if selected_queue_date is not None:
        operation_source["queue_date"] = selected_queue_date

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
            "has_manual_action_queue": False,
            "review_decision_count": 0,
            "queue_date": None,
            "reviewed_at": None,
            "reviewer": None,
        }

    queue = _as_mapping(source.get("options_manual_action_queue") or source.get("manual_action_queue"))
    review_decisions = _as_list(source.get("review_decisions"))

    return {
        "source_shape": "mapping",
        "has_manual_action_queue": bool(queue),
        "queue_status": _string_or_none(queue.get("status")),
        "queue_date": _string_or_none(source.get("queue_date") or queue.get("queue_date")),
        "reviewed_at": _string_or_none(source.get("reviewed_at")),
        "reviewer": _string_or_none(source.get("reviewer")),
        "priority_action_count": len(_as_list(queue.get("priority_actions"))),
        "review_decision_count": len(review_decisions),
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

