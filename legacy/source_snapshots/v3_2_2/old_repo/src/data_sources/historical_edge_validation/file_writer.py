from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


HISTORICAL_EDGE_VALIDATION_RESULT_FILENAME = "signalforge_historical_edge_validation.json"
HISTORICAL_EDGE_VALIDATION_SUMMARY_FILENAME = "signalforge_historical_edge_validation_summary.json"
HISTORICAL_EDGE_VALIDATION_CLI_SUMMARY_SCHEMA_VERSION = "signalforge_historical_edge_validation_cli_summary.v1"


def write_historical_edge_validation_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / HISTORICAL_EDGE_VALIDATION_RESULT_FILENAME
    summary_path = output_path / HISTORICAL_EDGE_VALIDATION_SUMMARY_FILENAME

    result_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    summary = build_historical_edge_validation_summary(
        result=result,
        result_path=result_path,
        summary_path=summary_path,
        output_dir=output_path,
    )
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return summary


def build_historical_edge_validation_summary(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    summary_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    validation_summary = result.get("historical_edge_validation_summary") or {}
    outcome_summary = result.get("contract_outcome_edge_summary") or {}
    portfolio_summary = result.get("portfolio_replay_edge_summary") or {}
    maintenance_summary = result.get("maintenance_trigger_edge_summary") or {}
    matrix_metadata_summary = result.get("matrix_metadata_validation_summary") or validation_summary.get("matrix_metadata_validation_summary") or {}
    return {
        "schema_version": HISTORICAL_EDGE_VALIDATION_CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_historical_edge_validation_cli",
        "artifact_type": result.get("artifact_type"),
        "contract": result.get("contract"),
        "adapter_type": result.get("adapter_type"),
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "requires_manual_approval": result.get("requires_manual_approval"),
        "review_scope": result.get("review_scope"),
        "source_artifacts": result.get("source_artifacts"),
        "covered_capabilities": result.get("covered_capabilities"),
        "depends_on_capabilities": result.get("depends_on_capabilities"),
        "next_build_recommendations": result.get("next_build_recommendations", []),
        "blocked_reasons": result.get("blocked_reasons", []),
        "historical_edge_validation_summary": validation_summary,
        "contract_outcome_edge_summary": outcome_summary,
        "portfolio_replay_edge_summary": portfolio_summary,
        "maintenance_trigger_edge_summary": maintenance_summary,
        "matrix_metadata_validation_summary": matrix_metadata_summary,
        "ready_to_build_exact_matrix_edge_summary": result.get("ready_to_build_exact_matrix_edge_summary", validation_summary.get("ready_to_build_exact_matrix_edge_summary", False)),
        "exact_matrix_cell_ready_record_count": matrix_metadata_summary.get("exact_matrix_cell_ready_record_count", 0),
        "matrix_metadata_needs_review_record_count": matrix_metadata_summary.get("needs_review_record_count", 0),
        "recommended_next_step": result.get("recommended_next_step"),
        "request_id": validation_summary.get("request_id"),
        "symbol_count": validation_summary.get("symbol_count", 0),
        "replay_candidate_count": validation_summary.get("replay_candidate_count", 0),
        "contract_outcome_count": validation_summary.get("contract_outcome_count", 0),
        "portfolio_replay_snapshot_count": validation_summary.get("portfolio_replay_snapshot_count", 0),
        "maintenance_trigger_snapshot_count": validation_summary.get("maintenance_trigger_snapshot_count", 0),
        "win_rate": validation_summary.get("win_rate", 0.0),
        "average_contract_mark_return": validation_summary.get("average_contract_mark_return", 0.0),
        "historical_edge_score": validation_summary.get("historical_edge_score", 0.0),
        "historical_edge_state": validation_summary.get("historical_edge_state"),
        "table_row_counts": validation_summary.get("table_row_counts", {}),
        "output_dir": str(output_dir),
        "files": {
            "historical_edge_validation_result": str(result_path),
            "summary": str(summary_path),
        },
        "file_summary": {
            "file_count": 2,
            "written_file_count": 2,
            "missing_files": [],
            "empty_files": [],
            "file_sizes": {
                "historical_edge_validation_result": result_path.stat().st_size if result_path.exists() else 0,
                "summary": summary_path.stat().st_size if summary_path.exists() else 0,
            },
        },
        "portfolio_action": result.get("portfolio_action"),
        "position_size": result.get("position_size"),
        "order_intent": result.get("order_intent"),
        "broker_order_id": result.get("broker_order_id"),
        "automatic_action": result.get("automatic_action"),
        "automatic_strategy_change": result.get("automatic_strategy_change"),
        "automatic_parameter_change": result.get("automatic_parameter_change"),
        "automatic_pause_action": result.get("automatic_pause_action"),
        "automatic_close_order": result.get("automatic_close_order"),
        "automatic_roll_order": result.get("automatic_roll_order"),
        "automatic_defense_order": result.get("automatic_defense_order"),
        "explicit_exclusions": result.get("explicit_exclusions"),
    }
