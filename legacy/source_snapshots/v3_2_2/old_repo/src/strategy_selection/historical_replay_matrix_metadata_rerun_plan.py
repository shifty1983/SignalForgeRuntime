"""Historical replay matrix metadata rerun plan.

This module builds a deterministic rerun plan after the matrix metadata patch
coverage audit has been completed. It is intentionally a planning artifact only:
it does not call brokers, route orders, submit orders, request fills, run
QuantConnect, mutate source files, or infer missing matrix dimensions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

ARTIFACT_TYPE = "signalforge_historical_replay_matrix_metadata_rerun_plan"
SCHEMA_VERSION = "signalforge_historical_replay_matrix_metadata_rerun_plan.v1"
SUMMARY_ARTIFACT_TYPE = "signalforge_historical_replay_matrix_metadata_rerun_plan_summary"
SUMMARY_SCHEMA_VERSION = "signalforge_historical_replay_matrix_metadata_rerun_plan_summary.v1"

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
    "automatic_close_orders",
    "automatic_roll_orders",
    "automatic_defense_orders",
    "automatic_strategy_changes",
    "automatic_parameter_changes",
    "automatic_pause_actions",
]

MATRIX_CELL_KEY_FIELDS = [
    "regime_state",
    "asset_behavior_state",
    "option_behavior_state",
    "strategy_id",
    "strategy_family",
    "symbol",
    "horizon_days",
]

RERUN_STEPS = [
    {
        "step_id": "quantconnect_replay_scaleout_plan",
        "stage": "replay_request_producer",
        "description": "Regenerate replay request candidates with matrix metadata envelope support.",
        "expected_matrix_metadata_action": "stamp_initial_symbol_horizon_and_preserve_available_matrix_dimensions",
        "command_template": "rerun the existing QuantConnect historical replay scaleout plan command for the selected date window",
        "required": True,
    },
    {
        "step_id": "quantconnect_historical_replay_handoff",
        "stage": "replay_handoff",
        "description": "Regenerate the QuantConnect replay handoff manifest while preserving matrix metadata.",
        "expected_matrix_metadata_action": "carry_matrix_metadata_into_quantconnect_payloads",
        "command_template": "rerun the existing QuantConnect historical replay handoff command using the refreshed scaleout plan",
        "required": True,
    },
    {
        "step_id": "quantconnect_cloud_replay_batch_runner",
        "stage": "cloud_replay_batch_transport",
        "description": "Regenerate cloud replay batch artifacts with matrix metadata context preserved.",
        "expected_matrix_metadata_action": "preserve_matrix_metadata_through_batch_manifest_and_result_import_context",
        "command_template": "rerun the existing QuantConnect cloud replay batch runner command using the refreshed handoff manifest",
        "required": True,
    },
    {
        "step_id": "quantconnect_replay_result_import_validator",
        "stage": "replay_result_import",
        "description": "Re-import and validate replay results with matrix metadata coverage diagnostics.",
        "expected_matrix_metadata_action": "validate_contract_outcome_snapshots_for_matrix_metadata_envelope",
        "command_template": "rerun the existing QuantConnect replay result import validator command using refreshed replay results",
        "required": True,
    },
    {
        "step_id": "historical_edge_validation",
        "stage": "edge_validation",
        "description": "Rebuild historical edge validation from metadata-stamped replay outcomes.",
        "expected_matrix_metadata_action": "preserve_matrix_metadata_on_edge_records_and_block_incomplete_exact_cell_promotion",
        "command_template": "rerun the existing historical edge validation command using refreshed imported replay outcomes",
        "required": True,
    },
    {
        "step_id": "historical_edge_multi_window_summary",
        "stage": "edge_summary",
        "description": "Rebuild multi-window summaries with matrix metadata coverage counts.",
        "expected_matrix_metadata_action": "summarize_matrix_metadata_coverage_by_window_and_horizon",
        "command_template": "rerun the existing historical edge multi-window summary command",
        "required": True,
    },
    {
        "step_id": "historical_edge_diagnostics",
        "stage": "edge_diagnostics",
        "description": "Rebuild edge diagnostics with missing matrix dimension diagnostics.",
        "expected_matrix_metadata_action": "diagnose_missing_matrix_metadata_by_dimension",
        "command_template": "rerun the existing historical edge diagnostics command",
        "required": True,
    },
    {
        "step_id": "portfolio_equity_reconstruction",
        "stage": "portfolio_reconstruction",
        "description": "Rebuild portfolio equity reconstructions while preserving matrix metadata on events and scenarios.",
        "expected_matrix_metadata_action": "carry_matrix_metadata_through_reconstructed_trade_events_and_scenarios",
        "command_template": "rerun the existing portfolio equity reconstruction commands for the selected scenarios",
        "required": True,
    },
    {
        "step_id": "portfolio_candidate_selection_summary",
        "stage": "portfolio_candidate_summary",
        "description": "Rebuild portfolio candidate selection summary with matrix metadata on selected candidates.",
        "expected_matrix_metadata_action": "preserve_selected_candidate_matrix_metadata",
        "command_template": "rerun the existing portfolio candidate selection summary command",
        "required": True,
    },
    {
        "step_id": "historical_final_review",
        "stage": "historical_final_review",
        "description": "Rebuild historical final review artifacts with matrix metadata coverage preserved.",
        "expected_matrix_metadata_action": "carry_matrix_metadata_through_final_review_records",
        "command_template": "rerun the existing historical final review summary/export commands",
        "required": True,
    },
    {
        "step_id": "historical_replay_matrix_metadata_backfill_adapter",
        "stage": "matrix_metadata_reconciliation",
        "description": "Re-run the backfill adapter against the refreshed artifacts to confirm record-level matrix metadata readiness.",
        "expected_matrix_metadata_action": "measure_exact_matrix_cell_ready_record_count_after_rerun",
        "command_template": "rerun src.strategy_selection.historical_replay_matrix_metadata_backfill_adapter_cli against refreshed artifacts",
        "required": True,
    },
    {
        "step_id": "exact_matrix_edge_summary",
        "stage": "exact_matrix_edge_summary",
        "description": "Build exact matrix edge summaries only from records with complete matrix metadata.",
        "expected_matrix_metadata_action": "aggregate_exact_matrix_cell_edge_evidence_without_inference",
        "command_template": "run src.strategy_selection.exact_matrix_edge_summary_cli against refreshed metadata-stamped records",
        "required": True,
    },
    {
        "step_id": "matrix_metadata_patch_coverage_audit",
        "stage": "post_rerun_audit",
        "description": "Re-run patch coverage and readiness audit after regenerated artifacts exist.",
        "expected_matrix_metadata_action": "confirm_patch_coverage_and_exact_summary_readiness",
        "command_template": "rerun src.strategy_selection.matrix_metadata_patch_coverage_audit_cli with the refreshed exact matrix edge summary",
        "required": True,
    },
]


def build_signalforge_historical_replay_matrix_metadata_rerun_plan(
    *,
    matrix_metadata_patch_coverage_audit_source: Mapping[str, Any],
    historical_replay_export_matrix_metadata_patch_plan_source: Mapping[str, Any] | None = None,
    exact_matrix_edge_summary_source: Mapping[str, Any] | None = None,
    replay_window_label: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic rerun plan after matrix metadata patches are applied."""

    warnings: list[str] = []
    blocked_reasons: list[str] = []

    coverage = matrix_metadata_patch_coverage_audit_source
    if not isinstance(coverage, Mapping) or not coverage:
        blocked_reasons.append("matrix_metadata_patch_coverage_audit_source_required")
        coverage = {}

    patch_plan = historical_replay_export_matrix_metadata_patch_plan_source or {}
    if patch_plan and not isinstance(patch_plan, Mapping):
        blocked_reasons.append("historical_replay_export_matrix_metadata_patch_plan_source_invalid")
        patch_plan = {}

    coverage_state = str(coverage.get("coverage_audit_state") or coverage.get("status") or "unknown")
    coverage_ready = bool(
        coverage.get("ready_to_rerun_historical_replay_with_matrix_metadata")
        or (coverage_state == "ready" and _as_int(coverage.get("required_needs_review_patch_target_count")) == 0)
    )

    if coverage and coverage_state == "blocked":
        blocked_reasons.append("matrix_metadata_patch_coverage_audit_blocked")
    elif coverage and not coverage_ready:
        warnings.append("matrix_metadata_patch_coverage_audit_not_ready_for_replay_rerun")

    required_needs_review_targets = _as_int(coverage.get("required_needs_review_patch_target_count"))
    if required_needs_review_targets:
        warnings.append("required_patch_targets_still_need_review")

    missing_or_review_targets = _as_target_list(coverage.get("missing_or_needs_review_targets"))

    exact_summary = _exact_summary(exact_matrix_edge_summary_source)
    exact_ready_records = _as_int(exact_summary.get("exact_matrix_cell_ready_record_count"))
    exact_ready_cells = _as_int(exact_summary.get("ready_matrix_edge_cell_count"))
    exact_summary_ready = bool(exact_summary.get("ready_to_use_for_strategy_selection"))

    rerun_steps = _build_rerun_steps(
        coverage_ready=coverage_ready,
        replay_window_label=replay_window_label,
    )

    status = "blocked" if blocked_reasons else ("ready" if coverage_ready else "needs_review")
    recommended_next_step = _recommended_next_step(
        status=status,
        coverage_ready=coverage_ready,
        exact_summary_ready=exact_summary_ready,
        exact_ready_records=exact_ready_records,
    )

    matrix_cell_key_fields = _as_text_list(
        coverage.get("matrix_cell_key_fields")
        or patch_plan.get("matrix_cell_key_fields")
        or MATRIX_CELL_KEY_FIELDS
    )

    result = {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "operation_type": "signalforge_historical_replay_matrix_metadata_rerun_plan_builder",
        "rerun_plan_id": _stable_id(coverage.get("artifact_type"), coverage_state, matrix_cell_key_fields, replay_window_label),
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": status,
        "is_ready": status == "ready",
        "rerun_plan_state": status,
        "coverage_audit_state": coverage_state,
        "coverage_ready_for_rerun": coverage_ready,
        "patch_plan_state": str(patch_plan.get("patch_plan_state") or patch_plan.get("status") or "unknown"),
        "replay_window_label": str(replay_window_label or "unspecified"),
        "matrix_metadata_envelope_key": str(coverage.get("matrix_metadata_envelope_key") or patch_plan.get("matrix_metadata_envelope_key") or "matrix_metadata"),
        "matrix_cell_key_fields": matrix_cell_key_fields,
        "patch_target_count": _as_int(coverage.get("patch_target_count")),
        "required_patch_target_count": _as_int(coverage.get("required_patch_target_count")),
        "ready_patch_target_count": _as_int(coverage.get("ready_patch_target_count")),
        "required_needs_review_patch_target_count": required_needs_review_targets,
        "missing_or_needs_review_targets": missing_or_review_targets,
        "rerun_step_count": len(rerun_steps),
        "required_rerun_step_count": sum(1 for step in rerun_steps if step.get("required")),
        "rerun_steps": rerun_steps,
        "pre_rerun_validation_checks": _pre_rerun_validation_checks(coverage_ready=coverage_ready),
        "post_rerun_validation_checks": _post_rerun_validation_checks(),
        "ready_to_execute_rerun_plan": bool(status == "ready"),
        "ready_to_build_exact_matrix_edge_summary": False,
        "ready_to_use_for_strategy_selection": bool(exact_summary_ready and exact_ready_cells > 0),
        "exact_matrix_edge_summary_audit": exact_summary,
        "recommended_next_step": recommended_next_step,
        "warnings": _ordered_unique(warnings + _as_text_list(coverage.get("warnings"))),
        "blocked_reasons": _ordered_unique(blocked_reasons),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "order_intent": None,
        "broker_order_id": None,
        "requires_manual_approval": True,
    }
    result["rerun_plan_summary"] = summarize_signalforge_historical_replay_matrix_metadata_rerun_plan(result)
    return result


