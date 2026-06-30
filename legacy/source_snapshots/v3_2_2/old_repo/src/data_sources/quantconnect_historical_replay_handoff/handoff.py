from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS
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


QUANTCONNECT_HISTORICAL_REPLAY_HANDOFF_SCHEMA_VERSION = "signalforge_quantconnect_historical_replay_handoff.v1"

COVERED_CAPABILITIES = [
    "quantconnect_historical_replay_handoff",
    "quantconnect_replay_request_manifest",
    "historical_market_option_replay_contract",
    "position_maintenance_policy_replay_bridge",
    "quantconnect_handoff_not_order_intent_or_execution",
]

DEPENDS_ON_CAPABILITIES = [
    "position_maintenance_policy",
    "portfolio_construction_optimizer",
    "position_sizing_recommendation",
]

POSITION_MAINTENANCE_KEYS = (
    "ranked_position_maintenance_policies",
    "position_maintenance_policy_queue",
    "position_maintenance_policy_items",
    "items",
    "data",
    "rows",
)

DEFAULT_OUTCOME_HORIZONS = [1, 5, 10, 21, 45]
DEFAULT_RESULT_FILES = [
    "signalforge_qc_replay_manifest.json",
    "signalforge_qc_market_price_snapshots.json",
    "signalforge_qc_filtered_option_rows.json",
    "signalforge_qc_contract_outcome_snapshots.json",
    "signalforge_qc_maintenance_trigger_snapshots.json",
    "signalforge_qc_portfolio_replay_snapshots.json",
]

MATRIX_METADATA_PATCH_CAPABILITIES = [
    "historical_replay_matrix_metadata_handoff_candidate_stamping",
    "historical_replay_matrix_metadata_handoff_manifest_summary",
    "matrix_metadata_no_regime_asset_option_strategy_inference",
]


