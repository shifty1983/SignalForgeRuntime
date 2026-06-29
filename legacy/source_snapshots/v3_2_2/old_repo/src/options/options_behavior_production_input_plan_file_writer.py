from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


OPTIONS_BEHAVIOR_PRODUCTION_INPUT_PLAN_RESULT_FILENAME = (
    "signalforge_options_behavior_production_input_plan.json"
)
OPTIONS_BEHAVIOR_PRODUCTION_INPUT_PLAN_SUMMARY_FILENAME = (
    "signalforge_options_behavior_production_input_plan_summary.json"
)
OPTIONS_BEHAVIOR_PRODUCTION_INPUT_PLAN_CLI_SUMMARY_SCHEMA_VERSION = (
    "signalforge_options_behavior_production_input_plan_cli_summary.v1"
)


def write_options_behavior_production_input_plan_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / OPTIONS_BEHAVIOR_PRODUCTION_INPUT_PLAN_RESULT_FILENAME
    summary_path = output_path / OPTIONS_BEHAVIOR_PRODUCTION_INPUT_PLAN_SUMMARY_FILENAME

    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    summary = build_options_behavior_production_input_plan_summary(
        result=result,
        result_path=result_path,
        summary_path=summary_path,
        output_dir=output_path,
    )

    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    return summary


def build_options_behavior_production_input_plan_summary(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    summary_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    input_summary = result.get("options_behavior_production_input_summary") or {}

    return {
        "schema_version": OPTIONS_BEHAVIOR_PRODUCTION_INPUT_PLAN_CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_options_behavior_production_input_plan_cli",
        "artifact_type": result.get("artifact_type"),
        "contract": result.get("contract"),
        "adapter_type": result.get("adapter_type"),
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "requires_manual_approval": result.get("requires_manual_approval"),
        "review_scope": result.get("review_scope"),
        "covered_capabilities": result.get("covered_capabilities"),
        "depends_on_capabilities": result.get("depends_on_capabilities"),
        "minimum_rows_per_symbol": result.get("minimum_rows_per_symbol"),
        "core_option_row_fields": result.get("core_option_row_fields"),
        "optional_option_row_fields": result.get("optional_option_row_fields"),
        "source_compatibility": result.get("source_compatibility"),
        "manual_import_contract": result.get("manual_import_contract"),
        "next_build_recommendations": result.get("next_build_recommendations"),
        "blocked_reasons": result.get("blocked_reasons", []),
        "options_behavior_production_input_summary": input_summary,
        "symbol_count": input_summary.get("symbol_count", 0),
        "option_row_count": input_summary.get("option_row_count", 0),
        "production_input_ready_symbol_count": input_summary.get(
            "production_input_ready_symbol_count", 0
        ),
        "production_input_review_symbol_count": input_summary.get(
            "production_input_review_symbol_count", 0
        ),
        "source_contract_state": input_summary.get("source_contract_state"),
        "output_dir": str(output_dir),
        "files": {
            "options_behavior_production_input_plan_result": str(result_path),
            "summary": str(summary_path),
        },
        "file_summary": {
            "file_count": 2,
            "written_file_count": 2,
            "missing_files": [],
            "empty_files": [],
            "file_sizes": {
                "options_behavior_production_input_plan_result": (
                    result_path.stat().st_size if result_path.exists() else 0
                ),
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
