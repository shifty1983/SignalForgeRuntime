from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


RESULT_FILENAME = "signalforge_quantconnect_historical_replay_scaleout_plan.json"
SUMMARY_FILENAME = "signalforge_quantconnect_historical_replay_scaleout_plan_summary.json"


def write_signalforge_quantconnect_historical_replay_scaleout_plan(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / RESULT_FILENAME
    summary_path = output_path / SUMMARY_FILENAME

    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    batch_dir = output_path / "batch_handoffs"
    batch_dir.mkdir(parents=True, exist_ok=True)

    batch_files: dict[str, str] = {}

    for batch in result.get("batches", []):
        if not isinstance(batch, Mapping):
            continue

        batch_id = str(batch.get("batch_id") or "unknown_batch")
        batch_path = batch_dir / f"{batch_id}_quantconnect_historical_replay_handoff.json"

        batch_payload = {
            "artifact_type": "signalforge_quantconnect_historical_replay_handoff",
            "schema_version": "signalforge_quantconnect_historical_replay_handoff.v2",
            "status": "ready",
            "is_ready": True,
            "matrix_metadata_envelope_key": batch.get("matrix_metadata_envelope_key"),
            "matrix_metadata_candidate_summary": dict(
                batch.get("matrix_metadata_candidate_summary", {})
            ),
            "matrix_metadata_source_patch_state": batch.get(
                "matrix_metadata_source_patch_state"
            ),
            "quantconnect_replay_request_manifest": batch.get(
                "quantconnect_replay_request_manifest", {}
            ),
            "quantconnect_result_contract": {
                "expected_result_files": list(batch.get("expected_result_files", [])),
                "expected_result_file_count": batch.get("expected_result_file_count", 0),
                "matrix_metadata_required_on_result_records": True,
                "matrix_metadata_envelope_key": batch.get("matrix_metadata_envelope_key"),
            },
            "scaleout_batch": {
                "batch_id": batch.get("batch_id"),
                "batch_number": batch.get("batch_number"),
                "estimated_object_store_bytes": batch.get("estimated_object_store_bytes"),
                "object_store_budget_bytes": batch.get("object_store_budget_bytes"),
                "object_store_budget_state": batch.get("object_store_budget_state"),
                "matrix_metadata_source_patch_state": batch.get(
                    "matrix_metadata_source_patch_state"
                ),
            },
            "order_intent": None,
            "broker_order_id": None,
            "portfolio_action": None,
            "position_size": None,
        }

        batch_path.write_text(
            json.dumps(batch_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        batch_files[batch_id] = str(batch_path)

    summary = {
        "operation_type": "signalforge_quantconnect_historical_replay_scaleout_plan_cli",
        "adapter_type": result.get("adapter_type"),
        "artifact_type": result.get("artifact_type"),
        "schema_version": "signalforge_quantconnect_historical_replay_scaleout_plan_cli_summary.v2",
        "contract": result.get("contract"),
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "requires_manual_approval": result.get("requires_manual_approval"),
        "review_scope": result.get("review_scope"),
        "blocked_reasons": list(result.get("blocked_reasons", [])),
        "warnings": list(result.get("warnings", [])),
        "covered_capabilities": list(result.get("covered_capabilities", [])),
        "depends_on_capabilities": list(result.get("depends_on_capabilities", [])),
        "explicit_exclusions": list(result.get("explicit_exclusions", [])),
        "source_artifacts": dict(result.get("source_artifacts", {})),
        "output_dir": str(output_path),
        "files": {
            "scaleout_plan_result": str(result_path),
            "summary": str(summary_path),
            "batch_handoffs": batch_files,
        },
        "source_request_id": result.get("source_request_id"),
        "source_start": result.get("source_start"),
        "source_end": result.get("source_end"),
        "source_symbol_count": result.get("source_symbol_count"),
        "source_candidate_count": result.get("source_candidate_count"),
        "batch_count": result.get("batch_count"),
        "exceeded_budget_batch_count": result.get("exceeded_budget_batch_count"),
        "exceeded_budget_batch_ids": list(result.get("exceeded_budget_batch_ids", [])),
        "object_store_budget_bytes_per_batch": result.get("object_store_budget_bytes_per_batch"),
        "matrix_metadata_envelope_key": result.get("matrix_metadata_envelope_key"),
        "matrix_cell_key_fields": list(result.get("matrix_cell_key_fields", [])),
        "source_matrix_metadata_candidate_summary": dict(
            result.get("source_matrix_metadata_candidate_summary", {})
        ),
        "matrix_metadata_batch_summary": dict(result.get("matrix_metadata_batch_summary", {})),
        "ready_to_build_exact_matrix_edge_summary": bool(
            result.get("ready_to_build_exact_matrix_edge_summary")
        ),
        "ready_to_continue_historical_replay_scaleout": bool(
            result.get("ready_to_continue_historical_replay_scaleout")
        ),
        "recommended_next_step": result.get("recommended_next_step"),
        "scaleout_plan_summary": dict(result.get("scaleout_plan_summary", {})),
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

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary
