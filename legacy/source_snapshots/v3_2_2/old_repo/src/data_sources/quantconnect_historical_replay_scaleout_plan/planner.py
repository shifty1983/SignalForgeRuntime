from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import Any

from src.signalforge.engines.strategy_selection.historical_replay_matrix_metadata_stamp import (
    MATRIX_CELL_KEY_KEY,
    MATRIX_METADATA_KEY,
    MATRIX_METADATA_MISSING_FIELDS_KEY,
    MATRIX_METADATA_STATE_KEY,
    REQUIRED_MATRIX_METADATA_FIELDS,
    matrix_metadata_coverage,
    normalize_horizon_days,
    stamp_matrix_metadata,
)


ARTIFACT_TYPE = "signalforge_quantconnect_historical_replay_scaleout_plan"
SCHEMA_VERSION = "signalforge_quantconnect_historical_replay_scaleout_plan.v2"
CONTRACT = "quantconnect_historical_replay_scaleout_plan"

EXPECTED_RESULT_FILES = [
    "signalforge_qc_replay_manifest.json",
    "signalforge_qc_market_price_snapshots.json",
    "signalforge_qc_filtered_option_rows.json",
    "signalforge_qc_contract_outcome_snapshots.json",
    "signalforge_qc_maintenance_trigger_snapshots.json",
    "signalforge_qc_portfolio_replay_snapshots.json",
]

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


MATRIX_METADATA_PATCH_CAPABILITIES = [
    "historical_replay_matrix_metadata_candidate_stamping",
    "historical_replay_matrix_metadata_scaleout_plan_summary",
    "matrix_metadata_no_regime_asset_option_strategy_inference",
]


