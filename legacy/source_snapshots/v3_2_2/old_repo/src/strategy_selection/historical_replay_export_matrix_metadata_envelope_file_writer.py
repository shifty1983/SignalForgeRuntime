"""File writer for historical replay export matrix metadata envelope artifacts."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from src.signalforge.engines.strategy_selection.historical_replay_export_matrix_metadata_envelope import (
    build_historical_replay_export_matrix_metadata_envelope_summary,
)


def write_historical_replay_export_matrix_metadata_envelope_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    """Write envelope result, summary, schema, and patch requirements."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / "signalforge_historical_replay_export_matrix_metadata_envelope.json"
    summary_path = output_path / "signalforge_historical_replay_export_matrix_metadata_envelope_summary.json"
    schema_path = output_path / "signalforge_historical_replay_export_matrix_metadata_envelope_schema.json"
    patch_requirements_path = output_path / "signalforge_historical_replay_export_matrix_metadata_patch_requirements.json"

    result_payload = deepcopy(dict(result))
    summary_payload = build_historical_replay_export_matrix_metadata_envelope_summary(result_payload)
    schema_payload = {
        "artifact_type": "signalforge_historical_replay_export_matrix_metadata_envelope_schema",
        "schema_version": "signalforge_historical_replay_export_matrix_metadata_envelope_schema.v1",
        "envelope_id": result_payload.get("envelope_id"),
        "matrix_metadata_envelope_key": result_payload.get("matrix_metadata_envelope_key"),
        "matrix_cell_key_fields": result_payload.get("matrix_cell_key_fields", []),
        "envelope_schema": result_payload.get("envelope_schema", {}),
        "blank_envelope_template": result_payload.get("blank_envelope_template", {}),
        "validation_rules": result_payload.get("validation_rules", []),
    }
    patch_payload = {
        "artifact_type": "signalforge_historical_replay_export_matrix_metadata_patch_requirements",
        "schema_version": "signalforge_historical_replay_export_matrix_metadata_patch_requirements.v1",
        "envelope_id": result_payload.get("envelope_id"),
        "ready_to_patch_historical_replay_exports": result_payload.get(
            "ready_to_patch_historical_replay_exports", False
        ),
        "source_patch_required": result_payload.get("source_patch_required", False),
        "producer_patch_requirements": result_payload.get("producer_patch_requirements", []),
        "field_stamping_requirements": result_payload.get("field_stamping_requirements", []),
    }

    summary_payload["result_path"] = str(result_path)
    summary_payload["summary_path"] = str(summary_path)
    summary_payload["schema_path"] = str(schema_path)
    summary_payload["patch_requirements_path"] = str(patch_requirements_path)
    result_payload["result_path"] = str(result_path)
    result_payload["summary_path"] = str(summary_path)
    result_payload["schema_path"] = str(schema_path)
    result_payload["patch_requirements_path"] = str(patch_requirements_path)

    _write_json(result_path, result_payload)
    _write_json(summary_path, summary_payload)
    _write_json(schema_path, schema_payload)
    _write_json(patch_requirements_path, patch_payload)

    return {
        "artifact_type": "historical_replay_export_matrix_metadata_envelope_write_result",
        "schema_version": "signalforge_historical_replay_export_matrix_metadata_envelope_write_result.v1",
        "operation_type": "signalforge_historical_replay_export_matrix_metadata_envelope_file_writer",
        "status": summary_payload["status"],
        "envelope_state": summary_payload["envelope_state"],
        "is_ready": summary_payload["is_ready"],
        "recommended_next_step": summary_payload["recommended_next_step"],
        "matrix_metadata_envelope_key": summary_payload["matrix_metadata_envelope_key"],
        "matrix_cell_key_fields": summary_payload["matrix_cell_key_fields"],
        "required_field_count": summary_payload["required_field_count"],
        "optional_field_count": summary_payload["optional_field_count"],
        "producer_patch_requirement_count": summary_payload["producer_patch_requirement_count"],
        "validation_rule_count": summary_payload["validation_rule_count"],
        "source_patch_required": summary_payload["source_patch_required"],
        "ready_to_patch_historical_replay_exports": summary_payload[
            "ready_to_patch_historical_replay_exports"
        ],
        "ready_to_build_exact_matrix_edge_summary": summary_payload[
            "ready_to_build_exact_matrix_edge_summary"
        ],
        "contract_state": summary_payload["contract_state"],
        "source_metadata_backfill_state": summary_payload["source_metadata_backfill_state"],
        "total_source_record_count": summary_payload["total_source_record_count"],
        "records_requiring_mapping_count": summary_payload["records_requiring_mapping_count"],
        "exact_matrix_cell_ready_record_count": summary_payload["exact_matrix_cell_ready_record_count"],
        "source_backfill_task_count": summary_payload["source_backfill_task_count"],
        "required_source_backfill_task_count": summary_payload[
            "required_source_backfill_task_count"
        ],
        "required_missing_dimensions": summary_payload["required_missing_dimensions"],
        "required_partial_dimensions": summary_payload["required_partial_dimensions"],
        "missing_required_dimension_counts": summary_payload["missing_required_dimension_counts"],
        "mapped_required_dimension_counts": summary_payload["mapped_required_dimension_counts"],
        "blocked_reasons": summary_payload["blocked_reasons"],
        "warnings": summary_payload["warnings"],
        "explicit_exclusions": summary_payload["explicit_exclusions"],
        "order_intent": summary_payload["order_intent"],
        "automatic_action": summary_payload["automatic_action"],
        "automatic_strategy_change": summary_payload["automatic_strategy_change"],
        "requires_manual_approval": summary_payload["requires_manual_approval"],
        "result_path": str(result_path),
        "summary_path": str(summary_path),
        "schema_path": str(schema_path),
        "patch_requirements_path": str(patch_requirements_path),
        "output_dir": str(output_path),
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
