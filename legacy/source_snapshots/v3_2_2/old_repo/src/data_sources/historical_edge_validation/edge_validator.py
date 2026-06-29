from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from statistics import mean
from typing import Any

from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS
from src.strategy_selection.historical_replay_matrix_metadata_stamp import (
    MATRIX_METADATA_KEY,
    REQUIRED_MATRIX_METADATA_FIELDS,
    matrix_metadata_coverage,
    validate_matrix_metadata_record,
)


HISTORICAL_EDGE_VALIDATION_SCHEMA_VERSION = "signalforge_historical_edge_validation.v1"

COVERED_CAPABILITIES = [
    "historical_edge_validation",
    "quantconnect_replay_result_edge_analysis",
    "contract_outcome_edge_summary",
    "portfolio_replay_edge_summary",
    "maintenance_trigger_edge_summary",
    "historical_edge_validation_not_order_intent_or_execution",
]

DEPENDS_ON_CAPABILITIES = [
    "quantconnect_replay_result_import_validator",
    "quantconnect_historical_replay_handoff",
    "position_maintenance_policy",
]

REQUIRED_TABLES = [
    "replay_manifest",
    "market_price_snapshots",
    "filtered_option_rows",
    "contract_outcome_snapshots",
    "maintenance_trigger_snapshots",
    "portfolio_replay_snapshots",
]


