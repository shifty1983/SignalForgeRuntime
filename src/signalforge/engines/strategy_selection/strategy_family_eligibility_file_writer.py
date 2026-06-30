from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


STRATEGY_FAMILY_ELIGIBILITY_RESULT_FILENAME = "signalforge_strategy_family_eligibility.json"
STRATEGY_FAMILY_ELIGIBILITY_SUMMARY_FILENAME = "signalforge_strategy_family_eligibility_summary.json"
STRATEGY_FAMILY_ELIGIBILITY_CLI_SUMMARY_SCHEMA_VERSION = (
    "signalforge_strategy_family_eligibility_cli_summary.v2"
)


def write_strategy_family_eligibility_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / STRATEGY_FAMILY_ELIGIBILITY_RESULT_FILENAME
    summary_path = output_path / STRATEGY_FAMILY_ELIGIBILITY_SUMMARY_FILENAME

    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    summary = build_strategy_family_eligibility_summary(
        result=result,
        result_path=result_path,
        summary_path=summary_path,
        output_dir=output_path,
    )

    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    return summary


def build_strategy_family_eligibility_summary(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    summary_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    eligibility_summary = result.get("strategy_family_eligibility_summary") or {}

    return {
        "schema_version": STRATEGY_FAMILY_ELIGIBILITY_CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_strategy_family_eligibility_cli",
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
        "matrix_metadata_envelope_key": result.get("matrix_metadata_envelope_key"),
        "matrix_cell_key_fields": result.get("matrix_cell_key_fields", []),
        "matrix_dimension_provider": result.get("matrix_dimension_provider"),
        "matrix_dimension_fields": result.get("matrix_dimension_fields", []),
        "matrix_metadata_strategy_family_summary": result.get(
            "matrix_metadata_strategy_family_summary",
            eligibility_summary.get("matrix_metadata_strategy_family_summary", {}),
        ),
        "exact_matrix_cell_ready_record_count": result.get(
            "exact_matrix_cell_ready_record_count",
            eligibility_summary.get("exact_matrix_cell_ready_record_count", 0),
        ),
        "matrix_metadata_needs_review_record_count": result.get(
            "matrix_metadata_needs_review_record_count",
            eligibility_summary.get("matrix_metadata_needs_review_record_count", 0),
        ),
        "ready_to_patch_historical_replay_exports": result.get(
            "ready_to_patch_historical_replay_exports"
        ),
        "ready_to_build_exact_matrix_edge_summary": result.get(
            "ready_to_build_exact_matrix_edge_summary",
            eligibility_summary.get("ready_to_build_exact_matrix_edge_summary", False),
        ),
        "recommended_next_step": result.get("recommended_next_step"),
        "strategy_family_eligibility_summary": eligibility_summary,
        "symbol_count": eligibility_summary.get("symbol_count", 0),
        "ready_symbol_count": eligibility_summary.get("ready_symbol_count", 0),
        "constrained_symbol_count": eligibility_summary.get("constrained_symbol_count", 0),
        "ev_eligible_symbol_count": eligibility_summary.get("ev_eligible_symbol_count", 0),
        "risk_adjusted_ev_symbol_count": eligibility_summary.get("risk_adjusted_ev_symbol_count", 0),
        "data_review_symbol_count": eligibility_summary.get("data_review_symbol_count", 0),
        "blocked_symbol_count": eligibility_summary.get("blocked_symbol_count", 0),
        "needs_review_symbol_count": eligibility_summary.get("needs_review_symbol_count", 0),
        "manual_review_symbol_count": eligibility_summary.get("manual_review_symbol_count", 0),
        "output_dir": str(output_dir),
        "files": {
            "strategy_family_eligibility_result": str(result_path),
            "summary": str(summary_path),
        },
        "file_summary": {
            "file_count": 2,
            "written_file_count": 2,
            "missing_files": [],
            "empty_files": [],
            "file_sizes": {
                "strategy_family_eligibility_result": (
                    result_path.stat().st_size if result_path.exists() else 0
                ),
                "summary": summary_path.stat().st_size if summary_path.exists() else 0,
            },
        },
        "order_intent": result.get("order_intent"),
        "broker_order_id": result.get("broker_order_id"),
        "automatic_action": result.get("automatic_action"),
        "automatic_strategy_change": result.get("automatic_strategy_change"),
        "automatic_parameter_change": result.get("automatic_parameter_change"),
        "automatic_pause_action": result.get("automatic_pause_action"),
        "explicit_exclusions": result.get("explicit_exclusions"),
    }


