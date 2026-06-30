"""Contract selection readiness matrix metadata helpers.

This module stamps and summarizes the shared ``matrix_metadata`` envelope on
contract-selection readiness artifacts. It is intentionally conservative: it
copies only explicit matrix dimensions already present on the readiness item,
its upstream candidate/final-review result, or an existing ``matrix_metadata``
envelope.

It does not infer regime, asset behavior, option behavior, strategy, symbol, or
horizon from contract fields, strikes, expirations, option rights, quote state,
readiness labels, broker readiness, or any paper/live execution fields.

The helper is additive so it can be called from the existing contract-selection
readiness producer without changing contract selection, quote validation,
strategy selection, broker behavior, order routing, fills, slippage modeling, or
execution readiness.
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

ARTIFACT_TYPE = "signalforge_contract_selection_readiness_matrix_metadata_patch"
SUMMARY_ARTIFACT_TYPE = "signalforge_contract_selection_readiness_matrix_metadata_summary"
SCHEMA_VERSION = "signalforge_contract_selection_readiness_matrix_metadata.v1"
SUMMARY_SCHEMA_VERSION = "signalforge_contract_selection_readiness_matrix_metadata_summary.v1"

CONTRACT_SELECTION_LIST_KEYS = (
    "contract_selection_readiness_items",
    "contract_selection_items",
    "contract_readiness_items",
    "contract_candidates",
    "ready_contract_candidates",
    "selected_contract_candidates",
    "candidate_final_review_items",
    "final_review_queue",
    "selected_candidates",
    "candidate_rows",
    "candidates",
    "items",
    "rows",
)

CONTRACT_SELECTION_FIELD_ALIASES = (
    "candidate_id",
    "contract_selection_state",
    "contract_readiness_state",
    "contract_selection_status",
    "selected_contract_symbol",
    "selected_contract_expiration",
    "selected_contract_right",
    "selected_contract_strike",
    "spread_type",
    "contract_strategy_family",
    "contract_selection_blocked_reasons",
    "contract_selection_warnings",
    "quote_validation_state",
    "broker_contract_resolution_state",
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


def stamp_contract_selection_readiness_item(
    readiness_item: Mapping[str, Any],
    readiness_result: Mapping[str, Any] | None = None,
    *,
    metadata: Mapping[str, Any] | None = None,
    source_refs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Stamp one contract-selection readiness item with matrix metadata.

    Values are copied only from explicit fields, an optional readiness result,
    an optional metadata mapping, or an existing ``matrix_metadata`` envelope.
    This helper never derives strategy identity or market-condition state from
    option-contract attributes such as strike, expiration, right, quote state,
    or spread type.
    """

    result = readiness_result if isinstance(readiness_result, Mapping) else {}
    explicit_metadata = metadata if isinstance(metadata, Mapping) else {}

    item_metadata = extract_candidate_matrix_metadata(readiness_item)
    result_metadata = extract_candidate_matrix_metadata(result)
    merged_metadata = merge_matrix_metadata(item_metadata, result_metadata)
    merged_metadata = merge_matrix_metadata(merged_metadata, explicit_metadata)

    record = dict(readiness_item)
    if result:
        record["contract_selection_readiness_source_summary"] = _readiness_source_summary(result)
        for key in CONTRACT_SELECTION_FIELD_ALIASES:
            if key in result and key not in record:
                record[key] = result.get(key)

    refs = {
        "symbol": "contract_selection_readiness_item.symbol_or_matrix_metadata",
        "horizon_days": "contract_selection_readiness_item.horizon_or_matrix_metadata",
        "strategy_id": "upstream_candidate_final_review_or_matrix_metadata",
        "strategy_family": "upstream_candidate_final_review_or_matrix_metadata",
        "regime_state": "upstream_regime_asset_options_alignment_or_matrix_metadata",
        "asset_behavior_state": "upstream_asset_behavior_policy_or_matrix_metadata",
        "option_behavior_state": "upstream_option_behavior_policy_or_matrix_metadata",
    }
    refs.update(_as_mapping(source_refs))

    stamped = stamp_matrix_metadata(record, merged_metadata, source_refs=refs)
    stamped["matrix_metadata_provider"] = "contract_selection_readiness"
    stamped["ready_for_exact_matrix_cell_edge"] = stamped.get(MATRIX_METADATA_STATE_KEY) == "ready"
    stamped["ready_for_contract_selection_matrix_cell_edge"] = (
        stamped.get(MATRIX_METADATA_STATE_KEY) == "ready"
    )
    stamped.setdefault("manual_review_required", True)
    stamped.setdefault("requires_manual_approval", True)
    stamped.setdefault("order_intent", None)
    stamped.setdefault("automatic_action", None)
    stamped.setdefault("automatic_strategy_change", None)
    return stamped


