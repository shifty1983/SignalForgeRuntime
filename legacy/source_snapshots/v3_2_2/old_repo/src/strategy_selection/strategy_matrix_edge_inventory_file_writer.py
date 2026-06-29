from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


STRATEGY_MATRIX_EDGE_INVENTORY_RESULT_FILENAME = "signalforge_strategy_matrix_edge_inventory.json"
STRATEGY_MATRIX_EDGE_INVENTORY_SUMMARY_FILENAME = "signalforge_strategy_matrix_edge_inventory_summary.json"
STRATEGY_MATRIX_EDGE_INVENTORY_CLI_SUMMARY_SCHEMA_VERSION = "signalforge_strategy_matrix_edge_inventory_cli_summary.v1"


def write_strategy_matrix_edge_inventory_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / STRATEGY_MATRIX_EDGE_INVENTORY_RESULT_FILENAME
    summary_path = output_path / STRATEGY_MATRIX_EDGE_INVENTORY_SUMMARY_FILENAME

    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    summary = build_strategy_matrix_edge_inventory_summary(
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


def build_strategy_matrix_edge_inventory_summary(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    summary_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    inventory_summary = result.get("strategy_matrix_edge_inventory_summary") or {}
    portfolio_evidence = result.get("portfolio_level_edge_evidence") or {}
    return {
        "schema_version": STRATEGY_MATRIX_EDGE_INVENTORY_CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_strategy_matrix_edge_inventory_cli",
        "artifact_type": result.get("artifact_type"),
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "requires_manual_approval": result.get("requires_manual_approval"),
        "catalog_strategy_count": inventory_summary.get("catalog_strategy_count", 0),
        "defined_risk_strategy_count": inventory_summary.get("defined_risk_strategy_count", 0),
        "ready_matrix_cell_count": inventory_summary.get("ready_matrix_cell_count", 0),
        "review_required_matrix_cell_count": inventory_summary.get("review_required_matrix_cell_count", 0),
        "exact_strategy_edge_validated_count": inventory_summary.get("exact_strategy_edge_validated_count", 0),
        "family_edge_evidence_present_count": inventory_summary.get("family_edge_evidence_present_count", 0),
        "portfolio_level_mapping_required_count": inventory_summary.get("portfolio_level_mapping_required_count", 0),
        "missing_historical_edge_evidence_count": inventory_summary.get("missing_historical_edge_evidence_count", 0),
        "portfolio_edge_evidence_state": portfolio_evidence.get("portfolio_edge_evidence_state"),
        "historical_edge_state": portfolio_evidence.get("historical_edge_state"),
        "historical_edge_score": portfolio_evidence.get("historical_edge_score"),
        "warnings": result.get("warnings", []),
        "blocked_reasons": result.get("blocked_reasons", []),
        "result_path": str(result_path),
        "summary_path": str(summary_path),
        "output_dir": str(output_dir),
        "order_intent": result.get("order_intent"),
        "broker_order_id": result.get("broker_order_id"),
        "automatic_action": result.get("automatic_action"),
        "automatic_strategy_change": result.get("automatic_strategy_change"),
        "automatic_parameter_change": result.get("automatic_parameter_change"),
        "automatic_pause_action": result.get("automatic_pause_action"),
        "explicit_exclusions": result.get("explicit_exclusions"),
    }
