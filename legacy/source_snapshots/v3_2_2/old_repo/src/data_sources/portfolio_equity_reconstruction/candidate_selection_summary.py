from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from src.strategy_selection.historical_replay_matrix_metadata_stamp import (
    MATRIX_METADATA_KEY,
    REQUIRED_MATRIX_METADATA_FIELDS,
    matrix_metadata_coverage,
    stamp_matrix_metadata,
    validate_matrix_metadata_record,
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


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")



def _metadata_from_candidate_source(record: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    existing = record.get(MATRIX_METADATA_KEY)
    if isinstance(existing, dict):
        metadata.update(existing)
    if record.get("horizon") not in (None, ""):
        metadata.setdefault("horizon_days", record.get("horizon"))
    return metadata


def _matrix_metadata_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    coverage = matrix_metadata_coverage(records)
    missing_field_counts: dict[str, int] = {field: 0 for field in REQUIRED_MATRIX_METADATA_FIELDS}
    matrix_cell_counts: dict[str, int] = {}
    blocked_reasons: list[str] = []

    for record in records:
        validation = validate_matrix_metadata_record(record)
        matrix_cell_key = validation.get("matrix_cell_key")
        if matrix_cell_key:
            matrix_cell_counts[str(matrix_cell_key)] = matrix_cell_counts.get(str(matrix_cell_key), 0) + 1
        for field in validation.get("matrix_metadata_missing_fields") or []:
            missing_field_counts[str(field)] = missing_field_counts.get(str(field), 0) + 1
        blocked_reasons.extend(str(reason) for reason in validation.get("blocked_reasons") or [])

    ready_to_build = bool(coverage.get("ready_to_build_exact_matrix_edge_summary"))
    if not records:
        state = "blocked"
        recommended_next_step = "provide_portfolio_candidate_rows"
    elif ready_to_build:
        state = "ready"
        recommended_next_step = "build_exact_matrix_edge_summary"
    else:
        state = "needs_review"
        recommended_next_step = "populate_matrix_metadata_before_exact_matrix_edge_summary"

    return {
        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
        "matrix_cell_key_fields": list(REQUIRED_MATRIX_METADATA_FIELDS),
        "matrix_metadata_state": state,
        "total_record_count": len(records),
        "exact_matrix_cell_ready_record_count": int(coverage.get("exact_matrix_cell_ready_record_count") or 0),
        "needs_review_record_count": int(coverage.get("needs_review_record_count") or 0),
        "ready_to_build_exact_matrix_edge_summary": ready_to_build,
        "mapped_required_field_counts": coverage.get("mapped_required_field_counts") or {},
        "missing_required_field_counts": coverage.get("missing_required_field_counts") or {},
        "missing_field_counts": {k: v for k, v in sorted(missing_field_counts.items()) if v},
        "matrix_cell_count": len(matrix_cell_counts),
        "matrix_cell_counts": dict(sorted(matrix_cell_counts.items())),
        "blocked_reasons": sorted(dict.fromkeys(blocked_reasons)),
        "recommended_next_step": recommended_next_step,
    }

def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int:
    number = _number(value)
    if number is None:
        return 0
    return int(number)


def _horizon_key(value: Any) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 999999


def _stress_by_horizon(stress_diagnostics: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("horizon")): row
        for row in stress_diagnostics.get("horizon_stress_summaries") or []
        if row.get("horizon") not in (None, "")
    }


def _tail_stress_wipeout_horizons(comparison_summary: dict[str, Any]) -> set[str]:
    wipeouts = (
        comparison_summary.get("tail_stress_summary", {})
        .get("tail_stress_wipeouts", [])
        or []
    )

    return {
        str(row.get("horizon"))
        for row in wipeouts
        if row.get("horizon") not in (None, "")
    }


def _baseline_records(comparison_summary: dict[str, Any]) -> list[dict[str, Any]]:
    records = comparison_summary.get("scenario_records") or []

    baseline = [
        record
        for record in records
        if record.get("is_investable_model") is True
        and record.get("variant_type") == "baseline"
    ]

    return sorted(baseline, key=lambda row: _horizon_key(row.get("horizon")))


def _candidate_rows(
    comparison_summary: dict[str, Any],
    stress_diagnostics: dict[str, Any],
) -> list[dict[str, Any]]:
    stress_lookup = _stress_by_horizon(stress_diagnostics)
    wipeout_horizons = _tail_stress_wipeout_horizons(comparison_summary)

    rows: list[dict[str, Any]] = []

    for record in _baseline_records(comparison_summary):
        horizon = str(record.get("horizon"))
        stress = stress_lookup.get(horizon, {})

        worst_mae = _number(stress.get("worst_active_mae_stress_fraction"))
        annualized = _number(record.get("annualized_return"))
        sharpe = _number(record.get("sharpe_ratio"))
        max_drawdown = _number(record.get("max_drawdown"))

        mae_abs = abs(worst_mae) if worst_mae is not None else None

        primary_score = None
        if annualized is not None:
            primary_score = annualized
            if sharpe is not None:
                primary_score += 0.05 * sharpe
            if max_drawdown is not None:
                primary_score += max_drawdown
            if horizon in wipeout_horizons:
                primary_score -= 1.0

        conservative_score = None
        if annualized is not None:
            conservative_score = annualized
            if sharpe is not None:
                conservative_score += 0.10 * sharpe
            if mae_abs is not None:
                conservative_score -= 2.0 * mae_abs
            if horizon in wipeout_horizons:
                conservative_score -= 2.0

        aggressive_score = annualized

        candidate = {
            "horizon": horizon,
            "variant_id": record.get("variant_id"),
            "scenario_id": record.get("scenario_id"),
            "ending_equity": _number(record.get("ending_equity")),
            "total_return": _number(record.get("total_return")),
            "annualized_return": annualized,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe,
            "sortino_ratio": _number(record.get("sortino_ratio")),
            "win_rate": _number(record.get("win_rate")),
            "profit_factor": _number(record.get("profit_factor")),
            "trade_count": _integer(record.get("trade_count")),
            "tail_capped_trade_count": _integer(record.get("tail_capped_trade_count")),
            "max_active_risk_fraction": _number(stress.get("max_active_risk_fraction")),
            "max_active_risk_date": stress.get("max_active_risk_date"),
            "worst_active_mae_stress_fraction": worst_mae,
            "worst_active_mae_stress_date": stress.get("worst_active_mae_stress_date"),
            "mae_capped_trade_count": _integer(stress.get("mae_capped_trade_count")),
            "exit_return_capped_trade_count": _integer(
                stress.get("exit_return_capped_trade_count")
            ),
            "tail_stress_wipeout_horizon": horizon in wipeout_horizons,
            "primary_score": round(primary_score, 6) if primary_score is not None else None,
            "conservative_score": (
                round(conservative_score, 6)
                if conservative_score is not None
                else None
            ),
            "aggressive_score": (
                round(aggressive_score, 6)
                if aggressive_score is not None
                else None
            ),
        }

        rows.append(
            stamp_matrix_metadata(
                candidate,
                metadata=_metadata_from_candidate_source(record),
                source_refs={
                    "horizon_days": "portfolio_equity_reconstruction_comparison_summary.scenario_records.horizon",
                },
            )
        )

    return rows


def _pick_highest(rows: list[dict[str, Any]], field: str) -> dict[str, Any] | None:
    eligible = [row for row in rows if row.get(field) is not None]
    if not eligible:
        return None

    return sorted(eligible, key=lambda row: row[field], reverse=True)[0]


def _pick_conservative(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    # Favor strong return, but avoid the highest MAE/cap-dependence region.
    eligible = [
        row
        for row in rows
        if row.get("tail_stress_wipeout_horizon") is False
        and row.get("worst_active_mae_stress_fraction") is not None
        and abs(row["worst_active_mae_stress_fraction"]) <= 0.105
    ]

    if eligible:
        return _pick_highest(eligible, "annualized_return")

    return _pick_highest(rows, "conservative_score")


def _pick_primary(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    # Primary avoids horizons that wiped out in uncapped stress.
    eligible = [
        row
        for row in rows
        if row.get("tail_stress_wipeout_horizon") is False
    ]

    if eligible:
        return _pick_highest(eligible, "annualized_return")

    return _pick_highest(rows, "primary_score")


def _pick_aggressive(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    # Aggressive allows capped model leader, but records stress warning.
    return _pick_highest(rows, "annualized_return")


def _selection_notes(
    *,
    conservative: dict[str, Any] | None,
    primary: dict[str, Any] | None,
    aggressive: dict[str, Any] | None,
) -> list[str]:
    notes: list[str] = []

    if conservative:
        notes.append(
            f"Conservative candidate selected at {conservative['horizon']} days "
            "because it preserves strong annualized return while keeping MAE stress lower."
        )

    if primary:
        notes.append(
            f"Primary candidate selected at {primary['horizon']} days because it is the "
            "highest-return baseline horizon that avoids uncapped tail-stress wipeout."
        )

    if aggressive:
        if aggressive.get("tail_stress_wipeout_horizon"):
            notes.append(
                f"Aggressive candidate at {aggressive['horizon']} days is the capped return "
                "leader, but it has an uncapped tail-stress wipeout warning."
            )
        else:
            notes.append(
                f"Aggressive candidate at {aggressive['horizon']} days is the highest "
                "annualized-return baseline horizon."
            )

    return notes


def build_portfolio_candidate_selection_summary(
    *,
    comparison_summary: dict[str, Any],
    stress_diagnostics: dict[str, Any],
    multi_window_edge_summary: dict[str, Any] | None = None,
    period_id: str | None = None,
) -> dict[str, Any]:
    candidates = _candidate_rows(comparison_summary, stress_diagnostics)

    conservative = _pick_conservative(candidates)
    primary = _pick_primary(candidates)
    aggressive = _pick_aggressive(candidates)

    edge_state = None
    edge_score = None
    edge_win_rate = None

    if multi_window_edge_summary:
        edge_state = multi_window_edge_summary.get("historical_edge_state")
        edge_score = _number(multi_window_edge_summary.get("historical_edge_score"))
        edge_win_rate = _number(multi_window_edge_summary.get("strategy_adjusted_win_rate"))

    status = "ready" if candidates and primary else "blocked"
    matrix_metadata_candidate_summary = _matrix_metadata_summary(candidates)

    return {
        "adapter_type": "portfolio_candidate_selection_summary_builder",
        "artifact_type": "signalforge_portfolio_candidate_selection_summary",
        "schema_version": "signalforge_portfolio_candidate_selection_summary.v1",
        "period_id": period_id,
        "status": status,
        "is_ready": status == "ready",
        "historical_edge_state": edge_state,
        "historical_edge_score": edge_score,
        "strategy_adjusted_win_rate": edge_win_rate,
        "candidate_count": len(candidates),
        "conservative_candidate": conservative,
        "primary_candidate": primary,
        "aggressive_candidate": aggressive,
        "candidate_rows": candidates,
        "matrix_metadata_candidate_summary": matrix_metadata_candidate_summary,
        "exact_matrix_cell_ready_record_count": matrix_metadata_candidate_summary.get("exact_matrix_cell_ready_record_count", 0),
        "matrix_metadata_needs_review_record_count": matrix_metadata_candidate_summary.get("needs_review_record_count", 0),
        "ready_to_build_exact_matrix_edge_summary": matrix_metadata_candidate_summary.get("ready_to_build_exact_matrix_edge_summary", False),
        "recommended_next_step": matrix_metadata_candidate_summary.get("recommended_next_step"),
        "selection_notes": _selection_notes(
            conservative=conservative,
            primary=primary,
            aggressive=aggressive,
        ),
        "required_next_validation": [
            "confirm preferred horizon against portfolio-equity reconstruction artifacts",
            "document realized exit-date limitation",
            "do not treat results as broker/live/slippage-adjusted performance",
            "consider future intraperiod mark-to-market reconstruction if daily option marks are retained",
        ],
        "selection_interpretation": (
            "Candidate selection ranks fixed-horizon realized exit-date synthetic portfolio "
            "scenarios. It uses capped defined-risk reconstruction as the investable baseline "
            "and treats uncapped runs as stress diagnostics only."
        ),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "automatic_action": None,
        "automatic_close_order": None,
        "automatic_defense_order": None,
        "automatic_roll_order": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
    }
