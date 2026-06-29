from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from os import PathLike
from pathlib import Path
from typing import Any

from src.options_portfolio.control_report_manifest_builder_operation import (
    run_options_portfolio_control_report_manifest_builder_operation,
)


FILE_WRITER_SCHEMA_VERSION = "options_portfolio_control_report_manifest_builder_files.v1"
OPERATION_TYPE = "options_portfolio_control_report_manifest_builder_file_writer"

DEFAULT_FILENAMES = {
    "manifest_artifact": "options_portfolio_control_report_artifact_manifest.json",
    "manifest": "options_portfolio_control_report_manifest.json",
    "operation_result": "options_portfolio_control_report_manifest_builder_operation.json",
    "audit_report": "options_portfolio_control_report_manifest_builder_audit.json",
    "health_report": "options_portfolio_control_report_manifest_builder_health.json",
    "events": "options_portfolio_control_report_manifest_builder_events.json",
    "event_log": "options_portfolio_control_report_manifest_builder_operation.jsonl",
}


def write_options_portfolio_control_report_manifest_builder_operation_files(
    source: Any,
    *,
    output_dir: str | PathLike[str],
    base_dir: str | PathLike[str] | None = None,
    report_date: str | None = None,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    source_args = _extract_source_args(source, report_date=report_date)

    event_log_path = output_path / DEFAULT_FILENAMES["event_log"]
    operation_result = run_options_portfolio_control_report_manifest_builder_operation(
        source_args["operation_source"],
        base_dir=base_dir,
        metadata=source_args["metadata"],
        event_log_path=event_log_path,
    )

    manifest_artifact = _as_mapping(
        operation_result.get("options_portfolio_control_report_artifact_manifest")
    )
    manifest = _as_mapping(manifest_artifact.get("manifest"))
    audit_report = _as_mapping(operation_result.get("audit_report"))
    health_report = _as_mapping(operation_result.get("health_report"))
    events = _as_list(operation_result.get("events"))

    files = {
        "manifest_artifact": output_path / DEFAULT_FILENAMES["manifest_artifact"],
        "manifest": output_path / DEFAULT_FILENAMES["manifest"],
        "operation_result": output_path / DEFAULT_FILENAMES["operation_result"],
        "audit_report": output_path / DEFAULT_FILENAMES["audit_report"],
        "health_report": output_path / DEFAULT_FILENAMES["health_report"],
        "events": output_path / DEFAULT_FILENAMES["events"],
        "event_log": event_log_path,
    }

    _write_json(files["manifest_artifact"], manifest_artifact)
    _write_json(files["manifest"], manifest)
    _write_json(files["operation_result"], operation_result)
    _write_json(files["audit_report"], audit_report)
    _write_json(files["health_report"], health_report)
    _write_json(files["events"], events)

    return {
        "schema_version": FILE_WRITER_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": operation_result.get("status", "needs_review"),
        "output_dir": str(output_path),
        "base_dir": str(base_dir) if base_dir is not None else None,
        "files": {key: str(path) for key, path in files.items()},
        "file_summary": _build_file_summary(files),
        "operation_result": operation_result,
        "manifest_artifact": manifest_artifact,
        "manifest": manifest,
        "manifest_summary": _as_mapping(manifest_artifact.get("manifest_summary")),
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

