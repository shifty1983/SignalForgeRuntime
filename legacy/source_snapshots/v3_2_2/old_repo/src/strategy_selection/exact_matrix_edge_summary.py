"""Exact strategy-matrix edge summary builder.

This module aggregates historical replay records that already carry a complete
``matrix_metadata`` envelope into exact strategy-matrix cells. It is deliberately
conservative: records with missing regime, asset behavior, option behavior,
strategy, symbol, or horizon fields remain ``needs_review`` and are not promoted
into exact matrix-cell evidence.

It does not backfill missing metadata, infer strategy selection, connect to
brokers, request quotes, submit orders, model fills, or change strategy rules.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from statistics import mean
from typing import Any

from src.signalforge.engines.strategy_selection.historical_replay_matrix_metadata_stamp import (
    MATRIX_CELL_KEY_KEY,
    MATRIX_METADATA_KEY,
    MATRIX_METADATA_MISSING_FIELDS_KEY,
    MATRIX_METADATA_STATE_KEY,
    REQUIRED_MATRIX_METADATA_FIELDS,
    build_matrix_cell_key,
    extract_candidate_matrix_metadata,
    matrix_metadata_coverage,
    normalize_matrix_metadata,
    stamp_matrix_metadata,
    validate_matrix_metadata_record,
)

ARTIFACT_TYPE = "signalforge_exact_matrix_edge_summary"
SCHEMA_VERSION = "signalforge_exact_matrix_edge_summary.v1"
SUMMARY_ARTIFACT_TYPE = "signalforge_exact_matrix_edge_summary_compact"
SUMMARY_SCHEMA_VERSION = "signalforge_exact_matrix_edge_summary_compact.v1"

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

RECORD_LIST_KEYS = (
    "records",
    "backfilled_records",
    "matrix_metadata_records",
    "contract_outcome_snapshots",
    "contract_outcomes",
    "candidate_rows",
    "portfolio_candidate_rows",
    "matrix_cell_outcome_summaries",
    "matrix_cell_records",
    "exact_matrix_edge_cells",
    "scenario_rows",
    "window_summaries",
    "window_outcome_summaries",
    "items",
    "rows",
    "data",
)

POSITIVE_OUTCOME_STATES = {
    "win",
    "winner",
    "positive",
    "profitable",
    "ready",
    "historical_positive_edge_candidate",
    "positive_edge_candidate",
    "validated_positive_edge",
    "edge_validated",
}

NEGATIVE_OUTCOME_STATES = {
    "loss",
    "loser",
    "negative",
    "unprofitable",
    "blocked",
    "historical_negative_edge_candidate",
    "negative_edge_candidate",
}

SCORE_KEYS = (
    "edge_score",
    "historical_edge_score",
    "risk_adjusted_edge_score",
    "score",
    "primary_score",
)

RETURN_KEYS = (
    "total_return",
    "return",
    "strategy_adjusted_return",
    "average_strategy_adjusted_return",
    "pnl",
    "profit_loss",
)


def build_signalforge_exact_matrix_edge_summary(
    *,
    matrix_metadata_sources: Sequence[Any],
    strategy_matrix_edge_inventory_source: Mapping[str, Any] | None = None,
    min_records_per_cell: int = 1,
) -> dict[str, Any]:
    """Aggregate exact matrix-cell edge evidence from metadata-stamped records."""

    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if not matrix_metadata_sources:
        blocked_reasons.append("matrix_metadata_source_required")

    min_records = max(int(min_records_per_cell or 1), 1)
    source_records = _extract_source_records(matrix_metadata_sources)
    stamped_records = [_stamp_and_validate_record(record, index) for index, record in enumerate(source_records)]

    coverage = matrix_metadata_coverage(stamped_records)
    ready_records = [record for record in stamped_records if record.get(MATRIX_METADATA_STATE_KEY) == "ready"]
    needs_review_records = [
        record for record in stamped_records if record.get(MATRIX_METADATA_STATE_KEY) != "ready"
    ]
    blocked_records = [record for record in stamped_records if record.get(MATRIX_METADATA_STATE_KEY) == "blocked"]

    cells = _build_exact_matrix_cells(ready_records, min_records_per_cell=min_records)
    ready_cell_count = sum(1 for cell in cells if cell.get("matrix_edge_cell_state") == "ready")
    review_cell_count = sum(1 for cell in cells if cell.get("matrix_edge_cell_state") != "ready")

    if not blocked_reasons and not source_records:
        warnings.append("no_matrix_metadata_records_found")
    if source_records and not ready_records:
        warnings.append("no_exact_matrix_cell_ready_records_found")
    if needs_review_records:
        warnings.append("some_records_missing_required_matrix_metadata")
    if blocked_records:
        warnings.append("some_records_have_blocked_matrix_metadata")

    inventory_summary = _inventory_summary(strategy_matrix_edge_inventory_source)
    expected_matrix_cell_count = _as_int(inventory_summary.get("expected_matrix_cell_count"))
    if expected_matrix_cell_count == 0:
        expected_matrix_cell_count = _as_int(inventory_summary.get("catalog_strategy_count"))

    status = "blocked" if blocked_reasons else ("ready" if ready_records else "needs_review")
    matrix_edge_summary_state = status

    return {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "matrix_edge_summary_state": matrix_edge_summary_state,
        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
        "matrix_cell_key_fields": list(REQUIRED_MATRIX_METADATA_FIELDS),
        "source_count": len(matrix_metadata_sources),
        "total_source_record_count": len(source_records),
        "validated_record_count": len(stamped_records),
        "exact_matrix_cell_ready_record_count": len(ready_records),
        "matrix_metadata_needs_review_record_count": len(needs_review_records),
        "matrix_metadata_blocked_record_count": len(blocked_records),
        "exact_matrix_cell_count": len(cells),
        "ready_matrix_edge_cell_count": ready_cell_count,
        "review_required_matrix_edge_cell_count": review_cell_count,
        "expected_matrix_cell_count": expected_matrix_cell_count,
        "min_records_per_cell": min_records,
        "ready_to_update_strategy_matrix_edge_inventory": bool(ready_records),
        "ready_to_use_for_strategy_selection": bool(status == "ready" and ready_cell_count > 0),
        "ready_to_build_exact_matrix_edge_summary": bool(status == "ready" and ready_cell_count > 0),
        "recommended_next_step": (
            "update_strategy_matrix_edge_inventory_with_exact_matrix_edge_summary"
            if status == "ready" and ready_cell_count > 0
            else "rerun_historical_replay_with_populated_matrix_metadata_envelope"
        ),
        "matrix_metadata_coverage": coverage,
        "mapped_required_field_counts": dict(coverage.get("mapped_required_field_counts") or {}),
        "missing_required_field_counts": dict(coverage.get("missing_required_field_counts") or {}),
        "exact_matrix_edge_cells": cells,
        "needs_review_record_samples": _record_samples(needs_review_records),
        "blocked_record_samples": _record_samples(blocked_records),
        "source_reference_summary": _source_reference_summary(matrix_metadata_sources),
        "strategy_matrix_inventory_summary": inventory_summary,
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


def summarize_signalforge_exact_matrix_edge_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    """Build a compact summary for CLI/file-writer output."""

    coverage = result.get("matrix_metadata_coverage") if isinstance(result, Mapping) else {}
    return {
        "artifact_type": SUMMARY_ARTIFACT_TYPE,
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "status": result.get("status"),
        "is_ready": bool(result.get("is_ready")),
        "matrix_edge_summary_state": result.get("matrix_edge_summary_state"),
        "source_count": _as_int(result.get("source_count")),
        "total_source_record_count": _as_int(result.get("total_source_record_count")),
        "validated_record_count": _as_int(result.get("validated_record_count")),
        "exact_matrix_cell_ready_record_count": _as_int(
            result.get("exact_matrix_cell_ready_record_count")
        ),
        "matrix_metadata_needs_review_record_count": _as_int(
            result.get("matrix_metadata_needs_review_record_count")
        ),
        "matrix_metadata_blocked_record_count": _as_int(
            result.get("matrix_metadata_blocked_record_count")
        ),
        "exact_matrix_cell_count": _as_int(result.get("exact_matrix_cell_count")),
        "ready_matrix_edge_cell_count": _as_int(result.get("ready_matrix_edge_cell_count")),
        "review_required_matrix_edge_cell_count": _as_int(
            result.get("review_required_matrix_edge_cell_count")
        ),
        "expected_matrix_cell_count": _as_int(result.get("expected_matrix_cell_count")),
        "ready_to_update_strategy_matrix_edge_inventory": bool(
            result.get("ready_to_update_strategy_matrix_edge_inventory")
        ),
        "ready_to_use_for_strategy_selection": bool(result.get("ready_to_use_for_strategy_selection")),
        "ready_to_build_exact_matrix_edge_summary": bool(
            result.get("ready_to_build_exact_matrix_edge_summary")
        ),
        "recommended_next_step": result.get("recommended_next_step"),
        "mapped_required_field_counts": dict(coverage.get("mapped_required_field_counts") or {}),
        "missing_required_field_counts": dict(coverage.get("missing_required_field_counts") or {}),
        "warnings": list(result.get("warnings") or []),
        "blocked_reasons": list(result.get("blocked_reasons") or []),
        "explicit_exclusions": list(result.get("explicit_exclusions") or EXPLICIT_EXCLUSIONS),
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "order_intent": None,
        "broker_order_id": None,
        "requires_manual_approval": True,
    }


def _stamp_and_validate_record(record: Mapping[str, Any], source_record_index: int) -> dict[str, Any]:
    metadata = extract_candidate_matrix_metadata(record)
    stamped = stamp_matrix_metadata(
        record,
        metadata,
        source_refs={
            "source_record_index": source_record_index,
            "matrix_metadata": "existing_matrix_metadata_or_explicit_record_fields",
        },
    )
    validation = validate_matrix_metadata_record(stamped)
    stamped[MATRIX_METADATA_STATE_KEY] = validation.get("matrix_metadata_state")
    stamped[MATRIX_METADATA_MISSING_FIELDS_KEY] = validation.get("matrix_metadata_missing_fields")
    stamped[MATRIX_CELL_KEY_KEY] = validation.get("matrix_cell_key")
    stamped["matrix_cell_key_state"] = validation.get("matrix_cell_key_state")
    stamped["ready_for_exact_matrix_cell_edge"] = bool(validation.get("ready_for_exact_matrix_cell"))
    stamped["matrix_metadata_blocked_reasons"] = list(validation.get("blocked_reasons") or [])
    stamped["source_record_index"] = source_record_index
    return stamped


def _build_exact_matrix_cells(
    ready_records: Sequence[Mapping[str, Any]], *, min_records_per_cell: int
) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in ready_records:
        metadata = normalize_matrix_metadata(_as_mapping(record.get(MATRIX_METADATA_KEY)))
        key = str(record.get(MATRIX_CELL_KEY_KEY) or build_matrix_cell_key(metadata) or "")
        if key:
            groups[key].append(record)

    cells = []
    for matrix_cell_key, records in sorted(groups.items(), key=lambda item: item[0]):
        first_metadata = normalize_matrix_metadata(_as_mapping(records[0].get(MATRIX_METADATA_KEY)))
        outcomes = [_outcome_summary(record) for record in records]
        edge_scores = [item["edge_score"] for item in outcomes if item.get("edge_score") is not None]
        returns = [item["total_return"] for item in outcomes if item.get("total_return") is not None]
        positive_count = sum(1 for item in outcomes if item.get("outcome_direction") == "positive")
        negative_count = sum(1 for item in outcomes if item.get("outcome_direction") == "negative")
        unknown_count = len(outcomes) - positive_count - negative_count
        record_count = len(records)
        positive_rate = positive_count / record_count if record_count else None
        cell_state = "ready" if record_count >= min_records_per_cell else "needs_review"
        warnings: list[str] = []
        if record_count < min_records_per_cell:
            warnings.append("matrix_cell_record_count_below_minimum")
        if unknown_count:
            warnings.append("matrix_cell_contains_unknown_outcome_records")

        cells.append(
            {
                "matrix_cell_key": matrix_cell_key,
                "matrix_edge_cell_state": cell_state,
                "matrix_metadata": {field: first_metadata.get(field) for field in REQUIRED_MATRIX_METADATA_FIELDS},
                "regime_state": first_metadata.get("regime_state"),
                "asset_behavior_state": first_metadata.get("asset_behavior_state"),
                "option_behavior_state": first_metadata.get("option_behavior_state"),
                "strategy_id": first_metadata.get("strategy_id"),
                "strategy_family": first_metadata.get("strategy_family"),
                "symbol": first_metadata.get("symbol"),
                "horizon_days": first_metadata.get("horizon_days"),
                "record_count": record_count,
                "positive_outcome_count": positive_count,
                "negative_outcome_count": negative_count,
                "unknown_outcome_count": unknown_count,
                "positive_outcome_rate": positive_rate,
                "average_edge_score": mean(edge_scores) if edge_scores else None,
                "average_total_return": mean(returns) if returns else None,
                "source_record_indices": [record.get("source_record_index") for record in records],
                "edge_summary_state": _edge_summary_state(
                    cell_state=cell_state,
                    positive_count=positive_count,
                    negative_count=negative_count,
                    unknown_count=unknown_count,
                ),
                "warnings": warnings,
            }
        )
    return cells


def _edge_summary_state(
    *, cell_state: str, positive_count: int, negative_count: int, unknown_count: int
) -> str:
    if cell_state != "ready":
        return "needs_review"
    if positive_count > 0 and negative_count == 0:
        return "positive_edge_evidence"
    if negative_count > 0 and positive_count == 0:
        return "negative_edge_evidence"
    if positive_count > 0 and negative_count > 0:
        return "mixed_edge_evidence"
    if unknown_count > 0:
        return "outcome_evidence_needs_review"
    return "needs_review"


def _outcome_summary(record: Mapping[str, Any]) -> dict[str, Any]:
    metadata = _as_mapping(record.get(MATRIX_METADATA_KEY))
    edge_score = _first_float(metadata, SCORE_KEYS)
    if edge_score is None:
        edge_score = _first_float(record, SCORE_KEYS)

    total_return = _first_float(record, RETURN_KEYS)
    if total_return is None:
        total_return = _first_float(metadata, RETURN_KEYS)

    outcome_state = _first_text(metadata, ("outcome_state",)) or _first_text(
        record,
        (
            "outcome_state",
            "outcome",
            "result_state",
            "historical_edge_state",
            "edge_state",
            "trade_outcome",
        ),
    )
    win_value = record.get("win") if "win" in record else record.get("is_win")
    outcome_direction = _outcome_direction(
        outcome_state=outcome_state,
        edge_score=edge_score,
        total_return=total_return,
        win_value=win_value,
    )
    return {
        "edge_score": edge_score,
        "total_return": total_return,
        "outcome_state": outcome_state,
        "outcome_direction": outcome_direction,
    }


def _outcome_direction(
    *, outcome_state: str | None, edge_score: float | None, total_return: float | None, win_value: Any
) -> str:
    if isinstance(win_value, bool):
        return "positive" if win_value else "negative"
    state = _stable_token(outcome_state) if outcome_state else ""
    if state in POSITIVE_OUTCOME_STATES:
        return "positive"
    if state in NEGATIVE_OUTCOME_STATES:
        return "negative"
    if total_return is not None:
        if total_return > 0:
            return "positive"
        if total_return < 0:
            return "negative"
    if edge_score is not None:
        if edge_score > 0:
            return "positive"
        if edge_score < 0:
            return "negative"
    return "unknown"


def _extract_source_records(sources: Sequence[Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for source_index, source in enumerate(sources):
        for record in _extract_records_from_source(source):
            item = dict(record)
            item.setdefault("source_index", source_index)
            records.append(item)
    return records


def _extract_records_from_source(source: Any) -> list[Mapping[str, Any]]:
    if isinstance(source, list):
        records: list[Mapping[str, Any]] = []
        for item in source:
            records.extend(_extract_records_from_source(item))
        return records

    if not isinstance(source, Mapping):
        return []

    records: list[Mapping[str, Any]] = []
    if _looks_like_matrix_record(source):
        records.append(source)

    for key in RECORD_LIST_KEYS:
        value = source.get(key)
        if isinstance(value, list):
            for item in value:
                records.extend(_extract_records_from_source(item))

    # Some producers nest the useful rows inside summary containers. Walk only
    # mappings that look like artifact containers or summaries to avoid pulling
    # arbitrary nested scalars into separate records.
    for key, value in source.items():
        if key in RECORD_LIST_KEYS:
            continue
        if isinstance(value, Mapping) and _should_walk_mapping(key, value):
            records.extend(_extract_records_from_source(value))

    return _dedupe_records(records)


def _looks_like_matrix_record(record: Mapping[str, Any]) -> bool:
    if MATRIX_METADATA_KEY in record or MATRIX_CELL_KEY_KEY in record:
        return True
    metadata = extract_candidate_matrix_metadata(record)
    return any(metadata.get(field) is not None for field in REQUIRED_MATRIX_METADATA_FIELDS)


def _should_walk_mapping(key: str, value: Mapping[str, Any]) -> bool:
    lowered = key.lower()
    if any(token in lowered for token in ("summary", "records", "items", "cells", "outcomes")):
        return True
    return any(list_key in value for list_key in RECORD_LIST_KEYS)


def _dedupe_records(records: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    deduped: list[Mapping[str, Any]] = []
    seen: set[int] = set()
    for record in records:
        marker = id(record)
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(record)
    return deduped


def _source_reference_summary(sources: Sequence[Any]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for index, source in enumerate(sources):
        if isinstance(source, Mapping):
            summaries.append(
                {
                    "source_index": index,
                    "source_shape": "mapping",
                    "artifact_type": str(source.get("artifact_type") or "unknown"),
                    "schema_version": str(source.get("schema_version") or "unknown"),
                    "record_count": len(_extract_records_from_source(source)),
                }
            )
        elif isinstance(source, list):
            summaries.append(
                {
                    "source_index": index,
                    "source_shape": "list",
                    "artifact_type": "json_list",
                    "schema_version": "unknown",
                    "record_count": len(_extract_records_from_source(source)),
                }
            )
        else:
            summaries.append(
                {
                    "source_index": index,
                    "source_shape": type(source).__name__,
                    "artifact_type": "unknown",
                    "schema_version": "unknown",
                    "record_count": 0,
                }
            )
    return summaries


def _inventory_summary(source: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {}
    summary = source.get("strategy_matrix_edge_inventory_summary")
    if isinstance(summary, Mapping):
        return dict(summary)
    compact = {
        "expected_matrix_cell_count": source.get("expected_matrix_cell_count"),
        "catalog_strategy_count": source.get("catalog_strategy_count"),
        "ready_matrix_cell_count": source.get("ready_matrix_cell_count"),
        "review_required_matrix_cell_count": source.get("review_required_matrix_cell_count"),
    }
    return {key: value for key, value in compact.items() if value is not None}


def _record_samples(records: Sequence[Mapping[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for record in records[:limit]:
        metadata = _as_mapping(record.get(MATRIX_METADATA_KEY))
        samples.append(
            {
                "source_record_index": record.get("source_record_index"),
                "matrix_metadata_state": record.get(MATRIX_METADATA_STATE_KEY),
                "matrix_metadata_missing_fields": list(
                    record.get(MATRIX_METADATA_MISSING_FIELDS_KEY) or []
                ),
                "matrix_cell_key": record.get(MATRIX_CELL_KEY_KEY),
                "symbol": metadata.get("symbol"),
                "horizon_days": metadata.get("horizon_days"),
                "strategy_id": metadata.get("strategy_id"),
                "strategy_family": metadata.get("strategy_family"),
            }
        )
    return samples


def _first_float(source: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    for key in keys:
        value = source.get(key)
        parsed = _as_float_or_none(value)
        if parsed is not None:
            return parsed
    return None


def _first_text(source: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = source.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _as_float_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _as_int(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _ordered_unique(values: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _stable_token(value: Any) -> str:
    return str(value).strip().lower().replace(" ", "_").replace("-", "_")