def summarize_signalforge_historical_replay_matrix_metadata_rerun_plan(result: Mapping[str, Any]) -> dict[str, Any]:
    """Build a compact rerun plan summary."""

    return {
        "artifact_type": SUMMARY_ARTIFACT_TYPE,
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "status": str(result.get("status") or "blocked"),
        "is_ready": bool(result.get("is_ready")),
        "rerun_plan_state": str(result.get("rerun_plan_state") or "blocked"),
        "coverage_audit_state": str(result.get("coverage_audit_state") or "unknown"),
        "coverage_ready_for_rerun": bool(result.get("coverage_ready_for_rerun")),
        "patch_plan_state": str(result.get("patch_plan_state") or "unknown"),
        "replay_window_label": str(result.get("replay_window_label") or "unspecified"),
        "patch_target_count": _as_int(result.get("patch_target_count")),
        "required_patch_target_count": _as_int(result.get("required_patch_target_count")),
        "ready_patch_target_count": _as_int(result.get("ready_patch_target_count")),
        "required_needs_review_patch_target_count": _as_int(result.get("required_needs_review_patch_target_count")),
        "rerun_step_count": _as_int(result.get("rerun_step_count")),
        "required_rerun_step_count": _as_int(result.get("required_rerun_step_count")),
        "ready_to_execute_rerun_plan": bool(result.get("ready_to_execute_rerun_plan")),
        "ready_to_build_exact_matrix_edge_summary": bool(result.get("ready_to_build_exact_matrix_edge_summary")),
        "ready_to_use_for_strategy_selection": bool(result.get("ready_to_use_for_strategy_selection")),
        "recommended_next_step": str(result.get("recommended_next_step") or "unknown"),
        "warnings": _as_text_list(result.get("warnings")),
        "blocked_reasons": _as_text_list(result.get("blocked_reasons")),
        "explicit_exclusions": _as_text_list(result.get("explicit_exclusions")) or list(EXPLICIT_EXCLUSIONS),
        "automatic_action": None,
        "automatic_strategy_change": None,
        "order_intent": None,
        "requires_manual_approval": True,
    }


