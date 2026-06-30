"""Historical replay matrix metadata stamping helpers.

This module provides deterministic helpers for creating, normalizing, stamping,
validating, and merging the ``matrix_metadata`` envelope required on historical
replay records before SignalForge can attribute edge to exact strategy-matrix
cells.

It intentionally does not infer missing regime/behavior/strategy values, score
strategies, select candidates, connect to brokers, request quotes, route orders,
submit orders, or alter strategy availability rules.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "signalforge_historical_replay_matrix_metadata_stamp.v1"
SUMMARY_SCHEMA_VERSION = "signalforge_historical_replay_matrix_metadata_stamp_summary.v1"
ARTIFACT_TYPE = "signalforge_historical_replay_matrix_metadata_stamp_helpers"

MATRIX_METADATA_KEY = "matrix_metadata"
MATRIX_METADATA_STATE_KEY = "matrix_metadata_state"
MATRIX_METADATA_MISSING_FIELDS_KEY = "matrix_metadata_missing_fields"
MATRIX_METADATA_SOURCE_REFS_KEY = "matrix_metadata_source_refs"
MATRIX_CELL_KEY_KEY = "matrix_cell_key"

RECOMMENDED_NEXT_WHEN_READY = "patch_quantconnect_replay_scaleout_plan_matrix_metadata"
RECOMMENDED_NEXT_WHEN_BLOCKED = "resolve_historical_replay_matrix_metadata_stamping_helper_blockers"

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

REQUIRED_MATRIX_METADATA_FIELDS = [
    "regime_state",
    "asset_behavior_state",
    "option_behavior_state",
    "strategy_id",
    "strategy_family",
    "symbol",
    "horizon_days",
]

OPTIONAL_MATRIX_METADATA_FIELDS = [
    "asset_class",
    "strategy_direction",
    "risk_structure",
    "replay_window_id",
    "edge_score",
    "outcome_state",
]

ALL_MATRIX_METADATA_FIELDS = REQUIRED_MATRIX_METADATA_FIELDS + OPTIONAL_MATRIX_METADATA_FIELDS

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

FIELD_ALIASES = {
    "symbol": ["symbol", "ticker", "underlying", "underlying_symbol", "root_symbol"],
    "horizon_days": [
        "horizon_days",
        "horizon",
        "window_days",
        "selected_window_days",
        "target_horizon_days",
    ],
    "strategy_id": ["strategy_id", "strategy", "strategy_name", "setup_id", "scenario_id"],
    "strategy_family": ["strategy_family", "family", "strategy_type", "variant_id"],
    "regime_state": ["regime_state", "regime", "market_regime", "regime_label"],
    "asset_behavior_state": [
        "asset_behavior_state",
        "asset_behavior",
        "asset_behavior_label",
        "behavior_state",
    ],
    "option_behavior_state": [
        "option_behavior_state",
        "option_behavior",
        "option_behavior_label",
        "options_behavior_state",
    ],
    "asset_class": ["asset_class", "security_type", "instrument_type"],
    "strategy_direction": ["strategy_direction", "direction", "bias"],
    "risk_structure": ["risk_structure", "risk_profile", "defined_risk_state"],
    "replay_window_id": ["replay_window_id", "window_id", "window", "batch_window_id"],
    "edge_score": ["edge_score", "historical_edge_score", "risk_adjusted_edge_score", "score"],
    "outcome_state": ["outcome_state", "outcome", "result_state", "historical_edge_state"],
}


def build_signalforge_historical_replay_matrix_metadata_stamping_helpers(
    *,
    historical_replay_export_matrix_metadata_patch_plan_source: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a readiness artifact for the shared stamping helpers."""

    patch_plan = _extract_patch_plan(historical_replay_export_matrix_metadata_patch_plan_source)
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if not patch_plan:
        blocked_reasons.append("historical_replay_export_matrix_metadata_patch_plan_source_required")

    patch_plan_state = str(patch_plan.get("patch_plan_state") or patch_plan.get("status") or "unknown")
    if patch_plan and patch_plan_state != "ready":
        blocked_reasons.append("historical_replay_export_matrix_metadata_patch_plan_not_ready")

    matrix_cell_key_fields = _ordered_unique(
        _as_text_list(patch_plan.get("matrix_cell_key_fields")) or REQUIRED_MATRIX_METADATA_FIELDS
    )
    missing_helper_fields = [
        field for field in REQUIRED_MATRIX_METADATA_FIELDS if field not in matrix_cell_key_fields
    ]
    if missing_helper_fields:
        blocked_reasons.append("matrix_cell_key_fields_missing_required_helper_fields")

    source_patch_required = bool(patch_plan.get("source_patch_required"))
    ready_to_apply_patches = bool(patch_plan.get("ready_to_apply_patches"))
    if source_patch_required and not ready_to_apply_patches:
        blocked_reasons.append("historical_replay_export_patch_plan_not_ready_to_apply")

    if source_patch_required:
        warnings.append("historical_replay_export_producers_still_require_stamping_helper_patch")
    if bool(patch_plan.get("ready_to_build_exact_matrix_edge_summary")):
        warnings.append("unexpected_exact_matrix_edge_summary_ready_before_source_stamping")

    helper_contract = _helper_contract(matrix_cell_key_fields=matrix_cell_key_fields)
    helper_id = _stable_id(
        {
            "artifact_type": ARTIFACT_TYPE,
            "schema_version": SCHEMA_VERSION,
            "matrix_cell_key_fields": matrix_cell_key_fields,
            "helper_functions": helper_contract["helper_functions"],
        }
    )

    helper_state = "blocked" if blocked_reasons else "ready"
    ready_to_patch_historical_replay_exports = helper_state == "ready" and ready_to_apply_patches

    return {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "helper_id": f"historical_replay_matrix_metadata_stamp_helpers_{helper_id}",
        "created_at": _utc_now_iso(),
        "helper_state": helper_state,
        "status": helper_state,
        "is_ready": helper_state == "ready",
        "patch_plan_state": patch_plan_state,
        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
        "matrix_cell_key_fields": matrix_cell_key_fields,
        "required_matrix_metadata_fields": list(REQUIRED_MATRIX_METADATA_FIELDS),
        "optional_matrix_metadata_fields": list(OPTIONAL_MATRIX_METADATA_FIELDS),
        "required_field_count": len(REQUIRED_MATRIX_METADATA_FIELDS),
        "optional_field_count": len(OPTIONAL_MATRIX_METADATA_FIELDS),
        "helper_function_count": len(helper_contract["helper_functions"]),
        "normalization_rule_count": len(FIELD_ALIASES),
        "validation_rule_count": 6,
        "source_patch_required": source_patch_required,
        "ready_to_apply_patches": ready_to_apply_patches,
        "ready_to_patch_historical_replay_exports": ready_to_patch_historical_replay_exports,
        "ready_to_build_exact_matrix_edge_summary": False,
        "recommended_next_step": (
            RECOMMENDED_NEXT_WHEN_READY
            if ready_to_patch_historical_replay_exports
            else RECOMMENDED_NEXT_WHEN_BLOCKED
        ),
        "records_requiring_mapping_count": _as_int(patch_plan.get("records_requiring_mapping_count")),
        "total_source_record_count": _as_int(patch_plan.get("total_source_record_count")),
        "mapped_required_dimension_counts": _as_mapping(
            patch_plan.get("mapped_required_dimension_counts")
        ),
        "missing_required_dimension_counts": _as_mapping(
            patch_plan.get("missing_required_dimension_counts")
        ),
        "required_missing_dimensions": _ordered_unique(
            _as_text_list(patch_plan.get("required_missing_dimensions"))
        ),
        "required_partial_dimensions": _ordered_unique(
            _as_text_list(patch_plan.get("required_partial_dimensions"))
        ),
        "helper_contract": helper_contract,
        "blocked_reasons": _ordered_unique(blocked_reasons),
        "warnings": _ordered_unique(warnings),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        "automatic_action": None,
        "automatic_strategy_change": None,
        "order_intent": None,
        "requires_manual_approval": True,
    }


