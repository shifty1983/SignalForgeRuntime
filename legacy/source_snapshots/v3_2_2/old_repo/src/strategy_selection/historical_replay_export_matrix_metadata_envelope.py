"""Historical replay export matrix metadata envelope.

This module defines the source-facing metadata envelope that historical replay
exports must stamp onto every replay outcome before SignalForge can attribute
edge to exact strategy-matrix cells.

It intentionally does not infer missing matrix dimensions, mutate historical
records, score strategies, select candidates, connect to brokers, request
quotes, route orders, submit orders, or alter strategy availability rules.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "signalforge_historical_replay_export_matrix_metadata_envelope.v1"
SUMMARY_SCHEMA_VERSION = "signalforge_historical_replay_export_matrix_metadata_envelope_summary.v1"
ARTIFACT_TYPE = "signalforge_historical_replay_export_matrix_metadata_envelope"

RECOMMENDED_NEXT_WHEN_READY = "historical_replay_export_matrix_metadata_patch_plan"
RECOMMENDED_NEXT_WHEN_BLOCKED = "resolve_historical_replay_export_matrix_metadata_envelope_blockers"

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

FIELD_SOURCE_STAMPING_GUIDANCE = {
    "regime_state": {
        "source_requirement": "Stamp the regime classification active at the historical replay decision timestamp.",
        "source_artifact_candidates": [
            "regime_decision_export",
            "historical_regime_snapshot",
            "regime_asset_options_alignment",
        ],
        "join_keys": ["decision_timestamp", "window_start", "window_end"],
    },
    "asset_behavior_state": {
        "source_requirement": "Stamp the asset behavior classification for the underlying at the decision timestamp.",
        "source_artifact_candidates": [
            "asset_behavior_decision_export",
            "historical_asset_behavior_export",
            "regime_asset_options_alignment",
        ],
        "join_keys": ["symbol", "decision_timestamp", "window_start", "window_end"],
    },
    "option_behavior_state": {
        "source_requirement": "Stamp the option behavior classification for the option chain at the decision timestamp.",
        "source_artifact_candidates": [
            "option_behavior_decision_export",
            "historical_option_behavior_export",
            "regime_asset_options_alignment",
        ],
        "join_keys": ["symbol", "expiration", "decision_timestamp", "window_start", "window_end"],
    },
    "strategy_id": {
        "source_requirement": "Stamp the exact strategy-matrix strategy identifier used to create the replay outcome.",
        "source_artifact_candidates": [
            "strategy_family_eligibility",
            "options_strategy_catalog",
            "options_strategy_setup_matcher",
            "candidate_selection_review",
        ],
        "join_keys": ["strategy_id", "strategy_family", "symbol", "decision_timestamp"],
    },
    "strategy_family": {
        "source_requirement": "Stamp the exact strategy family used to create the replay outcome.",
        "source_artifact_candidates": [
            "strategy_family_eligibility",
            "options_strategy_catalog",
            "options_strategy_setup_matcher",
            "candidate_selection_review",
        ],
        "join_keys": ["strategy_id", "strategy_family", "symbol", "decision_timestamp"],
    },
    "symbol": {
        "source_requirement": "Stamp the normalized underlying symbol on every replay outcome.",
        "source_artifact_candidates": [
            "quantconnect_replay_window_plan",
            "historical_replay_candidate_export",
            "contract_outcome_snapshot",
        ],
        "join_keys": ["symbol", "underlying_symbol", "ticker"],
    },
    "horizon_days": {
        "source_requirement": "Stamp normalized integer horizon_days on every replay outcome.",
        "source_artifact_candidates": [
            "quantconnect_replay_window_plan",
            "historical_edge_validation_multi_window_summary",
            "portfolio_candidate_selection_summary",
        ],
        "join_keys": ["horizon", "window_days", "selected_window_days", "target_horizon_days"],
    },
}


def build_signalforge_historical_replay_export_matrix_metadata_envelope(
    *,
    historical_replay_matrix_metadata_contract_source: Mapping[str, Any],
    historical_replay_source_metadata_backfill_source: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the historical replay export matrix metadata envelope specification."""

    contract = _extract_contract(historical_replay_matrix_metadata_contract_source)
    source_backfill_summary = _extract_summary(historical_replay_source_metadata_backfill_source)

    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if not contract:
        blocked_reasons.append("historical_replay_matrix_metadata_contract_source_required")
    contract_state = str(contract.get("contract_state") or contract.get("status") or "unknown")
    if contract and contract_state != "ready":
        blocked_reasons.append("historical_replay_matrix_metadata_contract_not_ready")

    if not source_backfill_summary:
        blocked_reasons.append("historical_replay_source_metadata_backfill_source_required")

    source_metadata_backfill_state = str(
        source_backfill_summary.get("source_metadata_backfill_state")
        or source_backfill_summary.get("status")
        or "unknown"
    )

    matrix_cell_key_fields = _as_text_list(
        contract.get("matrix_cell_key_fields")
        or source_backfill_summary.get("matrix_cell_key_fields")
        or DEFAULT_MATRIX_CELL_KEY_FIELDS
    )
    if not matrix_cell_key_fields:
        blocked_reasons.append("matrix_cell_key_fields_required")

    required_fields = _required_fields_from_contract(contract, matrix_cell_key_fields)
    optional_fields = _optional_fields_from_contract(contract)
    required_missing_dimensions = _ordered_unique(
        _as_text_list(source_backfill_summary.get("required_missing_dimensions"))
    )
    required_partial_dimensions = _ordered_unique(
        _as_text_list(source_backfill_summary.get("required_partial_dimensions"))
    )
    missing_counts = _as_int_mapping(source_backfill_summary.get("missing_required_dimension_counts"))
    mapped_counts = _as_int_mapping(source_backfill_summary.get("mapped_required_dimension_counts"))

    total_source_record_count = _as_int(source_backfill_summary.get("total_source_record_count"), default=0)
    records_requiring_mapping_count = _as_int(
        source_backfill_summary.get("records_requiring_mapping_count"), default=0
    )
    exact_matrix_cell_ready_record_count = _as_int(
        source_backfill_summary.get("exact_matrix_cell_ready_record_count"), default=0
    )
    source_backfill_task_count = _as_int(
        source_backfill_summary.get("source_backfill_task_count"), default=0
    )
    required_source_backfill_task_count = _as_int(
        source_backfill_summary.get("required_source_backfill_task_count"), default=0
    )

    source_patch_required = bool(
        required_missing_dimensions
        or required_partial_dimensions
        or records_requiring_mapping_count > 0
        or source_backfill_task_count > 0
    )

    if source_patch_required:
        warnings.append("historical_replay_exports_must_stamp_matrix_metadata_envelope")
    if exact_matrix_cell_ready_record_count == 0:
        warnings.append("exact_matrix_edge_summary_blocked_until_envelope_is_populated")
    if "strategy_id" in matrix_cell_key_fields and "strategy_family" in matrix_cell_key_fields:
        warnings.append("strategy_dimension_requires_exact_strategy_id_and_strategy_family")
    for dimension in required_missing_dimensions:
        warnings.append(f"envelope_source_backfill_required_dimension:{dimension}")
    for dimension in required_partial_dimensions:
        warnings.append(f"envelope_source_normalization_required_dimension:{dimension}")

    envelope_schema = _build_envelope_schema(
        matrix_cell_key_fields=matrix_cell_key_fields,
        required_fields=required_fields,
        optional_fields=optional_fields,
    )
    blank_envelope_template = _build_blank_envelope_template(
        matrix_cell_key_fields=matrix_cell_key_fields,
        optional_fields=optional_fields,
    )
    field_stamping_requirements = _build_field_stamping_requirements(
        matrix_cell_key_fields=matrix_cell_key_fields,
        required_fields=required_fields,
        optional_fields=optional_fields,
        missing_counts=missing_counts,
        mapped_counts=mapped_counts,
    )
    producer_patch_requirements = _build_producer_patch_requirements(field_stamping_requirements)
    validation_rules = _build_validation_rules(matrix_cell_key_fields)

    if blocked_reasons:
        envelope_state = "blocked"
        status = "blocked"
    else:
        envelope_state = "ready"
        status = "ready"

    ready_to_patch_historical_replay_exports = status == "ready" and source_patch_required
    ready_to_build_exact_matrix_edge_summary = (
        status == "ready"
        and not source_patch_required
        and exact_matrix_cell_ready_record_count > 0
        and records_requiring_mapping_count == 0
    )

    result = {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "operation_type": "signalforge_historical_replay_export_matrix_metadata_envelope_builder",
        "envelope_id": _stable_id(
            contract.get("contract_id"),
            source_backfill_summary.get("source_metadata_backfill_id"),
            matrix_cell_key_fields,
        ),
        "envelope_state": envelope_state,
        "status": status,
        "is_ready": status == "ready",
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "matrix_metadata_envelope_key": "matrix_metadata",
        "matrix_metadata_state_field": "matrix_metadata_state",
        "matrix_metadata_missing_fields_field": "matrix_metadata_missing_fields",
        "matrix_metadata_source_refs_field": "matrix_metadata_source_refs",
        "matrix_cell_key_fields": matrix_cell_key_fields,
        "required_fields": required_fields,
        "optional_fields": optional_fields,
        "required_field_count": len(required_fields),
        "optional_field_count": len(optional_fields),
        "envelope_schema": envelope_schema,
        "blank_envelope_template": blank_envelope_template,
        "field_stamping_requirements": field_stamping_requirements,
        "producer_patch_requirements": producer_patch_requirements,
        "producer_patch_requirement_count": len(producer_patch_requirements),
        "validation_rules": validation_rules,
        "validation_rule_count": len(validation_rules),
        "source_patch_required": source_patch_required,
        "ready_to_patch_historical_replay_exports": ready_to_patch_historical_replay_exports,
        "ready_to_build_exact_matrix_edge_summary": ready_to_build_exact_matrix_edge_summary,
        "recommended_next_step": (
            RECOMMENDED_NEXT_WHEN_READY if status == "ready" else RECOMMENDED_NEXT_WHEN_BLOCKED
        ),
        "contract_state": contract_state,
        "contract_id": str(contract.get("contract_id") or "unknown"),
        "source_metadata_backfill_state": source_metadata_backfill_state,
        "total_source_record_count": total_source_record_count,
        "records_requiring_mapping_count": records_requiring_mapping_count,
        "exact_matrix_cell_ready_record_count": exact_matrix_cell_ready_record_count,
        "source_backfill_task_count": source_backfill_task_count,
        "required_source_backfill_task_count": required_source_backfill_task_count,
        "required_missing_dimensions": required_missing_dimensions,
        "required_partial_dimensions": required_partial_dimensions,
        "missing_required_dimension_counts": missing_counts,
        "mapped_required_dimension_counts": mapped_counts,
        "blocked_reasons": _ordered_unique(blocked_reasons),
        "warnings": _ordered_unique(warnings),
        "automatic_action": None,
        "automatic_strategy_change": None,
        "order_intent": None,
        "requires_manual_approval": True,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
    result["envelope_summary"] = build_historical_replay_export_matrix_metadata_envelope_summary(result)
    return result


def build_historical_replay_export_matrix_metadata_envelope_summary(
    result: Mapping[str, Any]
) -> dict[str, Any]:
    """Build a compact summary for the envelope artifact."""

    return {
        "artifact_type": "signalforge_historical_replay_export_matrix_metadata_envelope_summary",
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "envelope_state": str(result.get("envelope_state") or "blocked"),
        "status": str(result.get("status") or result.get("envelope_state") or "blocked"),
        "is_ready": bool(result.get("is_ready")),
        "recommended_next_step": str(result.get("recommended_next_step") or "unknown"),
        "matrix_metadata_envelope_key": str(result.get("matrix_metadata_envelope_key") or "matrix_metadata"),
        "matrix_cell_key_fields": _as_text_list(result.get("matrix_cell_key_fields")),
        "required_field_count": _as_int(result.get("required_field_count"), default=0),
        "optional_field_count": _as_int(result.get("optional_field_count"), default=0),
        "producer_patch_requirement_count": _as_int(
            result.get("producer_patch_requirement_count"), default=0
        ),
        "validation_rule_count": _as_int(result.get("validation_rule_count"), default=0),
        "source_patch_required": bool(result.get("source_patch_required")),
        "ready_to_patch_historical_replay_exports": bool(
            result.get("ready_to_patch_historical_replay_exports")
        ),
        "ready_to_build_exact_matrix_edge_summary": bool(
            result.get("ready_to_build_exact_matrix_edge_summary")
        ),
        "contract_state": str(result.get("contract_state") or "unknown"),
        "contract_id": str(result.get("contract_id") or "unknown"),
        "source_metadata_backfill_state": str(result.get("source_metadata_backfill_state") or "unknown"),
        "total_source_record_count": _as_int(result.get("total_source_record_count"), default=0),
        "records_requiring_mapping_count": _as_int(result.get("records_requiring_mapping_count"), default=0),
        "exact_matrix_cell_ready_record_count": _as_int(
            result.get("exact_matrix_cell_ready_record_count"), default=0
        ),
        "source_backfill_task_count": _as_int(result.get("source_backfill_task_count"), default=0),
        "required_source_backfill_task_count": _as_int(
            result.get("required_source_backfill_task_count"), default=0
        ),
        "required_missing_dimensions": _as_text_list(result.get("required_missing_dimensions")),
        "required_partial_dimensions": _as_text_list(result.get("required_partial_dimensions")),
        "missing_required_dimension_counts": _as_int_mapping(
            result.get("missing_required_dimension_counts")
        ),
        "mapped_required_dimension_counts": _as_int_mapping(
            result.get("mapped_required_dimension_counts")
        ),
        "blocked_reasons": _as_text_list(result.get("blocked_reasons")),
        "warnings": _as_text_list(result.get("warnings")),
        "explicit_exclusions": _as_text_list(result.get("explicit_exclusions")),
        "order_intent": result.get("order_intent"),
        "automatic_action": result.get("automatic_action"),
        "automatic_strategy_change": result.get("automatic_strategy_change"),
        "requires_manual_approval": bool(result.get("requires_manual_approval", True)),
    }


def _extract_contract(source: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {}
    if source.get("artifact_type") == "signalforge_historical_replay_matrix_metadata_contract":
        return dict(source)
    nested = source.get("contract") or source.get("metadata_contract") or source.get("result")
    if isinstance(nested, Mapping):
        return dict(nested)
    if source.get("contract_state") == "ready" or source.get("matrix_cell_key_fields"):
        return dict(source)
    return {}


def _extract_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {}
    for key in (
        "source_metadata_backfill_summary",
        "envelope_summary",
        "summary",
        "result",
    ):
        value = source.get(key)
        if isinstance(value, Mapping):
            merged = dict(source)
            merged.update(dict(value))
            return merged
    if source.get("source_metadata_backfill_state") or source.get("required_missing_dimensions"):
        return dict(source)
    return {}


def _required_fields_from_contract(
    contract: Mapping[str, Any], matrix_cell_key_fields: Sequence[str]
) -> list[dict[str, Any]]:
    fields = contract.get("required_fields")
    if isinstance(fields, Sequence) and not isinstance(fields, (str, bytes, bytearray)):
        parsed = [dict(field) for field in fields if isinstance(field, Mapping)]
        if parsed:
            return parsed

    result = []
    for field_name in matrix_cell_key_fields:
        result.append(
            {
                "field_name": str(field_name),
                "dimension": FIELD_TO_DIMENSION.get(str(field_name), "unknown"),
                "required": True,
                "missing_policy": "block_exact_matrix_cell_mapping",
            }
        )
    return result


def _optional_fields_from_contract(contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    fields = contract.get("optional_fields")
    if isinstance(fields, Sequence) and not isinstance(fields, (str, bytes, bytearray)):
        return [dict(field) for field in fields if isinstance(field, Mapping)]
    return []


def _build_envelope_schema(
    *,
    matrix_cell_key_fields: Sequence[str],
    required_fields: Sequence[Mapping[str, Any]],
    optional_fields: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for field in [*required_fields, *optional_fields]:
        field_name = str(field.get("field_name") or "")
        if not field_name:
            continue
        properties[field_name] = {
            "type": str(field.get("type") or _default_json_type(field_name)),
            "dimension": str(field.get("dimension") or FIELD_TO_DIMENSION.get(field_name, "unknown")),
            "required": bool(field.get("required", field_name in matrix_cell_key_fields)),
            "missing_policy": str(
                field.get("missing_policy")
                or ("block_exact_matrix_cell_mapping" if field_name in matrix_cell_key_fields else "allow_cell_mapping_with_warning")
            ),
        }

    return {
        "type": "object",
        "required_top_level_fields": [
            "matrix_metadata",
            "matrix_metadata_state",
            "matrix_metadata_missing_fields",
            "matrix_metadata_source_refs",
        ],
        "matrix_metadata": {
            "type": "object",
            "required_fields": list(matrix_cell_key_fields),
            "properties": properties,
        },
    }


def _build_blank_envelope_template(
    *,
    matrix_cell_key_fields: Sequence[str],
    optional_fields: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    matrix_metadata: dict[str, Any] = {field: None for field in matrix_cell_key_fields}
    for field in optional_fields:
        field_name = str(field.get("field_name") or "")
        if field_name and field_name not in matrix_metadata:
            matrix_metadata[field_name] = None

    return {
        "matrix_metadata": matrix_metadata,
        "matrix_metadata_state": "needs_review",
        "matrix_metadata_missing_fields": list(matrix_cell_key_fields),
        "matrix_metadata_source_refs": {},
    }


def _build_field_stamping_requirements(
    *,
    matrix_cell_key_fields: Sequence[str],
    required_fields: Sequence[Mapping[str, Any]],
    optional_fields: Sequence[Mapping[str, Any]],
    missing_counts: Mapping[str, int],
    mapped_counts: Mapping[str, int],
) -> list[dict[str, Any]]:
    field_definitions = {str(field.get("field_name")): dict(field) for field in [*required_fields, *optional_fields]}
    requirements: list[dict[str, Any]] = []
    all_field_names = _ordered_unique([*matrix_cell_key_fields, *field_definitions.keys()])

    for field_name in all_field_names:
        if not field_name:
            continue
        definition = field_definitions.get(field_name, {})
        dimension = str(definition.get("dimension") or FIELD_TO_DIMENSION.get(field_name, "unknown"))
        guidance = FIELD_SOURCE_STAMPING_GUIDANCE.get(field_name, {})
        required = bool(definition.get("required", field_name in matrix_cell_key_fields))
        requirements.append(
            {
                "field_name": field_name,
                "dimension": dimension,
                "required": required,
                "source_requirement": str(
                    guidance.get("source_requirement")
                    or f"Stamp {field_name} into the matrix_metadata envelope."
                ),
                "source_artifact_candidates": _as_text_list(guidance.get("source_artifact_candidates")),
                "join_keys": _as_text_list(guidance.get("join_keys")),
                "currently_missing_record_count": _as_int(missing_counts.get(dimension), default=0),
                "currently_mapped_record_count": _as_int(mapped_counts.get(dimension), default=0),
                "blocks_exact_matrix_edge_summary": required,
            }
        )

    return requirements


def _build_producer_patch_requirements(
    field_stamping_requirements: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for requirement in field_stamping_requirements:
        dimension = str(requirement.get("dimension") or "unknown")
        if not dimension:
            continue
        entry = grouped.setdefault(
            dimension,
            {
                "dimension": dimension,
                "required_fields": [],
                "optional_fields": [],
                "source_artifact_candidates": [],
                "join_keys": [],
                "producer_action": f"stamp_{dimension}_metadata_into_historical_replay_outcomes",
                "blocks_exact_matrix_edge_summary": False,
            },
        )
        field_name = str(requirement.get("field_name") or "")
        if not field_name:
            continue
        if bool(requirement.get("required")):
            entry["required_fields"].append(field_name)
            entry["blocks_exact_matrix_edge_summary"] = True
        else:
            entry["optional_fields"].append(field_name)
        entry["source_artifact_candidates"].extend(_as_text_list(requirement.get("source_artifact_candidates")))
        entry["join_keys"].extend(_as_text_list(requirement.get("join_keys")))

    result = []
    for dimension in sorted(grouped):
        entry = grouped[dimension]
        entry["required_fields"] = _ordered_unique(entry["required_fields"])
        entry["optional_fields"] = _ordered_unique(entry["optional_fields"])
        entry["source_artifact_candidates"] = _ordered_unique(entry["source_artifact_candidates"])
        entry["join_keys"] = _ordered_unique(entry["join_keys"])
        result.append(entry)
    return result


def _build_validation_rules(matrix_cell_key_fields: Sequence[str]) -> list[dict[str, Any]]:
    rules = [
        {
            "rule_id": "matrix_metadata_envelope_required",
            "description": "Every replay outcome must include a matrix_metadata object.",
            "severity": "block_exact_matrix_cell_mapping",
        },
        {
            "rule_id": "matrix_metadata_state_required",
            "description": "Every replay outcome must include matrix_metadata_state.",
            "severity": "block_exact_matrix_cell_mapping",
        },
        {
            "rule_id": "missing_required_fields_block_ready_state",
            "description": "matrix_metadata_state cannot be ready while required matrix fields are missing.",
            "severity": "block_exact_matrix_cell_mapping",
        },
    ]
    for field_name in matrix_cell_key_fields:
        rules.append(
            {
                "rule_id": f"required_field_present:{field_name}",
                "field_name": field_name,
                "description": f"matrix_metadata.{field_name} must be source-stamped and non-empty.",
                "severity": "block_exact_matrix_cell_mapping",
            }
        )
    return rules


def _default_json_type(field_name: str) -> str:
    if field_name == "horizon_days":
        return "integer"
    if field_name == "edge_score":
        return "number"
    return "string"


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, Mapping):
        return [str(key) for key in value.keys()]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(item) for item in value if item is not None and str(item) != ""]
    return [str(value)]


def _as_int(value: Any, *, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_int_mapping(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _as_int(raw, default=0) for key, raw in value.items()}


def _ordered_unique(values: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _stable_id(*parts: Any) -> str:
    payload = repr(parts).encode("utf-8")
    return "historical_replay_export_matrix_metadata_envelope_" + sha256(payload).hexdigest()[:16]
