from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.quantconnect_manual_backtest_evidence_pipeline.builder import (
    StageFunction,
)
from src.backtesting.quantconnect_manual_backtest_evidence_pipeline.operation import (
    run_quantconnect_manual_backtest_evidence_pipeline_operation,
)


FILE_WRITER_SCHEMA_VERSION = "quantconnect_manual_backtest_evidence_pipeline_files.v1"
OPERATION_TYPE = "quantconnect_manual_backtest_evidence_pipeline_file_writer"

DEFAULT_FILENAMES = {
    "pipeline_result": "quantconnect_manual_backtest_evidence_pipeline.json",
    "operation_result": "quantconnect_manual_backtest_evidence_pipeline_operation.json",
    "audit_report": "quantconnect_manual_backtest_evidence_pipeline_audit.json",
    "health_report": "quantconnect_manual_backtest_evidence_pipeline_health.json",
    "final_summary": "quantconnect_manual_backtest_evidence_pipeline_final_summary.json",
    "stage_statuses": "quantconnect_manual_backtest_evidence_pipeline_stage_statuses.json",
    "event_log": "quantconnect_manual_backtest_evidence_pipeline_operation.jsonl",
    "promotion_gate": ("quantconnect_manual_backtest_evidence_pipeline_promotion_gate.json"),
    "promotion_handoff": (
        "quantconnect_manual_backtest_evidence_pipeline_promotion_handoff.json"
    ),
    "downstream_intake": (
        "quantconnect_manual_backtest_evidence_pipeline_downstream_intake.json"
    ),
}


def write_quantconnect_manual_backtest_evidence_pipeline_files(
    source: Any,
    *,
    output_dir: str | PathLike[str],
    stage_functions: Mapping[str, StageFunction] | None = None,
) -> dict[str, Any]:
    """Write manual QuantConnect backtest evidence pipeline artifacts.

    This writer does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only writes deterministic local pipeline
    files from an existing manual QuantConnect backtest result source.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    event_log_path = output_path / DEFAULT_FILENAMES["event_log"]

    operation_result = run_quantconnect_manual_backtest_evidence_pipeline_operation(
        source,
        stage_functions=stage_functions,
        event_log_path=event_log_path,
    )

    pipeline_result = _as_mapping(operation_result.get("pipeline_result"))
    audit_report = _as_mapping(operation_result.get("audit_report"))
    health_report = _as_mapping(operation_result.get("health_report"))
    final_summary = _as_mapping(operation_result.get("final_summary"))
    promotion_gate = _as_mapping(operation_result.get("promotion_gate"))
    if not promotion_gate:
        promotion_gate = _as_mapping(pipeline_result.get("promotion_gate"))
    promotion_handoff = _as_mapping(
        operation_result.get("promotion_handoff")
    )
    if not promotion_handoff:
        promotion_handoff = _as_mapping(
            pipeline_result.get("promotion_handoff")
        )   
    

    downstream_intake = _as_mapping(
        operation_result.get("downstream_intake")
    )
    if not downstream_intake:
        downstream_intake = _as_mapping(
            pipeline_result.get("downstream_intake")
        )

    files = {
        "pipeline_result": output_path / DEFAULT_FILENAMES["pipeline_result"],
        "operation_result": output_path / DEFAULT_FILENAMES["operation_result"],
        "audit_report": output_path / DEFAULT_FILENAMES["audit_report"],
        "health_report": output_path / DEFAULT_FILENAMES["health_report"],
        "final_summary": output_path / DEFAULT_FILENAMES["final_summary"],
        "promotion_gate": output_path / DEFAULT_FILENAMES["promotion_gate"],
        "promotion_handoff": output_path / DEFAULT_FILENAMES["promotion_handoff"],
        "downstream_intake": output_path / DEFAULT_FILENAMES["downstream_intake"],
        "stage_statuses": output_path / DEFAULT_FILENAMES["stage_statuses"],
        "event_log": event_log_path,
    }

    _write_json(files["pipeline_result"], pipeline_result)
    _write_json(files["operation_result"], operation_result)
    _write_json(files["audit_report"], audit_report)
    _write_json(files["health_report"], health_report)
    _write_json(files["final_summary"], final_summary)
    _write_json(files["promotion_gate"], promotion_gate)
    _write_json(files["promotion_handoff"], promotion_handoff)
    _write_json(files["downstream_intake"], downstream_intake)
    _write_json(files["stage_statuses"], _as_mapping(pipeline_result.get("stage_statuses")))

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
