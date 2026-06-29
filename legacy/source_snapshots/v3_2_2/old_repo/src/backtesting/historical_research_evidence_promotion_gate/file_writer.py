from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.historical_research_evidence_promotion_gate.operation import (
    run_historical_research_evidence_promotion_gate_operation,
)


FILE_WRITER_SCHEMA_VERSION = "historical_research_evidence_promotion_gate_files.v1"
OPERATION_TYPE = "historical_research_evidence_promotion_gate_file_writer"

DEFAULT_FILENAMES = {
    "promotion_gate": "historical_research_evidence_promotion_gate.json",
    "operation_result": "historical_research_evidence_promotion_gate_operation.json",
    "audit_report": "historical_research_evidence_promotion_gate_audit.json",
    "health_report": "historical_research_evidence_promotion_gate_health.json",
    "promotable_evidence": "historical_research_promotable_evidence.json",
    "needs_review_evidence": "historical_research_promotion_needs_review_evidence.json",
    "blocked_evidence": "historical_research_promotion_blocked_evidence.json",
    "event_log": "historical_research_evidence_promotion_gate_operation.jsonl",
}


def write_historical_research_evidence_promotion_gate_files(
    source: Any,
    *,
    output_dir: str | PathLike[str],
) -> dict[str, Any]:
    """Write historical research evidence promotion gate artifacts.

    This writer does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only writes deterministic local promotion
    gate files from an existing final reviewed historical research evidence artifact.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    event_log_path = output_path / DEFAULT_FILENAMES["event_log"]

    operation_result = run_historical_research_evidence_promotion_gate_operation(
        source,
        event_log_path=event_log_path,
    )

    promotion_gate = _as_mapping(operation_result.get("promotion_gate"))
    audit_report = _as_mapping(operation_result.get("audit_report"))
    health_report = _as_mapping(operation_result.get("health_report"))

    files = {
        "promotion_gate": output_path / DEFAULT_FILENAMES["promotion_gate"],
        "operation_result": output_path / DEFAULT_FILENAMES["operation_result"],
        "audit_report": output_path / DEFAULT_FILENAMES["audit_report"],
        "health_report": output_path / DEFAULT_FILENAMES["health_report"],
        "promotable_evidence": output_path / DEFAULT_FILENAMES["promotable_evidence"],
        "needs_review_evidence": output_path
        / DEFAULT_FILENAMES["needs_review_evidence"],
        "blocked_evidence": output_path / DEFAULT_FILENAMES["blocked_evidence"],
        "event_log": event_log_path,
    }

    _write_json(files["promotion_gate"], promotion_gate)
    _write_json(files["operation_result"], operation_result)
    _write_json(files["audit_report"], audit_report)
    _write_json(files["health_report"], health_report)
    _write_json(
        files["promotable_evidence"],
        _as_list(promotion_gate.get("promotable_evidence")),
    )
    _write_json(
        files["needs_review_evidence"],
        _as_list(promotion_gate.get("needs_review_evidence")),
    )
    _write_json(
        files["blocked_evidence"],
        _as_list(promotion_gate.get("blocked_evidence")),
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
