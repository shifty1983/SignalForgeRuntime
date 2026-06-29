"""Candidate final review matrix metadata helpers.

This module stamps and summarizes the shared ``matrix_metadata`` envelope on
candidate final-review export records. It is intentionally conservative: it
copies only explicit matrix dimensions already present on the final-review item,
its upstream candidate review item, or an existing ``matrix_metadata`` envelope.
It does not infer regime, asset behavior, option behavior, strategy, symbol, or
horizon values.

The helper is additive so it can be called from the existing candidate final
review export producer without changing candidate ranking, human-review
handoff, broker behavior, order routing, fills, slippage modeling, or execution
readiness.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.strategy_selection.historical_replay_matrix_metadata_stamp import (
    MATRIX_CELL_KEY_KEY,
    MATRIX_METADATA_KEY,
    MATRIX_METADATA_MISSING_FIELDS_KEY,
    MATRIX_METADATA_SOURCE_REFS_KEY,
    MATRIX_METADATA_STATE_KEY,
    REQUIRED_MATRIX_METADATA_FIELDS,
    extract_candidate_matrix_metadata,
    matrix_metadata_coverage,
    merge_matrix_metadata,
    stamp_matrix_metadata,
)

ARTIFACT_TYPE = "signalforge_candidate_final_review_matrix_metadata_patch"
SUMMARY_ARTIFACT_TYPE = "signalforge_candidate_final_review_matrix_metadata_summary"
SCHEMA_VERSION = "signalforge_candidate_final_review_matrix_metadata.v1"
SUMMARY_SCHEMA_VERSION = "signalforge_candidate_final_review_matrix_metadata_summary.v1"

FINAL_REVIEW_LIST_KEYS = (
    "final_review_queue",
    "ranked_final_review_items",
    "candidate_final_review_items",
    "candidate_final_review_export_items",
    "candidate_review_items",
    "reviewed_candidates",
    "selected_candidates",
    "candidate_rows",
    "candidates",
    "items",
    "rows",
)

FINAL_REVIEW_FIELD_ALIASES = (
    "candidate_id",
    "candidate_review_rank",
    "final_review_rank",
    "final_review_handoff_status",
    "final_review_export_status",
    "coverage_status",
    "eligible_for_final_review_export",
    "included_in_final_review_export",
    "selected_strategy_family",
    "selected_expected_value_score",
    "selected_expected_value_state",
)

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


def stamp_candidate_final_review_item(
    final_review_item: Mapping[str, Any],
    final_review_result: Mapping[str, Any] | None = None,
    *,
    metadata: Mapping[str, Any] | None = None,
    source_refs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Stamp one candidate final-review item with matrix metadata.

    Values are copied only from explicit item fields, an optional final-review
    result, an optional metadata mapping, or an existing ``matrix_metadata``
    envelope. The function does not infer missing matrix dimensions from ranks,
    scores, handoff labels, or selected-for-review flags.
    """

    result = final_review_result if isinstance(final_review_result, Mapping) else {}
    explicit_metadata = metadata if isinstance(metadata, Mapping) else {}

    item_metadata = merge_matrix_metadata(
        extract_candidate_matrix_metadata(final_review_item),
        _final_review_explicit_matrix_metadata(final_review_item),
    )
    result_metadata = merge_matrix_metadata(
        extract_candidate_matrix_metadata(result),
        _final_review_explicit_matrix_metadata(result),
    )
    merged_metadata = merge_matrix_metadata(item_metadata, result_metadata)
    merged_metadata = merge_matrix_metadata(merged_metadata, explicit_metadata)

    record = dict(final_review_item)
    if result:
        record["candidate_final_review_source_summary"] = _final_review_source_summary(result)
        for key in FINAL_REVIEW_FIELD_ALIASES:
            if key in result and key not in record:
                record[key] = result.get(key)

    refs = {
        "symbol": "candidate_final_review_item.symbol_or_matrix_metadata",
        "horizon_days": "candidate_final_review_item.horizon_or_matrix_metadata",
        "strategy_id": "candidate_final_review_item.strategy_or_matrix_metadata",
        "strategy_family": "candidate_final_review_item.strategy_family_or_matrix_metadata",
        "regime_state": "upstream_matrix_metadata_or_regime_asset_options_alignment",
        "asset_behavior_state": "upstream_matrix_metadata_or_asset_behavior_policy",
        "option_behavior_state": "upstream_matrix_metadata_or_option_behavior_policy",
    }
    refs.update(_as_mapping(source_refs))

    stamped = stamp_matrix_metadata(record, merged_metadata, source_refs=refs)
    stamped["matrix_metadata_provider"] = "candidate_final_review"
    stamped["ready_for_exact_matrix_cell_edge"] = stamped.get(MATRIX_METADATA_STATE_KEY) == "ready"
    stamped.setdefault("manual_review_required", True)
    stamped.setdefault("requires_manual_approval", True)
    stamped.setdefault("order_intent", None)
    stamped.setdefault("automatic_action", None)
    stamped.setdefault("automatic_strategy_change", None)
    return stamped


