"""File writer for historical replay source metadata backfill requirements."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from src.signalforge.engines.strategy_selection.historical_replay_source_metadata_backfill import (
    build_historical_replay_source_metadata_backfill_summary,
)

RESULT_FILENAME = "signalforge_historical_replay_source_metadata_backfill.json"
SUMMARY_FILENAME = "signalforge_historical_replay_source_metadata_backfill_summary.json"
CONTRACT_FILENAME = "signalforge_historical_replay_source_metadata_backfill_contract.json"
TASKS_FILENAME = "signalforge_historical_replay_source_metadata_backfill_tasks.json"


def write_historical_replay_source_metadata_backfill_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    """Write source metadata backfill artifacts to ``output_dir``."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / RESULT_FILENAME
    summary_path = output_path / SUMMARY_FILENAME
    contract_path = output_path / CONTRACT_FILENAME
    tasks_path = output_path / TASKS_FILENAME

    result_payload = dict(result)
    summary_payload = build_historical_replay_source_metadata_backfill_summary(result_payload)
    contract_payload = dict(result_payload.get("source_backfill_contract") or {})
    tasks_payload = {
        "required_source_tasks": list(result_payload.get("required_source_tasks") or []),
        "optional_source_tasks": list(result_payload.get("optional_source_tasks") or []),
        "source_patch_sequence": list(result_payload.get("source_patch_sequence") or []),
        "upstream_artifact_requirements": list(result_payload.get("upstream_artifact_requirements") or []),
    }

    result_payload["result_path"] = str(result_path)
    result_payload["summary_path"] = str(summary_path)
    result_payload["contract_path"] = str(contract_path)
    result_payload["tasks_path"] = str(tasks_path)

    _write_json(result_path, result_payload)
    _write_json(summary_path, summary_payload)
    _write_json(contract_path, contract_payload)
    _write_json(tasks_path, tasks_payload)

    return {
        "artifact_type": "historical_replay_source_metadata_backfill_write_result",
        "schema_version": "signalforge_historical_replay_source_metadata_backfill_write_result.v1",
        "operation_type": "signalforge_historical_replay_source_metadata_backfill_file_writer",
        "status": summary_payload["status"],
        "source_metadata_backfill_state": summary_payload["source_metadata_backfill_state"],
        "is_ready": summary_payload["is_ready"],
        "matrix_mapping_state": summary_payload["matrix_mapping_state"],
        "recommended_next_step": summary_payload["recommended_next_step"],
        "ready_to_patch_historical_replay_exports": summary_payload[
            "ready_to_patch_historical_replay_exports"
        ],
        "ready_to_build_exact_matrix_edge_summary": summary_payload[
            "ready_to_build_exact_matrix_edge_summary"
        ],
        "contract_state": summary_payload["contract_state"],
        "contract_id": summary_payload["contract_id"],
        "adapter_state": summary_payload["adapter_state"],
        "total_source_record_count": summary_payload["total_source_record_count"],
        "records_requiring_mapping_count": summary_payload["records_requiring_mapping_count"],
        "exact_matrix_cell_ready_record_count": summary_payload[
            "exact_matrix_cell_ready_record_count"
        ],
        "expected_matrix_cell_count": summary_payload["expected_matrix_cell_count"],
        "required_field_count": summary_payload["required_field_count"],
        "optional_field_count": summary_payload["optional_field_count"],
        "matrix_cell_key_fields": summary_payload["matrix_cell_key_fields"],
        "required_missing_dimensions": summary_payload["required_missing_dimensions"],
        "required_partial_dimensions": summary_payload["required_partial_dimensions"],
        "missing_required_dimension_counts": summary_payload["missing_required_dimension_counts"],
        "mapped_required_dimension_counts": summary_payload["mapped_required_dimension_counts"],
        "partial_required_dimension_counts": summary_payload["partial_required_dimension_counts"],
        "required_source_backfill_task_count": summary_payload[
            "required_source_backfill_task_count"
        ],
        "required_source_normalization_task_count": summary_payload[
            "required_source_normalization_task_count"
        ],
        "optional_source_enrichment_task_count": summary_payload[
            "optional_source_enrichment_task_count"
        ],
        "source_backfill_task_count": summary_payload["source_backfill_task_count"],
        "blocked_reasons": summary_payload["blocked_reasons"],
        "warnings": summary_payload["warnings"],
        "explicit_exclusions": summary_payload["explicit_exclusions"],
        "order_intent": summary_payload["order_intent"],
        "automatic_action": summary_payload["automatic_action"],
        "automatic_strategy_change": summary_payload["automatic_strategy_change"],
        "requires_manual_approval": summary_payload["requires_manual_approval"],
        "result_path": str(result_path),
        "summary_path": str(summary_path),
        "contract_path": str(contract_path),
        "tasks_path": str(tasks_path),
        "output_dir": str(output_path),
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
