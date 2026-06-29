"""Candidate selection review matrix metadata helpers.

This module stamps and summarizes the shared ``matrix_metadata`` envelope on
candidate-selection review records. It is intentionally conservative: it copies
only explicit matrix dimensions already present on the candidate, review record,
or upstream ``matrix_metadata`` envelope. It does not infer regime, asset
behavior, option behavior, strategy, symbol, or horizon values.

The helper is additive so it can be called from the existing candidate-selection
review producer without changing ranking math, strategy eligibility, broker
behavior, order routing, fills, slippage modeling, or execution readiness.
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

ARTIFACT_TYPE = "signalforge_candidate_selection_review_matrix_metadata_patch"
SUMMARY_ARTIFACT_TYPE = "signalforge_candidate_selection_review_matrix_metadata_summary"
SCHEMA_VERSION = "signalforge_candidate_selection_review_matrix_metadata.v1"
SUMMARY_SCHEMA_VERSION = "signalforge_candidate_selection_review_matrix_metadata_summary.v1"

CANDIDATE_LIST_KEYS = (
    "candidate_selection_review_items",
    "candidate_selection_items",
    "candidate_review_items",
    "reviewed_candidates",
    "selected_candidates",
    "candidate_rows",
    "candidates",
    "items",
    "rows",
)

SELECTION_FIELD_ALIASES = (
    "candidate_id",
    "candidate_rank",
    "selection_rank",
    "rank",
    "review_state",
    "selection_state",
    "candidate_state",
    "expected_value_score",
    "edge_score",
    "historical_edge_score",
    "risk_adjusted_edge_score",
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


def stamp_candidate_selection_review_item(
    candidate: Mapping[str, Any],
    review_result: Mapping[str, Any] | None = None,
    *,
    metadata: Mapping[str, Any] | None = None,
    source_refs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Stamp one candidate-selection review item with matrix metadata.

    Values are copied only from explicit candidate fields, an optional review
    result, an optional metadata mapping, or an existing ``matrix_metadata``
    envelope. The function does not infer missing matrix dimensions from ranks,
    scores, names, or selected-candidate flags.
    """

    review = review_result if isinstance(review_result, Mapping) else {}
    explicit_metadata = metadata if isinstance(metadata, Mapping) else {}

    candidate_metadata = extract_candidate_matrix_metadata(candidate)
    review_metadata = extract_candidate_matrix_metadata(review)
    merged_metadata = merge_matrix_metadata(candidate_metadata, review_metadata)
    merged_metadata = merge_matrix_metadata(merged_metadata, explicit_metadata)

    record = dict(candidate)
    if review:
        record["candidate_selection_review_source_summary"] = _review_source_summary(review)
        for key in SELECTION_FIELD_ALIASES:
            if key in review and key not in record:
                record[key] = review.get(key)

    refs = {
        "symbol": "candidate_selection_review_item.symbol_or_matrix_metadata",
        "horizon_days": "candidate_selection_review_item.horizon_or_matrix_metadata",
        "strategy_id": "candidate_selection_review_item.strategy_or_matrix_metadata",
        "strategy_family": "candidate_selection_review_item.strategy_family_or_matrix_metadata",
        "regime_state": "upstream_matrix_metadata_or_regime_asset_options_alignment",
        "asset_behavior_state": "upstream_matrix_metadata_or_asset_behavior_policy",
        "option_behavior_state": "upstream_matrix_metadata_or_option_behavior_policy",
    }
    refs.update(_as_mapping(source_refs))

    stamped = stamp_matrix_metadata(record, merged_metadata, source_refs=refs)
    stamped["matrix_metadata_provider"] = "candidate_selection_review"
    stamped["ready_for_exact_matrix_cell_edge"] = stamped.get(MATRIX_METADATA_STATE_KEY) == "ready"
    stamped.setdefault("requires_manual_approval", True)
    stamped.setdefault("order_intent", None)
    stamped.setdefault("automatic_action", None)
    stamped.setdefault("automatic_strategy_change", None)
    return stamped


def stamp_candidate_selection_review_batch(
    candidates: Sequence[Mapping[str, Any]],
    *,
    source_refs: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Stamp a sequence of candidate-selection review records."""

    return [
        stamp_candidate_selection_review_item(candidate, source_refs=source_refs)
        for candidate in candidates
        if isinstance(candidate, Mapping)
    ]


def build_candidate_selection_review_matrix_metadata_summary(
    reviewed_candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize matrix metadata coverage for reviewed candidates."""

    stamped_records = [dict(candidate) for candidate in reviewed_candidates if isinstance(candidate, Mapping)]
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
        "exact_matrix_cell_ready_record_count": ready_count,
        "matrix_metadata_needs_review_record_count": needs_review_count,
        "mapped_required_field_counts": dict(coverage.get("mapped_required_field_counts") or {}),
        "missing_required_field_counts": dict(coverage.get("missing_required_field_counts") or {}),
        "ready_to_build_exact_matrix_edge_summary": bool(
            candidate_count > 0 and ready_count == candidate_count and needs_review_count == 0
        ),
        "recommended_next_step": (
            "patch_candidate_final_review_matrix_metadata"
            if candidate_count > 0 and ready_count == candidate_count and needs_review_count == 0
            else "carry_candidate_selection_review_matrix_metadata_into_final_review"
        ),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        "automatic_action": None,
        "automatic_strategy_change": None,
        "order_intent": None,
        "requires_manual_approval": True,
    }


def patch_candidate_selection_review_result(
    candidate_selection_review_result: Mapping[str, Any],
    *,
    candidate_list_key: str | None = None,
) -> dict[str, Any]:
    """Return a candidate-selection review artifact with matrix metadata stamped.

    The input artifact shape is preserved. The first recognized candidate list is
    stamped in place, and a compact summary is attached. If no candidate list is
    found, the result is returned with an empty summary and no readiness claim.
    """

    if not isinstance(candidate_selection_review_result, Mapping):
        return {
            "artifact_type": ARTIFACT_TYPE,
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "is_ready": False,
            "blocked_reasons": ["candidate_selection_review_result_mapping_required"],
            "warnings": [],
            "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
            "automatic_action": None,
            "automatic_strategy_change": None,
            "order_intent": None,
            "requires_manual_approval": True,
        }

    result = dict(candidate_selection_review_result)
    list_key = candidate_list_key or _find_candidate_list_key(result)
    candidates = _as_candidate_list(result.get(list_key)) if list_key else []
    stamped_candidates = stamp_candidate_selection_review_batch(candidates)
    summary = build_candidate_selection_review_matrix_metadata_summary(stamped_candidates)

    if list_key:
        result[list_key] = stamped_candidates
    result["matrix_metadata_envelope_key"] = MATRIX_METADATA_KEY
    result["matrix_cell_key_fields"] = list(REQUIRED_MATRIX_METADATA_FIELDS)
    result["matrix_metadata_candidate_selection_review_summary"] = summary
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


def _find_candidate_list_key(record: Mapping[str, Any]) -> str | None:
    for key in CANDIDATE_LIST_KEYS:
        value = record.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return key
    return None


def _as_candidate_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _review_source_summary(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": str(record.get("artifact_type") or "unknown"),
        "schema_version": str(record.get("schema_version") or "unknown"),
        "status": str(record.get("status") or record.get("review_state") or "unknown"),
        "candidate_count": _candidate_count(record),
    }


def _candidate_count(record: Mapping[str, Any]) -> int:
    for key in CANDIDATE_LIST_KEYS:
        value = record.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return len(value)
    return 0


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
