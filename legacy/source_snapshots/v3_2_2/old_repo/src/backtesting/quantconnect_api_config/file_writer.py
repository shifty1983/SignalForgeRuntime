from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.quantconnect_api_config.operation import (
    run_quantconnect_api_config_operation,
)


FILE_WRITER_SCHEMA_VERSION = "quantconnect_api_config_files.v1"
OPERATION_TYPE = "quantconnect_api_config_file_writer"

DEFAULT_FILENAMES = {
    "api_config": "quantconnect_api_config.json",
    "operation_result": "quantconnect_api_config_operation.json",
    "audit_report": "quantconnect_api_config_audit.json",
    "health_report": "quantconnect_api_config_health.json",
    "event_log": "quantconnect_api_config_operation.jsonl",
}


def write_quantconnect_api_config_files(
    source: Any,
    *,
    output_dir: str | PathLike[str],
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Write safe QuantConnect API config artifacts to local files.

    This writer does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only writes deterministic local config
    artifacts. API token values are never written to artifacts.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    event_log_path = output_path / DEFAULT_FILENAMES["event_log"]

    operation_result = run_quantconnect_api_config_operation(
        source,
        environment=environment,
        event_log_path=event_log_path,
    )

    api_config = _as_mapping(operation_result.get("api_config"))
    audit_report = _as_mapping(operation_result.get("audit_report"))
    health_report = _as_mapping(operation_result.get("health_report"))

    files = {
        "api_config": output_path / DEFAULT_FILENAMES["api_config"],
        "operation_result": output_path / DEFAULT_FILENAMES["operation_result"],
        "audit_report": output_path / DEFAULT_FILENAMES["audit_report"],
        "health_report": output_path / DEFAULT_FILENAMES["health_report"],
        "event_log": event_log_path,
    }

    _write_json(files["api_config"], api_config)
    _write_json(files["operation_result"], operation_result)
    _write_json(files["audit_report"], audit_report)
    _write_json(files["health_report"], health_report)

    file_summary = _build_file_summary(files)

    return {
        "schema_version": FILE_WRITER_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": operation_result.get("status", "needs_review"),
        "output_dir": str(output_path),
        "files": {key: str(path) for key, path in files.items()},
        "file_summary": file_summary,
        "operation_result": operation_result,
        "explicit_exclusions": list(operation_result.get("explicit_exclusions", [])),
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
            key for key, path in files.items() if not path.exists()
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
