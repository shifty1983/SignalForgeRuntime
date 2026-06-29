from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


RESULT_FILENAME = "signalforge_quantconnect_cloud_replay_batch_runner_plan.json"
SUMMARY_FILENAME = "signalforge_quantconnect_cloud_replay_batch_runner_plan_summary.json"


def write_signalforge_quantconnect_cloud_replay_batch_runner_plan(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / RESULT_FILENAME
    summary_path = output_path / SUMMARY_FILENAME

    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    batch_plan_dir = output_path / "batch_operation_plans"
    batch_plan_dir.mkdir(parents=True, exist_ok=True)

    batch_plan_files: dict[str, str] = {}
    for batch_plan in result.get("batch_plans", []):
        if not isinstance(batch_plan, Mapping):
            continue

        batch_id = str(batch_plan.get("batch_id") or "unknown_batch")
        batch_path = batch_plan_dir / f"{batch_id}_cloud_replay_operations.json"
        batch_path.write_text(json.dumps(batch_plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        batch_plan_files[batch_id] = str(batch_path)

    summary = _summary_payload(result, output_path, result_path, summary_path, batch_plan_files)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _summary_payload(
    result: Mapping[str, Any],
    output_dir: Path,
    result_path: Path,
    summary_path: Path,
    batch_plan_files: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "operation_type": "signalforge_quantconnect_cloud_replay_batch_runner_plan_cli",
        "adapter_type": result.get("adapter_type"),
        "artifact_type": result.get("artifact_type"),
        "schema_version": "signalforge_quantconnect_cloud_replay_batch_runner_plan_cli_summary.v1",
        "contract": result.get("contract"),
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "mode": result.get("mode"),
        "requires_manual_approval": result.get("requires_manual_approval"),
        "review_scope": result.get("review_scope"),
        "blocked_reasons": list(result.get("blocked_reasons", [])),
        "warnings": list(result.get("warnings", [])),
        "covered_capabilities": list(result.get("covered_capabilities", [])),
        "depends_on_capabilities": list(result.get("depends_on_capabilities", [])),
        "explicit_exclusions": list(result.get("explicit_exclusions", [])),
        "source_artifacts": dict(result.get("source_artifacts", {})),
        "matrix_metadata_envelope_key": result.get("matrix_metadata_envelope_key"),
        "matrix_cell_key_fields": list(result.get("matrix_cell_key_fields", [])),
        "matrix_metadata_batch_summary": dict(result.get("matrix_metadata_batch_summary", {})),
        "ready_to_build_exact_matrix_edge_summary": result.get(
            "ready_to_build_exact_matrix_edge_summary"
        ),
        "output_dir": str(output_dir),
        "files": {
            "cloud_replay_batch_runner_plan": str(result_path),
            "summary": str(summary_path),
            "batch_operation_plans": dict(batch_plan_files),
        },
        "file_summary": {
            "file_count": 2 + len(batch_plan_files),
            "written_file_count": 2 + len(batch_plan_files),
            "missing_files": [],
            "empty_files": [],
            "file_sizes": {
                "cloud_replay_batch_runner_plan": result_path.stat().st_size if result_path.exists() else 0,
                "summary": summary_path.stat().st_size if summary_path.exists() else 0,
            },
        },
        "quantconnect_project_id": result.get("quantconnect_project_id"),
        "quantconnect_organization_id": result.get("quantconnect_organization_id"),
        "quantconnect_project_file_name": result.get("quantconnect_project_file_name"),
        "delete_object_store_after_local_validation": result.get(
            "delete_object_store_after_local_validation"
        ),
        "source_request_id": result.get("source_request_id"),
        "source_start": result.get("source_start"),
        "source_end": result.get("source_end"),
        "batch_count": result.get("batch_count"),
        "operation_count": result.get("operation_count"),
        "api_operation_count": result.get("api_operation_count"),
        "matrix_metadata_batch_summary": dict(result.get("matrix_metadata_batch_summary", {})),
        "runner_plan_summary": dict(result.get("runner_plan_summary", {})),
        "next_build_recommendations": list(result.get("next_build_recommendations", [])),
        "order_intent": result.get("order_intent"),
        "broker_order_id": result.get("broker_order_id"),
        "portfolio_action": result.get("portfolio_action"),
        "position_size": result.get("position_size"),
        "automatic_action": result.get("automatic_action"),
        "automatic_close_order": result.get("automatic_close_order"),
        "automatic_roll_order": result.get("automatic_roll_order"),
        "automatic_defense_order": result.get("automatic_defense_order"),
        "automatic_strategy_change": result.get("automatic_strategy_change"),
        "automatic_parameter_change": result.get("automatic_parameter_change"),
        "automatic_pause_action": result.get("automatic_pause_action"),
    }
