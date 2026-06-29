from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


CANDIDATE_FINAL_REVIEW_EXPORT_RESULT_FILENAME = "signalforge_candidate_final_review_export.json"
CANDIDATE_FINAL_REVIEW_EXPORT_SUMMARY_FILENAME = "signalforge_candidate_final_review_export_summary.json"
CANDIDATE_FINAL_REVIEW_EXPORT_CLI_SUMMARY_SCHEMA_VERSION = "signalforge_candidate_final_review_export_cli_summary.v1"


def write_candidate_final_review_export_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / CANDIDATE_FINAL_REVIEW_EXPORT_RESULT_FILENAME
    summary_path = output_path / CANDIDATE_FINAL_REVIEW_EXPORT_SUMMARY_FILENAME

    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    summary = build_candidate_final_review_export_summary(
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


def build_candidate_final_review_export_summary(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    summary_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    final_summary = result.get("candidate_final_review_export_summary") or {}

    return {
        "schema_version": CANDIDATE_FINAL_REVIEW_EXPORT_CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_candidate_final_review_export_cli",
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
        "candidate_final_review_export_summary": final_summary,
        "symbol_count": final_summary.get("symbol_count", 0),
        "ready_final_review_symbol_count": final_summary.get("ready_final_review_symbol_count", 0),
        "constrained_final_review_symbol_count": final_summary.get("constrained_final_review_symbol_count", 0),
        "candidate_final_review_symbol_count": final_summary.get("candidate_final_review_symbol_count", 0),
        "selected_for_final_review_symbol_count": final_summary.get("selected_for_final_review_symbol_count", 0),
        "final_review_queue_count": final_summary.get("final_review_queue_count", 0),
        "ranked_final_review_count": final_summary.get("ranked_final_review_count", 0),
        "data_review_symbol_count": final_summary.get("data_review_symbol_count", 0),
        "blocked_symbol_count": final_summary.get("blocked_symbol_count", 0),
        "not_recommended_symbol_count": final_summary.get("not_recommended_symbol_count", 0),
        "needs_review_symbol_count": final_summary.get("needs_review_symbol_count", 0),
        "manual_review_symbol_count": final_summary.get("manual_review_symbol_count", 0),
        "output_dir": str(output_dir),
        "files": {
            "candidate_final_review_export_result": str(result_path),
            "summary": str(summary_path),
        },
        "file_summary": {
            "file_count": 2,
            "written_file_count": 2,
            "missing_files": [],
            "empty_files": [],
            "file_sizes": {
                "candidate_final_review_export_result": (
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
