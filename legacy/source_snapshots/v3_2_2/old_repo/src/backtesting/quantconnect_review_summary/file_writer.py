from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.quantconnect_review_summary.operation import (
    run_quantconnect_review_summary_operation,
)


FILE_WRITER_SCHEMA_VERSION = "quantconnect_review_summary_files.v1"
OPERATION_TYPE = "quantconnect_review_summary_file_writer"

DEFAULT_FILENAMES = {
    "review_summary": "quantconnect_review_summary.json",
    "operation_result": "quantconnect_review_summary_operation.json",
    "audit_report": "quantconnect_review_summary_audit.json",
    "health_report": "quantconnect_review_summary_health.json",
    "alignment": "quantconnect_review_summary_alignment.json",
    "decision_summary": "quantconnect_review_summary_decisions.json",
    "performance_summary": "quantconnect_review_summary_performance.json",
    "event_log": "quantconnect_review_summary_operation.jsonl",
}


def write_quantconnect_review_summary_files(
    export_operation_result: Any,
    result_import_operation_result: Any,
    *,
    output_dir: str | PathLike[str],
) -> dict[str, Any]:
    """Write QuantConnect review summary artifacts to local JSON/JSONL files.

    This writer does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only writes deterministic local review files
    from existing export and result-import operation artifacts.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    event_log_path = output_path / DEFAULT_FILENAMES["event_log"]

    operation_result = run_quantconnect_review_summary_operation(
        export_operation_result,
        result_import_operation_result,
        event_log_path=event_log_path,
    )

    review_summary = _as_mapping(operation_result.get("review_summary"))
    audit_report = _as_mapping(operation_result.get("audit_report"))
    health_report = _as_mapping(operation_result.get("health_report"))

    files = {
        "review_summary": output_path / DEFAULT_FILENAMES["review_summary"],
        "operation_result": output_path / DEFAULT_FILENAMES["operation_result"],
        "audit_report": output_path / DEFAULT_FILENAMES["audit_report"],
        "health_report": output_path / DEFAULT_FILENAMES["health_report"],
        "alignment": output_path / DEFAULT_FILENAMES["alignment"],
        "decision_summary": output_path / DEFAULT_FILENAMES["decision_summary"],
        "performance_summary": output_path / DEFAULT_FILENAMES["performance_summary"],
        "event_log": event_log_path,
    }

    _write_json(files["review_summary"], review_summary)
    _write_json(files["operation_result"], operation_result)
    _write_json(files["audit_report"], audit_report)
    _write_json(files["health_report"], health_report)
    _write_json(files["alignment"], _as_mapping(review_summary.get("alignment")))
    _write_json(
        files["decision_summary"],
        _as_mapping(review_summary.get("decision_summary")),
    )
    _write_json(
        files["performance_summary"],
        _as_mapping(review_summary.get("performance_summary")),
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
