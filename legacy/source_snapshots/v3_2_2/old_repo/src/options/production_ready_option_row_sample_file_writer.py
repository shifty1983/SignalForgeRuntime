from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


PRODUCTION_READY_OPTION_ROW_SAMPLE_RESULT_FILENAME = (
    "signalforge_production_ready_option_row_sample.json"
)
PRODUCTION_READY_OPTION_ROW_SAMPLE_OPTION_ROWS_FILENAME = "option_rows.json"
PRODUCTION_READY_OPTION_ROW_SAMPLE_SUMMARY_FILENAME = (
    "signalforge_production_ready_option_row_sample_summary.json"
)
PRODUCTION_READY_OPTION_ROW_SAMPLE_CLI_SUMMARY_SCHEMA_VERSION = (
    "signalforge_production_ready_option_row_sample_cli_summary.v1"
)


def write_production_ready_option_row_sample_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / PRODUCTION_READY_OPTION_ROW_SAMPLE_RESULT_FILENAME
    option_rows_path = output_path / PRODUCTION_READY_OPTION_ROW_SAMPLE_OPTION_ROWS_FILENAME
    summary_path = output_path / PRODUCTION_READY_OPTION_ROW_SAMPLE_SUMMARY_FILENAME

    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    option_rows_path.write_text(
        json.dumps({"option_rows": result.get("option_rows", [])}, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )

    summary = build_production_ready_option_row_sample_summary(
        result=result,
        result_path=result_path,
        option_rows_path=option_rows_path,
        summary_path=summary_path,
        output_dir=output_path,
    )
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return summary


def build_production_ready_option_row_sample_summary(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    option_rows_path: Path,
    summary_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    sample_summary = result.get("production_ready_option_row_sample_summary") or {}
    return {
        "schema_version": PRODUCTION_READY_OPTION_ROW_SAMPLE_CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_production_ready_option_row_sample_cli",
        "artifact_type": result.get("artifact_type"),
        "contract": result.get("contract"),
        "adapter_type": result.get("adapter_type"),
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "requires_manual_approval": result.get("requires_manual_approval"),
        "review_scope": result.get("review_scope"),
        "covered_capabilities": result.get("covered_capabilities"),
        "depends_on_capabilities": result.get("depends_on_capabilities"),
        "core_option_row_fields": result.get("core_option_row_fields"),
        "optional_option_row_fields": result.get("optional_option_row_fields"),
        "sample_policy": result.get("sample_policy"),
        "sample_parameters": result.get("sample_parameters"),
        "next_build_recommendations": result.get("next_build_recommendations"),
        "blocked_reasons": result.get("blocked_reasons", []),
        "production_ready_option_row_sample_summary": sample_summary,
        "symbol_count": sample_summary.get("symbol_count", 0),
        "option_row_count": sample_summary.get("option_row_count", 0),
        "output_dir": str(output_dir),
        "files": {
            "production_ready_option_row_sample_result": str(result_path),
            "option_rows": str(option_rows_path),
            "summary": str(summary_path),
        },
        "file_summary": {
            "file_count": 3,
            "written_file_count": 3,
            "missing_files": [],
            "empty_files": [],
            "file_sizes": {
                "production_ready_option_row_sample_result": result_path.stat().st_size
                if result_path.exists()
                else 0,
                "option_rows": option_rows_path.stat().st_size
                if option_rows_path.exists()
                else 0,
                "summary": summary_path.stat().st_size if summary_path.exists() else 0,
            },
        },
        "order_intent": result.get("order_intent"),
        "broker_order_id": result.get("broker_order_id"),
        "automatic_action": result.get("automatic_action"),
        "automatic_strategy_change": result.get("automatic_strategy_change"),
        "automatic_parameter_change": result.get("automatic_parameter_change"),
        "automatic_pause_action": result.get("automatic_pause_action"),
        "explicit_exclusions": result.get("explicit_exclusions"),
    }
