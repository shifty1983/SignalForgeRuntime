"""Matrix metadata patch coverage audit.

This module audits whether the historical replay/export patch plan has been
applied across the expected producer and consumer modules. It is intentionally a
coverage/audit layer only: it does not mutate source files, infer missing matrix
metadata, score strategies, connect to brokers, request quotes, submit orders,
or change strategy-selection rules.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ARTIFACT_TYPE = "signalforge_matrix_metadata_patch_coverage_audit"
SCHEMA_VERSION = "signalforge_matrix_metadata_patch_coverage_audit.v1"
SUMMARY_ARTIFACT_TYPE = "signalforge_matrix_metadata_patch_coverage_audit_compact"
SUMMARY_SCHEMA_VERSION = "signalforge_matrix_metadata_patch_coverage_audit_compact.v1"

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

MATRIX_METADATA_TOKENS = [
    "matrix_metadata",
    "matrix_metadata_state",
    "matrix_metadata_missing_fields",
    "matrix_cell_key",
]

STAMPING_HELPER_TOKENS = [
    "historical_replay_matrix_metadata_stamp",
    "stamp_matrix_metadata",
    "build_matrix_cell_key",
    "matrix_metadata_coverage",
]

REQUIRED_STAMPING_HELPER_PATH = "src/strategy_selection/historical_replay_matrix_metadata_stamp.py"


def build_signalforge_matrix_metadata_patch_coverage_audit(
    *,
    historical_replay_export_matrix_metadata_patch_plan_source: Mapping[str, Any],
    repo_root: str | Path | None = None,
    additional_patch_targets: Sequence[Mapping[str, Any]] | None = None,
    exact_matrix_edge_summary_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit patch-plan targets for matrix metadata source coverage."""

    warnings: list[str] = []
    blocked_reasons: list[str] = []

    patch_plan = historical_replay_export_matrix_metadata_patch_plan_source
    if not isinstance(patch_plan, Mapping) or not patch_plan:
        blocked_reasons.append("historical_replay_export_matrix_metadata_patch_plan_source_required")
        patch_plan = {}

    patch_plan_state = str(patch_plan.get("patch_plan_state") or patch_plan.get("status") or "unknown")
    if patch_plan and patch_plan_state != "ready":
        blocked_reasons.append("historical_replay_export_matrix_metadata_patch_plan_not_ready")

    root = Path(repo_root or ".").resolve()
    patch_targets = _extract_patch_targets(patch_plan)
    if additional_patch_targets:
        patch_targets.extend(
            target
            for target in (_normalize_patch_target(item) for item in additional_patch_targets if isinstance(item, Mapping))
            if str(target.get("module_path") or "").strip()
        )
    patch_targets = _dedupe_patch_targets(patch_targets)

    if not patch_targets and not blocked_reasons:
        blocked_reasons.append("patch_targets_required")

    helper_audit = _audit_stamping_helper(root)
    target_audits = [_audit_patch_target(root, target) for target in patch_targets]

    required_target_audits = [item for item in target_audits if item.get("required")]
    source_file_found_count = sum(1 for item in target_audits if item.get("source_file_found"))
    matrix_metadata_reference_count = sum(1 for item in target_audits if item.get("matrix_metadata_referenced"))
    stamping_helper_reference_count = sum(1 for item in target_audits if item.get("stamping_helper_referenced"))
    ready_target_count = sum(1 for item in target_audits if item.get("patch_target_audit_state") == "ready")
    needs_review_target_count = sum(
        1 for item in target_audits if item.get("patch_target_audit_state") == "needs_review"
    )
    missing_source_target_count = sum(
        1 for item in target_audits if item.get("patch_target_audit_state") == "missing_source"
    )
    blocked_target_count = sum(
        1 for item in target_audits if item.get("patch_target_audit_state") == "blocked"
    )

    required_ready_count = sum(
        1 for item in required_target_audits if item.get("patch_target_audit_state") == "ready"
    )
    required_needs_review_count = sum(
        1
        for item in required_target_audits
        if item.get("patch_target_audit_state") in {"needs_review", "missing_source", "blocked"}
    )

    if not helper_audit.get("source_file_found"):
        warnings.append("matrix_metadata_stamping_helper_source_not_found")
    elif not helper_audit.get("matrix_metadata_referenced"):
        warnings.append("matrix_metadata_stamping_helper_missing_matrix_metadata_tokens")

    if missing_source_target_count:
        warnings.append("some_patch_targets_missing_source_files")
    if needs_review_target_count:
        warnings.append("some_patch_targets_need_matrix_metadata_patch_review")
    if required_needs_review_count:
        warnings.append("required_patch_targets_not_fully_matrix_metadata_covered")

    exact_summary = _exact_summary(exact_matrix_edge_summary_source)
    exact_ready_records = _as_int(exact_summary.get("exact_matrix_cell_ready_record_count"))
    exact_ready_cells = _as_int(exact_summary.get("ready_matrix_edge_cell_count"))
    exact_summary_ready = bool(exact_summary.get("ready_to_use_for_strategy_selection"))
    if exact_matrix_edge_summary_source and not exact_summary_ready:
        warnings.append("exact_matrix_edge_summary_not_ready_for_strategy_selection")

    coverage_ready = bool(
        not blocked_reasons
        and patch_targets
        and helper_audit.get("source_file_found")
        and required_needs_review_count == 0
        and required_ready_count == len(required_target_audits)
    )

    status = "blocked" if blocked_reasons else ("ready" if coverage_ready else "needs_review")

    recommended_next_step = _recommended_next_step(
        status=status,
        helper_audit=helper_audit,
        required_needs_review_count=required_needs_review_count,
        exact_summary_ready=exact_summary_ready,
        exact_ready_records=exact_ready_records,
    )

    return {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "coverage_audit_state": status,
        "patch_plan_state": patch_plan_state,
        "repo_root": str(root),
        "matrix_metadata_envelope_key": str(patch_plan.get("matrix_metadata_envelope_key") or "matrix_metadata"),
        "matrix_cell_key_fields": _as_text_list(patch_plan.get("matrix_cell_key_fields")),
        "patch_target_count": len(target_audits),
        "required_patch_target_count": len(required_target_audits),
        "source_file_found_count": source_file_found_count,
        "matrix_metadata_reference_count": matrix_metadata_reference_count,
        "stamping_helper_reference_count": stamping_helper_reference_count,
        "ready_patch_target_count": ready_target_count,
        "needs_review_patch_target_count": needs_review_target_count,
        "missing_source_patch_target_count": missing_source_target_count,
        "blocked_patch_target_count": blocked_target_count,
        "required_ready_patch_target_count": required_ready_count,
        "required_needs_review_patch_target_count": required_needs_review_count,
        "stamping_helper_audit": helper_audit,
        "patch_target_audits": target_audits,
        "patch_target_stage_summary": _stage_summary(target_audits),
        "missing_or_needs_review_targets": [
            item for item in target_audits if item.get("patch_target_audit_state") != "ready"
        ],
        "ready_to_rerun_historical_replay_with_matrix_metadata": bool(status == "ready"),
        "ready_to_build_exact_matrix_edge_summary": bool(exact_summary_ready),
        "ready_to_use_for_strategy_selection": bool(exact_summary_ready and exact_ready_cells > 0),
        "exact_matrix_edge_summary_audit": exact_summary,
        "recommended_next_step": recommended_next_step,
        "warnings": _ordered_unique(warnings),
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


def summarize_signalforge_matrix_metadata_patch_coverage_audit(result: Mapping[str, Any]) -> dict[str, Any]:
    """Build a compact audit summary."""

    return {
        "artifact_type": SUMMARY_ARTIFACT_TYPE,
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "status": result.get("status"),
        "is_ready": bool(result.get("is_ready")),
        "coverage_audit_state": result.get("coverage_audit_state"),
        "patch_plan_state": result.get("patch_plan_state"),
        "patch_target_count": _as_int(result.get("patch_target_count")),
        "required_patch_target_count": _as_int(result.get("required_patch_target_count")),
        "source_file_found_count": _as_int(result.get("source_file_found_count")),
        "matrix_metadata_reference_count": _as_int(result.get("matrix_metadata_reference_count")),
        "stamping_helper_reference_count": _as_int(result.get("stamping_helper_reference_count")),
        "ready_patch_target_count": _as_int(result.get("ready_patch_target_count")),
        "needs_review_patch_target_count": _as_int(result.get("needs_review_patch_target_count")),
        "missing_source_patch_target_count": _as_int(result.get("missing_source_patch_target_count")),
        "required_ready_patch_target_count": _as_int(result.get("required_ready_patch_target_count")),
        "required_needs_review_patch_target_count": _as_int(result.get("required_needs_review_patch_target_count")),
        "ready_to_rerun_historical_replay_with_matrix_metadata": bool(
            result.get("ready_to_rerun_historical_replay_with_matrix_metadata")
        ),
        "ready_to_build_exact_matrix_edge_summary": bool(
            result.get("ready_to_build_exact_matrix_edge_summary")
        ),
        "ready_to_use_for_strategy_selection": bool(result.get("ready_to_use_for_strategy_selection")),
        "recommended_next_step": result.get("recommended_next_step"),
        "warnings": list(result.get("warnings") or []),
        "blocked_reasons": list(result.get("blocked_reasons") or []),
        "explicit_exclusions": list(result.get("explicit_exclusions") or EXPLICIT_EXCLUSIONS),
        "automatic_action": None,
        "automatic_strategy_change": None,
        "order_intent": None,
        "requires_manual_approval": True,
    }


def _audit_stamping_helper(repo_root: Path) -> dict[str, Any]:
    target = {
        "target_id": "matrix_metadata_stamping_helper",
        "module_path": REQUIRED_STAMPING_HELPER_PATH,
        "patch_stage": "shared_helper",
        "target_type": "new_helper",
        "required": True,
    }
    return _audit_patch_target(repo_root, target)


def _audit_patch_target(repo_root: Path, target: Mapping[str, Any]) -> dict[str, Any]:
    module_path = str(target.get("module_path") or "").replace("\\", "/")
    target_id = str(target.get("target_id") or module_path or "unknown_target")
    required = bool(target.get("required", True))

    if not module_path:
        return {
            "target_id": target_id,
            "module_path": module_path,
            "patch_stage": str(target.get("patch_stage") or "unknown"),
            "target_type": str(target.get("target_type") or "unknown"),
            "required": required,
            "source_file_found": False,
            "matrix_metadata_referenced": False,
            "stamping_helper_referenced": False,
            "patch_target_audit_state": "blocked",
            "blocked_reasons": ["patch_target_module_path_required"],
            "warnings": [],
        }

    source_path = (repo_root / module_path).resolve()
    source_file_found = source_path.exists() and source_path.is_file()
    source_text = ""
    read_error = None
    if source_file_found:
        try:
            source_text = source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            source_text = source_path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            read_error = str(exc)

    matrix_token_hits = [token for token in MATRIX_METADATA_TOKENS if token in source_text]
    helper_token_hits = [token for token in STAMPING_HELPER_TOKENS if token in source_text]
    matrix_metadata_referenced = bool(matrix_token_hits)
    stamping_helper_referenced = bool(helper_token_hits)

    warnings: list[str] = []
    blocked_reasons: list[str] = []
    if not source_file_found:
        warnings.append("patch_target_source_file_not_found")
    if read_error:
        blocked_reasons.append("patch_target_source_file_read_failed")
    if source_file_found and not matrix_metadata_referenced:
        warnings.append("matrix_metadata_not_referenced_in_patch_target")
    if source_file_found and not stamping_helper_referenced:
        warnings.append("matrix_metadata_stamping_helper_not_referenced_in_patch_target")

    if blocked_reasons:
        audit_state = "blocked"
    elif not source_file_found:
        audit_state = "missing_source"
    elif matrix_metadata_referenced:
        audit_state = "ready" if (stamping_helper_referenced or target_id == "matrix_metadata_stamping_helper") else "needs_review"
    else:
        audit_state = "needs_review"

    return {
        "target_id": target_id,
        "target_type": str(target.get("target_type") or "unknown"),
        "patch_stage": str(target.get("patch_stage") or "unknown"),
        "priority": _as_int(target.get("priority")),
        "module_path": module_path,
        "required": required,
        "source_file_found": source_file_found,
        "source_file_size": source_path.stat().st_size if source_file_found else 0,
        "matrix_metadata_referenced": matrix_metadata_referenced,
        "stamping_helper_referenced": stamping_helper_referenced,
        "matrix_metadata_token_hits": matrix_token_hits,
        "stamping_helper_token_hits": helper_token_hits,
        "patch_target_audit_state": audit_state,
        "warnings": _ordered_unique(warnings),
        "blocked_reasons": _ordered_unique(blocked_reasons),
    }


def _extract_patch_targets(patch_plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates: list[Any] = []
    for key in ("patch_targets", "producer_patch_requirements", "patch_sequence"):
        value = patch_plan.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            candidates.extend(value)

    targets = [
        target
        for target in (_normalize_patch_target(item) for item in candidates if isinstance(item, Mapping))
        if str(target.get("module_path") or "").strip()
    ]

    # Some write-result artifacts store paths to target files instead of the full
    # lists. If the lists are absent, still audit the known default target count
    # by using the target ids/module paths encoded in the patch-plan summary when
    # present. This keeps the audit useful for compact write-result artifacts.
    if not targets and _as_int(patch_plan.get("patch_target_count")):
        targets = _default_target_skeletons()

    return targets


def _normalize_patch_target(item: Mapping[str, Any]) -> dict[str, Any]:
    module_path = str(item.get("module_path") or item.get("source_path") or item.get("path") or "")
    target_id = str(item.get("target_id") or item.get("id") or module_path or "unknown_target")
    return {
        "target_id": target_id,
        "target_type": str(item.get("target_type") or item.get("type") or "unknown"),
        "patch_stage": str(item.get("patch_stage") or item.get("stage") or "unknown"),
        "priority": _as_int(item.get("priority")),
        "module_path": module_path,
        "required": bool(item.get("required", True)),
    }


def _default_target_skeletons() -> list[dict[str, Any]]:
    paths = [
        ("matrix_metadata_stamping_helper", "src/strategy_selection/historical_replay_matrix_metadata_stamp.py", "shared_helper"),
        ("regime_asset_options_alignment_source", "src/alignment/regime_asset_options_alignment.py", "source_dimension_provider"),
        ("strategy_family_eligibility_source", "src/strategy_selection/strategy_family_eligibility.py", "source_dimension_provider"),
        ("options_strategy_setup_matcher_source", "src/options_strategy/setup_matcher.py", "source_dimension_provider"),
        ("quantconnect_replay_scaleout_plan", "src/data_sources/quantconnect_historical_replay_scaleout_plan/planner.py", "replay_request_producer"),
        ("quantconnect_historical_replay_handoff", "src/data_sources/quantconnect_historical_replay_handoff/handoff.py", "replay_handoff"),
        ("quantconnect_cloud_replay_batch_runner", "src/data_sources/quantconnect_cloud_replay_batch_runner/runner.py", "cloud_replay_batch_transport"),
        ("quantconnect_replay_result_import_validator", "src/data_sources/quantconnect_replay_result_import_validator/validator.py", "replay_result_import"),
        ("historical_edge_validator", "src/data_sources/historical_edge_validation/edge_validator.py", "edge_validation"),
        ("historical_edge_multi_window_summary", "src/data_sources/historical_edge_validation/multi_window_summary.py", "edge_summary"),
        ("historical_edge_diagnostics", "src/data_sources/historical_edge_validation/edge_diagnostics.py", "edge_diagnostics"),
        ("portfolio_candidate_selection_summary", "src/data_sources/portfolio_equity_reconstruction/candidate_selection_summary.py", "portfolio_candidate_summary"),
    ]
    return [
        {
            "target_id": target_id,
            "module_path": module_path,
            "patch_stage": stage,
            "target_type": "historical_replay_patch_target",
            "priority": index + 1,
            "required": True,
        }
        for index, (target_id, module_path, stage) in enumerate(paths)
    ]


def _dedupe_patch_targets(targets: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for target in targets:
        key = str(target.get("target_id") or target.get("module_path") or len(deduped))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(dict(target))
    return deduped


def _stage_summary(target_audits: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_stage: dict[str, dict[str, Any]] = {}
    for item in target_audits:
        stage = str(item.get("patch_stage") or "unknown")
        summary = by_stage.setdefault(
            stage,
            {
                "patch_stage": stage,
                "target_count": 0,
                "ready_target_count": 0,
                "needs_review_target_count": 0,
                "missing_source_target_count": 0,
                "blocked_target_count": 0,
            },
        )
        summary["target_count"] += 1
        state = str(item.get("patch_target_audit_state") or "unknown")
        if state == "ready":
            summary["ready_target_count"] += 1
        elif state == "missing_source":
            summary["missing_source_target_count"] += 1
        elif state == "blocked":
            summary["blocked_target_count"] += 1
        else:
            summary["needs_review_target_count"] += 1
    return sorted(by_stage.values(), key=lambda item: item["patch_stage"])


def _exact_summary(source: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {
            "source_provided": False,
            "ready_to_build_exact_matrix_edge_summary": False,
            "ready_to_use_for_strategy_selection": False,
            "exact_matrix_cell_ready_record_count": 0,
            "ready_matrix_edge_cell_count": 0,
        }
    return {
        "source_provided": True,
        "status": source.get("status"),
        "matrix_edge_summary_state": source.get("matrix_edge_summary_state"),
        "ready_to_build_exact_matrix_edge_summary": bool(
            source.get("ready_to_build_exact_matrix_edge_summary")
        ),
        "ready_to_use_for_strategy_selection": bool(source.get("ready_to_use_for_strategy_selection")),
        "exact_matrix_cell_ready_record_count": _as_int(source.get("exact_matrix_cell_ready_record_count")),
        "ready_matrix_edge_cell_count": _as_int(source.get("ready_matrix_edge_cell_count")),
        "exact_matrix_cell_count": _as_int(source.get("exact_matrix_cell_count")),
        "recommended_next_step": source.get("recommended_next_step"),
    }


def _recommended_next_step(
    *,
    status: str,
    helper_audit: Mapping[str, Any],
    required_needs_review_count: int,
    exact_summary_ready: bool,
    exact_ready_records: int,
) -> str:
    if status == "blocked":
        return "resolve_matrix_metadata_patch_coverage_audit_blockers"
    if not helper_audit.get("source_file_found"):
        return "install_historical_replay_matrix_metadata_stamping_helpers"
    if required_needs_review_count:
        return "complete_remaining_matrix_metadata_patch_targets"
    if exact_summary_ready and exact_ready_records > 0:
        return "update_strategy_matrix_edge_inventory_with_exact_matrix_edge_summary"
    return "rerun_historical_replay_with_populated_matrix_metadata_envelope"


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [str(item) for item in value.keys()]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _ordered_unique(values: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = str(value)
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered
