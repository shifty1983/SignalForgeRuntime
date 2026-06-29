from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


QUANTCONNECT_REPLAY_RESULT_IMPORT_VALIDATION_RESULT_FILENAME = (
    "signalforge_quantconnect_replay_result_import_validation.json"
)
QUANTCONNECT_REPLAY_RESULT_IMPORT_VALIDATION_SUMMARY_FILENAME = (
    "signalforge_quantconnect_replay_result_import_validation_summary.json"
)
QUANTCONNECT_REPLAY_RESULT_IMPORT_VALIDATION_CLI_SUMMARY_SCHEMA_VERSION = (
    "signalforge_quantconnect_replay_result_import_validation_cli_summary.v1"
)


def write_quantconnect_replay_result_import_validation_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / QUANTCONNECT_REPLAY_RESULT_IMPORT_VALIDATION_RESULT_FILENAME
    summary_path = output_path / QUANTCONNECT_REPLAY_RESULT_IMPORT_VALIDATION_SUMMARY_FILENAME

    result_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    summary = build_quantconnect_replay_result_import_validation_summary(
        result=result,
        result_path=result_path,
        summary_path=summary_path,
        output_dir=output_path,
    )
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return summary


def build_quantconnect_replay_result_import_validation_summary(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    summary_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    validation_summary = result.get("quantconnect_replay_result_import_validation_summary") or {}
    return {
        "schema_version": QUANTCONNECT_REPLAY_RESULT_IMPORT_VALIDATION_CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_quantconnect_replay_result_import_validator_cli",
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
        "quantconnect_replay_result_import_validation_summary": validation_summary,
        "matrix_metadata_envelope_key": result.get("matrix_metadata_envelope_key"),
        "matrix_cell_key_fields": result.get("matrix_cell_key_fields", []),
        "matrix_metadata_import_summary": result.get("matrix_metadata_import_summary", {}),
        "ready_to_build_exact_matrix_edge_summary": result.get("ready_to_build_exact_matrix_edge_summary"),
        "recommended_next_step": result.get("recommended_next_step"),
        "request_id": validation_summary.get("request_id"),
        "symbol_count": validation_summary.get("symbol_count", 0),
        "replay_candidate_count": validation_summary.get("replay_candidate_count", 0),
        "expected_result_file_count": validation_summary.get("expected_result_file_count", 0),
        "provided_result_file_count": validation_summary.get("provided_result_file_count", 0),
        "valid_result_file_count": validation_summary.get("valid_result_file_count", 0),
        "missing_result_file_count": validation_summary.get("missing_result_file_count", 0),
        "invalid_result_file_count": validation_summary.get("invalid_result_file_count", 0),
        "table_row_counts": validation_summary.get("table_row_counts", {}),
        "table_missing_field_counts": validation_summary.get("table_missing_field_counts", {}),
        "output_dir": str(output_dir),
        "files": {
            "quantconnect_replay_result_import_validation_result": str(result_path),
            "summary": str(summary_path),
        },
        "file_summary": {
            "file_count": 2,
            "written_file_count": 2,
            "missing_files": [],
            "empty_files": [],
            "file_sizes": {
                "quantconnect_replay_result_import_validation_result": result_path.stat().st_size
                if result_path.exists()
                else 0,
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