def _build_rerun_steps(*, coverage_ready: bool, replay_window_label: str | None) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for index, raw_step in enumerate(RERUN_STEPS, start=1):
        step = dict(raw_step)
        step["step"] = index
        step["rerun_step_state"] = "ready" if coverage_ready else "waiting_for_patch_coverage_ready"
        step["replay_window_label"] = str(replay_window_label or "unspecified")
        step["blocks_exact_matrix_edge_summary"] = bool(step.get("required"))
        steps.append(step)
    return steps


def _pre_rerun_validation_checks(*, coverage_ready: bool) -> list[dict[str, Any]]:
    return [
        {
            "check_id": "patch_coverage_audit_ready",
            "description": "Coverage audit must report all required patch targets ready before rerunning historical replay.",
            "required": True,
            "check_state": "ready" if coverage_ready else "needs_review",
        },
        {
            "check_id": "generated_artifacts_should_use_new_output_dirs",
            "description": "Regenerated artifacts should use a new or clearly replaced output directory to avoid mixing old non-stamped records with refreshed records.",
            "required": True,
            "check_state": "manual_review_required",
        },
        {
            "check_id": "no_strategy_inference_allowed",
            "description": "The rerun must stamp only explicit matrix metadata from source artifacts and must not infer missing regime, asset behavior, option behavior, strategy, symbol, or horizon.",
            "required": True,
            "check_state": "ready",
        },
    ]


