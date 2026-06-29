from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.historical_research_evidence_review_final_summary.operation import (
    run_historical_research_evidence_review_final_summary_operation,
)


FILE_WRITER_SCHEMA_VERSION = "historical_research_evidence_review_final_summary_files.v1"
OPERATION_TYPE = "historical_research_evidence_review_final_summary_file_writer"

DEFAULT_FILENAMES = {
    "final_summary": "historical_research_evidence_review_final_summary.json",
    "operation_result": "historical_research_evidence_review_final_summary_operation.json",
    "audit_report": "historical_research_evidence_review_final_summary_audit.json",
    "health_report": "historical_research_evidence_review_final_summary_health.json",
    "final_review_items": "historical_research_evidence_review_final_items.json",
    "event_log": "historical_research_evidence_review_final_summary_operation.jsonl",
}


def write_historical_research_evidence_review_final_summary_files(
    source: Any,
    *,
    output_dir: str | PathLike[str],
) -> dict[str, Any]:
    """Write historical research evidence review final summary artifacts.

    This writer does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only writes deterministic local final-summary
    files from an existing historical research evidence review artifact.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    event_log_path = output_path / DEFAULT_FILENAMES["event_log"]

    operation_result = run_historical_research_evidence_review_final_summary_operation(
        source,
        event_log_path=event_log_path,
    )

    final_summary = _as_mapping(operation_result.get("final_summary"))
    audit_report = _as_mapping(operation_result.get("audit_report"))
    health_report = _as_mapping(operation_result.get("health_report"))

    files = {
        "final_summary": output_path / DEFAULT_FILENAMES["final_summary"],
        "operation_result": output_path / DEFAULT_FILENAMES["operation_result"],
        "audit_report": output_path / DEFAULT_FILENAMES["audit_report"],
        "health_report": output_path / DEFAULT_FILENAMES["health_report"],
        "final_review_items": output_path / DEFAULT_FILENAMES["final_review_items"],
        "event_log": event_log_path,
    }

    _write_json(files["final_summary"], final_summary)
    _write_json(files["operation_result"], operation_result)
    _write_json(files["audit_report"], audit_report)
    _write_json(files["health_report"], health_report)
    _write_json(
        files["final_review_items"],
        _as_list(final_summary.get("final_review_items")),
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
