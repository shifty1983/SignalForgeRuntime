from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from os import PathLike
from pathlib import Path
from typing import Any

from src.options_portfolio.control_report import SECTION_DEFINITIONS
from src.options_portfolio.control_report_operation import (
    run_options_portfolio_control_report_operation,
)


FILE_WRITER_SCHEMA_VERSION = "options_portfolio_control_report_files.v1"
OPERATION_TYPE = "options_portfolio_control_report_file_writer"

DEFAULT_FILENAMES = {
    "options_portfolio_control_report": "options_portfolio_control_report.json",
    "operation_result": "options_portfolio_control_report_operation.json",
    "audit_report": "options_portfolio_control_report_audit.json",
    "health_report": "options_portfolio_control_report_health.json",
    "events": "options_portfolio_control_report_events.json",
    "event_log": "options_portfolio_control_report_operation.jsonl",
}


def write_options_portfolio_control_report_operation_files(
    source: Any,
    *,
    output_dir: str | PathLike[str],
    report_date: str | None = None,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    source_args = _extract_source_args(source, report_date=report_date)

    event_log_path = output_path / DEFAULT_FILENAMES["event_log"]
    operation_result = run_options_portfolio_control_report_operation(
        source_args["operation_source"],
        metadata=source_args["metadata"],
        event_log_path=event_log_path,
    )

    control_report = _as_mapping(operation_result.get("options_portfolio_control_report"))
    audit_report = _as_mapping(operation_result.get("audit_report"))
    health_report = _as_mapping(operation_result.get("health_report"))
    events = _as_list(operation_result.get("events"))

    files = {
        "options_portfolio_control_report": output_path / DEFAULT_FILENAMES["options_portfolio_control_report"],
        "operation_result": output_path / DEFAULT_FILENAMES["operation_result"],
        "audit_report": output_path / DEFAULT_FILENAMES["audit_report"],
        "health_report": output_path / DEFAULT_FILENAMES["health_report"],
        "events": output_path / DEFAULT_FILENAMES["events"],
        "event_log": event_log_path,
    }

    _write_json(files["options_portfolio_control_report"], control_report)
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


def _extract_source_args(source: Any, *, report_date: str | None) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {"operation_source": source, "metadata": {}}

    operation_source = dict(source)

    selected_report_date = _string_or_none(report_date) or _string_or_none(
        source.get("report_date")
        or source.get("control_date")
        or source.get("as_of_date")
        or source.get("run_date")
    )
    if selected_report_date is not None:
        operation_source["report_date"] = selected_report_date

    return {
        "operation_source": operation_source,
        "metadata": _metadata(source.get("metadata")),
    }


def _metadata(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
            "report_date": None,
            "control_section_count": len(SECTION_DEFINITIONS),
            "present_control_source_count": 0,
            "missing_control_source_count": len(SECTION_DEFINITIONS),
            "has_control_sources": False,
        }

    present_sections = [
        definition["section"]
        for definition in SECTION_DEFINITIONS
        if _find_artifact(source, definition["keys"])
    ]
    missing_sections = [
        definition["section"]
        for definition in SECTION_DEFINITIONS
        if definition["section"] not in present_sections
    ]

    return {
        "source_shape": "mapping",
        "report_date": _string_or_none(source.get("report_date")),
        "control_section_count": len(SECTION_DEFINITIONS),
        "present_control_source_count": len(present_sections),
        "missing_control_source_count": len(missing_sections),
        "has_control_sources": bool(present_sections),
        "present_sections": sorted(present_sections),
        "missing_sections": sorted(missing_sections),
    }


def _find_artifact(source: Mapping[str, Any], keys: Sequence[str]) -> Mapping[str, Any]:
    for key in keys:
        value = source.get(key)
        if isinstance(value, Mapping):
            return value

    for nested_key in ("artifacts", "source_artifacts", "control_sources"):
        nested = source.get(nested_key)
        if isinstance(nested, Mapping):
            for key in keys:
                value = nested.get(key)
                if isinstance(value, Mapping):
                    return value

    return {}


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

