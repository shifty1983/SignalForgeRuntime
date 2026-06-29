"""Historical replay export matrix metadata patch plan.

This module converts the matrix metadata envelope into a concrete source patch
plan for the historical replay/export pipeline. It identifies which producers
must stamp, preserve, validate, and summarize matrix metadata before exact
strategy-matrix edge validation can be built.

It intentionally does not mutate source files, infer missing regime/behavior
values, score strategies, select candidates, request data, connect to brokers,
route orders, submit orders, or alter strategy availability rules.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "signalforge_historical_replay_export_matrix_metadata_patch_plan.v1"
SUMMARY_SCHEMA_VERSION = "signalforge_historical_replay_export_matrix_metadata_patch_plan_summary.v1"
ARTIFACT_TYPE = "signalforge_historical_replay_export_matrix_metadata_patch_plan"

RECOMMENDED_NEXT_WHEN_READY = "historical_replay_matrix_metadata_stamping_helpers"
RECOMMENDED_NEXT_WHEN_BLOCKED = "resolve_historical_replay_export_matrix_metadata_patch_plan_blockers"

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

DEFAULT_MATRIX_CELL_KEY_FIELDS = [
    "regime_state",
    "asset_behavior_state",
    "option_behavior_state",
    "strategy_id",
    "strategy_family",
    "symbol",
    "horizon_days",
]

FIELD_TO_DIMENSION = {
    "regime_state": "regime",
    "asset_behavior_state": "asset_behavior",
    "option_behavior_state": "option_behavior",
    "strategy_id": "strategy",
    "strategy_family": "strategy",
    "symbol": "symbol",
    "horizon_days": "horizon",
    "asset_class": "asset_class",
    "strategy_direction": "direction",
    "risk_structure": "risk_structure",
    "replay_window_id": "window",
    "edge_score": "score",
    "outcome_state": "outcome",
}

# These are source-level producers/consumers that should be patched or checked.
# The plan intentionally names likely modules rather than mutating them. The next
# build should introduce reusable stamping helpers, then patch these producers.
DEFAULT_PATCH_TARGETS = [
    {
        "target_id": "matrix_metadata_stamping_helper",
        "target_type": "new_helper",
        "module_path": "src/strategy_selection/historical_replay_matrix_metadata_stamp.py",
        "patch_stage": "shared_helper",
        "priority": 1,
        "action": "create_shared_helper_for_matrix_metadata_envelope",
        "required_fields": list(DEFAULT_MATRIX_CELL_KEY_FIELDS),
        "description": "Create deterministic helper functions to build, validate, and merge matrix_metadata envelopes on replay records.",
    },
    {
        "target_id": "regime_asset_options_alignment_source",
        "target_type": "source_dimension_provider",
        "module_path": "src/alignment/regime_asset_options_alignment.py",
        "patch_stage": "source_dimension_provider",
        "priority": 2,
        "dimensions": ["regime", "asset_behavior", "option_behavior"],
        "fields": ["regime_state", "asset_behavior_state", "option_behavior_state"],
        "action": "expose_matrix_dimension_fields_for_replay_join",
        "description": "Ensure alignment outputs expose historical regime, asset behavior, and option behavior states using stable field names.",
    },
    {
        "target_id": "strategy_family_eligibility_source",
        "target_type": "source_dimension_provider",
        "module_path": "src/strategy_selection/strategy_family_eligibility.py",
        "patch_stage": "source_dimension_provider",
        "priority": 2,
        "dimensions": ["strategy"],
        "fields": ["strategy_id", "strategy_family"],
        "action": "expose_exact_strategy_matrix_identifiers",
        "description": "Ensure strategy availability/eligibility records expose exact strategy_id and strategy_family used to generate replay candidates.",
    },
    {
        "target_id": "options_strategy_setup_matcher_source",
        "target_type": "source_dimension_provider",
        "module_path": "src/options_strategy/setup_matcher.py",
        "patch_stage": "source_dimension_provider",
        "priority": 2,
        "dimensions": ["strategy"],
        "fields": ["strategy_id", "strategy_family"],
        "action": "preserve_setup_to_strategy_matrix_mapping",
        "description": "Preserve the strategy matrix strategy selected by the setup matcher for candidate generation.",
    },
    {
        "target_id": "quantconnect_replay_scaleout_plan",
        "target_type": "historical_replay_producer",
        "module_path": "src/data_sources/quantconnect_historical_replay_scaleout_plan/planner.py",
        "patch_stage": "replay_request_producer",
        "priority": 3,
        "dimensions": ["symbol", "horizon"],
        "fields": ["symbol", "horizon_days", "replay_window_id"],
        "action": "stamp_initial_symbol_horizon_window_metadata",
        "description": "Stamp normalized symbol, horizon_days, and replay window metadata into every replay request row.",
    },
    {
        "target_id": "quantconnect_historical_replay_handoff",
        "target_type": "historical_replay_handoff",
        "module_path": "src/data_sources/quantconnect_historical_replay_handoff/handoff.py",
        "patch_stage": "replay_handoff",
        "priority": 4,
        "dimensions": ["regime", "asset_behavior", "option_behavior", "strategy", "symbol", "horizon"],
        "fields": list(DEFAULT_MATRIX_CELL_KEY_FIELDS),
        "action": "carry_matrix_metadata_into_quantconnect_replay_payloads",
        "description": "Carry matrix_metadata from SignalForge replay candidate/request rows into the QuantConnect replay handoff payload.",
    },
    {
        "target_id": "quantconnect_cloud_replay_batch_runner",
        "target_type": "historical_replay_transport",
        "module_path": "src/data_sources/quantconnect_cloud_replay_batch_runner/runner.py",
        "patch_stage": "cloud_replay_batch_transport",
        "priority": 5,
        "dimensions": ["regime", "asset_behavior", "option_behavior", "strategy", "symbol", "horizon"],
        "fields": list(DEFAULT_MATRIX_CELL_KEY_FIELDS),
        "action": "preserve_matrix_metadata_through_batch_execution",
        "description": "Preserve matrix_metadata in batch manifests/results so QuantConnect replay outcomes can be joined back to matrix cells.",
    },
    {
        "target_id": "quantconnect_replay_result_import_validator",
        "target_type": "historical_replay_result_importer",
        "module_path": "src/data_sources/quantconnect_replay_result_import_validator/validator.py",
        "patch_stage": "replay_result_import",
        "priority": 6,
        "dimensions": ["regime", "asset_behavior", "option_behavior", "strategy", "symbol", "horizon"],
        "fields": list(DEFAULT_MATRIX_CELL_KEY_FIELDS),
        "action": "validate_and_preserve_imported_matrix_metadata",
        "description": "Validate imported replay outcomes include matrix_metadata and preserve missing-field diagnostics without guessing values.",
    },
    {
        "target_id": "historical_edge_validator",
        "target_type": "edge_validation_consumer",
        "module_path": "src/data_sources/historical_edge_validation/edge_validator.py",
        "patch_stage": "edge_validation",
        "priority": 7,
        "dimensions": ["regime", "asset_behavior", "option_behavior", "strategy", "symbol", "horizon"],
        "fields": list(DEFAULT_MATRIX_CELL_KEY_FIELDS),
        "action": "group_or_preserve_edge_records_by_matrix_metadata",
        "description": "Preserve matrix metadata on edge records and block exact cell promotion when required metadata is missing.",
    },
    {
        "target_id": "historical_edge_multi_window_summary",
        "target_type": "edge_summary_consumer",
        "module_path": "src/data_sources/historical_edge_validation/multi_window_summary.py",
        "patch_stage": "edge_summary",
        "priority": 8,
        "dimensions": ["strategy", "symbol", "horizon"],
        "fields": ["strategy_id", "strategy_family", "symbol", "horizon_days"],
        "action": "summarize_matrix_metadata_coverage_by_window",
        "description": "Report matrix metadata coverage by window/horizon without promoting incomplete records to exact matrix cells.",
    },
    {
        "target_id": "historical_edge_diagnostics",
        "target_type": "edge_diagnostics_consumer",
        "module_path": "src/data_sources/historical_edge_validation/edge_diagnostics.py",
        "patch_stage": "edge_diagnostics",
        "priority": 9,
        "dimensions": ["regime", "asset_behavior", "option_behavior", "strategy", "symbol", "horizon"],
        "fields": list(DEFAULT_MATRIX_CELL_KEY_FIELDS),
        "action": "diagnose_missing_matrix_metadata_by_dimension",
        "description": "Add diagnostics explaining which dimensions prevent exact matrix-cell edge validation.",
    },
    {
        "target_id": "portfolio_candidate_selection_summary",
        "target_type": "portfolio_summary_consumer",
        "module_path": "src/data_sources/portfolio_equity_reconstruction/candidate_selection_summary.py",
        "patch_stage": "portfolio_candidate_summary",
        "priority": 10,
        "dimensions": ["strategy", "symbol", "horizon"],
        "fields": ["strategy_id", "strategy_family", "symbol", "horizon_days"],
        "action": "preserve_selected_candidate_matrix_metadata",
        "description": "Preserve matrix metadata on selected portfolio candidates so paper-trading fixtures remain downstream from the matrix.",
    },
]


def build_signalforge_historical_replay_export_matrix_metadata_patch_plan(
    *,
    historical_replay_export_matrix_metadata_envelope_source: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a concrete patch plan from the matrix metadata envelope."""

    envelope = _extract_envelope(historical_replay_export_matrix_metadata_envelope_source)
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if not envelope:
        blocked_reasons.append("historical_replay_export_matrix_metadata_envelope_source_required")

    envelope_state = str(envelope.get("envelope_state") or envelope.get("status") or "unknown")
    if envelope and envelope_state != "ready":
        blocked_reasons.append("historical_replay_export_matrix_metadata_envelope_not_ready")

    matrix_cell_key_fields = _as_text_list(
        envelope.get("matrix_cell_key_fields") or DEFAULT_MATRIX_CELL_KEY_FIELDS
    )
    if not matrix_cell_key_fields:
        blocked_reasons.append("matrix_cell_key_fields_required")

    source_patch_required = bool(envelope.get("source_patch_required"))
    ready_to_patch_historical_replay_exports = bool(
        envelope.get("ready_to_patch_historical_replay_exports")
    )
    if not source_patch_required:
        warnings.append("historical_replay_exports_do_not_require_source_patch")
    if source_patch_required and not ready_to_patch_historical_replay_exports:
        blocked_reasons.append("historical_replay_exports_not_ready_to_patch")

    required_missing_dimensions = _ordered_unique(
        _as_text_list(envelope.get("required_missing_dimensions"))
    )
    required_partial_dimensions = _ordered_unique(
        _as_text_list(envelope.get("required_partial_dimensions"))
    )
    missing_counts = _as_int_mapping(envelope.get("missing_required_dimension_counts"))
    mapped_counts = _as_int_mapping(envelope.get("mapped_required_dimension_counts"))
    required_fields = _required_field_names_from_envelope(envelope, matrix_cell_key_fields)
    field_stamping_requirements = _field_stamping_requirements_from_envelope(
        envelope, required_fields
    )
    producer_patch_requirements = _producer_patch_requirements_from_envelope(
        envelope, field_stamping_requirements
    )
    patch_targets = _build_patch_targets(
        matrix_cell_key_fields=matrix_cell_key_fields,
        required_missing_dimensions=required_missing_dimensions,
        required_partial_dimensions=required_partial_dimensions,
        missing_counts=missing_counts,
        mapped_counts=mapped_counts,
        field_stamping_requirements=field_stamping_requirements,
        producer_patch_requirements=producer_patch_requirements,
    )
    patch_sequence = _build_patch_sequence(patch_targets)
    validation_checklist = _build_validation_checklist(matrix_cell_key_fields)

    if source_patch_required and not patch_targets:
        blocked_reasons.append("patch_targets_required_when_source_patch_required")

    if source_patch_required:
        warnings.append("historical_replay_export_producers_require_matrix_metadata_patch")
    for dimension in required_missing_dimensions:
        warnings.append(f"patch_plan_required_dimension:{dimension}")
    for dimension in required_partial_dimensions:
        warnings.append(f"patch_plan_normalization_dimension:{dimension}")

    status = "blocked" if blocked_reasons else "ready"
    patch_plan_state = status
    ready_to_apply_patches = status == "ready" and source_patch_required and bool(patch_targets)
    ready_to_build_exact_matrix_edge_summary = False

    result = {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "operation_type": "signalforge_historical_replay_export_matrix_metadata_patch_plan_builder",
        "patch_plan_id": _stable_id(
            envelope.get("envelope_id"), matrix_cell_key_fields, required_missing_dimensions, patch_targets
        ),
        "patch_plan_state": patch_plan_state,
        "status": status,
        "is_ready": status == "ready",
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "recommended_next_step": (
            RECOMMENDED_NEXT_WHEN_READY if status == "ready" else RECOMMENDED_NEXT_WHEN_BLOCKED
        ),
        "envelope_state": envelope_state,
        "envelope_id": str(envelope.get("envelope_id") or "unknown"),
        "source_patch_required": source_patch_required,
        "ready_to_patch_historical_replay_exports": ready_to_patch_historical_replay_exports,
        "ready_to_apply_patches": ready_to_apply_patches,
        "ready_to_build_exact_matrix_edge_summary": ready_to_build_exact_matrix_edge_summary,
        "matrix_metadata_envelope_key": str(envelope.get("matrix_metadata_envelope_key") or "matrix_metadata"),
        "matrix_cell_key_fields": matrix_cell_key_fields,
        "required_fields": required_fields,
        "required_field_count": len(required_fields),
        "required_missing_dimensions": required_missing_dimensions,
        "required_partial_dimensions": required_partial_dimensions,
        "missing_required_dimension_counts": missing_counts,
        "mapped_required_dimension_counts": mapped_counts,
        "total_source_record_count": _as_int(envelope.get("total_source_record_count"), default=0),
        "records_requiring_mapping_count": _as_int(envelope.get("records_requiring_mapping_count"), default=0),
        "exact_matrix_cell_ready_record_count": _as_int(
            envelope.get("exact_matrix_cell_ready_record_count"), default=0
        ),
        "field_stamping_requirements": field_stamping_requirements,
        "field_stamping_requirement_count": len(field_stamping_requirements),
        "producer_patch_requirements": producer_patch_requirements,
        "producer_patch_requirement_count": len(producer_patch_requirements),
        "patch_targets": patch_targets,
        "patch_target_count": len(patch_targets),
        "required_patch_target_count": len([target for target in patch_targets if target.get("required")]),
        "patch_sequence": patch_sequence,
        "patch_sequence_step_count": len(patch_sequence),
        "validation_checklist": validation_checklist,
        "validation_check_count": len(validation_checklist),
        "blocked_reasons": _ordered_unique(blocked_reasons),
        "warnings": _ordered_unique(warnings),
        "automatic_action": None,
        "automatic_strategy_change": None,
        "order_intent": None,
        "requires_manual_approval": True,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
    result["patch_plan_summary"] = build_historical_replay_export_matrix_metadata_patch_plan_summary(result)
    return result


def build_historical_replay_export_matrix_metadata_patch_plan_summary(
    result: Mapping[str, Any]
) -> dict[str, Any]:
    """Build a compact summary for the patch plan artifact."""

    return {
        "artifact_type": "signalforge_historical_replay_export_matrix_metadata_patch_plan_summary",
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "patch_plan_state": str(result.get("patch_plan_state") or "blocked"),
        "status": str(result.get("status") or result.get("patch_plan_state") or "blocked"),
        "is_ready": bool(result.get("is_ready")),
        "recommended_next_step": str(result.get("recommended_next_step") or "unknown"),
        "envelope_state": str(result.get("envelope_state") or "unknown"),
        "envelope_id": str(result.get("envelope_id") or "unknown"),
        "source_patch_required": bool(result.get("source_patch_required")),
        "ready_to_patch_historical_replay_exports": bool(result.get("ready_to_patch_historical_replay_exports")),
        "ready_to_apply_patches": bool(result.get("ready_to_apply_patches")),
        "ready_to_build_exact_matrix_edge_summary": bool(result.get("ready_to_build_exact_matrix_edge_summary")),
        "matrix_metadata_envelope_key": str(result.get("matrix_metadata_envelope_key") or "matrix_metadata"),
        "matrix_cell_key_fields": _as_text_list(result.get("matrix_cell_key_fields")),
        "required_field_count": _as_int(result.get("required_field_count"), default=0),
        "required_missing_dimensions": _as_text_list(result.get("required_missing_dimensions")),
        "required_partial_dimensions": _as_text_list(result.get("required_partial_dimensions")),
        "missing_required_dimension_counts": _as_int_mapping(result.get("missing_required_dimension_counts")),
        "mapped_required_dimension_counts": _as_int_mapping(result.get("mapped_required_dimension_counts")),
        "total_source_record_count": _as_int(result.get("total_source_record_count"), default=0),
        "records_requiring_mapping_count": _as_int(result.get("records_requiring_mapping_count"), default=0),
        "exact_matrix_cell_ready_record_count": _as_int(result.get("exact_matrix_cell_ready_record_count"), default=0),
        "field_stamping_requirement_count": _as_int(result.get("field_stamping_requirement_count"), default=0),
        "producer_patch_requirement_count": _as_int(result.get("producer_patch_requirement_count"), default=0),
        "patch_target_count": _as_int(result.get("patch_target_count"), default=0),
        "required_patch_target_count": _as_int(result.get("required_patch_target_count"), default=0),
        "patch_sequence_step_count": _as_int(result.get("patch_sequence_step_count"), default=0),
        "validation_check_count": _as_int(result.get("validation_check_count"), default=0),
        "blocked_reasons": _as_text_list(result.get("blocked_reasons")),
        "warnings": _as_text_list(result.get("warnings")),
        "explicit_exclusions": _as_text_list(result.get("explicit_exclusions")),
        "order_intent": result.get("order_intent"),
        "automatic_action": result.get("automatic_action"),
        "automatic_strategy_change": result.get("automatic_strategy_change"),
        "requires_manual_approval": bool(result.get("requires_manual_approval", True)),
    }


def _extract_envelope(source: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {}
    if source.get("artifact_type") == ARTIFACT_TYPE:
        return dict(source)
    if source.get("artifact_type") == "signalforge_historical_replay_export_matrix_metadata_envelope":
        return dict(source)
    for key in ("envelope", "matrix_metadata_envelope", "result"):
        value = source.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    if source.get("envelope_state") or source.get("matrix_cell_key_fields"):
        return dict(source)
    return {}


def _required_field_names_from_envelope(
    envelope: Mapping[str, Any], matrix_cell_key_fields: Sequence[str]
) -> list[str]:
    names: list[str] = []
    for field in envelope.get("required_fields") or []:
        if isinstance(field, Mapping):
            name = str(field.get("field_name") or "").strip()
            if name:
                names.append(name)
        elif field is not None:
            names.append(str(field).strip())
    return _ordered_unique(names or list(matrix_cell_key_fields))


def _field_stamping_requirements_from_envelope(
    envelope: Mapping[str, Any], required_fields: Sequence[str]
) -> list[dict[str, Any]]:
    requirements = []
    source_requirements = envelope.get("field_stamping_requirements")
    if isinstance(source_requirements, Sequence) and not isinstance(source_requirements, (str, bytes, bytearray)):
        for item in source_requirements:
            if isinstance(item, Mapping):
                requirements.append(dict(item))
    if requirements:
        return requirements

    for field_name in required_fields:
        requirements.append(
            {
                "field_name": field_name,
                "dimension": FIELD_TO_DIMENSION.get(field_name, "unknown"),
                "required": True,
                "source_requirement": f"Stamp {field_name} into the matrix_metadata envelope.",
                "source_artifact_candidates": [],
                "join_keys": [],
                "blocks_exact_matrix_edge_summary": True,
            }
        )
    return requirements


def _producer_patch_requirements_from_envelope(
    envelope: Mapping[str, Any], field_requirements: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    requirements = []
    source_requirements = envelope.get("producer_patch_requirements")
    if isinstance(source_requirements, Sequence) and not isinstance(source_requirements, (str, bytes, bytearray)):
        for item in source_requirements:
            if isinstance(item, Mapping):
                requirements.append(dict(item))
    if requirements:
        return requirements

    for item in field_requirements:
        field_name = str(item.get("field_name") or "")
        if not field_name:
            continue
        requirements.append(
            {
                "field_name": field_name,
                "dimension": str(item.get("dimension") or FIELD_TO_DIMENSION.get(field_name, "unknown")),
                "producer_patch_required": bool(item.get("required", True)),
                "source_artifact_candidates": _as_text_list(item.get("source_artifact_candidates")),
                "join_keys": _as_text_list(item.get("join_keys")),
            }
        )
    return requirements


def _build_patch_targets(
    *,
    matrix_cell_key_fields: Sequence[str],
    required_missing_dimensions: Sequence[str],
    required_partial_dimensions: Sequence[str],
    missing_counts: Mapping[str, int],
    mapped_counts: Mapping[str, int],
    field_stamping_requirements: Sequence[Mapping[str, Any]],
    producer_patch_requirements: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    missing_dimensions = set(required_missing_dimensions)
    partial_dimensions = set(required_partial_dimensions)
    required_dimensions = missing_dimensions | partial_dimensions
    required_fields_by_dimension: dict[str, list[str]] = {}
    for field_name in matrix_cell_key_fields:
        dimension = FIELD_TO_DIMENSION.get(str(field_name), "unknown")
        required_fields_by_dimension.setdefault(dimension, []).append(str(field_name))

    source_artifacts_by_dimension: dict[str, list[str]] = {}
    for requirement in [*field_stamping_requirements, *producer_patch_requirements]:
        dimension = str(requirement.get("dimension") or "unknown")
        source_artifacts_by_dimension.setdefault(dimension, [])
        source_artifacts_by_dimension[dimension].extend(
            _as_text_list(requirement.get("source_artifact_candidates"))
        )

    targets = []
    for raw_target in DEFAULT_PATCH_TARGETS:
        target = dict(raw_target)
        dimensions = _as_text_list(target.get("dimensions"))
        fields = _as_text_list(target.get("fields")) or [
            field for dimension in dimensions for field in required_fields_by_dimension.get(dimension, [])
        ]
        covered_dimensions = set(dimensions)
        target_required = (
            target.get("target_type") == "new_helper"
            or not required_dimensions
            or bool(covered_dimensions & required_dimensions)
            or bool(set(fields) & set(matrix_cell_key_fields))
        )
        if target.get("target_type") == "source_dimension_provider" and not (covered_dimensions & required_dimensions):
            target_required = False

        target["required"] = bool(target_required)
        target["dimensions"] = dimensions
        target["fields"] = fields
        target["currently_missing_record_count"] = sum(_as_int(missing_counts.get(dim), default=0) for dim in dimensions)
        target["currently_mapped_record_count"] = sum(_as_int(mapped_counts.get(dim), default=0) for dim in dimensions)
        target["source_artifact_candidates"] = _ordered_unique(
            candidate for dimension in dimensions for candidate in source_artifacts_by_dimension.get(dimension, [])
        )
        target["blocks_exact_matrix_edge_summary"] = bool(target_required)
        targets.append(target)

    return sorted(targets, key=lambda item: (int(item.get("priority", 999)), str(item.get("target_id"))))


def _build_patch_sequence(patch_targets: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    required_targets = [target for target in patch_targets if bool(target.get("required"))]
    sequence = []
    for index, target in enumerate(required_targets, start=1):
        sequence.append(
            {
                "step": index,
                "target_id": str(target.get("target_id") or "unknown"),
                "module_path": str(target.get("module_path") or "unknown"),
                "patch_stage": str(target.get("patch_stage") or "unknown"),
                "action": str(target.get("action") or "patch_required"),
                "fields": _as_text_list(target.get("fields")),
                "dimensions": _as_text_list(target.get("dimensions")),
            }
        )
    return sequence


def _build_validation_checklist(matrix_cell_key_fields: Sequence[str]) -> list[dict[str, Any]]:
    return [
        {
            "check_id": "stamp_matrix_metadata_top_level_fields",
            "description": "Every replay outcome includes matrix_metadata, matrix_metadata_state, matrix_metadata_missing_fields, and matrix_metadata_source_refs.",
            "required": True,
        },
        {
            "check_id": "no_exact_cell_promotion_with_missing_fields",
            "description": "Records missing any matrix-cell key field remain needs_review and cannot be counted as exact matrix-cell edge evidence.",
            "required": True,
        },
        {
            "check_id": "matrix_cell_key_fields_present",
            "description": "Required matrix-cell key fields are populated before exact matrix edge summary is allowed.",
            "required": True,
            "fields": list(matrix_cell_key_fields),
        },
        {
            "check_id": "source_refs_preserved",
            "description": "Each populated matrix metadata field includes a source reference explaining where the value came from.",
            "required": True,
        },
        {
            "check_id": "regression_blocks_broker_and_order_side_effects",
            "description": "Patch introduces no broker calls, order routing, order submission, fills, live execution, or slippage modeling.",
            "required": True,
        },
    ]


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


def _as_int_mapping(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _as_int(raw_value, default=0) for key, raw_value in value.items()}


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
    return f"historical_replay_export_matrix_metadata_patch_plan_{sha256(payload).hexdigest()[:16]}"
