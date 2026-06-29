from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.quantconnect_historical_research_adapter.operation import (
    run_quantconnect_historical_research_adapter_operation,
)


FILE_WRITER_SCHEMA_VERSION = "quantconnect_historical_research_adapter_files.v1"
OPERATION_TYPE = "quantconnect_historical_research_adapter_file_writer"

DEFAULT_FILENAMES = {
    "research_input": "quantconnect_historical_research_input.json",
    "operation_result": "quantconnect_historical_research_adapter_operation.json",
    "audit_report": "quantconnect_historical_research_adapter_audit.json",
    "health_report": "quantconnect_historical_research_adapter_health.json",
    "ready_payloads": "quantconnect_historical_research_ready_payloads.json",
    "needs_review_payloads": "quantconnect_historical_research_needs_review_payloads.json",
    "blocked_payloads": "quantconnect_historical_research_blocked_payloads.json",
    "event_log": "quantconnect_historical_research_adapter_operation.jsonl",
}


def write_quantconnect_historical_research_adapter_files(
    final_summary_result: Any,
    *,
    output_dir: str | PathLike[str],
) -> dict[str, Any]:
    """Write QuantConnect historical research adapter artifacts.

    This writer does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only writes deterministic local adapter files
    from an existing QuantConnect final summary result.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    event_log_path = output_path / DEFAULT_FILENAMES["event_log"]

    operation_result = run_quantconnect_historical_research_adapter_operation(
        final_summary_result,
        event_log_path=event_log_path,
    )

    research_input = _as_mapping(operation_result.get("research_input"))
    audit_report = _as_mapping(operation_result.get("audit_report"))
    health_report = _as_mapping(operation_result.get("health_report"))

    files = {
        "research_input": output_path / DEFAULT_FILENAMES["research_input"],
        "operation_result": output_path / DEFAULT_FILENAMES["operation_result"],
        "audit_report": output_path / DEFAULT_FILENAMES["audit_report"],
        "health_report": output_path / DEFAULT_FILENAMES["health_report"],
        "ready_payloads": output_path / DEFAULT_FILENAMES["ready_payloads"],
        "needs_review_payloads": output_path
        / DEFAULT_FILENAMES["needs_review_payloads"],
        "blocked_payloads": output_path / DEFAULT_FILENAMES["blocked_payloads"],
        "event_log": event_log_path,
    }

    _write_json(files["research_input"], research_input)
    _write_json(files["operation_result"], operation_result)
    _write_json(files["audit_report"], audit_report)
    _write_json(files["health_report"], health_report)
    _write_json(files["ready_payloads"], _as_list(research_input.get("ready_payloads")))
    _write_json(
        files["needs_review_payloads"],
        _as_list(research_input.get("needs_review_payloads")),
    )
    _write_json(
        files["blocked_payloads"],
        _as_list(research_input.get("blocked_payloads")),
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


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []
