from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.quantconnect_result_import.operation import (
    run_quantconnect_result_import_operation,
)


FILE_WRITER_SCHEMA_VERSION = "quantconnect_result_import_files.v1"
OPERATION_TYPE = "quantconnect_result_import_file_writer"

DEFAULT_FILENAMES = {
    "import_result": "quantconnect_result_import.json",
    "operation_result": "quantconnect_result_import_operation.json",
    "audit_report": "quantconnect_result_import_audit.json",
    "health_report": "quantconnect_result_import_health.json",
    "performance_summary": "quantconnect_result_import_performance_summary.json",
    "signalforge_events": "quantconnect_result_import_signalforge_events.json",
    "event_log": "quantconnect_result_import_operation.jsonl",
}


def write_quantconnect_result_import_files(
    source: Any,
    *,
    output_dir: str | PathLike[str],
) -> dict[str, Any]:
    """Write QuantConnect result import artifacts to local JSON/JSONL files.

    This writer does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only writes deterministic local files from
    manually supplied QuantConnect backtest results/logs.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    event_log_path = output_path / DEFAULT_FILENAMES["event_log"]

    operation_result = run_quantconnect_result_import_operation(
        source,
        event_log_path=event_log_path,
    )

    import_result = _as_mapping(operation_result.get("import_result"))
    audit_report = _as_mapping(operation_result.get("audit_report"))
    health_report = _as_mapping(operation_result.get("health_report"))

    files = {
        "import_result": output_path / DEFAULT_FILENAMES["import_result"],
        "operation_result": output_path / DEFAULT_FILENAMES["operation_result"],
        "audit_report": output_path / DEFAULT_FILENAMES["audit_report"],
        "health_report": output_path / DEFAULT_FILENAMES["health_report"],
        "performance_summary": output_path
        / DEFAULT_FILENAMES["performance_summary"],
        "signalforge_events": output_path / DEFAULT_FILENAMES["signalforge_events"],
        "event_log": event_log_path,
    }

    _write_json(files["import_result"], import_result)
    _write_json(files["operation_result"], operation_result)
    _write_json(files["audit_report"], audit_report)
    _write_json(files["health_report"], health_report)
    _write_json(
        files["performance_summary"],
        _as_mapping(import_result.get("performance_summary")),
    )
    _write_json(
        files["signalforge_events"],
        _as_mapping(import_result.get("signalforge_events")),
    )

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
