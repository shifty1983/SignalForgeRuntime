from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


HISTORICAL_EDGE_MATRIX_BACKFILL_PLAN_RESULT_FILENAME = (
    "signalforge_historical_edge_matrix_backfill_plan.json"
)
HISTORICAL_EDGE_MATRIX_BACKFILL_PLAN_SUMMARY_FILENAME = (
    "signalforge_historical_edge_matrix_backfill_plan_summary.json"
)
HISTORICAL_EDGE_MATRIX_BACKFILL_PLAN_CLI_SUMMARY_SCHEMA_VERSION = (
    "signalforge_historical_edge_matrix_backfill_plan_cli_summary.v1"
)


def write_historical_edge_matrix_backfill_plan_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / HISTORICAL_EDGE_MATRIX_BACKFILL_PLAN_RESULT_FILENAME
    summary_path = output_path / HISTORICAL_EDGE_MATRIX_BACKFILL_PLAN_SUMMARY_FILENAME

    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    summary = build_historical_edge_matrix_backfill_plan_summary(
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


def build_historical_edge_matrix_backfill_plan_summary(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    summary_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    plan_summary = result.get("backfill_plan_summary", {})
    audit_summary = result.get("audit_summary", {})
    return {
        "artifact_type": "historical_edge_matrix_backfill_plan_write_result",
        "schema_version": HISTORICAL_EDGE_MATRIX_BACKFILL_PLAN_CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_historical_edge_matrix_backfill_plan_cli",
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "requires_manual_approval": result.get("requires_manual_approval"),
        "result_path": str(result_path),
        "summary_path": str(summary_path),
        "output_dir": str(output_dir),
        "task_count": plan_summary.get("task_count", 0),
        "required_backfill_task_count": plan_summary.get("required_backfill_task_count", 0),
        "required_normalization_task_count": plan_summary.get(
            "required_normalization_task_count", 0
        ),
        "optional_enrichment_task_count": plan_summary.get("optional_enrichment_task_count", 0),
        "required_backfill_dimensions": plan_summary.get("required_backfill_dimensions", []),
        "required_normalization_dimensions": plan_summary.get(
            "required_normalization_dimensions", []
        ),
        "ready_to_build_exact_matrix_edge_summary": plan_summary.get(
            "ready_to_build_exact_matrix_edge_summary", False
        ),
        "recommended_next_contract": plan_summary.get("recommended_next_contract"),
        "matrix_mapping_state": audit_summary.get("matrix_mapping_state"),
        "records_requiring_mapping_count": plan_summary.get("records_requiring_mapping_count", 0),
        "exact_matrix_cell_ready_record_count": plan_summary.get(
            "exact_matrix_cell_ready_record_count", 0
        ),
        "warnings": result.get("warnings", []),
        "blocked_reasons": result.get("blocked_reasons", []),
        "explicit_exclusions": result.get("explicit_exclusions", []),
        "order_intent": result.get("order_intent"),
        "automatic_action": result.get("automatic_action"),
        "automatic_strategy_change": result.get("automatic_strategy_change"),
    }
