"""File writer for the historical replay matrix metadata backfill adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from src.signalforge.engines.strategy_selection.historical_replay_matrix_metadata_backfill_adapter import (
    build_historical_replay_matrix_metadata_backfill_adapter_summary,
)

ADAPTER_FILENAME = "signalforge_historical_replay_matrix_metadata_backfill_adapter.json"
SUMMARY_FILENAME = "signalforge_historical_replay_matrix_metadata_backfill_adapter_summary.json"
RECORDS_FILENAME = "signalforge_historical_replay_matrix_metadata_backfilled_records.json"


def write_historical_replay_matrix_metadata_backfill_adapter_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    """Write backfill adapter, summary, and record artifacts to ``output_dir``."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / ADAPTER_FILENAME
    summary_path = output_path / SUMMARY_FILENAME
    records_path = output_path / RECORDS_FILENAME

    result_payload = dict(result)
    records_payload = list(result_payload.get("backfilled_records") or [])
    summary_payload = build_historical_replay_matrix_metadata_backfill_adapter_summary(result_payload)

    result_payload["result_path"] = str(result_path)
    result_payload["summary_path"] = str(summary_path)
    result_payload["records_path"] = str(records_path)

    _write_json(result_path, result_payload)
    _write_json(summary_path, summary_payload)
    _write_json(records_path, {"records": records_payload})

    return {
        "artifact_type": "historical_replay_matrix_metadata_backfill_adapter_write_result",
        "schema_version": "signalforge_historical_replay_matrix_metadata_backfill_adapter_write_result.v1",
        "operation_type": "signalforge_historical_replay_matrix_metadata_backfill_adapter_file_writer",
        "status": summary_payload["status"],
        "adapter_state": summary_payload["adapter_state"],
        "is_ready": summary_payload["is_ready"],
        "matrix_mapping_state": summary_payload["matrix_mapping_state"],
        "recommended_next_step": summary_payload["recommended_next_step"],
        "ready_to_build_exact_matrix_edge_summary": summary_payload[
            "ready_to_build_exact_matrix_edge_summary"
        ],
        "contract_state": summary_payload["contract_state"],
        "contract_id": summary_payload["contract_id"],
        "total_source_record_count": summary_payload["total_source_record_count"],
        "backfilled_record_count": summary_payload["backfilled_record_count"],
        "exact_matrix_cell_ready_record_count": summary_payload[
            "exact_matrix_cell_ready_record_count"
        ],
        "needs_review_record_count": summary_payload["needs_review_record_count"],
        "blocked_record_count": summary_payload["blocked_record_count"],
        "records_requiring_mapping_count": summary_payload["records_requiring_mapping_count"],
        "expected_matrix_cell_count": summary_payload["expected_matrix_cell_count"],
        "required_field_count": summary_payload["required_field_count"],
        "optional_field_count": summary_payload["optional_field_count"],
        "matrix_cell_key_fields": summary_payload["matrix_cell_key_fields"],
        "required_missing_dimensions": summary_payload["required_missing_dimensions"],
        "required_partial_dimensions": summary_payload["required_partial_dimensions"],
        "missing_required_dimension_counts": summary_payload["missing_required_dimension_counts"],
        "mapped_required_dimension_counts": summary_payload["mapped_required_dimension_counts"],
        "partial_required_dimension_counts": summary_payload["partial_required_dimension_counts"],
        "blocked_reasons": summary_payload["blocked_reasons"],
        "warnings": summary_payload["warnings"],
        "explicit_exclusions": summary_payload["explicit_exclusions"],
        "order_intent": summary_payload["order_intent"],
        "automatic_action": summary_payload["automatic_action"],
        "automatic_strategy_change": summary_payload["automatic_strategy_change"],
        "requires_manual_approval": summary_payload["requires_manual_approval"],
        "result_path": str(result_path),
        "summary_path": str(summary_path),
        "records_path": str(records_path),
        "output_dir": str(output_path),
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
