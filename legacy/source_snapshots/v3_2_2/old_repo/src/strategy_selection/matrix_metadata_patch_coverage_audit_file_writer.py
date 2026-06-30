"""File writer for matrix metadata patch coverage audit artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from src.signalforge.engines.strategy_selection.matrix_metadata_patch_coverage_audit import (
    summarize_signalforge_matrix_metadata_patch_coverage_audit,
)

RESULT_FILENAME = "signalforge_matrix_metadata_patch_coverage_audit.json"
SUMMARY_FILENAME = "signalforge_matrix_metadata_patch_coverage_audit_summary.json"
PATCH_TARGET_AUDITS_FILENAME = "signalforge_matrix_metadata_patch_target_audits.json"
STAGE_SUMMARY_FILENAME = "signalforge_matrix_metadata_patch_stage_summary.json"


def write_signalforge_matrix_metadata_patch_coverage_audit(
    *,
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    """Write the full audit, compact summary, target audits, and stage summary."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / RESULT_FILENAME
    summary_path = output_path / SUMMARY_FILENAME
    target_audits_path = output_path / PATCH_TARGET_AUDITS_FILENAME
    stage_summary_path = output_path / STAGE_SUMMARY_FILENAME

    summary = summarize_signalforge_matrix_metadata_patch_coverage_audit(result)

    _write_json(result_path, result)
    _write_json(summary_path, summary)
    _write_json(target_audits_path, list(result.get("patch_target_audits") or []))
    _write_json(stage_summary_path, list(result.get("patch_target_stage_summary") or []))

    return {
        "artifact_type": "matrix_metadata_patch_coverage_audit_write_result",
        "schema_version": "signalforge_matrix_metadata_patch_coverage_audit_write_result.v1",
        "operation_type": "signalforge_matrix_metadata_patch_coverage_audit_file_writer",
        "status": result.get("status"),
        "is_ready": bool(result.get("is_ready")),
        "coverage_audit_state": result.get("coverage_audit_state"),
        "patch_plan_state": result.get("patch_plan_state"),
        "patch_target_count": int(result.get("patch_target_count") or 0),
        "required_patch_target_count": int(result.get("required_patch_target_count") or 0),
        "ready_patch_target_count": int(result.get("ready_patch_target_count") or 0),
        "needs_review_patch_target_count": int(result.get("needs_review_patch_target_count") or 0),
        "missing_source_patch_target_count": int(result.get("missing_source_patch_target_count") or 0),
        "required_ready_patch_target_count": int(result.get("required_ready_patch_target_count") or 0),
        "required_needs_review_patch_target_count": int(result.get("required_needs_review_patch_target_count") or 0),
        "source_file_found_count": int(result.get("source_file_found_count") or 0),
        "matrix_metadata_reference_count": int(result.get("matrix_metadata_reference_count") or 0),
        "stamping_helper_reference_count": int(result.get("stamping_helper_reference_count") or 0),
        "ready_to_rerun_historical_replay_with_matrix_metadata": bool(
            result.get("ready_to_rerun_historical_replay_with_matrix_metadata")
        ),
        "ready_to_build_exact_matrix_edge_summary": bool(
            result.get("ready_to_build_exact_matrix_edge_summary")
        ),
        "ready_to_use_for_strategy_selection": bool(result.get("ready_to_use_for_strategy_selection")),
        "recommended_next_step": result.get("recommended_next_step"),
        "output_dir": str(output_path),
        "result_path": str(result_path),
        "summary_path": str(summary_path),
        "patch_target_audits_path": str(target_audits_path),
        "stage_summary_path": str(stage_summary_path),
        "warnings": list(result.get("warnings") or []),
        "blocked_reasons": list(result.get("blocked_reasons") or []),
        "explicit_exclusions": list(result.get("explicit_exclusions") or []),
        "automatic_action": None,
        "automatic_strategy_change": None,
        "order_intent": None,
        "requires_manual_approval": True,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
