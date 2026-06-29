from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


QUANTCONNECT_HISTORICAL_REPLAY_HANDOFF_RESULT_FILENAME = "signalforge_quantconnect_historical_replay_handoff.json"
QUANTCONNECT_HISTORICAL_REPLAY_HANDOFF_SUMMARY_FILENAME = "signalforge_quantconnect_historical_replay_handoff_summary.json"
QUANTCONNECT_REPLAY_REQUEST_MANIFEST_FILENAME = "quantconnect_replay_request_manifest.json"
QUANTCONNECT_HISTORICAL_REPLAY_HANDOFF_CLI_SUMMARY_SCHEMA_VERSION = "signalforge_quantconnect_historical_replay_handoff_cli_summary.v1"


def write_quantconnect_historical_replay_handoff_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / QUANTCONNECT_HISTORICAL_REPLAY_HANDOFF_RESULT_FILENAME
    summary_path = output_path / QUANTCONNECT_HISTORICAL_REPLAY_HANDOFF_SUMMARY_FILENAME
    manifest_path = output_path / QUANTCONNECT_REPLAY_REQUEST_MANIFEST_FILENAME

    result_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    manifest_path.write_text(
        json.dumps(result.get("quantconnect_replay_request_manifest") or {}, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    summary = build_quantconnect_historical_replay_handoff_summary(
        result=result,
        result_path=result_path,
        summary_path=summary_path,
        manifest_path=manifest_path,
        output_dir=output_path,
    )
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return summary


def build_quantconnect_historical_replay_handoff_summary(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    summary_path: Path,
    manifest_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    handoff_summary = result.get("quantconnect_historical_replay_handoff_summary") or {}
    replay_request = result.get("quantconnect_replay_request_manifest") or {}
    result_contract = result.get("quantconnect_result_contract") or {}
    return {
        "schema_version": QUANTCONNECT_HISTORICAL_REPLAY_HANDOFF_CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_quantconnect_historical_replay_handoff_cli",
        "artifact_type": result.get("artifact_type"),
        "contract": result.get("contract"),
        "adapter_type": result.get("adapter_type"),
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "requires_manual_approval": result.get("requires_manual_approval"),
        "review_scope": result.get("review_scope"),
        "replay_mode": result.get("replay_mode"),
        "source_artifacts": result.get("source_artifacts"),
        "covered_capabilities": result.get("covered_capabilities"),
        "depends_on_capabilities": result.get("depends_on_capabilities"),
        "next_build_recommendations": result.get("next_build_recommendations", []),
        "blocked_reasons": result.get("blocked_reasons", []),
        "quantconnect_historical_replay_handoff_summary": handoff_summary,
        "request_id": replay_request.get("request_id"),
        "lean_project_name": replay_request.get("lean_project_name"),
        "symbol_count": handoff_summary.get("symbol_count", 0),
        "replay_candidate_count": handoff_summary.get("replay_candidate_count", 0),
        "replay_start": handoff_summary.get("replay_start"),
        "replay_end": handoff_summary.get("replay_end"),
        "benchmark_symbol": handoff_summary.get("benchmark_symbol"),
        "outcome_horizon_count": handoff_summary.get("outcome_horizon_count", 0),
        "expected_result_file_count": result_contract.get("expected_result_file_count", 0),
        "expected_object_store_key_count": handoff_summary.get("expected_object_store_key_count", 0),
        "matrix_metadata_envelope_key": result.get("matrix_metadata_envelope_key") or replay_request.get("matrix_metadata_envelope_key"),
        "matrix_cell_key_fields": result.get("matrix_cell_key_fields") or replay_request.get("matrix_cell_key_fields"),
        "matrix_metadata_candidate_summary": result.get("matrix_metadata_candidate_summary") or replay_request.get("matrix_metadata_candidate_summary"),
        "ready_to_build_exact_matrix_edge_summary": bool(result.get("ready_to_build_exact_matrix_edge_summary")),
        "ready_to_continue_historical_replay_handoff": bool(result.get("ready_to_continue_historical_replay_handoff")),
        "recommended_next_step": result.get("recommended_next_step"),
        "option_slice_policy": handoff_summary.get("option_slice_policy"),
        "execution_policy": handoff_summary.get("execution_policy"),
        "output_dir": str(output_dir),
        "files": {
            "quantconnect_historical_replay_handoff_result": str(result_path),
            "quantconnect_replay_request_manifest": str(manifest_path),
            "summary": str(summary_path),
        },
        "file_summary": {
            "file_count": 3,
            "written_file_count": 3,
            "missing_files": [],
            "empty_files": [],
            "file_sizes": {
                "quantconnect_historical_replay_handoff_result": result_path.stat().st_size if result_path.exists() else 0,
                "quantconnect_replay_request_manifest": manifest_path.stat().st_size if manifest_path.exists() else 0,
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
