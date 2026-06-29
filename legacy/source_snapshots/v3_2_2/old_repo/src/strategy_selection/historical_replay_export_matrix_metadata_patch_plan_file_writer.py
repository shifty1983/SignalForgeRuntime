"""File writer for historical replay export matrix metadata patch plan artifacts."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from src.strategy_selection.historical_replay_export_matrix_metadata_patch_plan import (
    build_historical_replay_export_matrix_metadata_patch_plan_summary,
)


def write_historical_replay_export_matrix_metadata_patch_plan_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    """Write patch plan result, summary, targets, sequence, and validation checklist."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / "signalforge_historical_replay_export_matrix_metadata_patch_plan.json"
    summary_path = output_path / "signalforge_historical_replay_export_matrix_metadata_patch_plan_summary.json"
    patch_targets_path = output_path / "signalforge_historical_replay_export_matrix_metadata_patch_targets.json"
    patch_sequence_path = output_path / "signalforge_historical_replay_export_matrix_metadata_patch_sequence.json"
    validation_checklist_path = output_path / "signalforge_historical_replay_export_matrix_metadata_patch_validation_checklist.json"

    result_payload = deepcopy(dict(result))
    summary_payload = build_historical_replay_export_matrix_metadata_patch_plan_summary(result_payload)
    patch_targets_payload = {
        "artifact_type": "signalforge_historical_replay_export_matrix_metadata_patch_targets",
        "schema_version": "signalforge_historical_replay_export_matrix_metadata_patch_targets.v1",
        "patch_plan_id": result_payload.get("patch_plan_id"),
        "patch_targets": result_payload.get("patch_targets", []),
        "patch_target_count": result_payload.get("patch_target_count", 0),
        "required_patch_target_count": result_payload.get("required_patch_target_count", 0),
    }
    patch_sequence_payload = {
        "artifact_type": "signalforge_historical_replay_export_matrix_metadata_patch_sequence",
        "schema_version": "signalforge_historical_replay_export_matrix_metadata_patch_sequence.v1",
        "patch_plan_id": result_payload.get("patch_plan_id"),
        "patch_sequence": result_payload.get("patch_sequence", []),
        "patch_sequence_step_count": result_payload.get("patch_sequence_step_count", 0),
    }
    validation_payload = {
        "artifact_type": "signalforge_historical_replay_export_matrix_metadata_patch_validation_checklist",
        "schema_version": "signalforge_historical_replay_export_matrix_metadata_patch_validation_checklist.v1",
        "patch_plan_id": result_payload.get("patch_plan_id"),
        "validation_checklist": result_payload.get("validation_checklist", []),
        "validation_check_count": result_payload.get("validation_check_count", 0),
    }

    summary_payload["result_path"] = str(result_path)
    summary_payload["summary_path"] = str(summary_path)
    summary_payload["patch_targets_path"] = str(patch_targets_path)
    summary_payload["patch_sequence_path"] = str(patch_sequence_path)
    summary_payload["validation_checklist_path"] = str(validation_checklist_path)
    result_payload["result_path"] = str(result_path)
    result_payload["summary_path"] = str(summary_path)
    result_payload["patch_targets_path"] = str(patch_targets_path)
    result_payload["patch_sequence_path"] = str(patch_sequence_path)
    result_payload["validation_checklist_path"] = str(validation_checklist_path)

    _write_json(result_path, result_payload)
    _write_json(summary_path, summary_payload)
    _write_json(patch_targets_path, patch_targets_payload)
    _write_json(patch_sequence_path, patch_sequence_payload)
    _write_json(validation_checklist_path, validation_payload)

    return {
        "artifact_type": "historical_replay_export_matrix_metadata_patch_plan_write_result",
        "schema_version": "signalforge_historical_replay_export_matrix_metadata_patch_plan_write_result.v1",
        "operation_type": "signalforge_historical_replay_export_matrix_metadata_patch_plan_file_writer",
        "status": summary_payload["status"],
        "patch_plan_state": summary_payload["patch_plan_state"],
        "is_ready": summary_payload["is_ready"],
        "recommended_next_step": summary_payload["recommended_next_step"],
        "envelope_state": summary_payload["envelope_state"],
        "source_patch_required": summary_payload["source_patch_required"],
        "ready_to_patch_historical_replay_exports": summary_payload["ready_to_patch_historical_replay_exports"],
        "ready_to_apply_patches": summary_payload["ready_to_apply_patches"],
        "ready_to_build_exact_matrix_edge_summary": summary_payload["ready_to_build_exact_matrix_edge_summary"],
        "matrix_metadata_envelope_key": summary_payload["matrix_metadata_envelope_key"],
        "matrix_cell_key_fields": summary_payload["matrix_cell_key_fields"],
        "required_field_count": summary_payload["required_field_count"],
        "required_missing_dimensions": summary_payload["required_missing_dimensions"],
        "required_partial_dimensions": summary_payload["required_partial_dimensions"],
        "missing_required_dimension_counts": summary_payload["missing_required_dimension_counts"],
        "mapped_required_dimension_counts": summary_payload["mapped_required_dimension_counts"],
        "total_source_record_count": summary_payload["total_source_record_count"],
        "records_requiring_mapping_count": summary_payload["records_requiring_mapping_count"],
        "exact_matrix_cell_ready_record_count": summary_payload["exact_matrix_cell_ready_record_count"],
        "field_stamping_requirement_count": summary_payload["field_stamping_requirement_count"],
        "producer_patch_requirement_count": summary_payload["producer_patch_requirement_count"],
        "patch_target_count": summary_payload["patch_target_count"],
        "required_patch_target_count": summary_payload["required_patch_target_count"],
        "patch_sequence_step_count": summary_payload["patch_sequence_step_count"],
        "validation_check_count": summary_payload["validation_check_count"],
        "blocked_reasons": summary_payload["blocked_reasons"],
        "warnings": summary_payload["warnings"],
        "explicit_exclusions": summary_payload["explicit_exclusions"],
        "order_intent": summary_payload["order_intent"],
        "automatic_action": summary_payload["automatic_action"],
        "automatic_strategy_change": summary_payload["automatic_strategy_change"],
        "requires_manual_approval": summary_payload["requires_manual_approval"],
        "result_path": str(result_path),
        "summary_path": str(summary_path),
        "patch_targets_path": str(patch_targets_path),
        "patch_sequence_path": str(patch_sequence_path),
        "validation_checklist_path": str(validation_checklist_path),
        "output_dir": str(output_path),
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
