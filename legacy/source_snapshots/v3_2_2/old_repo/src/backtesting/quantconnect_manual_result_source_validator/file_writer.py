from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.quantconnect_manual_result_source_validator.operation import (
    run_quantconnect_manual_result_source_validation_operation,
)


FILE_WRITER_SCHEMA_VERSION = (
    "quantconnect_manual_result_source_validation_files.v1"
)
OPERATION_TYPE = "quantconnect_manual_result_source_validation_file_writer"

DEFAULT_FILENAMES = {
    "validation": "quantconnect_manual_result_source_validation.json",
    "operation_result": (
        "quantconnect_manual_result_source_validation_operation.json"
    ),
    "audit_report": "quantconnect_manual_result_source_validation_audit.json",
    "health_report": "quantconnect_manual_result_source_validation_health.json",
    "checks": "quantconnect_manual_result_source_validation_checks.json",
    "placeholders": (
        "quantconnect_manual_result_source_validation_placeholders.json"
    ),
    "sensitive_fields": (
        "quantconnect_manual_result_source_validation_sensitive_fields.json"
    ),
    "event_log": "quantconnect_manual_result_source_validation_operation.jsonl",
}


def write_quantconnect_manual_result_source_validation_files(
    source: Any,
    *,
    output_dir: str | PathLike[str],
) -> dict[str, Any]:
    """Write manual QuantConnect source validation artifacts.

    This writer does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses.

    It only writes deterministic local validation files from a local manual
    QuantConnect result source JSON.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    event_log_path = output_path / DEFAULT_FILENAMES["event_log"]

    operation_result = run_quantconnect_manual_result_source_validation_operation(
        source,
        event_log_path=event_log_path,
    )

    validation = _as_mapping(operation_result.get("validation"))
    audit_report = _as_mapping(operation_result.get("audit_report"))
    health_report = _as_mapping(operation_result.get("health_report"))

    files = {
        "validation": output_path / DEFAULT_FILENAMES["validation"],
        "operation_result": output_path / DEFAULT_FILENAMES[
            "operation_result"
        ],
        "audit_report": output_path / DEFAULT_FILENAMES["audit_report"],
        "health_report": output_path / DEFAULT_FILENAMES["health_report"],
        "checks": output_path / DEFAULT_FILENAMES["checks"],
        "placeholders": output_path / DEFAULT_FILENAMES["placeholders"],
        "sensitive_fields": output_path / DEFAULT_FILENAMES[
            "sensitive_fields"
        ],
        "event_log": event_log_path,
    }

    _write_json(files["validation"], validation)
    _write_json(files["operation_result"], operation_result)
    _write_json(files["audit_report"], audit_report)
    _write_json(files["health_report"], health_report)
    _write_json(files["checks"], _as_list(validation.get("checks")))
    _write_json(
        files["placeholders"],
        _as_list(validation.get("placeholders")),
    )
    _write_json(
        files["sensitive_fields"],
        _as_list(validation.get("sensitive_fields")),
    )

    file_summary = _build_file_summary(files)

    return {
        "schema_version": FILE_WRITER_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": operation_result.get("status", "needs_review"),
        "output_dir": str(output_path),
        "files": {
            key: str(path)
            for key, path in files.items()
        },
        "file_summary": file_summary,
        "operation_result": operation_result,
        "explicit_exclusions": list(
            operation_result.get("explicit_exclusions", [])
        ),
    }


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
            key
            for key, path in files.items()
            if not path.exists()
        ),
        "empty_files": sorted(
            key
            for key, path in files.items()
            if path.exists() and path.stat().st_size == 0
        ),
    }


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)

    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value

    return []
