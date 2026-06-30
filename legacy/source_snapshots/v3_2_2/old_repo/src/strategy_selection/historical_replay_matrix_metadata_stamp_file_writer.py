"""File writer for historical replay matrix metadata stamping helper artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from src.signalforge.engines.strategy_selection.historical_replay_matrix_metadata_stamp import (
    ARTIFACT_TYPE,
    EXPLICIT_EXCLUSIONS,
    build_signalforge_historical_replay_matrix_metadata_stamping_helpers,
    summarize_signalforge_historical_replay_matrix_metadata_stamping_helpers,
)

WRITE_RESULT_SCHEMA_VERSION = "signalforge_historical_replay_matrix_metadata_stamp_helpers_write_result.v1"

RESULT_FILENAME = "signalforge_historical_replay_matrix_metadata_stamp_helpers.json"
SUMMARY_FILENAME = "signalforge_historical_replay_matrix_metadata_stamp_helpers_summary.json"
CONTRACT_FILENAME = "signalforge_historical_replay_matrix_metadata_stamp_helper_contract.json"


def write_signalforge_historical_replay_matrix_metadata_stamping_helpers(
    *,
    historical_replay_export_matrix_metadata_patch_plan_source: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    result = build_signalforge_historical_replay_matrix_metadata_stamping_helpers(
        historical_replay_export_matrix_metadata_patch_plan_source=historical_replay_export_matrix_metadata_patch_plan_source,
    )
    summary = summarize_signalforge_historical_replay_matrix_metadata_stamping_helpers(result)

    result_path = out / RESULT_FILENAME
    summary_path = out / SUMMARY_FILENAME
    contract_path = out / CONTRACT_FILENAME

    _write_json(result_path, result)
    _write_json(summary_path, summary)
    _write_json(contract_path, result.get("helper_contract", {}))

    write_result = {
        "artifact_type": "historical_replay_matrix_metadata_stamping_helpers_write_result",
        "schema_version": WRITE_RESULT_SCHEMA_VERSION,
        "operation_type": "signalforge_historical_replay_matrix_metadata_stamping_helpers_file_writer",
        "output_dir": str(out),
        "result_path": str(result_path),
        "summary_path": str(summary_path),
        "helper_contract_path": str(contract_path),
        "status": result.get("status"),
        "helper_state": result.get("helper_state"),
        "is_ready": bool(result.get("is_ready")),
        "helper_id": result.get("helper_id"),
        "patch_plan_state": result.get("patch_plan_state"),
        "matrix_metadata_envelope_key": result.get("matrix_metadata_envelope_key"),
        "matrix_cell_key_fields": result.get("matrix_cell_key_fields", []),
        "required_field_count": result.get("required_field_count", 0),
        "optional_field_count": result.get("optional_field_count", 0),
        "helper_function_count": result.get("helper_function_count", 0),
        "normalization_rule_count": result.get("normalization_rule_count", 0),
        "validation_rule_count": result.get("validation_rule_count", 0),
        "source_patch_required": bool(result.get("source_patch_required")),
        "ready_to_apply_patches": bool(result.get("ready_to_apply_patches")),
        "ready_to_patch_historical_replay_exports": bool(
            result.get("ready_to_patch_historical_replay_exports")
        ),
        "ready_to_build_exact_matrix_edge_summary": bool(
            result.get("ready_to_build_exact_matrix_edge_summary")
        ),
        "recommended_next_step": result.get("recommended_next_step"),
        "records_requiring_mapping_count": result.get("records_requiring_mapping_count", 0),
        "total_source_record_count": result.get("total_source_record_count", 0),
        "required_missing_dimensions": result.get("required_missing_dimensions", []),
        "required_partial_dimensions": result.get("required_partial_dimensions", []),
        "blocked_reasons": result.get("blocked_reasons", []),
        "warnings": result.get("warnings", []),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        "automatic_action": None,
        "automatic_strategy_change": None,
        "order_intent": None,
        "requires_manual_approval": True,
    }
    return write_result


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
