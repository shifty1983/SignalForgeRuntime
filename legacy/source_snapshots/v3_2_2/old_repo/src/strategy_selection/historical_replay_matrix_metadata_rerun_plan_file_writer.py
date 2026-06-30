"""File writer for the historical replay matrix metadata rerun plan."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.signalforge.engines.strategy_selection.historical_replay_matrix_metadata_rerun_plan import (
    build_signalforge_historical_replay_matrix_metadata_rerun_plan,
    summarize_signalforge_historical_replay_matrix_metadata_rerun_plan,
)

RESULT_FILENAME = "signalforge_historical_replay_matrix_metadata_rerun_plan.json"
SUMMARY_FILENAME = "signalforge_historical_replay_matrix_metadata_rerun_plan_summary.json"
STEPS_FILENAME = "signalforge_historical_replay_matrix_metadata_rerun_steps.json"
CHECKLIST_FILENAME = "signalforge_historical_replay_matrix_metadata_rerun_validation_checklist.json"


def write_signalforge_historical_replay_matrix_metadata_rerun_plan(
    *,
    matrix_metadata_patch_coverage_audit_source: Mapping[str, Any],
    output_dir: str | Path,
    historical_replay_export_matrix_metadata_patch_plan_source: Mapping[str, Any] | None = None,
    exact_matrix_edge_summary_source: Mapping[str, Any] | None = None,
    replay_window_label: str | None = None,
) -> dict[str, Any]:
    """Build and write the historical replay matrix metadata rerun plan."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result = build_signalforge_historical_replay_matrix_metadata_rerun_plan(
        matrix_metadata_patch_coverage_audit_source=matrix_metadata_patch_coverage_audit_source,
        historical_replay_export_matrix_metadata_patch_plan_source=historical_replay_export_matrix_metadata_patch_plan_source,
        exact_matrix_edge_summary_source=exact_matrix_edge_summary_source,
        replay_window_label=replay_window_label,
    )
    summary = summarize_signalforge_historical_replay_matrix_metadata_rerun_plan(result)

    result_path = output_path / RESULT_FILENAME
    summary_path = output_path / SUMMARY_FILENAME
    steps_path = output_path / STEPS_FILENAME
    checklist_path = output_path / CHECKLIST_FILENAME

    _write_json(result_path, result)
    _write_json(summary_path, summary)
    _write_json(steps_path, list(result.get("rerun_steps") or []))
    _write_json(
        checklist_path,
        {
            "pre_rerun_validation_checks": list(result.get("pre_rerun_validation_checks") or []),
            "post_rerun_validation_checks": list(result.get("post_rerun_validation_checks") or []),
        },
    )

    return {
        "artifact_type": "historical_replay_matrix_metadata_rerun_plan_write_result",
        "schema_version": "signalforge_historical_replay_matrix_metadata_rerun_plan_write_result.v1",
        "operation_type": "signalforge_historical_replay_matrix_metadata_rerun_plan_file_writer",
        "status": result.get("status"),
        "is_ready": bool(result.get("is_ready")),
        "rerun_plan_state": result.get("rerun_plan_state"),
        "coverage_audit_state": result.get("coverage_audit_state"),
        "coverage_ready_for_rerun": bool(result.get("coverage_ready_for_rerun")),
        "ready_to_execute_rerun_plan": bool(result.get("ready_to_execute_rerun_plan")),
        "ready_to_build_exact_matrix_edge_summary": bool(result.get("ready_to_build_exact_matrix_edge_summary")),
        "ready_to_use_for_strategy_selection": bool(result.get("ready_to_use_for_strategy_selection")),
        "replay_window_label": result.get("replay_window_label"),
        "patch_target_count": result.get("patch_target_count"),
        "required_patch_target_count": result.get("required_patch_target_count"),
        "ready_patch_target_count": result.get("ready_patch_target_count"),
        "required_needs_review_patch_target_count": result.get("required_needs_review_patch_target_count"),
        "rerun_step_count": result.get("rerun_step_count"),
        "required_rerun_step_count": result.get("required_rerun_step_count"),
        "recommended_next_step": result.get("recommended_next_step"),
        "output_dir": str(output_path),
        "result_path": str(result_path),
        "summary_path": str(summary_path),
        "steps_path": str(steps_path),
        "validation_checklist_path": str(checklist_path),
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
