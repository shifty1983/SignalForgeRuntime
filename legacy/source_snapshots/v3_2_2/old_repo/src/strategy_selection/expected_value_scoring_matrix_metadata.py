"""Expected value scoring matrix metadata helpers.

This module stamps and summarizes the shared ``matrix_metadata`` envelope on
expected-value scored strategy candidates. It is intentionally conservative: it
copies only explicit matrix dimensions already present on the candidate, score
record, or upstream ``matrix_metadata`` envelope. It does not infer regime,
asset behavior, option behavior, strategy, symbol, or horizon values.

The helper is additive so it can be called from the existing expected-value
scoring producer without changing EV math, ranking, broker behavior, order
routing, fills, slippage modeling, or strategy-selection rules.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.signalforge.engines.strategy_selection.historical_replay_matrix_metadata_stamp import (
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

ARTIFACT_TYPE = "signalforge_expected_value_scoring_matrix_metadata_patch"
SUMMARY_ARTIFACT_TYPE = "signalforge_expected_value_scoring_matrix_metadata_summary"
SCHEMA_VERSION = "signalforge_expected_value_scoring_matrix_metadata.v1"
SUMMARY_SCHEMA_VERSION = "signalforge_expected_value_scoring_matrix_metadata_summary.v1"

CANDIDATE_LIST_KEYS = (
    "expected_value_items",
    "expected_value_scored_candidates",
    "scored_candidates",
    "candidate_scores",
    "strategy_candidate_scores",
    "candidates",
    "items",
)

EV_SCORE_ALIASES = (
    "expected_value_score",
    "ev_score",
    "opportunity_score",
    "score",
    "risk_adjusted_score",
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


def stamp_expected_value_scored_candidate(
    candidate: Mapping[str, Any],
    expected_value_result: Mapping[str, Any] | None = None,
    *,
    metadata: Mapping[str, Any] | None = None,
    source_refs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Stamp one EV-scored candidate with the shared matrix metadata envelope.

    Values are copied only from explicit candidate fields, an optional EV result,
    an optional metadata mapping, or an existing ``matrix_metadata`` envelope. The
    function does not infer missing matrix dimensions from scores or names.
    """

    ev_result = expected_value_result if isinstance(expected_value_result, Mapping) else {}
    explicit_metadata = metadata if isinstance(metadata, Mapping) else {}

    candidate_metadata = extract_candidate_matrix_metadata(candidate)
    ev_metadata = extract_candidate_matrix_metadata(ev_result)
    merged_metadata = merge_matrix_metadata(candidate_metadata, ev_metadata)
    merged_metadata = merge_matrix_metadata(merged_metadata, explicit_metadata)

    record = dict(candidate)
    if ev_result:
        record["expected_value_source_summary"] = _expected_value_source_summary(ev_result)
        for key in EV_SCORE_ALIASES:
            if key in ev_result and key not in record:
                record[key] = ev_result.get(key)

    refs = {
        "symbol": "expected_value_candidate.symbol_or_matrix_metadata",
        "horizon_days": "expected_value_candidate.horizon_or_matrix_metadata",
        "strategy_id": "expected_value_candidate.strategy_or_matrix_metadata",
        "strategy_family": "expected_value_candidate.strategy_family_or_matrix_metadata",
        "regime_state": "upstream_matrix_metadata_or_regime_alignment",
        "asset_behavior_state": "upstream_matrix_metadata_or_asset_behavior_policy",
        "option_behavior_state": "upstream_matrix_metadata_or_option_behavior_policy",
    }
    refs.update(_as_mapping(source_refs))

    stamped = stamp_matrix_metadata(record, merged_metadata, source_refs=refs)
    stamped["matrix_metadata_provider"] = "expected_value_scoring"
    stamped["ready_for_exact_matrix_cell_edge"] = stamped.get(MATRIX_METADATA_STATE_KEY) == "ready"
    stamped.setdefault("requires_manual_approval", True)
    stamped.setdefault("order_intent", None)
    stamped.setdefault("automatic_action", None)
    stamped.setdefault("automatic_strategy_change", None)
    return stamped


def stamp_expected_value_candidate_batch(
    candidates: Sequence[Mapping[str, Any]],
    *,
    source_refs: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Stamp a sequence of EV candidate records."""

    return [
        stamp_expected_value_scored_candidate(candidate, source_refs=source_refs)
        for candidate in candidates
        if isinstance(candidate, Mapping)
    ]


def build_expected_value_scoring_matrix_metadata_summary(
    scored_candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize matrix metadata coverage for EV-scored candidates."""

    stamped_records = [dict(candidate) for candidate in scored_candidates if isinstance(candidate, Mapping)]
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
            "patch_candidate_selection_review_matrix_metadata"
            if candidate_count > 0 and ready_count == candidate_count and needs_review_count == 0
            else "carry_expected_value_matrix_metadata_into_candidate_selection_review"
        ),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        "automatic_action": None,
        "automatic_strategy_change": None,
        "order_intent": None,
        "requires_manual_approval": True,
    }


def patch_expected_value_scoring_result(
    expected_value_result: Mapping[str, Any],
    *,
    candidate_list_key: str | None = None,
) -> dict[str, Any]:
    """Return an EV scoring artifact with candidate matrix metadata stamped.

    The input artifact shape is preserved. The first recognized candidate list is
    stamped in place, and a compact summary is attached. If no candidate list is
    found, the result is returned with an empty summary and no readiness claim.
    """

    if not isinstance(expected_value_result, Mapping):
        return {
            "artifact_type": ARTIFACT_TYPE,
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "is_ready": False,
            "blocked_reasons": ["expected_value_result_mapping_required"],
            "warnings": [],
            "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
            "automatic_action": None,
            "automatic_strategy_change": None,
            "order_intent": None,
            "requires_manual_approval": True,
        }

    result = dict(expected_value_result)
    list_key = candidate_list_key or _find_candidate_list_key(result)
    candidates = _as_candidate_list(result.get(list_key)) if list_key else []
    stamped_candidates = stamp_expected_value_candidate_batch(candidates)
    summary = build_expected_value_scoring_matrix_metadata_summary(stamped_candidates)

    if list_key:
        result[list_key] = stamped_candidates
    result["matrix_metadata_envelope_key"] = MATRIX_METADATA_KEY
    result["matrix_cell_key_fields"] = list(REQUIRED_MATRIX_METADATA_FIELDS)
    result["matrix_metadata_expected_value_summary"] = summary
    result["exact_matrix_cell_ready_record_count"] = summary["exact_matrix_cell_ready_record_count"]
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
        if isinstance(record.get(key), Sequence) and not isinstance(record.get(key), (str, bytes, bytearray)):
            return key
    return None


def _as_candidate_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _expected_value_source_summary(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": str(record.get("artifact_type") or "expected_value_result"),
        "status": str(record.get("status") or record.get("state") or "unknown"),
        "expected_value_score": _first_present(record, EV_SCORE_ALIASES),
        "expected_return": _first_present(record, ("expected_return", "annualized_expected_return")),
        "probability_of_profit": _first_present(record, ("probability_of_profit", "probability_profit")),
    }


def _first_present(record: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return None


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