def build_signalforge_historical_edge_validation(
    import_validation_source: Mapping[str, Any] | None,
    replay_result_sources: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Measure historical edge from validated compact QuantConnect replay results.

    This module consumes already-imported compact QuantConnect replay outputs and
    summarizes realized contract outcomes, portfolio replay exposure, and
    maintenance-trigger behavior. It does not call QuantConnect, submit orders,
    route orders, model fills/slippage, or execute anything live.
    """

    replay_sources = replay_result_sources or {}
    blocked_reasons: list[str] = []

    if not isinstance(import_validation_source, Mapping):
        blocked_reasons.append("missing_quantconnect_replay_result_import_validation_source")
    elif import_validation_source.get("is_ready") is not True:
        blocked_reasons.append("quantconnect_replay_result_import_validation_not_ready")

    table_rows = _extract_replay_tables(replay_sources)
    table_row_counts = {name: len(rows) for name, rows in table_rows.items()}

    contract_outcomes = table_rows["contract_outcome_snapshots"]
    portfolio_snapshots = table_rows["portfolio_replay_snapshots"]
    market_snapshots = table_rows["market_price_snapshots"]
    option_rows = table_rows["filtered_option_rows"]
    maintenance_triggers = table_rows["maintenance_trigger_snapshots"]

    if not contract_outcomes:
        blocked_reasons.append("empty_contract_outcome_snapshots")
    if not portfolio_snapshots:
        blocked_reasons.append("empty_portfolio_replay_snapshots")
    if not market_snapshots:
        blocked_reasons.append("empty_market_price_snapshots")
    if not option_rows:
        blocked_reasons.append("empty_filtered_option_rows")

    outcome_summary = _contract_outcome_summary(contract_outcomes)
    matrix_metadata_summary = _matrix_metadata_validation_summary(contract_outcomes)
    portfolio_summary = _portfolio_replay_summary(portfolio_snapshots)
    maintenance_summary = _maintenance_trigger_summary(maintenance_triggers)
    replay_summary = _source_replay_summary(import_validation_source)

    status = "ready" if not blocked_reasons else "blocked"
    summary = _summary(
        status=status,
        blocked_reasons=blocked_reasons,
        table_row_counts=table_row_counts,
        replay_summary=replay_summary,
        outcome_summary=outcome_summary,
        matrix_metadata_summary=matrix_metadata_summary,
        portfolio_summary=portfolio_summary,
        maintenance_summary=maintenance_summary,
    )

    return _normalize_historical_edge_validation_root_fields({
        "artifact_type": "signalforge_historical_edge_validation",
        "schema_version": HISTORICAL_EDGE_VALIDATION_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "historical_edge_validation",
        "adapter_type": "historical_edge_validation_builder",
        "review_scope": "historical_edge_validation_not_order_intent_or_execution",
        "source_artifacts": {
            "quantconnect_replay_result_import_validation_source": _source_artifact_type(import_validation_source),
        },
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "next_build_recommendations": [
            {
                "capability": "historical_replay_scaleout",
                "priority": "high",
                "recommendation": "Expand the QuantConnect replay across more dates, symbols, regimes, and option candidates before using results for live workflow design.",
            }
        ],
        "historical_edge_validation_summary": summary,
        "contract_outcome_edge_summary": outcome_summary,
        "matrix_metadata_validation_summary": matrix_metadata_summary,
        "ready_to_build_exact_matrix_edge_summary": matrix_metadata_summary.get("ready_to_build_exact_matrix_edge_summary", False),
        "recommended_next_step": matrix_metadata_summary.get("recommended_next_step"),
        "portfolio_replay_edge_summary": portfolio_summary,
        "maintenance_trigger_edge_summary": maintenance_summary,
        "table_row_counts": table_row_counts,
        "blocked_reasons": list(dict.fromkeys(blocked_reasons)),
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
    })


def _extract_replay_tables(replay_sources: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    return {
        "replay_manifest": _rows_from_payload(replay_sources.get("signalforge_qc_replay_manifest.json"), "replay_manifest"),
        "market_price_snapshots": _rows_from_payload(
            replay_sources.get("signalforge_qc_market_price_snapshots.json"), "market_price_snapshots"
        ),
        "filtered_option_rows": _rows_from_payload(
            replay_sources.get("signalforge_qc_filtered_option_rows.json"), "filtered_option_rows"
        ),
        "contract_outcome_snapshots": _rows_from_payload(
            replay_sources.get("signalforge_qc_contract_outcome_snapshots.json"), "contract_outcome_snapshots"
        ),
        "maintenance_trigger_snapshots": _rows_from_payload(
            replay_sources.get("signalforge_qc_maintenance_trigger_snapshots.json"), "maintenance_trigger_snapshots"
        ),
        "portfolio_replay_snapshots": _rows_from_payload(
            replay_sources.get("signalforge_qc_portfolio_replay_snapshots.json"), "portfolio_replay_snapshots"
        ),
    }


def _rows_from_payload(payload: Any, table_name: str) -> list[Mapping[str, Any]]:
    if payload is None:
        return []
    if table_name == "replay_manifest" and isinstance(payload, Mapping):
        return [payload]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    for key in (table_name, "rows", "data", "items"):
        value = payload.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [row for row in value if isinstance(row, Mapping)]
    return []


def _strategy_adjustment_policy(row: Mapping[str, Any]) -> str:
    strategy_family = str(row.get("strategy_family") or "").strip().lower()

    if strategy_family == "defined_risk_short_premium":
        return "invert_short_premium_contract_mark"

    return "raw_contract_mark"


def _strategy_adjusted_outcome_values(row: Mapping[str, Any]) -> dict[str, float]:
    raw_return = _safe_float(row.get("contract_mark_return"))
    raw_adverse = _safe_float(row.get("max_adverse_excursion"))
    raw_favorable = _safe_float(row.get("max_favorable_excursion"))

    if _strategy_adjustment_policy(row) == "invert_short_premium_contract_mark":
        return {
            "strategy_adjusted_return": -raw_return,
            "strategy_adjusted_max_adverse_excursion": -raw_favorable,
            "strategy_adjusted_max_favorable_excursion": -raw_adverse,
        }

    return {
        "strategy_adjusted_return": raw_return,
        "strategy_adjusted_max_adverse_excursion": raw_adverse,
        "strategy_adjusted_max_favorable_excursion": raw_favorable,
    }


def _contract_outcome_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    raw_returns = [_safe_float(row.get("contract_mark_return")) for row in rows]
    underlying_returns = [_safe_float(row.get("underlying_forward_return")) for row in rows]
    raw_adverse = [_safe_float(row.get("max_adverse_excursion")) for row in rows]
    raw_favorable = [_safe_float(row.get("max_favorable_excursion")) for row in rows]

    adjusted_values = [_strategy_adjusted_outcome_values(row) for row in rows]
    strategy_returns = [value["strategy_adjusted_return"] for value in adjusted_values]
    strategy_adverse = [value["strategy_adjusted_max_adverse_excursion"] for value in adjusted_values]
    strategy_favorable = [value["strategy_adjusted_max_favorable_excursion"] for value in adjusted_values]

    positive_count = len([value for value in strategy_returns if value > 0])
    negative_count = len([value for value in strategy_returns if value < 0])
    flat_count = len([value for value in strategy_returns if value == 0])

    raw_positive_count = len([value for value in raw_returns if value > 0])
    raw_negative_count = len([value for value in raw_returns if value < 0])
    raw_flat_count = len([value for value in raw_returns if value == 0])

    row_count = len(rows)
    win_rate = positive_count / row_count if row_count else 0.0
    raw_contract_win_rate = raw_positive_count / row_count if row_count else 0.0

    average_contract_mark_return = _mean(raw_returns)
    average_strategy_adjusted_return = _mean(strategy_returns)
    average_underlying_forward_return = _mean(underlying_returns)

    average_max_adverse_excursion = _mean(raw_adverse)
    average_max_favorable_excursion = _mean(raw_favorable)
    average_strategy_adjusted_max_adverse_excursion = _mean(strategy_adverse)
    average_strategy_adjusted_max_favorable_excursion = _mean(strategy_favorable)

    by_symbol: dict[str, list[float]] = defaultdict(list)
    by_horizon: dict[str, list[float]] = defaultdict(list)
    raw_by_symbol: dict[str, list[float]] = defaultdict(list)
    raw_by_horizon: dict[str, list[float]] = defaultdict(list)

    horizon_counts: Counter[str] = Counter()
    symbol_counts: Counter[str] = Counter()
    strategy_family_counts: Counter[str] = Counter()
    strategy_adjustment_policy_counts: Counter[str] = Counter()

    for row, raw_value, strategy_value in zip(rows, raw_returns, strategy_returns, strict=False):
        symbol = str(row.get("symbol") or "unknown")
        horizon = str(row.get("horizon_days") or "unknown")
        strategy_family = str(row.get("strategy_family") or "unspecified")
        policy = _strategy_adjustment_policy(row)

        by_symbol[symbol].append(strategy_value)
        by_horizon[horizon].append(strategy_value)
        raw_by_symbol[symbol].append(raw_value)
        raw_by_horizon[horizon].append(raw_value)

        symbol_counts[symbol] += 1
        horizon_counts[horizon] += 1
        strategy_family_counts[strategy_family] += 1
        strategy_adjustment_policy_counts[policy] += 1

    average_return_by_symbol = {
        symbol: _round(_mean(values)) for symbol, values in sorted(by_symbol.items())
    }
    average_return_by_horizon = {
        horizon: _round(_mean(values)) for horizon, values in sorted(by_horizon.items())
    }
    average_contract_mark_return_by_symbol = {
        symbol: _round(_mean(values)) for symbol, values in sorted(raw_by_symbol.items())
    }
    average_contract_mark_return_by_horizon = {
        horizon: _round(_mean(values)) for horizon, values in sorted(raw_by_horizon.items())
    }

    positive_horizon_count = len([value for value in average_return_by_horizon.values() if value > 0])
    negative_horizon_count = len([value for value in average_return_by_horizon.values() if value < 0])

    raw_positive_horizon_count = len(
        [value for value in average_contract_mark_return_by_horizon.values() if value > 0]
    )
    raw_negative_horizon_count = len(
        [value for value in average_contract_mark_return_by_horizon.values() if value < 0]
    )

    historical_edge_score = _historical_edge_score(
        average_contract_mark_return=average_strategy_adjusted_return,
        win_rate=win_rate,
        average_max_adverse_excursion=average_strategy_adjusted_max_adverse_excursion,
    )

    return {
        "contract_outcome_count": row_count,
        "symbol_count": len(symbol_counts),
        "horizon_count": len(horizon_counts),

        "positive_outcome_count": positive_count,
        "negative_outcome_count": negative_count,
        "flat_outcome_count": flat_count,
        "win_rate": _round(win_rate),

        "strategy_adjusted_positive_outcome_count": positive_count,
        "strategy_adjusted_negative_outcome_count": negative_count,
        "strategy_adjusted_flat_outcome_count": flat_count,
        "strategy_adjusted_win_rate": _round(win_rate),

        "raw_positive_contract_mark_return_count": raw_positive_count,
        "raw_negative_contract_mark_return_count": raw_negative_count,
        "raw_flat_contract_mark_return_count": raw_flat_count,
        "raw_contract_mark_win_rate": _round(raw_contract_win_rate),

        "average_contract_mark_return": _round(average_contract_mark_return),
        "average_strategy_adjusted_return": _round(average_strategy_adjusted_return),
        "average_underlying_forward_return": _round(average_underlying_forward_return),

        "average_max_adverse_excursion": _round(average_max_adverse_excursion),
        "average_max_favorable_excursion": _round(average_max_favorable_excursion),
        "average_strategy_adjusted_max_adverse_excursion": _round(
            average_strategy_adjusted_max_adverse_excursion
        ),
        "average_strategy_adjusted_max_favorable_excursion": _round(
            average_strategy_adjusted_max_favorable_excursion
        ),

        "average_return_by_symbol": average_return_by_symbol,
        "average_return_by_horizon": average_return_by_horizon,
        "average_contract_mark_return_by_symbol": average_contract_mark_return_by_symbol,
        "average_contract_mark_return_by_horizon": average_contract_mark_return_by_horizon,

        "horizon_counts": dict(sorted(horizon_counts.items())),
        "symbol_counts": dict(sorted(symbol_counts.items())),
        "strategy_family_counts": dict(sorted(strategy_family_counts.items())),
        "strategy_adjustment_policy_counts": dict(sorted(strategy_adjustment_policy_counts.items())),

        "positive_horizon_count": positive_horizon_count,
        "negative_horizon_count": negative_horizon_count,
        "raw_positive_horizon_count": raw_positive_horizon_count,
        "raw_negative_horizon_count": raw_negative_horizon_count,

        "historical_edge_score": _round(historical_edge_score),
        "historical_edge_state": _historical_edge_state(
            average_contract_mark_return=average_strategy_adjusted_return,
            win_rate=win_rate,
            historical_edge_score=historical_edge_score,
        ),
    }


def _matrix_metadata_validation_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize matrix metadata coverage on contract outcome rows.

    This is an attribution gate only. It does not infer missing regime,
    asset-behavior, option-behavior, strategy, symbol, or horizon values and it
    does not change historical edge scoring.
    """

    coverage = matrix_metadata_coverage(rows)
    cell_counts: Counter[str] = Counter()
    missing_field_counts: Counter[str] = Counter()
    blocked_reason_counts: Counter[str] = Counter()

    for row in rows:
        validation = validate_matrix_metadata_record(row)
        cell_key = validation.get("matrix_cell_key")
        if cell_key:
            cell_counts[str(cell_key)] += 1
        for field in validation.get("matrix_metadata_missing_fields") or []:
            missing_field_counts[str(field)] += 1
        for reason in validation.get("blocked_reasons") or []:
            blocked_reason_counts[str(reason)] += 1

    ready_count = int(coverage.get("exact_matrix_cell_ready_record_count") or 0)
    needs_review_count = int(coverage.get("needs_review_record_count") or 0)
    ready_to_build = bool(coverage.get("ready_to_build_exact_matrix_edge_summary"))

    if not rows:
        state = "blocked"
        recommended_next_step = "provide_contract_outcome_snapshots_with_matrix_metadata"
    elif ready_to_build:
        state = "ready"
        recommended_next_step = "patch_historical_edge_validation_multi_window_summary_matrix_metadata"
    else:
        state = "needs_review"
        recommended_next_step = "ensure_quantconnect_replay_results_include_matrix_metadata_envelope"

    return {
        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
        "matrix_cell_key_fields": list(REQUIRED_MATRIX_METADATA_FIELDS),
        "matrix_metadata_state": state,
        "contract_outcome_count": len(rows),
        "exact_matrix_cell_ready_record_count": ready_count,
        "needs_review_record_count": needs_review_count,
        "ready_to_build_exact_matrix_edge_summary": ready_to_build,
        "mapped_required_field_counts": coverage.get("mapped_required_field_counts", {}),
        "missing_required_field_counts": coverage.get("missing_required_field_counts", {}),
        "missing_field_counts": dict(sorted(missing_field_counts.items())),
        "matrix_cell_count": len(cell_counts),
        "matrix_cell_counts": dict(sorted(cell_counts.items())),
        "blocked_reason_counts": dict(sorted(blocked_reason_counts.items())),
        "recommended_next_step": recommended_next_step,
    }


def _portfolio_replay_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    net_delta_values = [_safe_float(row.get("net_delta")) for row in rows]
    gross_abs_delta_values = [_safe_float(row.get("gross_abs_delta")) for row in rows]
    gross_abs_gamma_values = [_safe_float(row.get("gross_abs_gamma")) for row in rows]
    gross_abs_vega_values = [_safe_float(row.get("gross_abs_vega")) for row in rows]
    net_theta_values = [_safe_float(row.get("net_theta")) for row in rows]
    candidate_counts = [_safe_float(row.get("candidate_count")) for row in rows]

    return {
        "portfolio_replay_snapshot_count": len(rows),
        "average_candidate_count": _round(_mean(candidate_counts)),
        "average_net_delta": _round(_mean(net_delta_values)),
        "max_abs_net_delta": _round(max([abs(value) for value in net_delta_values], default=0.0)),
        "average_gross_abs_delta": _round(_mean(gross_abs_delta_values)),
        "max_gross_abs_delta": _round(max(gross_abs_delta_values, default=0.0)),
        "average_gross_abs_gamma": _round(_mean(gross_abs_gamma_values)),
        "max_gross_abs_gamma": _round(max(gross_abs_gamma_values, default=0.0)),
        "average_gross_abs_vega": _round(_mean(gross_abs_vega_values)),
        "max_gross_abs_vega": _round(max(gross_abs_vega_values, default=0.0)),
        "average_net_theta": _round(_mean(net_theta_values)),
    }


def _maintenance_trigger_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    trigger_type_counts: Counter[str] = Counter()
    trigger_state_counts: Counter[str] = Counter()
    triggered_count = 0
    for row in rows:
        trigger_type = str(row.get("trigger_type") or "unknown")
        trigger_state = str(row.get("trigger_state") or "unknown")
        trigger_type_counts[trigger_type] += 1
        trigger_state_counts[trigger_state] += 1
        if trigger_state == "triggered":
            triggered_count += 1

    return {
        "maintenance_trigger_snapshot_count": len(rows),
        "triggered_count": triggered_count,
        "not_triggered_count": len(rows) - triggered_count,
        "trigger_rate": _round(triggered_count / len(rows)) if rows else 0.0,
        "trigger_type_counts": dict(sorted(trigger_type_counts.items())),
        "trigger_state_counts": dict(sorted(trigger_state_counts.items())),
    }


def _summary(
    *,
    status: str,
    blocked_reasons: Sequence[str],
    table_row_counts: Mapping[str, int],
    replay_summary: Mapping[str, Any],
    outcome_summary: Mapping[str, Any],
    portfolio_summary: Mapping[str, Any],
    matrix_metadata_summary: Mapping[str, Any],
    maintenance_summary: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "status": status,
        "is_ready": status == "ready",
        "request_id": replay_summary.get("request_id"),
        "symbol_count": _safe_int(replay_summary.get("symbol_count")),
        "replay_candidate_count": _safe_int(replay_summary.get("replay_candidate_count")),
        "replay_start": replay_summary.get("replay_start"),
        "replay_end": replay_summary.get("replay_end"),
        "table_row_counts": dict(sorted(table_row_counts.items())),
        "contract_outcome_count": outcome_summary.get("contract_outcome_count", 0),
        "matrix_metadata_validation_summary": dict(matrix_metadata_summary),
        "exact_matrix_cell_ready_record_count": matrix_metadata_summary.get("exact_matrix_cell_ready_record_count", 0),
        "matrix_metadata_needs_review_record_count": matrix_metadata_summary.get("needs_review_record_count", 0),
        "ready_to_build_exact_matrix_edge_summary": matrix_metadata_summary.get("ready_to_build_exact_matrix_edge_summary", False),
        "portfolio_replay_snapshot_count": portfolio_summary.get("portfolio_replay_snapshot_count", 0),
        "maintenance_trigger_snapshot_count": maintenance_summary.get("maintenance_trigger_snapshot_count", 0),
        "win_rate": outcome_summary.get("win_rate", 0.0),
        "strategy_adjusted_win_rate": outcome_summary.get("strategy_adjusted_win_rate", 0.0),
        "average_contract_mark_return": outcome_summary.get("average_contract_mark_return", 0.0),
        "average_strategy_adjusted_return": outcome_summary.get("average_strategy_adjusted_return", 0.0),
        "average_strategy_adjusted_max_adverse_excursion": outcome_summary.get(
            "average_strategy_adjusted_max_adverse_excursion", 0.0
        ),
        "average_strategy_adjusted_max_favorable_excursion": outcome_summary.get(
            "average_strategy_adjusted_max_favorable_excursion", 0.0
        ),
        "historical_edge_score": outcome_summary.get("historical_edge_score", 0.0),
        "historical_edge_state": outcome_summary.get("historical_edge_state", "historical_edge_not_available"),
        "positive_outcome_count": outcome_summary.get("positive_outcome_count", 0),
        "negative_outcome_count": outcome_summary.get("negative_outcome_count", 0),
        "strategy_adjusted_positive_outcome_count": outcome_summary.get(
            "strategy_adjusted_positive_outcome_count", 0
        ),
        "strategy_adjusted_negative_outcome_count": outcome_summary.get(
            "strategy_adjusted_negative_outcome_count", 0
        ),
        "positive_horizon_count": outcome_summary.get("positive_horizon_count", 0),
        "negative_horizon_count": outcome_summary.get("negative_horizon_count", 0),
        "strategy_family_counts": outcome_summary.get("strategy_family_counts", {}),
        "strategy_adjustment_policy_counts": outcome_summary.get("strategy_adjustment_policy_counts", {}),
        "triggered_maintenance_count": maintenance_summary.get("triggered_count", 0),
        "blocked_reason_counts": dict(sorted(Counter(blocked_reasons).items())),
    }


def _source_replay_summary(import_validation_source: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(import_validation_source, Mapping):
        return {}
    summary = import_validation_source.get("quantconnect_replay_result_import_validation_summary")
    if isinstance(summary, Mapping):
        return dict(summary)
    return {}


def _historical_edge_score(
    *,
    average_contract_mark_return: float,
    win_rate: float,
    average_max_adverse_excursion: float,
) -> float:
    return _clamp(0.50 + average_contract_mark_return + (win_rate - 0.50) * 0.50 + average_max_adverse_excursion * 0.25, 0.0, 1.0)


def _historical_edge_state(
    *,
    average_contract_mark_return: float,
    win_rate: float,
    historical_edge_score: float,
) -> str:
    if average_contract_mark_return > 0 and win_rate >= 0.50 and historical_edge_score >= 0.55:
        return "historical_positive_edge_candidate"
    if average_contract_mark_return > 0 or win_rate >= 0.50 or historical_edge_score >= 0.50:
        return "historical_mixed_edge_candidate"
    return "historical_negative_edge_candidate"


def _source_artifact_type(source: Any) -> str:
    if isinstance(source, Mapping):
        return str(source.get("artifact_type") or "provided_unknown_artifact")
    if source is None:
        return "missing"
    return type(source).__name__


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _mean(values: Sequence[float]) -> float:
    return mean(values) if values else 0.0


def _round(value: float) -> float:
    return round(float(value or 0.0), 6)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _normalize_historical_edge_validation_root_fields(result: dict) -> dict:
    """Mirror calculated nested edge fields onto the root result object.

    This is a reporting/schema normalization only. It does not recalculate edge,
    change trading logic, submit orders, route orders, model fills, model
    slippage, or perform live execution.
    """
    if not isinstance(result, dict):
        return result

    summary = result.get("historical_edge_validation_summary")
    if not isinstance(summary, dict):
        summary = {}

    contract_summary = result.get("contract_outcome_edge_summary")
    if not isinstance(contract_summary, dict):
        contract_summary = {}

    for field_name in (
        "contract_outcome_count",
        "market_price_snapshot_count",
        "filtered_option_row_count",
        "maintenance_trigger_snapshot_count",
        "portfolio_replay_snapshot_count",
        "symbol_count",
    ):
        if result.get(field_name) is None and summary.get(field_name) is not None:
            result[field_name] = summary.get(field_name)

    if result.get("symbol_count") in (None, "", 0):
        result["symbol_count"] = contract_summary.get("symbol_count")

    table_row_counts = summary.get("table_row_counts")
    if not isinstance(table_row_counts, dict):
        table_row_counts = {}

    if result.get("filtered_option_row_count") is None:
        result["filtered_option_row_count"] = table_row_counts.get("filtered_option_rows")
    if result.get("market_price_snapshot_count") is None:
        result["market_price_snapshot_count"] = table_row_counts.get("market_price_snapshots")

    if result.get("historical_edge_state") in (None, ""):
        result["historical_edge_state"] = (
            summary.get("historical_edge_state")
            or contract_summary.get("historical_edge_state")
        )

    if result.get("historical_edge_score") in (None, ""):
        result["historical_edge_score"] = (
            summary.get("historical_edge_score")
            if summary.get("historical_edge_score") is not None
            else contract_summary.get("historical_edge_score")
        )

    if result.get("average_contract_mark_return") in (None, ""):
        result["average_contract_mark_return"] = (
            summary.get("average_contract_mark_return")
            if summary.get("average_contract_mark_return") is not None
            else contract_summary.get("average_contract_mark_return")
        )

    if result.get("average_strategy_adjusted_return") in (None, ""):
        result["average_strategy_adjusted_return"] = summary.get(
            "average_strategy_adjusted_return",
            contract_summary.get("average_strategy_adjusted_return"),
        )

    if result.get("strategy_adjusted_win_rate") in (None, ""):
        result["strategy_adjusted_win_rate"] = summary.get(
            "strategy_adjusted_win_rate",
            contract_summary.get("strategy_adjusted_win_rate"),
        )

    return result