def build_signalforge_quantconnect_historical_replay_handoff(
    position_maintenance_policy_source: Mapping[str, Any] | Sequence[Any] | None,
    *,
    start: str,
    end: str,
    benchmark_symbol: str = "SPY",
    resolution: str = "Daily",
    min_dte: int = 7,
    max_dte: int = 90,
    moneyness_lower_bound: float = 0.80,
    moneyness_upper_bound: float = 1.20,
    max_spread_pct: float = 0.15,
    min_open_interest: int = 100,
    min_volume: int = 1,
    outcome_horizons: Sequence[int] | None = None,
    object_store_prefix: str = "signalforge/historical_replay",
    lean_project_name: str = "SignalForgeHistoricalReplayHandoff",
    smoke: bool = False,
) -> dict[str, Any]:
    """Build a review-only handoff contract for QuantConnect historical replay.

    The handoff does not call QuantConnect, create an order, route orders, submit
    orders, model fills/slippage, or perform live execution. It only describes the
    market/option data slices, model-policy inputs, and expected compact result
    files needed for a QuantConnect research/backtest job to produce replay data
    that SignalForge can import later.
    """

    source_artifacts = {
        "position_maintenance_policy_source": _source_artifact_type(position_maintenance_policy_source),
    }

    maintenance_items = _extract_items(position_maintenance_policy_source, POSITION_MAINTENANCE_KEYS)
    maintenance_mapping_items = [item for item in maintenance_items if isinstance(item, Mapping)]
    normalized_items = [_normalize_replay_candidate(item) for item in maintenance_mapping_items]
    normalized_items = [item for item in normalized_items if item.get("symbol")]

    parsed_start = _parse_date(start)
    parsed_end = _parse_date(end)
    blocked_reasons: list[str] = []
    if not parsed_start:
        blocked_reasons.append("invalid_replay_start_date")
    if not parsed_end:
        blocked_reasons.append("invalid_replay_end_date")
    if parsed_start and parsed_end and parsed_end < parsed_start:
        blocked_reasons.append("replay_end_before_start")
    if not normalized_items:
        blocked_reasons.append("missing_position_maintenance_policy_candidates")

    if smoke and normalized_items:
        normalized_items = sorted(normalized_items, key=lambda item: str(item.get("symbol") or ""))[:2]

    symbols = sorted({str(item.get("symbol")) for item in normalized_items if item.get("symbol")})
    if not symbols and "missing_position_maintenance_policy_candidates" not in blocked_reasons:
        blocked_reasons.append("missing_replay_symbols")

    horizons = [int(value) for value in (outcome_horizons or DEFAULT_OUTCOME_HORIZONS) if int(value) > 0]
    if not horizons:
        blocked_reasons.append("missing_outcome_horizons")
        horizons = list(DEFAULT_OUTCOME_HORIZONS)

    replay_request = _build_replay_request(
        symbols=symbols,
        candidates=normalized_items,
        start=start,
        end=end,
        benchmark_symbol=benchmark_symbol,
        resolution=resolution,
        min_dte=int(min_dte),
        max_dte=int(max_dte),
        moneyness_lower_bound=float(moneyness_lower_bound),
        moneyness_upper_bound=float(moneyness_upper_bound),
        max_spread_pct=float(max_spread_pct),
        min_open_interest=int(min_open_interest),
        min_volume=int(min_volume),
        outcome_horizons=horizons,
        object_store_prefix=str(object_store_prefix).rstrip("/"),
        lean_project_name=str(lean_project_name),
        smoke=bool(smoke),
    )

    normalized_items = _stamp_handoff_candidates(
        normalized_items,
        source_request_id=str(replay_request.get("request_id") or "signalforge_qc_replay"),
        source_scope="quantconnect_historical_replay_handoff.candidates",
        manifest=replay_request,
    )
    replay_request["candidates"] = [dict(item) for item in normalized_items]
    replay_request["candidate_ids"] = [str(item.get("candidate_id") or item.get("symbol") or "") for item in normalized_items]
    replay_request["candidate_count"] = len(normalized_items)

    matrix_metadata_candidate_summary = _candidate_matrix_metadata_summary(normalized_items)
    replay_request["matrix_metadata_envelope_key"] = MATRIX_METADATA_KEY
    replay_request["matrix_cell_key_fields"] = list(REQUIRED_MATRIX_METADATA_FIELDS)
    replay_request["matrix_metadata_candidate_summary"] = matrix_metadata_candidate_summary
    replay_request["matrix_metadata_source_patch_state"] = (
        "ready"
        if matrix_metadata_candidate_summary.get("ready_to_build_exact_matrix_edge_summary")
        else "needs_review"
    )

    result_contract = _build_result_contract(replay_request)
    summary = _summary(candidates=normalized_items, replay_request=replay_request, blocked_reasons=blocked_reasons)
    status = "ready" if not blocked_reasons else "blocked"

    return {
        "artifact_type": "signalforge_quantconnect_historical_replay_handoff",
        "schema_version": QUANTCONNECT_HISTORICAL_REPLAY_HANDOFF_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "quantconnect_historical_replay_handoff",
        "adapter_type": "quantconnect_historical_replay_handoff_builder",
        "review_scope": "quantconnect_historical_replay_handoff_not_order_intent_or_execution",
        "source_artifacts": source_artifacts,
        "covered_capabilities": [*COVERED_CAPABILITIES, *MATRIX_METADATA_PATCH_CAPABILITIES],
        "depends_on_capabilities": [
            *DEPENDS_ON_CAPABILITIES,
            "historical_replay_matrix_metadata_stamping_helpers",
        ],
        "next_build_recommendations": [
            {
                "capability": "quantconnect_replay_result_import_validator",
                "priority": "high",
                "recommendation": "Import and validate compact QuantConnect replay result files before historical edge analysis.",
            }
        ],
        "replay_mode": "smoke" if smoke else "research_replay",
        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
        "matrix_cell_key_fields": list(REQUIRED_MATRIX_METADATA_FIELDS),
        "matrix_metadata_candidate_summary": matrix_metadata_candidate_summary,
        "ready_to_build_exact_matrix_edge_summary": bool(
            matrix_metadata_candidate_summary.get("ready_to_build_exact_matrix_edge_summary")
        ),
        "ready_to_continue_historical_replay_handoff": status == "ready",
        "recommended_next_step": "patch_quantconnect_cloud_replay_batch_runner_matrix_metadata",
        "quantconnect_replay_candidates": normalized_items,
        "quantconnect_replay_request_manifest": replay_request,
        "quantconnect_result_contract": result_contract,
        "lean_workspace_instructions": _lean_workspace_instructions(replay_request),
        "quantconnect_historical_replay_handoff_summary": summary,
        "blocked_reasons": blocked_reasons,
        "portfolio_action": None,
        "position_size": None,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "automatic_close_order": None,
        "automatic_roll_order": None,
        "automatic_defense_order": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_replay_request(
    *,
    symbols: list[str],
    candidates: list[dict[str, Any]],
    start: str,
    end: str,
    benchmark_symbol: str,
    resolution: str,
    min_dte: int,
    max_dte: int,
    moneyness_lower_bound: float,
    moneyness_upper_bound: float,
    max_spread_pct: float,
    min_open_interest: int,
    min_volume: int,
    outcome_horizons: list[int],
    object_store_prefix: str,
    lean_project_name: str,
    smoke: bool,
) -> dict[str, Any]:
    candidate_ids = [str(item.get("candidate_id") or item.get("symbol")) for item in candidates]
    request_id = f"signalforge_qc_replay_{_safe_date_token(start)}_to_{_safe_date_token(end)}_{len(symbols)}symbols"
    return {
        "artifact_type": "signalforge_quantconnect_historical_replay_request_manifest",
        "schema_version": "signalforge_quantconnect_historical_replay_request_manifest.v1",
        "request_id": request_id,
        "mode": "smoke" if smoke else "research_replay",
        "lean_project_name": lean_project_name,
        "symbols": symbols,
        "symbol_count": len(symbols),
        "candidate_ids": candidate_ids,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "start": start,
        "end": end,
        "benchmark_symbol": _clean_symbol(benchmark_symbol) or "SPY",
        "resolution": str(resolution or "Daily"),
        "data_requirements": {
            "market_price_history": True,
            "filtered_option_rows": True,
            "contract_mark_price_timeseries": True,
            "underlying_forward_returns": True,
            "maintenance_trigger_snapshots": True,
            "portfolio_replay_snapshots": True,
        },
        "option_slice_policy": {
            "row_policy": "filtered_relevant_rows_not_all_raw_chain_rows",
            "min_dte": min_dte,
            "max_dte": max_dte,
            "moneyness_lower_bound": moneyness_lower_bound,
            "moneyness_upper_bound": moneyness_upper_bound,
            "max_spread_pct": max_spread_pct,
            "min_open_interest": min_open_interest,
            "min_volume": min_volume,
        },
        "outcome_horizons": outcome_horizons,
        "maintenance_evaluation_policy": {
            "evaluate_hold_review": True,
            "evaluate_take_profit_review": True,
            "evaluate_risk_cut_review": True,
            "evaluate_delta_drift_review": True,
            "evaluate_gamma_review": True,
            "evaluate_theta_review": True,
            "evaluate_vega_review": True,
            "evaluate_dte_review": True,
            "automatic_close_order": None,
            "automatic_roll_order": None,
            "automatic_defense_order": None,
        },
        "object_store_prefix": object_store_prefix,
        "expected_object_store_keys": [f"{object_store_prefix.rstrip('/')}/{name}" for name in DEFAULT_RESULT_FILES],
        "execution_policy": {
            "submit_orders": False,
            "route_orders": False,
            "model_fills": False,
            "model_slippage": False,
            "live_execution": False,
            "produce_compact_replay_results_only": True,
        },
    }


def _build_result_contract(replay_request: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_quantconnect_historical_replay_result_contract",
        "schema_version": "signalforge_quantconnect_historical_replay_result_contract.v1",
        "expected_result_files": list(DEFAULT_RESULT_FILES),
        "expected_result_file_count": len(DEFAULT_RESULT_FILES),
        "required_top_level_result_keys": [
            "artifact_type",
            "schema_version",
            "request_id",
            "as_of_run_time",
            "symbol_count",
            "candidate_count",
            "status",
        ],
        "required_replay_tables": {
            "market_price_snapshots": ["symbol", "date", "open", "high", "low", "close", "volume"],
            "filtered_option_rows": [
                "underlying_symbol",
                "quote_date",
                "expiration",
                "strike",
                "option_right",
                "bid",
                "ask",
                "implied_volatility",
                "delta",
                "gamma",
                "theta",
                "vega",
                "open_interest",
                "volume",
                "underlying_price",
                "matrix_metadata",
                "matrix_metadata_state",
                "matrix_cell_key",
            ],
            "contract_outcome_snapshots": [
                "symbol",
                "candidate_id",
                "quote_date",
                "horizon_days",
                "underlying_forward_return",
                "contract_mark_return",
                "max_adverse_excursion",
                "max_favorable_excursion",
                "matrix_metadata",
                "matrix_metadata_state",
                "matrix_cell_key",
            ],
            "maintenance_trigger_snapshots": [
                "symbol",
                "candidate_id",
                "date",
                "trigger_type",
                "trigger_state",
                "trigger_value",
                "matrix_metadata",
                "matrix_metadata_state",
                "matrix_cell_key",
            ],
            "portfolio_replay_snapshots": [
                "date",
                "candidate_count",
                "net_delta",
                "gross_abs_delta",
                "gross_abs_gamma",
                "gross_abs_vega",
                "net_theta",
            ],
        },
        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
        "matrix_cell_key_fields": list(REQUIRED_MATRIX_METADATA_FIELDS),
        "request_id": replay_request.get("request_id"),
        "object_store_prefix": replay_request.get("object_store_prefix"),
        "expected_object_store_keys": list(replay_request.get("expected_object_store_keys") or []),
    }


def _lean_workspace_instructions(replay_request: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "run_context": "quantconnect_lean_workspace",
        "lean_workspace_path_hint": "C:\\Users\\02011715\\Documents\\SignalForge\\lean_workspace",
        "signalforge_workspace_path_hint": "C:\\Users\\02011715\\Documents\\SignalForge\\raw_data_layer",
        "project_name": replay_request.get("lean_project_name"),
        "manual_steps": [
            "Copy the generated quantconnect_replay_request_manifest.json into the QuantConnect project or Object Store input path.",
            "Run the QuantConnect research/backtest job that reads the manifest and writes compact replay result files.",
            "Copy compact replay result JSON files back into raw_data_layer for import validation.",
        ],
        "not_in_scope": [
            "broker_api_calls",
            "order_routing",
            "order_submission",
            "fills",
            "live_execution",
            "slippage_modeling",
        ],
    }


def _normalize_replay_candidate(item: Mapping[str, Any]) -> dict[str, Any]:
    symbol = _clean_symbol(_first_value(item, ("symbol", "underlying_symbol", "ticker")))
    status = _clean_text(_first_value(item, ("position_maintenance_status", "coverage_status", "source_status")))
    strategy_family = _clean_text(_first_value(item, ("strategy_family", "selected_strategy_family", "recommended_strategy_family")))
    strategy_id = _clean_text(_first_value(item, ("strategy_id", "strategy", "strategy_name", "setup_id", "scenario_id")))
    candidate_id = _clean_text(_first_value(item, ("candidate_id", "contract_candidate_id", "portfolio_candidate_id")))
    if not candidate_id and symbol:
        candidate_id = f"{symbol}_historical_replay_candidate"

    normalized = {
        "candidate_id": candidate_id,
        "symbol": symbol,
        "source_status": status,
        "strategy_id": strategy_id or None,
        "strategy_family": strategy_family or None,
        "position_maintenance_score": _safe_float(item.get("position_maintenance_score")),
        "recommended_risk_budget_dollars": _safe_float(item.get("recommended_risk_budget_dollars")),
        "recommended_risk_budget_pct": _safe_float(item.get("recommended_risk_budget_pct")),
        "top_contract_symbol": _clean_text(_first_value(item, ("top_contract_symbol", "option_symbol", "contract_symbol"))),
        "top_contract_delta": _safe_float(_first_value(item, ("top_contract_delta", "delta"))),
        "top_contract_gamma": _safe_float(_first_value(item, ("top_contract_gamma", "gamma"))),
        "top_contract_theta": _safe_float(_first_value(item, ("top_contract_theta", "theta"))),
        "top_contract_vega": _safe_float(_first_value(item, ("top_contract_vega", "vega"))),
        "risk_flags": _merged_list(item.get("risk_flags")),
        "constraint_flags": _merged_list(item.get("constraint_flags")),
        "maintenance_review_flags": _merged_list(item.get("maintenance_review_flags")),
        "data_review_reasons": _merged_list(item.get("data_review_reasons")),
        "hard_block_reasons": _merged_list(item.get("hard_block_reasons")),
    }

    for field in [
        "regime_state",
        "asset_behavior_state",
        "option_behavior_state",
        "horizon_days",
        "asset_class",
        "strategy_direction",
        "risk_structure",
    ]:
        value = _first_value(item, (field,))
        if value is not None:
            normalized[field] = value

    if "horizon_days" not in normalized:
        value = _first_value(item, ("horizon", "window_days", "selected_window_days", "target_horizon_days"))
        if value is not None:
            normalized["horizon_days"] = value

    return normalized


def _stamp_handoff_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    source_request_id: str,
    source_scope: str,
    manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    stamped: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        supplemental_metadata = _supplemental_candidate_metadata(candidate, manifest=manifest)
        source_refs = _candidate_source_refs(
            candidate,
            supplemental_metadata=supplemental_metadata,
            source_request_id=source_request_id,
            source_scope=source_scope,
            index=index,
        )
        stamped.append(
            stamp_matrix_metadata(
                candidate,
                supplemental_metadata,
                source_refs=source_refs,
                preserve_existing=True,
            )
        )
    return stamped


def _supplemental_candidate_metadata(
    candidate: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
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
    return "manifest_singleton_or_handoff_context"


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


def _summary(
    *,
    candidates: Sequence[Mapping[str, Any]],
    replay_request: Mapping[str, Any],
    blocked_reasons: Sequence[str],
) -> dict[str, Any]:
    symbols = sorted({str(item.get("symbol")) for item in candidates if item.get("symbol")})
    strategy_counts = Counter(str(item.get("strategy_family") or "unknown_strategy_family") for item in candidates)
    status_counts = Counter(str(item.get("source_status") or "unknown") for item in candidates)
    risk_flag_counts = Counter(flag for item in candidates for flag in _merged_list(item.get("risk_flags")))
    constraint_flag_counts = Counter(flag for item in candidates for flag in _merged_list(item.get("constraint_flags")))
    data_review_reason_counts = Counter(flag for item in candidates for flag in _merged_list(item.get("data_review_reasons")))
    hard_block_reason_counts = Counter(flag for item in candidates for flag in _merged_list(item.get("hard_block_reasons")))

    return {
        "covered_capabilities": [*COVERED_CAPABILITIES, *MATRIX_METADATA_PATCH_CAPABILITIES],
        "depends_on_capabilities": [
            *DEPENDS_ON_CAPABILITIES,
            "historical_replay_matrix_metadata_stamping_helpers",
        ],
        "status_counts": dict(sorted(status_counts.items())),
        "strategy_family_counts": dict(sorted(strategy_counts.items())),
        "risk_flag_counts": dict(sorted(risk_flag_counts.items())),
        "constraint_flag_counts": dict(sorted(constraint_flag_counts.items())),
        "data_review_reason_counts": dict(sorted(data_review_reason_counts.items())),
        "hard_block_reason_counts": dict(sorted(hard_block_reason_counts.items())),
        "blocked_reason_counts": dict(sorted(Counter(blocked_reasons).items())),
        "symbol_count": len(symbols),
        "symbols": symbols,
        "replay_candidate_count": len(candidates),
        "replay_start": replay_request.get("start"),
        "replay_end": replay_request.get("end"),
        "benchmark_symbol": replay_request.get("benchmark_symbol"),
        "outcome_horizon_count": len(replay_request.get("outcome_horizons") or []),
        "expected_result_file_count": len(replay_request.get("expected_object_store_keys") or []),
        "expected_object_store_key_count": len(replay_request.get("expected_object_store_keys") or []),
        "option_slice_policy": replay_request.get("option_slice_policy"),
        "execution_policy": replay_request.get("execution_policy"),
        "matrix_metadata_envelope_key": replay_request.get("matrix_metadata_envelope_key"),
        "matrix_cell_key_fields": replay_request.get("matrix_cell_key_fields"),
        "matrix_metadata_candidate_summary": replay_request.get("matrix_metadata_candidate_summary"),
        "matrix_metadata_source_patch_state": replay_request.get("matrix_metadata_source_patch_state"),
    }


def _extract_items(source: Mapping[str, Any] | Sequence[Any] | None, keys: Sequence[str]) -> list[Any]:
    if source is None:
        return []
    if isinstance(source, Mapping):
        for key in keys:
            value = source.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                return list(value)
        summary = source.get("summary") if isinstance(source.get("summary"), Mapping) else None
        if summary:
            for key in keys:
                value = summary.get(key)
                if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                    return list(value)
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return list(source)
    return []


def _source_artifact_type(source: Any) -> str:
    if isinstance(source, Mapping):
        return str(source.get("artifact_type") or "mapping")
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return "sequence"
    return "missing"


def _first_value(item: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = item.get(key)
        if value is not None:
            return value
    return None


def _clean_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _safe_date_token(value: Any) -> str:
    text = str(value or "").strip()[:10]
    return text.replace("-", "") if text else "unknown"


def _merged_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(item) for item in value if str(item)]
    return [str(value)] if str(value) else []