def build_signalforge_quantconnect_historical_replay_scaleout_plan(
    handoff_source: Mapping[str, Any] | None,
    *,
    max_symbols_per_batch: int = 10,
    max_days_per_batch: int = 180,
    object_store_budget_bytes_per_batch: int = 1_600_000_000,
    object_store_prefix_root: str = "signalforge/historical_replay_scaleout",
) -> dict[str, Any]:
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if not isinstance(handoff_source, Mapping):
        blocked_reasons.append("missing_handoff_source")
        handoff_source = {}

    manifest = handoff_source.get("quantconnect_replay_request_manifest")
    if not isinstance(manifest, Mapping):
        blocked_reasons.append("missing_quantconnect_replay_request_manifest")
        manifest = {}

    symbols = [str(symbol) for symbol in manifest.get("symbols", []) if str(symbol)]
    candidates = _sequence_of_mappings(manifest.get("candidates"))
    start = str(manifest.get("start") or "")
    end = str(manifest.get("end") or "")
    source_request_id = str(manifest.get("request_id") or "signalforge_qc_replay")

    if not symbols:
        blocked_reasons.append("missing_symbols")
    if not candidates:
        blocked_reasons.append("missing_candidates")
    if not start or not end:
        blocked_reasons.append("missing_date_range")

    stamped_source_candidates = _stamp_candidates_for_manifest(
        candidates,
        manifest=manifest,
        source_request_id=source_request_id,
        source_scope="source_manifest.candidates",
    )
    source_matrix_metadata_summary = _candidate_matrix_metadata_summary(stamped_source_candidates)

    if stamped_source_candidates and not source_matrix_metadata_summary.get(
        "ready_to_build_exact_matrix_edge_summary"
    ):
        warnings.append("source_candidates_stamped_with_partial_matrix_metadata")

    batches: list[dict[str, Any]] = []

    if not blocked_reasons:
        batch_number = 1
        for window_start, window_end in _date_windows(start, end, max_days_per_batch):
            for symbol_group in _chunk(symbols, max_symbols_per_batch):
                batch_candidates = [
                    candidate
                    for candidate in stamped_source_candidates
                    if str(candidate.get("symbol") or "") in symbol_group
                ]

                if not batch_candidates:
                    continue

                batch_id = f"batch_{batch_number:04d}"
                object_store_prefix = f"{object_store_prefix_root.rstrip('/')}/{batch_id}"
                batch_request_id = (
                    f"{source_request_id}_{window_start}_to_{window_end}_{len(symbol_group)}symbols_{batch_id}"
                ).replace("-", "")

                batch_candidates = _stamp_candidates_for_manifest(
                    batch_candidates,
                    manifest=manifest,
                    source_request_id=batch_request_id,
                    source_scope=f"scaleout_batch.{batch_id}.candidates",
                    replay_window_id=batch_id,
                )
                batch_matrix_metadata_summary = _candidate_matrix_metadata_summary(batch_candidates)

                batch_manifest = dict(manifest)
                batch_manifest["request_id"] = batch_request_id
                batch_manifest["start"] = window_start
                batch_manifest["end"] = window_end
                batch_manifest["symbols"] = list(symbol_group)
                batch_manifest["symbol_count"] = len(symbol_group)
                batch_manifest["candidates"] = [dict(candidate) for candidate in batch_candidates]
                batch_manifest["candidate_ids"] = [
                    str(candidate.get("candidate_id") or "") for candidate in batch_candidates
                ]
                batch_manifest["candidate_count"] = len(batch_candidates)
                batch_manifest["object_store_prefix"] = object_store_prefix
                batch_manifest["matrix_metadata_envelope_key"] = MATRIX_METADATA_KEY
                batch_manifest["matrix_metadata_candidate_summary"] = batch_matrix_metadata_summary
                batch_manifest["matrix_metadata_source_patch_state"] = (
                    "ready"
                    if batch_matrix_metadata_summary.get("ready_to_build_exact_matrix_edge_summary")
                    else "needs_review"
                )

                estimated_bytes = _estimate_object_store_bytes(
                    symbol_count=len(symbol_group),
                    candidate_count=len(batch_candidates),
                    day_count=_inclusive_day_count(window_start, window_end),
                    horizon_count=len(manifest.get("outcome_horizons", []) or []),
                    max_option_rows_per_symbol_per_day=_max_option_rows_per_symbol_per_day(manifest),
                )
                utilization = estimated_bytes / object_store_budget_bytes_per_batch
                budget_state = (
                    "within_object_store_budget"
                    if estimated_bytes <= object_store_budget_bytes_per_batch
                    else "exceeds_object_store_budget"
                )

                batches.append(
                    {
                        "batch_id": batch_id,
                        "batch_number": batch_number,
                        "request_id": batch_request_id,
                        "start": window_start,
                        "end": window_end,
                        "symbols": list(symbol_group),
                        "symbol_count": len(symbol_group),
                        "candidate_ids": batch_manifest["candidate_ids"],
                        "candidate_count": len(batch_candidates),
                        "object_store_prefix": object_store_prefix,
                        "expected_result_files": list(EXPECTED_RESULT_FILES),
                        "expected_result_file_count": len(EXPECTED_RESULT_FILES),
                        "estimated_object_store_bytes": estimated_bytes,
                        "object_store_budget_bytes": object_store_budget_bytes_per_batch,
                        "object_store_budget_utilization": round(utilization, 6),
                        "object_store_budget_utilization_pct": round(utilization * 100.0, 3),
                        "object_store_budget_state": budget_state,
                        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
                        "matrix_metadata_candidate_summary": batch_matrix_metadata_summary,
                        "matrix_metadata_source_patch_state": batch_manifest[
                            "matrix_metadata_source_patch_state"
                        ],
                        "quantconnect_replay_request_manifest": batch_manifest,
                    }
                )
                batch_number += 1

    exceeded_budget_batch_ids = [
        batch["batch_id"]
        for batch in batches
        if batch.get("object_store_budget_state") == "exceeds_object_store_budget"
    ]
    if exceeded_budget_batch_ids:
        blocked_reasons.append("one_or_more_batches_exceed_object_store_budget")

    matrix_metadata_batch_summary = _batch_matrix_metadata_summary(batches)
    if batches and matrix_metadata_batch_summary.get("needs_review_candidate_count", 0) > 0:
        warnings.append("scaleout_plan_candidates_require_matrix_metadata_backfill")

    is_ready = not blocked_reasons

    return {
        "adapter_type": "quantconnect_historical_replay_scaleout_plan_builder",
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "contract": CONTRACT,
        "status": "ready" if is_ready else "blocked",
        "is_ready": is_ready,
        "requires_manual_approval": True,
        "review_scope": "historical_replay_scaleout_plan_not_order_intent_or_execution",
        "blocked_reasons": list(dict.fromkeys(blocked_reasons)),
        "warnings": list(dict.fromkeys(warnings)),
        "covered_capabilities": [
            "quantconnect_historical_replay_scaleout_plan",
            "manual_quantconnect_replay_batch_planning",
            "object_store_budget_aware_replay_partitioning",
            "historical_replay_scaleout_not_order_intent_or_execution",
            *MATRIX_METADATA_PATCH_CAPABILITIES,
        ],
        "depends_on_capabilities": [
            "quantconnect_historical_replay_handoff",
            "quantconnect_compact_replay_script",
            "historical_replay_matrix_metadata_stamping_helpers",
        ],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        "source_artifacts": {
            "quantconnect_historical_replay_handoff_source": str(
                handoff_source.get("artifact_type") or "provided_unknown_artifact"
            )
        },
        "source_request_id": source_request_id,
        "source_start": start,
        "source_end": end,
        "source_symbol_count": len(symbols),
        "source_candidate_count": len(candidates),
        "max_symbols_per_batch": max_symbols_per_batch,
        "max_days_per_batch": max_days_per_batch,
        "object_store_budget_bytes_per_batch": object_store_budget_bytes_per_batch,
        "object_store_prefix_root": object_store_prefix_root.rstrip("/"),
        "batch_count": len(batches),
        "exceeded_budget_batch_count": len(exceeded_budget_batch_ids),
        "exceeded_budget_batch_ids": exceeded_budget_batch_ids,
        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
        "matrix_cell_key_fields": list(REQUIRED_MATRIX_METADATA_FIELDS),
        "source_matrix_metadata_candidate_summary": source_matrix_metadata_summary,
        "matrix_metadata_batch_summary": matrix_metadata_batch_summary,
        "ready_to_build_exact_matrix_edge_summary": bool(
            matrix_metadata_batch_summary.get("ready_to_build_exact_matrix_edge_summary")
        ),
        "ready_to_continue_historical_replay_scaleout": is_ready,
        "recommended_next_step": "patch_quantconnect_replay_handoff_matrix_metadata",
        "batches": batches,
        "scaleout_plan_summary": {
            "batch_count": len(batches),
            "source_symbol_count": len(symbols),
            "source_candidate_count": len(candidates),
            "max_symbols_per_batch": max_symbols_per_batch,
            "max_days_per_batch": max_days_per_batch,
            "object_store_budget_bytes_per_batch": object_store_budget_bytes_per_batch,
            "max_estimated_object_store_bytes": max(
                [batch.get("estimated_object_store_bytes", 0) for batch in batches] or [0]
            ),
            "max_object_store_budget_utilization_pct": max(
                [batch.get("object_store_budget_utilization_pct", 0.0) for batch in batches] or [0.0]
            ),
            "exceeded_budget_batch_count": len(exceeded_budget_batch_ids),
            "manual_execution_required": True,
            "matrix_metadata_batch_summary": matrix_metadata_batch_summary,
        },
        "order_intent": None,
        "broker_order_id": None,
        "portfolio_action": None,
        "position_size": None,
        "automatic_action": None,
        "automatic_close_order": None,
        "automatic_roll_order": None,
        "automatic_defense_order": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
    }


