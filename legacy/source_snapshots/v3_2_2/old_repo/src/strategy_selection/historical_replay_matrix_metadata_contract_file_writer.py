"""File writer for the historical replay matrix metadata contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from src.signalforge.engines.strategy_selection.historical_replay_matrix_metadata_contract import (
    build_historical_replay_matrix_metadata_contract_summary,
)

CONTRACT_FILENAME = "signalforge_historical_replay_matrix_metadata_contract.json"
SUMMARY_FILENAME = "signalforge_historical_replay_matrix_metadata_contract_summary.json"


def write_historical_replay_matrix_metadata_contract_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    """Write contract and summary artifacts to ``output_dir``."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / CONTRACT_FILENAME
    summary_path = output_path / SUMMARY_FILENAME

    result_payload = dict(result)
    summary_payload = build_historical_replay_matrix_metadata_contract_summary(result_payload)

    result_payload["summary_path"] = str(summary_path)
    result_payload["result_path"] = str(result_path)

    _write_json(result_path, result_payload)
    _write_json(summary_path, summary_payload)

    return {
        "artifact_type": "historical_replay_matrix_metadata_contract_write_result",
        "schema_version": "signalforge_historical_replay_matrix_metadata_contract_write_result.v1",
        "operation_type": "signalforge_historical_replay_matrix_metadata_contract_file_writer",
        "status": summary_payload["status"],
        "contract_state": summary_payload["contract_state"],
        "is_ready": summary_payload["is_ready"],
        "matrix_mapping_state": summary_payload["matrix_mapping_state"],
        "recommended_next_adapter": summary_payload["recommended_next_adapter"],
        "ready_to_build_metadata_backfill_adapter": summary_payload[
            "ready_to_build_metadata_backfill_adapter"
        ],
        "ready_to_build_exact_matrix_edge_summary": summary_payload[
            "ready_to_build_exact_matrix_edge_summary"
        ],
        "records_requiring_mapping_count": summary_payload["records_requiring_mapping_count"],
        "expected_matrix_cell_count": summary_payload["expected_matrix_cell_count"],
        "required_matrix_dimension_count": summary_payload["required_matrix_dimension_count"],
        "required_field_count": summary_payload["required_field_count"],
        "optional_field_count": summary_payload["optional_field_count"],
        "normalization_rule_count": summary_payload["normalization_rule_count"],
        "validation_rule_count": summary_payload["validation_rule_count"],
        "matrix_cell_key_fields": summary_payload["matrix_cell_key_fields"],
        "blocked_reasons": summary_payload["blocked_reasons"],
        "warnings": summary_payload["warnings"],
        "explicit_exclusions": summary_payload["explicit_exclusions"],
        "order_intent": summary_payload["order_intent"],
        "automatic_action": summary_payload["automatic_action"],
        "automatic_strategy_change": summary_payload["automatic_strategy_change"],
        "requires_manual_approval": summary_payload["requires_manual_approval"],
        "result_path": str(result_path),
        "summary_path": str(summary_path),
        "output_dir": str(output_path),
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
