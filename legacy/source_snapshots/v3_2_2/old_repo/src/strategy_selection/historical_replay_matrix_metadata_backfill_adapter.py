"""Historical replay matrix metadata backfill adapter.

This module attempts to attach the historical replay matrix metadata contract
fields to existing historical replay / edge evidence records.

It intentionally does not infer missing matrix dimensions, select strategies,
connect to brokers, request quotes, route orders, submit orders, or alter the
original historical outcome payloads. Records that cannot be mapped exactly are
kept in ``needs_review`` state.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "signalforge_historical_replay_matrix_metadata_backfill_adapter.v1"
SUMMARY_SCHEMA_VERSION = "signalforge_historical_replay_matrix_metadata_backfill_adapter_summary.v1"
ARTIFACT_TYPE = "signalforge_historical_replay_matrix_metadata_backfill_adapter"
RECOMMENDED_NEXT_WHEN_READY = "exact_matrix_edge_summary"
RECOMMENDED_NEXT_WHEN_NEEDS_REVIEW = "historical_replay_source_metadata_backfill"

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

DEFAULT_REQUIRED_FIELDS = [
    {
        "field_name": "regime_state",
        "dimension": "regime",
        "accepted_aliases": ["regime", "market_regime", "regime_label"],
        "normalization_rule": "trim_lower_snake_case",
    },
    {
        "field_name": "asset_behavior_state",
        "dimension": "asset_behavior",
        "accepted_aliases": ["asset_behavior", "asset_behavior_label", "underlying_behavior_state"],
        "normalization_rule": "trim_lower_snake_case",
    },
    {
        "field_name": "option_behavior_state",
        "dimension": "option_behavior",
        "accepted_aliases": ["option_behavior", "options_behavior", "option_behavior_label"],
        "normalization_rule": "trim_lower_snake_case",
    },
    {
        "field_name": "strategy_id",
        "dimension": "strategy",
        "accepted_aliases": ["strategy", "strategy_name", "setup_id", "option_strategy_id"],
        "normalization_rule": "trim_lower_snake_case",
    },
    {
        "field_name": "strategy_family",
        "dimension": "strategy",
        "accepted_aliases": ["family", "strategy_family_name", "setup_family"],
        "normalization_rule": "trim_lower_snake_case",
    },
    {
        "field_name": "symbol",
        "dimension": "symbol",
        "accepted_aliases": ["ticker", "underlying", "underlying_symbol"],
        "normalization_rule": "trim_uppercase_symbol",
    },
    {
        "field_name": "horizon_days",
        "dimension": "horizon",
        "accepted_aliases": ["horizon", "window_days", "selected_window_days", "target_horizon_days"],
        "normalization_rule": "coerce_positive_integer_days",
    },
]

DEFAULT_OPTIONAL_FIELDS = [
    {
        "field_name": "asset_class",
        "dimension": "asset_class",
        "accepted_aliases": ["asset_type", "instrument_class"],
        "normalization_rule": "trim_lower_snake_case",
    },
    {
        "field_name": "strategy_direction",
        "dimension": "direction",
        "accepted_aliases": ["direction", "bias", "strategy_bias"],
        "normalization_rule": "trim_lower_snake_case",
    },
    {
        "field_name": "risk_structure",
        "dimension": "risk_structure",
        "accepted_aliases": ["risk_profile", "risk_type"],
        "normalization_rule": "trim_lower_snake_case",
    },
    {
        "field_name": "replay_window_id",
        "dimension": "window",
        "accepted_aliases": ["window", "window_id", "batch_id"],
        "normalization_rule": "trim_string",
    },
    {
        "field_name": "edge_score",
        "dimension": "score",
        "accepted_aliases": ["historical_edge_score", "risk_adjusted_edge_score", "score"],
        "normalization_rule": "coerce_number",
    },
    {
        "field_name": "outcome_state",
        "dimension": "outcome",
        "accepted_aliases": ["outcome", "result_state", "historical_edge_state"],
        "normalization_rule": "trim_lower_snake_case",
    },
]

RECORD_LIST_KEYS = {
    "records",
    "historical_records",
    "historical_replay_records",
    "replay_records",
    "replay_outcomes",
    "outcome_records",
    "contract_outcomes",
    "contract_outcome_snapshots",
    "candidate_records",
    "candidate_snapshots",
    "results",
    "windows",
    "batches",
    "matrix_records",
    "edge_records",
    "strategy_edge_items",
    "historical_edge_items",
    "edge_items",
    "candidate_rows",
    "portfolio_candidate_rows",
    "window_summaries",
    "window_outcome_summaries",
    "horizon_sensitivity_summary",
    "best_outcomes",
    "worst_outcomes",
    "top_positive_symbols",
    "top_negative_symbols",
    "rows",
    "items",
    "data",
}

RECORD_HINT_KEYS = {
    "symbol",
    "ticker",
    "underlying",
    "underlying_symbol",
    "horizon",
    "horizon_days",
    "window_days",
    "selected_window_days",
    "target_horizon_days",
    "strategy",
    "strategy_id",
    "strategy_family",
    "scenario_id",
    "variant_id",
    "historical_edge_state",
    "historical_edge_score",
    "risk_adjusted_edge_score",
    "total_return",
    "win_rate",
    "outcome",
    "result_state",
    "window_id",
    "start",
    "end",
    "source_path",
    "scaleout_plan_path",
}


def build_signalforge_historical_replay_matrix_metadata_backfill_adapter(
    *,
    historical_replay_matrix_metadata_contract_source: Mapping[str, Any],
    historical_replay_sources: Sequence[Mapping[str, Any]],
    strategy_matrix_edge_inventory_source: Mapping[str, Any] | None = None,
    mapping_overrides_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Backfill matrix metadata from historical replay records when exact fields exist."""

    contract = _extract_contract(historical_replay_matrix_metadata_contract_source)
    inventory = _extract_summary(strategy_matrix_edge_inventory_source or {})
    overrides = _extract_overrides(mapping_overrides_source or {})

    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if not contract:
        blocked_reasons.append("historical_replay_matrix_metadata_contract_source_required")

    contract_state = str(contract.get("contract_state") or contract.get("status") or "unknown")
    if contract and contract_state != "ready":
        blocked_reasons.append("historical_replay_matrix_metadata_contract_not_ready")

    required_fields = _fields_from_contract(contract, key="required_fields", default=DEFAULT_REQUIRED_FIELDS)
    optional_fields = _fields_from_contract(contract, key="optional_fields", default=DEFAULT_OPTIONAL_FIELDS)
    matrix_cell_key_fields = _as_text_list(
        contract.get("matrix_cell_key_fields")
        or [field.get("field_name") for field in required_fields]
    )

    source_records = _extract_source_records(historical_replay_sources)
    if not historical_replay_sources:
        blocked_reasons.append("historical_replay_source_required")
    elif not source_records:
        blocked_reasons.append("historical_replay_source_records_required")

    backfilled_records: list[dict[str, Any]] = []
    missing_dimension_counts: dict[str, int] = {}
    mapped_dimension_counts: dict[str, int] = {}
    partial_dimension_counts: dict[str, int] = {}

    for index, source_record in enumerate(source_records):
        mapped_record = _backfill_record(
            source_record=source_record,
            record_index=index,
            required_fields=required_fields,
            optional_fields=optional_fields,
            matrix_cell_key_fields=matrix_cell_key_fields,
            overrides=overrides,
        )
        backfilled_records.append(mapped_record)
        for dimension in _as_text_list(mapped_record.get("missing_required_dimensions")):
            missing_dimension_counts[dimension] = missing_dimension_counts.get(dimension, 0) + 1
        for dimension in _as_text_list(mapped_record.get("mapped_required_dimensions")):
            mapped_dimension_counts[dimension] = mapped_dimension_counts.get(dimension, 0) + 1
        for dimension in _as_text_list(mapped_record.get("partial_required_dimensions")):
            partial_dimension_counts[dimension] = partial_dimension_counts.get(dimension, 0) + 1

    exact_ready_count = sum(1 for record in backfilled_records if record.get("matrix_metadata_state") == "ready")
    needs_review_count = sum(
        1 for record in backfilled_records if record.get("matrix_metadata_state") == "needs_review"
    )
    blocked_record_count = sum(
        1 for record in backfilled_records if record.get("matrix_metadata_state") == "blocked"
    )

    if blocked_reasons:
        status = "blocked"
        matrix_mapping_state = "blocked"
        recommended_next_step = "resolve_historical_replay_matrix_metadata_backfill_blockers"
    elif needs_review_count or blocked_record_count or exact_ready_count == 0:
        status = "needs_review"
        matrix_mapping_state = "matrix_metadata_backfill_needs_review"
        recommended_next_step = RECOMMENDED_NEXT_WHEN_NEEDS_REVIEW
    else:
        status = "ready"
        matrix_mapping_state = "exact_matrix_metadata_ready"
        recommended_next_step = RECOMMENDED_NEXT_WHEN_READY

    if missing_dimension_counts:
        warnings.append("historical_replay_records_still_missing_required_matrix_dimensions")
        for dimension in sorted(missing_dimension_counts):
            warnings.append(f"missing_required_dimension:{dimension}")
    if partial_dimension_counts:
        warnings.append("historical_replay_records_have_partial_matrix_dimensions")
    if exact_ready_count == 0 and source_records:
        warnings.append("no_historical_replay_records_ready_for_exact_matrix_edge_summary")
    if overrides:
        warnings.append("mapping_overrides_applied_review_required")

    expected_matrix_cell_count = _as_int(
        contract.get("expected_matrix_cell_count") or inventory.get("expected_matrix_cell_count"),
        default=0,
    )

    result = {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "adapter_id": _adapter_id(required_fields, optional_fields, source_records),
        "adapter_state": status,
        "status": status,
        "is_ready": status == "ready",
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "matrix_mapping_state": matrix_mapping_state,
        "recommended_next_step": recommended_next_step,
        "ready_to_build_exact_matrix_edge_summary": status == "ready",
        "ready_to_build_metadata_backfill_adapter": False,
        "contract_state": contract_state,
        "contract_id": str(contract.get("contract_id") or ""),
        "total_source_record_count": len(source_records),
        "backfilled_record_count": len(backfilled_records),
        "exact_matrix_cell_ready_record_count": exact_ready_count,
        "needs_review_record_count": needs_review_count,
        "blocked_record_count": blocked_record_count,
        "records_requiring_mapping_count": needs_review_count + blocked_record_count,
        "expected_matrix_cell_count": expected_matrix_cell_count,
        "required_field_count": len(required_fields),
        "optional_field_count": len(optional_fields),
        "matrix_cell_key_fields": matrix_cell_key_fields,
        "missing_required_dimension_counts": missing_dimension_counts,
        "mapped_required_dimension_counts": mapped_dimension_counts,
        "partial_required_dimension_counts": partial_dimension_counts,
        "required_missing_dimensions": sorted(missing_dimension_counts),
        "required_partial_dimensions": sorted(partial_dimension_counts),
        "backfilled_records": backfilled_records,
        "source_reference_summary": _source_reference_summary(historical_replay_sources),
        "blocked_reasons": _ordered_unique(blocked_reasons),
        "warnings": _ordered_unique(warnings),
        "automatic_action": None,
        "automatic_strategy_change": None,
        "order_intent": None,
        "requires_manual_approval": True,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
    result["backfill_adapter_summary"] = build_historical_replay_matrix_metadata_backfill_adapter_summary(
        result
    )
    return result


def build_historical_replay_matrix_metadata_backfill_adapter_summary(
    result: Mapping[str, Any]
) -> dict[str, Any]:
    """Build a compact summary for CLI/file-writer output."""

    return {
        "artifact_type": "signalforge_historical_replay_matrix_metadata_backfill_adapter_summary",
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "adapter_state": str(result.get("adapter_state") or result.get("status") or "blocked"),
        "status": str(result.get("status") or result.get("adapter_state") or "blocked"),
        "is_ready": bool(result.get("is_ready")),
        "matrix_mapping_state": str(result.get("matrix_mapping_state") or "unknown"),
        "recommended_next_step": str(result.get("recommended_next_step") or ""),
        "ready_to_build_exact_matrix_edge_summary": bool(
            result.get("ready_to_build_exact_matrix_edge_summary")
        ),
        "contract_state": str(result.get("contract_state") or "unknown"),
        "contract_id": str(result.get("contract_id") or ""),
        "total_source_record_count": _as_int(result.get("total_source_record_count"), default=0),
        "backfilled_record_count": _as_int(result.get("backfilled_record_count"), default=0),
        "exact_matrix_cell_ready_record_count": _as_int(
            result.get("exact_matrix_cell_ready_record_count"), default=0
        ),
        "needs_review_record_count": _as_int(result.get("needs_review_record_count"), default=0),
        "blocked_record_count": _as_int(result.get("blocked_record_count"), default=0),
        "records_requiring_mapping_count": _as_int(
            result.get("records_requiring_mapping_count"), default=0
        ),
        "expected_matrix_cell_count": _as_int(result.get("expected_matrix_cell_count"), default=0),
        "required_field_count": _as_int(result.get("required_field_count"), default=0),
        "optional_field_count": _as_int(result.get("optional_field_count"), default=0),
        "matrix_cell_key_fields": _as_text_list(result.get("matrix_cell_key_fields")),
        "required_missing_dimensions": _as_text_list(result.get("required_missing_dimensions")),
        "required_partial_dimensions": _as_text_list(result.get("required_partial_dimensions")),
        "missing_required_dimension_counts": dict(result.get("missing_required_dimension_counts") or {}),
        "mapped_required_dimension_counts": dict(result.get("mapped_required_dimension_counts") or {}),
        "partial_required_dimension_counts": dict(result.get("partial_required_dimension_counts") or {}),
        "blocked_reasons": _as_text_list(result.get("blocked_reasons")),
        "warnings": _as_text_list(result.get("warnings")),
        "explicit_exclusions": _as_text_list(result.get("explicit_exclusions")),
        "order_intent": result.get("order_intent"),
        "automatic_action": result.get("automatic_action"),
        "automatic_strategy_change": result.get("automatic_strategy_change"),
        "requires_manual_approval": bool(result.get("requires_manual_approval", True)),
    }


def _backfill_record(
    *,
    source_record: Mapping[str, Any],
    record_index: int,
    required_fields: Sequence[Mapping[str, Any]],
    optional_fields: Sequence[Mapping[str, Any]],
    matrix_cell_key_fields: Sequence[str],
    overrides: Mapping[str, Any],
) -> dict[str, Any]:
    source_copy = deepcopy(dict(source_record))
    metadata: dict[str, Any] = {}
    optional_metadata: dict[str, Any] = {}
    field_mappings: list[dict[str, Any]] = []
    missing_required_dimensions: list[str] = []
    mapped_required_dimensions: list[str] = []
    partial_required_dimensions: list[str] = []

    for field in required_fields:
        mapping = _map_field(source_record, field, overrides=overrides)
        field_mappings.append(mapping)
        dimension = str(field.get("dimension") or "")
        if mapping["mapping_state"] == "mapped":
            metadata[str(field.get("field_name"))] = mapping["normalized_value"]
            mapped_required_dimensions.append(dimension)
        elif mapping["mapping_state"] == "partial":
            metadata[str(field.get("field_name"))] = mapping["normalized_value"]
            partial_required_dimensions.append(dimension)
        else:
            missing_required_dimensions.append(dimension)

    optional_field_mappings: list[dict[str, Any]] = []
    for field in optional_fields:
        mapping = _map_field(source_record, field, overrides=overrides)
        optional_field_mappings.append(mapping)
        if mapping["mapping_state"] in {"mapped", "partial"}:
            optional_metadata[str(field.get("field_name"))] = mapping["normalized_value"]

    missing_required_dimensions = _ordered_unique(missing_required_dimensions)
    mapped_required_dimensions = _ordered_unique(mapped_required_dimensions)
    partial_required_dimensions = _ordered_unique(partial_required_dimensions)

    matrix_cell_key = _build_matrix_cell_key(metadata, matrix_cell_key_fields)
    if missing_required_dimensions or partial_required_dimensions or not matrix_cell_key:
        state = "needs_review"
    else:
        state = "ready"

    return {
        "artifact_type": "signalforge_historical_replay_matrix_metadata_backfilled_record",
        "schema_version": "signalforge_historical_replay_matrix_metadata_backfilled_record.v1",
        "record_index": record_index,
        "record_id": _record_id(source_copy, record_index),
        "matrix_metadata_state": state,
        "matrix_cell_key": matrix_cell_key,
        "metadata": metadata,
        "optional_metadata": optional_metadata,
        "missing_required_dimensions": missing_required_dimensions,
        "mapped_required_dimensions": mapped_required_dimensions,
        "partial_required_dimensions": partial_required_dimensions,
        "required_field_mappings": field_mappings,
        "optional_field_mappings": optional_field_mappings,
        "source_record": source_copy,
        "manual_review_required": state != "ready",
        "automatic_promotion_allowed": False if state != "ready" else True,
    }


def _map_field(
    source_record: Mapping[str, Any], field: Mapping[str, Any], *, overrides: Mapping[str, Any]) -> dict[str, Any]:
    field_name = str(field.get("field_name") or "")
    aliases = [field_name, *_as_text_list(field.get("accepted_aliases"))]
    rule = str(field.get("normalization_rule") or "trim_string")

    if field_name in overrides:
        normalized = _normalize_value(overrides[field_name], rule)
        return {
            "field_name": field_name,
            "dimension": str(field.get("dimension") or ""),
            "mapping_state": "partial" if normalized is not None else "missing",
            "source_field": "mapping_overrides",
            "raw_value": overrides.get(field_name),
            "normalized_value": normalized,
            "mapping_confidence": "manual_override_requires_review",
        }

    for alias in aliases:
        found, raw_value = _lookup_value(source_record, alias)
        if not found:
            continue
        normalized = _normalize_value(raw_value, rule)
        if normalized is None:
            return {
                "field_name": field_name,
                "dimension": str(field.get("dimension") or ""),
                "mapping_state": "missing",
                "source_field": alias,
                "raw_value": raw_value,
                "normalized_value": None,
                "mapping_confidence": "invalid_source_value",
            }
        return {
            "field_name": field_name,
            "dimension": str(field.get("dimension") or ""),
            "mapping_state": "mapped",
            "source_field": alias,
            "raw_value": raw_value,
            "normalized_value": normalized,
            "mapping_confidence": "direct_or_alias_match",
        }

    return {
        "field_name": field_name,
        "dimension": str(field.get("dimension") or ""),
        "mapping_state": "missing",
        "source_field": None,
        "raw_value": None,
        "normalized_value": None,
        "mapping_confidence": "missing",
    }


def _lookup_value(source_record: Mapping[str, Any], key: str) -> tuple[bool, Any]:
    if key in source_record:
        return True, source_record[key]

    lowered = key.lower()
    for source_key, value in source_record.items():
        if str(source_key).lower() == lowered:
            return True, value

    for container_key in ("metadata", "matrix_metadata", "strategy_metadata", "replay_metadata"):
        container = source_record.get(container_key)
        if isinstance(container, Mapping):
            found, value = _lookup_value(container, key)
            if found:
                return True, value

    return False, None


def _normalize_value(value: Any, rule: str) -> Any:
    if value is None:
        return None
    if rule == "trim_lower_snake_case":
        text = str(value).strip().lower()
        if not text:
            return None
        text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
        return text or None
    if rule == "trim_uppercase_symbol":
        text = str(value).strip().upper()
        return text or None
    if rule == "coerce_positive_integer_days":
        try:
            days = int(float(value))
        except (TypeError, ValueError):
            return None
        return days if days > 0 else None
    if rule == "coerce_number":
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    text = str(value).strip()
    return text or None


def _build_matrix_cell_key(metadata: Mapping[str, Any], matrix_cell_key_fields: Sequence[str]) -> str | None:
    parts: list[str] = []
    for field_name in matrix_cell_key_fields:
        if field_name not in metadata or metadata.get(field_name) in {None, ""}:
            return None
        parts.append(f"{field_name}={metadata[field_name]}")
    return "|".join(parts)


def _extract_source_records(sources: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source_index, source in enumerate(sources):
        for record in _iter_records(source):
            record_copy = deepcopy(dict(record))
            record_copy.setdefault("source_index", source_index)
            digest = _stable_digest(record_copy)
            if digest in seen:
                continue
            seen.add(digest)
            records.append(record_copy)
    return records


def _iter_records(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        if _looks_like_record(value):
            yield value
        for key, nested in value.items():
            if key in RECORD_LIST_KEYS and isinstance(nested, list):
                for item in nested:
                    yield from _iter_records(item)
            elif isinstance(nested, Mapping):
                yield from _iter_records(nested)
            elif isinstance(nested, list) and key in RECORD_LIST_KEYS:
                for item in nested:
                    yield from _iter_records(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_records(item)


def _looks_like_record(value: Mapping[str, Any]) -> bool:
    keys = {str(key) for key in value.keys()}
    if keys & RECORD_HINT_KEYS:
        return True
    if "metadata" in value and isinstance(value.get("metadata"), Mapping):
        nested_keys = {str(key) for key in value["metadata"].keys()}
        return bool(nested_keys & RECORD_HINT_KEYS)
    return False


def _extract_contract(source: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {}
    if source.get("artifact_type") == "signalforge_historical_replay_matrix_metadata_contract":
        return dict(source)
    for key in ("contract", "metadata_contract", "result"):
        value = source.get(key)
        if isinstance(value, Mapping):
            contract = _extract_contract(value)
            if contract:
                return contract
    if "required_fields" in source or "matrix_cell_key_fields" in source:
        return dict(source)
    return dict(source) if source.get("contract_state") else {}


def _extract_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {}
    for key in ("summary", "inventory_summary", "contract_summary", "backfill_adapter_summary"):
        value = source.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return dict(source)


def _extract_overrides(source: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {}
    for key in ("mapping_overrides", "overrides", "metadata_overrides"):
        value = source.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return dict(source) if source else {}


def _fields_from_contract(
    contract: Mapping[str, Any], *, key: str, default: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    raw_fields = contract.get(key)
    if not isinstance(raw_fields, list) or not raw_fields:
        return [dict(field) for field in default]
    fields: list[dict[str, Any]] = []
    for field in raw_fields:
        if isinstance(field, Mapping) and field.get("field_name"):
            fields.append(dict(field))
    return fields or [dict(field) for field in default]


def _source_reference_summary(historical_replay_sources: Sequence[Any]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []

    for index, source in enumerate(historical_replay_sources):
        if isinstance(source, Mapping):
            summaries.append(
                {
                    "source_index": index,
                    "source_shape": "mapping",
                    "artifact_type": str(source.get("artifact_type") or "unknown"),
                    "adapter_type": str(source.get("adapter_type") or "unknown"),
                    "schema_version": str(source.get("schema_version") or "unknown"),
                    "top_level_key_count": len(source.keys()),
                    "record_count": _estimated_source_record_count(source),
                }
            )
            continue

        if isinstance(source, list):
            item_artifact_types = sorted(
                {
                    str(item.get("artifact_type") or "unknown")
                    for item in source
                    if isinstance(item, Mapping)
                }
            )

            summaries.append(
                {
                    "source_index": index,
                    "source_shape": "list",
                    "artifact_type": "json_list",
                    "adapter_type": "unknown",
                    "schema_version": "unknown",
                    "top_level_key_count": 0,
                    "record_count": len(source),
                    "item_artifact_types": item_artifact_types,
                }
            )
            continue

        summaries.append(
            {
                "source_index": index,
                "source_shape": type(source).__name__,
                "artifact_type": "unknown",
                "adapter_type": "unknown",
                "schema_version": "unknown",
                "top_level_key_count": 0,
                "record_count": 1 if source is not None else 0,
                "item_artifact_types": [],
            }
        )

    return summaries

def _estimated_source_record_count(source: Mapping[str, Any]) -> int:
    candidate_keys = [
        "records",
        "items",
        "windows",
        "batches",
        "contract_outcomes",
        "candidate_rows",
        "edge_records",
        "diagnostic_records",
        "matrix_cells",
    ]

    for key in candidate_keys:
        value = source.get(key)
        if isinstance(value, list):
            return len(value)

    max_nested_count = 0
    for value in source.values():
        if isinstance(value, list):
            max_nested_count = max(max_nested_count, len(value))
        elif isinstance(value, Mapping):
            for nested_value in value.values():
                if isinstance(nested_value, list):
                    max_nested_count = max(max_nested_count, len(nested_value))

    return max_nested_count

def _adapter_id(
    required_fields: Sequence[Mapping[str, Any]],
    optional_fields: Sequence[Mapping[str, Any]],
    source_records: Sequence[Mapping[str, Any]],
) -> str:
    material = {
        "required_fields": [field.get("field_name") for field in required_fields],
        "optional_fields": [field.get("field_name") for field in optional_fields],
        "record_count": len(source_records),
    }
    digest = sha256(repr(material).encode("utf-8")).hexdigest()[:16]
    return f"historical_replay_matrix_metadata_backfill_adapter_{digest}"


def _record_id(source_record: Mapping[str, Any], record_index: int) -> str:
    digest = _stable_digest(source_record)[:16]
    return f"historical_replay_matrix_metadata_record_{record_index}_{digest}"


def _stable_digest(value: Any) -> str:
    try:
        material = json.dumps(value, sort_keys=True, default=str)
    except TypeError:
        material = repr(value)
    return sha256(material.encode("utf-8")).hexdigest()


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw_values = value
    elif isinstance(value, tuple):
        raw_values = list(value)
    else:
        raw_values = [value]
    result: list[str] = []
    for item in raw_values:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def _ordered_unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _as_int(value: Any, *, default: int) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default