def _stamp_candidates_for_manifest(
    candidates: Sequence[Mapping[str, Any]],
    *,
    manifest: Mapping[str, Any],
    source_request_id: str,
    source_scope: str,
    replay_window_id: str | None = None,
) -> list[dict[str, Any]]:
    stamped: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        supplemental_metadata = _supplemental_candidate_metadata(
            candidate,
            manifest=manifest,
            replay_window_id=replay_window_id,
        )
        source_refs = _candidate_source_refs(
            candidate,
            supplemental_metadata=supplemental_metadata,
            source_request_id=source_request_id,
            source_scope=source_scope,
            index=index,
        )
        stamped_candidate = stamp_matrix_metadata(
            candidate,
            supplemental_metadata,
            source_refs=source_refs,
            preserve_existing=True,
        )
        stamped.append(stamped_candidate)
    return stamped


def _supplemental_candidate_metadata(
    candidate: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    replay_window_id: str | None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}

    for field in [
        "regime_state",
        "asset_behavior_state",
        "option_behavior_state",
        "strategy_id",
        "strategy_family",
        "symbol",
        "horizon_days",
        "asset_class",
        "strategy_direction",
        "risk_structure",
    ]:
        value = _first_present(candidate, [field])
        if value is not None:
            metadata[field] = value

    if "symbol" not in metadata:
        value = _first_present(candidate, ["ticker", "underlying", "underlying_symbol", "root_symbol"])
        if value is not None:
            metadata["symbol"] = value

    if "horizon_days" not in metadata:
        value = _first_present(
            candidate,
            ["horizon", "window_days", "selected_window_days", "target_horizon_days"],
        )
        if value is not None:
            metadata["horizon_days"] = value

    if "strategy_id" not in metadata:
        value = _first_present(candidate, ["strategy", "strategy_name", "setup_id", "scenario_id"])
        if value is not None:
            metadata["strategy_id"] = value

    if "strategy_family" not in metadata:
        value = _first_present(candidate, ["family", "strategy_type", "variant_id"])
        if value is not None:
            metadata["strategy_family"] = value

    if "horizon_days" not in metadata:
        singleton_horizon = _single_manifest_horizon_days(manifest)
        if singleton_horizon is not None:
            metadata["horizon_days"] = singleton_horizon

    if replay_window_id:
        metadata["replay_window_id"] = replay_window_id

    return metadata