def build_matrix_metadata_envelope(
    metadata: Mapping[str, Any] | None = None,
    *,
    source_refs: Mapping[str, Any] | None = None,
    required_fields: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Create a normalized matrix metadata envelope.

    Missing required fields are left as ``None`` and reported in
    ``matrix_metadata_missing_fields``. This helper never guesses regime,
    behavior, or strategy values.
    """

    required = list(required_fields or REQUIRED_MATRIX_METADATA_FIELDS)
    normalized = normalize_matrix_metadata(metadata or {})
    for field in ALL_MATRIX_METADATA_FIELDS:
        normalized.setdefault(field, None)

    missing_fields = _missing_required_fields(normalized, required)
    state = "ready" if not missing_fields else "needs_review"
    matrix_cell_key = build_matrix_cell_key(normalized, required_fields=required)

    return {
        MATRIX_METADATA_KEY: normalized,
        MATRIX_METADATA_STATE_KEY: state,
        MATRIX_METADATA_MISSING_FIELDS_KEY: missing_fields,
        MATRIX_METADATA_SOURCE_REFS_KEY: _normalize_source_refs(source_refs or {}, normalized),
        MATRIX_CELL_KEY_KEY: matrix_cell_key if state == "ready" else None,
    }


def stamp_matrix_metadata(
    record: Mapping[str, Any],
    metadata: Mapping[str, Any] | None = None,
    *,
    source_refs: Mapping[str, Any] | None = None,
    preserve_existing: bool = True,
    required_fields: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Return a copy of ``record`` stamped with a matrix metadata envelope."""

    stamped = dict(record)
    existing_metadata = _as_mapping(record.get(MATRIX_METADATA_KEY))
    incoming_metadata = metadata if metadata is not None else extract_candidate_matrix_metadata(record)
    if preserve_existing and existing_metadata:
        merged = merge_matrix_metadata(existing_metadata, incoming_metadata or {})
    else:
        merged = normalize_matrix_metadata(incoming_metadata or {})

    envelope = build_matrix_metadata_envelope(
        merged,
        source_refs=source_refs,
        required_fields=required_fields,
    )
    stamped.update(envelope)
    return stamped


def validate_matrix_metadata_record(
    record: Mapping[str, Any],
    *,
    required_fields: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Validate a record that should contain a matrix metadata envelope."""

    required = list(required_fields or REQUIRED_MATRIX_METADATA_FIELDS)
    metadata = _as_mapping(record.get(MATRIX_METADATA_KEY))
    normalized = normalize_matrix_metadata(metadata)
    missing_fields = _missing_required_fields(normalized, required)
    state = "ready" if not missing_fields else "needs_review"

    matrix_cell_key = build_matrix_cell_key(normalized, required_fields=required)
    existing_key = record.get(MATRIX_CELL_KEY_KEY)
    key_state = "not_required" if state != "ready" else "ready"
    if state == "ready" and existing_key and existing_key != matrix_cell_key:
        key_state = "mismatch"
        state = "blocked"

    return {
        "matrix_metadata_state": state,
        "matrix_metadata_missing_fields": missing_fields,
        "matrix_cell_key": matrix_cell_key if not missing_fields else None,
        "matrix_cell_key_state": key_state,
        "ready_for_exact_matrix_cell": state == "ready",
        "blocked_reasons": ["matrix_cell_key_mismatch"] if key_state == "mismatch" else [],
    }


def extract_candidate_matrix_metadata(record: Mapping[str, Any]) -> dict[str, Any]:
    """Extract known matrix fields and aliases from a replay record.

    The function only copies explicit fields or recognized aliases. It does not
    infer missing regime/behavior/strategy dimensions.
    """

    extracted: dict[str, Any] = {}
    nested_metadata = _as_mapping(record.get(MATRIX_METADATA_KEY))

    for field in ALL_MATRIX_METADATA_FIELDS:
        value = nested_metadata.get(field)
        if _has_value(value):
            extracted[field] = value
            continue
        for alias in FIELD_ALIASES.get(field, [field]):
            value = _deep_get(record, alias)
            if _has_value(value):
                extracted[field] = value
                break

    return normalize_matrix_metadata(extracted)


def normalize_matrix_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize matrix metadata values without fabricating missing fields."""

    normalized: dict[str, Any] = {}
    for field in ALL_MATRIX_METADATA_FIELDS:
        value = metadata.get(field)
        if not _has_value(value):
            normalized[field] = None
            continue
        normalized[field] = normalize_matrix_metadata_value(field, value)
    return normalized


def normalize_matrix_metadata_value(field: str, value: Any) -> Any:
    """Normalize one metadata value for deterministic cell-key generation."""

    if not _has_value(value):
        return None

    if field == "symbol":
        return normalize_symbol(value)
    if field == "horizon_days":
        return normalize_horizon_days(value)
    if field == "edge_score":
        return _as_float_or_none(value)

    text = str(value).strip()
    if not text:
        return None
    if field in {
        "regime_state",
        "asset_behavior_state",
        "option_behavior_state",
        "strategy_id",
        "strategy_family",
        "asset_class",
        "strategy_direction",
        "risk_structure",
        "outcome_state",
    }:
        return _stable_token(text)
    return text


def normalize_symbol(value: Any) -> str | None:
    text = str(value).strip().upper() if _has_value(value) else ""
    return text or None


def normalize_horizon_days(value: Any) -> int | None:
    if not _has_value(value):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        return int(value) if value > 0 and value.is_integer() else None
    text = str(value).strip().lower()
    if not text:
        return None
    for suffix in ["days", "day", "d"]:
        text = text.replace(suffix, "")
    text = text.strip()
    try:
        number = float(text)
    except ValueError:
        return None
    if number <= 0 or not number.is_integer():
        return None
    return int(number)


def merge_matrix_metadata(
    base_metadata: Mapping[str, Any],
    update_metadata: Mapping[str, Any],
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Merge matrix metadata deterministically.

    By default, non-empty existing values are preserved and updates only fill
    missing fields. Set ``overwrite=True`` to replace existing values.
    """

    base = normalize_matrix_metadata(base_metadata)
    updates = normalize_matrix_metadata(update_metadata)
    merged = dict(base)
    for field, value in updates.items():
        if not _has_value(value):
            continue
        if overwrite or not _has_value(merged.get(field)):
            merged[field] = value
    return merged


def build_matrix_cell_key(
    metadata: Mapping[str, Any],
    *,
    required_fields: Sequence[str] | None = None,
) -> str | None:
    """Build a deterministic exact matrix-cell key when required fields exist."""

    required = list(required_fields or REQUIRED_MATRIX_METADATA_FIELDS)
    normalized = normalize_matrix_metadata(metadata)
    if _missing_required_fields(normalized, required):
        return None
    parts = [f"{field}={normalized[field]}" for field in required]
    return "|".join(parts)


def matrix_metadata_coverage(metadata_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize required-field coverage across stamped records."""

    mapped_counts = {field: 0 for field in REQUIRED_MATRIX_METADATA_FIELDS}
    missing_counts = {field: 0 for field in REQUIRED_MATRIX_METADATA_FIELDS}
    ready_count = 0
    needs_review_count = 0

    for record in metadata_records:
        metadata = _as_mapping(record.get(MATRIX_METADATA_KEY) or record)
        normalized = normalize_matrix_metadata(metadata)
        missing = _missing_required_fields(normalized, REQUIRED_MATRIX_METADATA_FIELDS)
        if missing:
            needs_review_count += 1
        else:
            ready_count += 1
        for field in REQUIRED_MATRIX_METADATA_FIELDS:
            if _has_value(normalized.get(field)):
                mapped_counts[field] += 1
            else:
                missing_counts[field] += 1

    return {
        "total_record_count": len(metadata_records),
        "exact_matrix_cell_ready_record_count": ready_count,
        "needs_review_record_count": needs_review_count,
        "mapped_required_field_counts": mapped_counts,
        "missing_required_field_counts": missing_counts,
        "ready_to_build_exact_matrix_edge_summary": ready_count > 0 and needs_review_count == 0,
    }


def summarize_signalforge_historical_replay_matrix_metadata_stamping_helpers(
    result: Mapping[str, Any]
) -> dict[str, Any]:
    """Return a compact CLI/file-writer summary."""

    return {
        "artifact_type": "historical_replay_matrix_metadata_stamping_helpers_summary",
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "helper_state": str(result.get("helper_state") or result.get("status") or "unknown"),
        "status": str(result.get("status") or result.get("helper_state") or "unknown"),
        "is_ready": bool(result.get("is_ready")),
        "helper_id": result.get("helper_id"),
        "patch_plan_state": result.get("patch_plan_state"),
        "matrix_metadata_envelope_key": result.get("matrix_metadata_envelope_key"),
        "matrix_cell_key_fields": _as_text_list(result.get("matrix_cell_key_fields")),
        "required_field_count": _as_int(result.get("required_field_count")),
        "optional_field_count": _as_int(result.get("optional_field_count")),
        "helper_function_count": _as_int(result.get("helper_function_count")),
        "normalization_rule_count": _as_int(result.get("normalization_rule_count")),
        "validation_rule_count": _as_int(result.get("validation_rule_count")),
        "source_patch_required": bool(result.get("source_patch_required")),
        "ready_to_apply_patches": bool(result.get("ready_to_apply_patches")),
        "ready_to_patch_historical_replay_exports": bool(
            result.get("ready_to_patch_historical_replay_exports")
        ),
        "ready_to_build_exact_matrix_edge_summary": bool(
            result.get("ready_to_build_exact_matrix_edge_summary")
        ),
        "recommended_next_step": result.get("recommended_next_step"),
        "records_requiring_mapping_count": _as_int(result.get("records_requiring_mapping_count")),
        "total_source_record_count": _as_int(result.get("total_source_record_count")),
        "required_missing_dimensions": _as_text_list(result.get("required_missing_dimensions")),
        "required_partial_dimensions": _as_text_list(result.get("required_partial_dimensions")),
        "blocked_reasons": _as_text_list(result.get("blocked_reasons")),
        "warnings": _as_text_list(result.get("warnings")),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        "automatic_action": None,
        "automatic_strategy_change": None,
        "order_intent": None,
        "requires_manual_approval": True,
    }


def _helper_contract(*, matrix_cell_key_fields: Sequence[str]) -> dict[str, Any]:
    return {
        "contract_name": "historical_replay_matrix_metadata_stamping_helpers",
        "matrix_metadata_key": MATRIX_METADATA_KEY,
        "matrix_metadata_state_key": MATRIX_METADATA_STATE_KEY,
        "matrix_metadata_missing_fields_key": MATRIX_METADATA_MISSING_FIELDS_KEY,
        "matrix_metadata_source_refs_key": MATRIX_METADATA_SOURCE_REFS_KEY,
        "matrix_cell_key_key": MATRIX_CELL_KEY_KEY,
        "required_fields": list(REQUIRED_MATRIX_METADATA_FIELDS),
        "optional_fields": list(OPTIONAL_MATRIX_METADATA_FIELDS),
        "matrix_cell_key_fields": list(matrix_cell_key_fields),
        "helper_functions": [
            "build_matrix_metadata_envelope",
            "stamp_matrix_metadata",
            "validate_matrix_metadata_record",
            "extract_candidate_matrix_metadata",
            "normalize_matrix_metadata",
            "normalize_matrix_metadata_value",
            "normalize_symbol",
            "normalize_horizon_days",
            "merge_matrix_metadata",
            "build_matrix_cell_key",
            "matrix_metadata_coverage",
        ],
        "validation_rules": [
            "required_fields_must_be_present_for_ready_state",
            "missing_required_fields_must_produce_needs_review_state",
            "matrix_cell_key_only_generated_for_ready_records",
            "existing_matrix_cell_key_mismatch_blocks_record",
            "normalization_must_not_infer_missing_regime_behavior_or_strategy",
            "source_refs_must_remain_diagnostic_only",
        ],
    }


def _extract_patch_plan(source: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(source, Mapping):
        return {}
    if source.get("artifact_type") == "signalforge_historical_replay_export_matrix_metadata_patch_plan":
        return source
    nested = source.get("patch_plan") or source.get("result") or source.get("summary")
    if isinstance(nested, Mapping):
        return nested
    return source


def _normalize_source_refs(source_refs: Mapping[str, Any], metadata: Mapping[str, Any]) -> dict[str, Any]:
    refs: dict[str, Any] = {}
    for field in ALL_MATRIX_METADATA_FIELDS:
        ref_value = source_refs.get(field)
        if _has_value(ref_value):
            refs[field] = ref_value
        elif _has_value(metadata.get(field)):
            refs[field] = "explicit_source_field_or_alias"
    return refs


def _missing_required_fields(metadata: Mapping[str, Any], required_fields: Sequence[str]) -> list[str]:
    return [field for field in required_fields if not _has_value(metadata.get(field))]


def _stable_token(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _deep_get(record: Mapping[str, Any], key: str) -> Any:
    if key in record:
        return record.get(key)
    for value in record.values():
        if isinstance(value, Mapping) and key in value:
            return value.get(key)
    return None


def _has_value(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _as_float_or_none(value: Any) -> float | None:
    if not _has_value(value) or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value.strip()))
        except ValueError:
            return 0
    return 0


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [str(key) for key in value.keys()]
    if isinstance(value, Sequence):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _ordered_unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _stable_id(payload: Mapping[str, Any]) -> str:
    return sha256(str(payload).encode("utf-8")).hexdigest()[:16]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()




