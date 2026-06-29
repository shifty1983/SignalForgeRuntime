from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


HISTORICAL_EDGE_MATRIX_COVERAGE_AUDIT_RESULT_FILENAME = (
    "signalforge_historical_edge_matrix_coverage_audit.json"
)
HISTORICAL_EDGE_MATRIX_COVERAGE_AUDIT_SUMMARY_FILENAME = (
    "signalforge_historical_edge_matrix_coverage_audit_summary.json"
)
HISTORICAL_EDGE_MATRIX_COVERAGE_AUDIT_CLI_SUMMARY_SCHEMA_VERSION = (
    "signalforge_historical_edge_matrix_coverage_audit_cli_summary.v1"
)


def write_historical_edge_matrix_coverage_audit_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / HISTORICAL_EDGE_MATRIX_COVERAGE_AUDIT_RESULT_FILENAME
    summary_path = output_path / HISTORICAL_EDGE_MATRIX_COVERAGE_AUDIT_SUMMARY_FILENAME

    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    summary = build_historical_edge_matrix_coverage_audit_summary(
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


def build_historical_edge_matrix_coverage_audit_summary(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    summary_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    coverage_summary = result.get("coverage_summary", {})
    matrix_summary = result.get("matrix_inventory_summary", {})
    coverage_by_dimension = result.get("coverage_by_dimension", {})

    return {
        "artifact_type": "historical_edge_matrix_coverage_audit_write_result",
        "schema_version": HISTORICAL_EDGE_MATRIX_COVERAGE_AUDIT_CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_historical_edge_matrix_coverage_audit_cli",
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "requires_manual_approval": result.get("requires_manual_approval"),
        "result_path": str(result_path),
        "summary_path": str(summary_path),
        "output_dir": str(output_dir),
        "source_count": coverage_summary.get("source_count", 0),
        "total_record_count": coverage_summary.get("total_record_count", 0),
        "exact_matrix_cell_ready_record_count": coverage_summary.get(
            "exact_matrix_cell_ready_record_count", 0
        ),
        "records_requiring_mapping_count": coverage_summary.get(
            "records_requiring_mapping_count", 0
        ),
        "portfolio_level_edge_source_count": coverage_summary.get(
            "portfolio_level_edge_source_count", 0
        ),
        "matrix_mapping_state": coverage_summary.get("matrix_mapping_state"),
        "required_missing_dimensions": coverage_summary.get("required_missing_dimensions", []),
        "required_partial_dimensions": coverage_summary.get("required_partial_dimensions", []),
        "expected_matrix_cell_count": matrix_summary.get("catalog_strategy_count", 0),
        "inventory_ready_matrix_cell_count": matrix_summary.get("ready_matrix_cell_count", 0),
        "dimension_coverage_states": {
            dimension: detail.get("coverage_state")
            for dimension, detail in coverage_by_dimension.items()
        },
        "warnings": result.get("warnings", []),
        "blocked_reasons": result.get("blocked_reasons", []),
        "explicit_exclusions": result.get("explicit_exclusions", []),
        "order_intent": result.get("order_intent"),
        "automatic_action": result.get("automatic_action"),
        "automatic_strategy_change": result.get("automatic_strategy_change"),
    }