def _post_rerun_validation_checks() -> list[dict[str, Any]]:
    return [
        {
            "check_id": "backfill_adapter_record_count_matches_replay_records",
            "description": "Backfill adapter should evaluate the refreshed historical replay record set, not just source files.",
            "required": True,
        },
        {
            "check_id": "exact_matrix_cell_ready_record_count_positive_or_explained",
            "description": "If exact-ready record count remains zero, missing dimensions must be reported by dimension without promoting records.",
            "required": True,
        },
        {
            "check_id": "exact_matrix_edge_summary_not_ready_when_required_fields_missing",
            "description": "Exact matrix edge summary must remain needs_review until complete matrix metadata exists.",
            "required": True,
        },
        {
            "check_id": "no_order_or_broker_side_effects",
            "description": "The replay rerun plan introduces no broker calls, order routing, order submission, fills, live execution, or slippage modeling.",
            "required": True,
        },
    ]


def _exact_summary(source: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(source, Mapping) or not source:
        return {
            "source_provided": False,
            "status": "not_provided",
            "exact_matrix_cell_ready_record_count": 0,
            "ready_matrix_edge_cell_count": 0,
            "ready_to_use_for_strategy_selection": False,
        }

    return {
        "source_provided": True,
        "status": str(source.get("status") or source.get("summary_state") or "unknown"),
        "exact_matrix_cell_ready_record_count": _as_int(source.get("exact_matrix_cell_ready_record_count")),
        "ready_matrix_edge_cell_count": _as_int(
            source.get("ready_matrix_edge_cell_count") or source.get("ready_matrix_cell_count")
        ),
        "ready_to_use_for_strategy_selection": bool(
            source.get("ready_to_use_for_strategy_selection") or source.get("ready_for_strategy_selection")
        ),
        "recommended_next_step": str(source.get("recommended_next_step") or "unknown"),
    }


def _recommended_next_step(
    *,
    status: str,
    coverage_ready: bool,
    exact_summary_ready: bool,
    exact_ready_records: int,
) -> str:
    if status == "blocked":
        return "resolve_blocked_rerun_plan_inputs"
    if not coverage_ready:
        return "complete_matrix_metadata_patch_coverage_before_rerun"
    if exact_summary_ready and exact_ready_records > 0:
        return "review_exact_matrix_edge_summary_for_strategy_selection"
    return "rerun_historical_replay_with_populated_matrix_metadata_envelope"


def _as_target_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, Mapping):
            result.append(
                {
                    "target_id": str(item.get("target_id") or "unknown"),
                    "module_path": str(item.get("module_path") or "unknown"),
                    "patch_target_audit_state": str(item.get("patch_target_audit_state") or "unknown"),
                    "required": bool(item.get("required")),
                    "warnings": _as_text_list(item.get("warnings")),
                }
            )
    return result


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, bytearray)):
        text = value.decode() if isinstance(value, (bytes, bytearray)) else value
        return [text] if text else []
    if isinstance(value, Mapping):
        return [str(key) for key in value.keys()]
    if isinstance(value, Sequence):
        return [str(item) for item in value if item is not None and str(item) != ""]
    return [str(value)]


def _as_int(value: Any, *, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _ordered_unique(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in _as_text_list(values):
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _stable_id(*parts: Any) -> str:
    payload = repr(parts).encode("utf-8")
    return f"historical_replay_matrix_metadata_rerun_plan_{sha256(payload).hexdigest()[:16]}"