def _candidate_source_refs(
    candidate: Mapping[str, Any],
    *,
    supplemental_metadata: Mapping[str, Any],
    source_request_id: str,
    source_scope: str,
    index: int,
) -> dict[str, Any]:
    refs: dict[str, Any] = {}
    for field, value in supplemental_metadata.items():
        if value is None:
            continue
        refs[field] = {
            "source_request_id": source_request_id,
            "source_scope": source_scope,
            "source_index": index,
            "source_field": _source_field_for_metadata_field(candidate, field),
        }
    return refs


def _source_field_for_metadata_field(candidate: Mapping[str, Any], field: str) -> str:
    if field in candidate:
        return field
    aliases = {
        "symbol": ["ticker", "underlying", "underlying_symbol", "root_symbol"],
        "horizon_days": ["horizon", "window_days", "selected_window_days", "target_horizon_days"],
        "strategy_id": ["strategy", "strategy_name", "setup_id", "scenario_id"],
        "strategy_family": ["family", "strategy_type", "variant_id"],
    }
    for alias in aliases.get(field, []):
        if alias in candidate:
            return alias
    return "manifest_singleton_or_scaleout_context"


def _candidate_matrix_metadata_summary(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    coverage = matrix_metadata_coverage(candidates)
    return {
        "candidate_count": len(candidates),
        "exact_matrix_cell_ready_candidate_count": coverage.get(
            "exact_matrix_cell_ready_record_count", 0
        ),
        "needs_review_candidate_count": coverage.get("needs_review_record_count", 0),
        "mapped_required_field_counts": dict(coverage.get("mapped_required_field_counts", {})),
        "missing_required_field_counts": dict(coverage.get("missing_required_field_counts", {})),
        "ready_to_build_exact_matrix_edge_summary": bool(
            coverage.get("ready_to_build_exact_matrix_edge_summary")
        ),
    }


def _batch_matrix_metadata_summary(batches: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    candidate_count = 0
    ready_count = 0
    needs_review_count = 0
    mapped_counts = {field: 0 for field in REQUIRED_MATRIX_METADATA_FIELDS}
    missing_counts = {field: 0 for field in REQUIRED_MATRIX_METADATA_FIELDS}

    for batch in batches:
        summary = batch.get("matrix_metadata_candidate_summary")
        if not isinstance(summary, Mapping):
            continue
        candidate_count += _as_int(summary.get("candidate_count"))
        ready_count += _as_int(summary.get("exact_matrix_cell_ready_candidate_count"))
        needs_review_count += _as_int(summary.get("needs_review_candidate_count"))
        for field, count in dict(summary.get("mapped_required_field_counts", {})).items():
            if field in mapped_counts:
                mapped_counts[field] += _as_int(count)
        for field, count in dict(summary.get("missing_required_field_counts", {})).items():
            if field in missing_counts:
                missing_counts[field] += _as_int(count)

    return {
        "batch_count": len(batches),
        "candidate_count": candidate_count,
        "exact_matrix_cell_ready_candidate_count": ready_count,
        "needs_review_candidate_count": needs_review_count,
        "mapped_required_field_counts": mapped_counts,
        "missing_required_field_counts": missing_counts,
        "ready_to_build_exact_matrix_edge_summary": candidate_count > 0 and needs_review_count == 0,
    }


def _first_present(source: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = source.get(key)
        if value is not None and value != "" and value != [] and value != {}:
            return value
    return None


def _single_manifest_horizon_days(manifest: Mapping[str, Any]) -> int | None:
    horizons = manifest.get("outcome_horizons") or manifest.get("horizons")
    if isinstance(horizons, Sequence) and not isinstance(horizons, (str, bytes, bytearray)):
        normalized = [normalize_horizon_days(value) for value in horizons]
        normalized = [value for value in normalized if value is not None]
        unique = sorted(set(normalized))
        if len(unique) == 1:
            return unique[0]
    value = manifest.get("horizon_days") or manifest.get("target_horizon_days")
    return normalize_horizon_days(value)


def _sequence_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _chunk(values: Sequence[str], size: int) -> list[list[str]]:
    size = max(int(size or 1), 1)
    return [list(values[index:index + size]) for index in range(0, len(values), size)]


def _date_windows(start: str, end: str, max_days: int) -> list[tuple[str, str]]:
    max_days = max(int(max_days or 1), 1)
    current = _parse_date(start)
    end_date = _parse_date(end)
    windows: list[tuple[str, str]] = []

    while current <= end_date:
        window_end = min(current + timedelta(days=max_days - 1), end_date)
        windows.append((current.isoformat(), window_end.isoformat()))
        current = window_end + timedelta(days=1)

    return windows


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _inclusive_day_count(start: str, end: str) -> int:
    return (_parse_date(end) - _parse_date(start)).days + 1


def _max_option_rows_per_symbol_per_day(manifest: Mapping[str, Any]) -> int:
    policy = manifest.get("option_slice_policy")
    if isinstance(policy, Mapping):
        for key in ["max_option_rows_per_symbol_per_day", "max_rows_per_symbol_per_day", "max_option_rows"]:
            try:
                return int(policy[key])
            except (KeyError, TypeError, ValueError):
                continue
    return 50


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


def _estimate_object_store_bytes(
    *,
    symbol_count: int,
    candidate_count: int,
    day_count: int,
    horizon_count: int,
    max_option_rows_per_symbol_per_day: int,
) -> int:
    market_price_bytes = symbol_count * day_count * 250
    option_row_bytes = symbol_count * day_count * max_option_rows_per_symbol_per_day * 650
    contract_outcome_bytes = candidate_count * max(horizon_count, 1) * 950
    maintenance_bytes = candidate_count * 650
    portfolio_bytes = day_count * 450
    manifest_bytes = 10_000

    return int(
        market_price_bytes
        + option_row_bytes
        + contract_outcome_bytes
        + maintenance_bytes
        + portfolio_bytes
        + manifest_bytes
    )