def stamp_contract_selection_readiness_batch(
    readiness_items: Sequence[Mapping[str, Any]],
    *,
    source_refs: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Stamp a sequence of contract-selection readiness records."""

    return [
        stamp_contract_selection_readiness_item(item, source_refs=source_refs)
        for item in readiness_items
        if isinstance(item, Mapping)
    ]


def build_contract_selection_readiness_matrix_metadata_summary(
    readiness_items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize matrix metadata coverage for contract-selection readiness records."""

    stamped_records = [dict(item) for item in readiness_items if isinstance(item, Mapping)]
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
        "contract_selection_readiness_item_count": candidate_count,
        "exact_matrix_cell_ready_record_count": ready_count,
        "matrix_metadata_needs_review_record_count": needs_review_count,
        "mapped_required_field_counts": dict(coverage.get("mapped_required_field_counts") or {}),
        "missing_required_field_counts": dict(coverage.get("missing_required_field_counts") or {}),
        "ready_to_build_exact_matrix_edge_summary": bool(
            candidate_count > 0 and ready_count == candidate_count and needs_review_count == 0
        ),
        "recommended_next_step": (
            "build_exact_matrix_edge_summary"
            if candidate_count > 0 and ready_count == candidate_count and needs_review_count == 0
            else "carry_contract_selection_readiness_matrix_metadata_into_current_candidate_exports"
        ),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        "automatic_action": None,
        "automatic_strategy_change": None,
        "order_intent": None,
        "requires_manual_approval": True,
    }


def patch_contract_selection_readiness_result(
    contract_selection_readiness_result: Mapping[str, Any],
    *,
    candidate_list_key: str | None = None,
) -> dict[str, Any]:
    """Return a contract-selection readiness artifact with matrix metadata stamped.

    The input artifact shape is preserved. Every recognized candidate/readiness
    list is stamped in place. If no candidate list is found, the result is
    returned with an empty summary and no exact matrix-edge readiness claim.
    """

    if not isinstance(contract_selection_readiness_result, Mapping):
        return {
            "artifact_type": ARTIFACT_TYPE,
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "is_ready": False,
            "blocked_reasons": ["contract_selection_readiness_result_mapping_required"],
            "warnings": [],
            "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
            "automatic_action": None,
            "automatic_strategy_change": None,
            "order_intent": None,
            "requires_manual_approval": True,
        }

    result = dict(contract_selection_readiness_result)
    keys_to_stamp = _candidate_list_keys_to_stamp(result, preferred_key=candidate_list_key)
    primary_key = candidate_list_key or (keys_to_stamp[0] if keys_to_stamp else None)

    primary_stamped: list[dict[str, Any]] = []
    for key in keys_to_stamp:
        records = _as_candidate_list(result.get(key))
        stamped_records = stamp_contract_selection_readiness_batch(records)
        result[key] = stamped_records
        if key == primary_key:
            primary_stamped = stamped_records

    if not primary_stamped and primary_key:
        primary_stamped = stamp_contract_selection_readiness_batch(
            _as_candidate_list(result.get(primary_key))
        )

    summary = build_contract_selection_readiness_matrix_metadata_summary(primary_stamped)

    result["matrix_metadata_envelope_key"] = MATRIX_METADATA_KEY
    result["matrix_cell_key_fields"] = list(REQUIRED_MATRIX_METADATA_FIELDS)
    result["matrix_metadata_contract_selection_readiness_summary"] = summary
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


def _candidate_list_keys_to_stamp(record: Mapping[str, Any], *, preferred_key: str | None = None) -> list[str]:
    keys: list[str] = []
    if preferred_key and _is_candidate_sequence(record.get(preferred_key)):
        keys.append(preferred_key)
    for key in CONTRACT_SELECTION_LIST_KEYS:
        if key not in keys and _is_candidate_sequence(record.get(key)):
            keys.append(key)
    return keys


def _is_candidate_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _as_candidate_list(value: Any) -> list[Mapping[str, Any]]:
    if not _is_candidate_sequence(value):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _readiness_source_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": str(result.get("artifact_type") or "unknown"),
        "schema_version": str(result.get("schema_version") or "unknown"),
        "status": str(result.get("status") or result.get("readiness_state") or "unknown"),
        "contract_selection_state": str(
            result.get("contract_selection_state")
            or result.get("contract_selection_readiness_state")
            or result.get("readiness_state")
            or "unknown"
        ),
        "ready_to_build_exact_matrix_edge_summary": bool(
            result.get("ready_to_build_exact_matrix_edge_summary")
        ),
    }


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
