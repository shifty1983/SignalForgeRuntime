from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.quantconnect_review_pipeline.runner import (
    run_quantconnect_review_pipeline,
)


FILE_WRITER_SCHEMA_VERSION = "quantconnect_review_pipeline_files.v1"
OPERATION_TYPE = "quantconnect_review_pipeline_file_writer"

DEFAULT_FILENAMES = {
    "pipeline_result": "quantconnect_review_pipeline_result.json",
    "pipeline_summary": "quantconnect_review_pipeline_summary.json",
    "review_summary_operation": "quantconnect_review_pipeline_review_summary_operation.json",
    "review_handoff_operation": "quantconnect_review_pipeline_review_handoff_operation.json",
    "ready_payloads": "quantconnect_review_pipeline_ready_payloads.json",
    "needs_review_payloads": "quantconnect_review_pipeline_needs_review_payloads.json",
    "blocked_payloads": "quantconnect_review_pipeline_blocked_payloads.json",
}


def write_quantconnect_review_pipeline_files(
    export_operation_result: Any,
    result_import_operation_result: Any,
    *,
    output_dir: str | PathLike[str],
) -> dict[str, Any]:
    """Write QuantConnect review pipeline artifacts to local JSON files.

    This writer does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only writes deterministic local files from
    existing export and result-import operation artifacts.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    pipeline_result = run_quantconnect_review_pipeline(
        export_operation_result,
        result_import_operation_result,
    )

    review_summary_operation = _as_mapping(
        pipeline_result.get("review_summary_operation")
    )
    review_handoff_operation = _as_mapping(
        pipeline_result.get("review_handoff_operation")
    )
    handoff_bundle = _as_mapping(review_handoff_operation.get("handoff_bundle"))

    files = {
        "pipeline_result": output_path / DEFAULT_FILENAMES["pipeline_result"],
        "pipeline_summary": output_path / DEFAULT_FILENAMES["pipeline_summary"],
        "review_summary_operation": output_path
        / DEFAULT_FILENAMES["review_summary_operation"],
        "review_handoff_operation": output_path
        / DEFAULT_FILENAMES["review_handoff_operation"],
        "ready_payloads": output_path / DEFAULT_FILENAMES["ready_payloads"],
        "needs_review_payloads": output_path
        / DEFAULT_FILENAMES["needs_review_payloads"],
        "blocked_payloads": output_path / DEFAULT_FILENAMES["blocked_payloads"],
    }

    _write_json(files["pipeline_result"], pipeline_result)
    _write_json(files["pipeline_summary"], _as_mapping(pipeline_result.get("summary")))
    _write_json(files["review_summary_operation"], review_summary_operation)
    _write_json(files["review_handoff_operation"], review_handoff_operation)
    _write_json(files["ready_payloads"], _as_list(handoff_bundle.get("ready_payloads")))
    _write_json(
        files["needs_review_payloads"],
        _as_list(handoff_bundle.get("needs_review_payloads")),
    )
    _write_json(
        files["blocked_payloads"],
        _as_list(handoff_bundle.get("blocked_payloads")),
    )

    file_summary = _build_file_summary(files)

    return {
        "schema_version": FILE_WRITER_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": pipeline_result.get("status", "needs_review"),
        "output_dir": str(output_path),
        "files": {key: str(path) for key, path in files.items()},
        "file_summary": file_summary,
        "pipeline_result": pipeline_result,
        "explicit_exclusions": list(pipeline_result.get("explicit_exclusions", [])),
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