def stamp_candidate_final_review_batch(
    final_review_items: Sequence[Mapping[str, Any]],
    *,
    source_refs: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Stamp a sequence of candidate final-review records."""

    return [
        stamp_candidate_final_review_item(item, source_refs=source_refs)
        for item in final_review_items
        if isinstance(item, Mapping)
    ]


def build_candidate_final_review_matrix_metadata_summary(
    final_review_items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize matrix metadata coverage for final-review candidates."""

    stamped_records = [dict(item) for item in final_review_items if isinstance(item, Mapping)]
    coverage = matrix_metadata_coverage(stamped_records)
    ready_count = int(coverage.get("exact_matrix_cell_ready_record_count") or 0)
    needs_review_count = int(coverage.get("needs_review_record_count") or 0)
    candidate_count = len(stamped_records)

    return {
        "artifact_type": SUMMARY_ARTIFACT_TYPE,
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
        "matrix_cell_key_fields": list(REQUIRED_MATRIX_METADATA_FIELDS),
        "candidate_count": candidate_count,
        "final_review_item_count": candidate_count,
        "exact_matrix_cell_ready_record_count": ready_count,
        "matrix_metadata_needs_review_record_count": needs_review_count,
        "mapped_required_field_counts": dict(coverage.get("mapped_required_field_counts") or {}),
        "missing_required_field_counts": dict(coverage.get("missing_required_field_counts") or {}),
        "ready_to_build_exact_matrix_edge_summary": bool(
            candidate_count > 0 and ready_count == candidate_count and needs_review_count == 0
        ),
        "recommended_next_step": (
            "patch_contract_selection_readiness_matrix_metadata"
            if candidate_count > 0 and ready_count == candidate_count and needs_review_count == 0
            else "carry_candidate_final_review_matrix_metadata_into_contract_selection_readiness"
        ),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        "automatic_action": None,
        "automatic_strategy_change": None,
        "order_intent": None,
        "requires_manual_approval": True,
    }


def patch_candidate_final_review_export_result(
    candidate_final_review_export_result: Mapping[str, Any],
    *,
    candidate_list_key: str | None = None,
) -> dict[str, Any]:
    """Return a final-review export artifact with matrix metadata stamped.

    The input artifact shape is preserved. Every recognized final-review list is
    stamped in place so ``candidate_final_review_items`` and ``final_review_queue``
    stay consistent. If no candidate list is found, the result is returned with
    an empty summary and no exact matrix-edge readiness claim.
    """

    if not isinstance(candidate_final_review_export_result, Mapping):
        return {
            "artifact_type": ARTIFACT_TYPE,
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "is_ready": False,
            "blocked_reasons": ["candidate_final_review_export_result_mapping_required"],
            "warnings": [],
            "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
            "automatic_action": None,
            "automatic_strategy_change": None,
            "order_intent": None,
            "requires_manual_approval": True,
        }

    result = dict(candidate_final_review_export_result)
    keys_to_stamp = _candidate_list_keys_to_stamp(result, preferred_key=candidate_list_key)
    primary_key = candidate_list_key or (keys_to_stamp[0] if keys_to_stamp else None)

    primary_stamped: list[dict[str, Any]] = []
    for key in keys_to_stamp:
        records = _as_candidate_list(result.get(key))
        stamped_records = stamp_candidate_final_review_batch(records)
        result[key] = stamped_records
        if key == primary_key:
            primary_stamped = stamped_records

    if not primary_stamped and primary_key:
        primary_stamped = stamp_candidate_final_review_batch(_as_candidate_list(result.get(primary_key)))

    summary = build_candidate_final_review_matrix_metadata_summary(primary_stamped)

    result["matrix_metadata_envelope_key"] = MATRIX_METADATA_KEY
    result["matrix_cell_key_fields"] = list(REQUIRED_MATRIX_METADATA_FIELDS)
    result["matrix_metadata_candidate_final_review_summary"] = summary
    result["exact_matrix_cell_ready_record_count"] = summary[
        "exact_matrix_cell_ready_record_count"
    ]
    result["matrix_metadata_needs_review_record_count"] = summary[
        "matrix_metadata_needs_review_record_count"
    ]
    result["ready_to_build_exact_matrix_edge_summary"] = summary[
        "ready_to_build_exact_matrix_edge_summary"
    ]
    result["recommended_next_step"] = summary["recommended_next_step"]
    result.setdefault("explicit_exclusions", list(EXPLICIT_EXCLUSIONS))
    result.setdefault("automatic_action", None)
    result.setdefault("automatic_strategy_change", None)
    result.setdefault("order_intent", None)
    result.setdefault("requires_manual_approval", True)
    return result



def _final_review_explicit_matrix_metadata(record: Mapping[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    alias_map = {
        "strategy_family": (
            "selected_strategy_family",
            "final_review_strategy_family",
            "best_strategy_family",
        ),
        "strategy_id": (
            "selected_strategy_id",
            "final_review_strategy_id",
            "best_strategy_id",
        ),
        "horizon_days": (
            "selected_horizon_days",
            "final_review_horizon_days",
            "target_horizon_days",
        ),
    }
    for field, aliases in alias_map.items():
        for alias in aliases:
            value = record.get(alias)
            if value is not None and value != "" and value != [] and value != {}:
                metadata[field] = value
                break
    return metadata

def _candidate_list_keys_to_stamp(record: Mapping[str, Any], *, preferred_key: str | None = None) -> list[str]:
    keys: list[str] = []
    if preferred_key and _is_candidate_sequence(record.get(preferred_key)):
        keys.append(preferred_key)
    for key in FINAL_REVIEW_LIST_KEYS:
        if key not in keys and _is_candidate_sequence(record.get(key)):
            keys.append(key)
    return keys


def _as_candidate_list(value: Any) -> list[Mapping[str, Any]]:
    if not _is_candidate_sequence(value):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _is_candidate_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _final_review_source_summary(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": str(record.get("artifact_type") or "unknown"),
        "schema_version": str(record.get("schema_version") or "unknown"),
        "status": str(record.get("status") or record.get("final_review_state") or "unknown"),
        "candidate_count": _candidate_count(record),
    }


def _candidate_count(record: Mapping[str, Any]) -> int:
    for key in FINAL_REVIEW_LIST_KEYS:
        value = record.get(key)
        if _is_candidate_sequence(value):
            return len(value)
    return 0


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
