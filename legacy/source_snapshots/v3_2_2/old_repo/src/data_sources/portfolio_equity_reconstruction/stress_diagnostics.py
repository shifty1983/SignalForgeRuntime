from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable
import json
import re

from src.strategy_selection.historical_replay_matrix_metadata_stamp import (
    MATRIX_METADATA_KEY,
    REQUIRED_MATRIX_METADATA_FIELDS,
    matrix_metadata_coverage,
    stamp_matrix_metadata,
    validate_matrix_metadata_record,
)


CONTRACT_OUTCOME_FILE = "signalforge_qc_contract_outcome_snapshots.json"

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


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def discover_decoded_window_roots(paths: Iterable[str | Path]) -> list[Path]:
    discovered: list[Path] = []

    for raw_path in paths:
        path = Path(raw_path)

        if not path.exists():
            continue

        if path.is_dir() and path.name.startswith("quantconnect_research_export_decoded_batches_"):
            discovered.append(path)
            continue

        if path.is_dir():
            discovered.extend(
                sorted(
                    child
                    for child in path.rglob("quantconnect_research_export_decoded_batches_*")
                    if child.is_dir()
                )
            )

    return sorted(dict.fromkeys(discovered), key=lambda item: str(item))


def _window_id_from_decoded_root(path: Path) -> str:
    return path.name.replace("quantconnect_research_export_decoded_batches_", "")


def _window_start_date(window_id: str) -> str:
    match = re.match(r"(\d{8})_\d{8}", window_id)
    if not match:
        return "1900-01-01"

    return date(
        int(match.group(1)[0:4]),
        int(match.group(1)[4:6]),
        int(match.group(1)[6:8]),
    ).isoformat()


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]

    if not isinstance(payload, dict):
        return []

    for key in ["contract_outcome_snapshots", "rows", "data", "items"]:
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]

    for value in payload.values():
        if isinstance(value, list) and all(isinstance(row, dict) for row in value[:10]):
            return value

    return []


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None

    if isinstance(value, bool):
        return float(value)

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int:
    number = _number(value)
    if number is None:
        return 0
    return int(number)


def _first_present(row: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        if name in row and row.get(name) not in (None, ""):
            return row.get(name)

    contract = row.get("contract")
    if isinstance(contract, dict):
        for name in names:
            if name in contract and contract.get(name) not in (None, ""):
                return contract.get(name)

    return None


def _symbol_from_row(row: dict[str, Any]) -> str:
    value = _first_present(row, ["symbol", "underlying_symbol", "asset_symbol", "ticker"])
    if value:
        return str(value).strip().upper()

    contract = row.get("contract")
    if isinstance(contract, str) and contract.strip():
        return contract.strip().split()[0].upper()

    return "UNKNOWN"


def _horizon_from_row(row: dict[str, Any]) -> str:
    value = _first_present(
        row,
        [
            "horizon_days",
            "outcome_horizon_days",
            "holding_period_days",
            "days_forward",
            "forward_days",
            "horizon",
        ],
    )

    if value in (None, ""):
        return "unknown"

    number = _number(value)
    if number is not None:
        return str(int(number))

    match = re.search(r"\d+", str(value))
    return match.group(0) if match else str(value)


def _date_from_row(row: dict[str, Any], names: list[str], fallback: str) -> str:
    value = _first_present(row, names)

    if value in (None, ""):
        return fallback

    text = str(value).strip()
    if "T" in text:
        text = text.split("T", 1)[0]

    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return fallback


def _add_days(date_text: str, days: int) -> str:
    return (date.fromisoformat(date_text) + timedelta(days=days)).isoformat()


def _contract_return_from_row(row: dict[str, Any]) -> float | None:
    return _number(
        _first_present(
            row,
            [
                "contract_mark_return",
                "mark_return",
                "contract_return",
                "average_contract_mark_return",
                "return",
            ],
        )
    )


def _strategy_policy(row: dict[str, Any]) -> str:
    value = _first_present(
        row,
        [
            "strategy_adjustment_policy",
            "strategy_family",
            "option_strategy_family",
            "strategy_adjustment",
        ],
    )

    if value in (None, ""):
        return "invert_short_premium_contract_mark"

    return str(value).strip().lower()


def _is_short_premium(row: dict[str, Any]) -> bool:
    policy = _strategy_policy(row)
    return (
        "invert_short_premium_contract_mark" in policy
        or "defined_risk_short_premium" in policy
        or policy == ""
    )


def _strategy_adjusted_return(row: dict[str, Any]) -> float | None:
    explicit_adjusted = _number(
        _first_present(
            row,
            [
                "strategy_adjusted_return",
                "strategy_adjusted_contract_mark_return",
                "adjusted_contract_mark_return",
                "return_strategy_adjusted",
            ],
        )
    )

    if explicit_adjusted is not None:
        return explicit_adjusted

    raw_return = _contract_return_from_row(row)
    if raw_return is None:
        return None

    return -raw_return if _is_short_premium(row) else raw_return


def _strategy_adjusted_mae(row: dict[str, Any], adjusted_return: float) -> float:
    raw_contract_return = _contract_return_from_row(row)
    raw_mae = _number(_first_present(row, ["max_adverse_excursion"]))
    raw_mfe = _number(_first_present(row, ["max_favorable_excursion"]))

    path_values: list[float] = [adjusted_return]

    if raw_contract_return is not None:
        path_values.append(-raw_contract_return if _is_short_premium(row) else raw_contract_return)

    if raw_mae is not None:
        path_values.append(-raw_mae if _is_short_premium(row) else raw_mae)

    if raw_mfe is not None:
        path_values.append(-raw_mfe if _is_short_premium(row) else raw_mfe)

    return min(path_values)


def _clamp(value: float, lower: float | None, upper: float | None) -> float:
    result = value

    if lower is not None and result < lower:
        result = lower

    if upper is not None and result > upper:
        result = upper

    return result


def _date_range(start: str, end: str) -> list[str]:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)

    if end_date < start_date:
        return []

    days = (end_date - start_date).days + 1
    return [(start_date + timedelta(days=offset)).isoformat() for offset in range(days)]



def _matrix_source_ref(path: Path | str, row_index: int, field: str) -> dict[str, Any]:
    return {
        "source_path": str(path),
        "row_index": row_index,
        "field": field,
    }


def _matrix_metadata_source_refs(row: dict[str, Any], *, source_path: Path | str, row_index: int) -> dict[str, Any]:
    refs: dict[str, Any] = {}
    metadata = row.get(MATRIX_METADATA_KEY)
    if isinstance(metadata, dict):
        for field in REQUIRED_MATRIX_METADATA_FIELDS:
            if metadata.get(field) not in (None, ""):
                refs[field] = _matrix_source_ref(source_path, row_index, f"{MATRIX_METADATA_KEY}.{field}")

    alias_candidates = {
        "regime_state": ["regime_state", "regime", "market_regime", "regime_label"],
        "asset_behavior_state": ["asset_behavior_state", "asset_behavior", "asset_behavior_label", "behavior_state"],
        "option_behavior_state": ["option_behavior_state", "option_behavior", "option_behavior_label", "options_behavior_state"],
        "strategy_id": ["strategy_id", "strategy", "strategy_name", "setup_id", "scenario_id"],
        "strategy_family": ["strategy_family", "family", "strategy_type", "variant_id"],
        "symbol": ["symbol", "ticker", "underlying", "underlying_symbol", "root_symbol"],
        "horizon_days": ["horizon_days", "horizon", "window_days", "selected_window_days", "target_horizon_days"],
    }
    for field, aliases in alias_candidates.items():
        if field in refs:
            continue
        for alias in aliases:
            if row.get(alias) not in (None, ""):
                refs[field] = _matrix_source_ref(source_path, row_index, alias)
                break
    return refs


def _stamp_stress_event_matrix_metadata(
    event: dict[str, Any],
    *,
    source_row: dict[str, Any],
    outcome_path: Path,
    row_index: int,
    window_id: str,
) -> dict[str, Any]:
    metadata = {
        **source_row,
        "symbol": event.get("symbol"),
        "horizon_days": event.get("horizon_days"),
        "replay_window_id": window_id,
        "outcome_state": "stress_event",
    }
    refs = _matrix_metadata_source_refs(source_row, source_path=outcome_path, row_index=row_index)
    refs.setdefault("symbol", _matrix_source_ref(outcome_path, row_index, "symbol"))
    refs.setdefault("horizon_days", _matrix_source_ref(outcome_path, row_index, "horizon_days"))
    refs.setdefault("replay_window_id", _matrix_source_ref(outcome_path, row_index, "window_id"))

    return stamp_matrix_metadata(
        event,
        metadata,
        source_refs=refs,
        preserve_existing=True,
    )


def _matrix_metadata_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    coverage = matrix_metadata_coverage(records)
    missing_field_counts: dict[str, int] = {field: 0 for field in REQUIRED_MATRIX_METADATA_FIELDS}
    blocked_record_count = 0

    for record in records:
        validation = validate_matrix_metadata_record(record)
        if validation.get("blocked_reasons"):
            blocked_record_count += 1
        for field in validation.get("matrix_metadata_missing_fields") or []:
            missing_field_counts[str(field)] = missing_field_counts.get(str(field), 0) + 1

    ready_count = int(coverage.get("exact_matrix_cell_ready_record_count") or 0)
    needs_review_count = int(coverage.get("needs_review_record_count") or 0)
    state = "ready" if ready_count and not needs_review_count and not blocked_record_count else "needs_review"
    if not records:
        state = "blocked"

    if state == "ready":
        recommended_next_step = "build_exact_matrix_edge_summary"
    else:
        recommended_next_step = "populate_matrix_metadata_before_stress_edge_attribution"

    return {
        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
        "matrix_cell_key_fields": list(REQUIRED_MATRIX_METADATA_FIELDS),
        "matrix_metadata_state": state,
        "total_record_count": len(records),
        "exact_matrix_cell_ready_record_count": ready_count,
        "needs_review_record_count": needs_review_count,
        "blocked_record_count": blocked_record_count,
        "mapped_required_field_counts": coverage.get("mapped_required_field_counts", {}),
        "missing_required_field_counts": coverage.get("missing_required_field_counts", missing_field_counts),
        "missing_required_field_counts_from_validation": missing_field_counts,
        "ready_to_build_exact_matrix_edge_summary": bool(
            coverage.get("ready_to_build_exact_matrix_edge_summary")
        ),
        "recommended_next_step": recommended_next_step,
    }


def load_stress_events(decoded_window_roots: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    warnings: list[str] = []

    for decoded_root in decoded_window_roots:
        window_id = _window_id_from_decoded_root(decoded_root)
        fallback_entry = _window_start_date(window_id)

        for batch_dir in sorted(decoded_root.glob("batch_*")):
            outcome_path = batch_dir / CONTRACT_OUTCOME_FILE

            if not outcome_path.exists():
                warnings.append(f"missing outcome file: {outcome_path}")
                continue

            payload = read_json(outcome_path)
            rows = _extract_rows(payload)

            for row_index, row in enumerate(rows):
                adjusted = _strategy_adjusted_return(row)
                if adjusted is None:
                    continue

                horizon = _horizon_from_row(row)
                horizon_days = _integer(horizon)
                entry_date = _date_from_row(row, ["entry_date", "quote_date", "signal_date", "date"], fallback_entry)
                exit_date = _date_from_row(row, ["exit_date", "outcome_date", "target_date"], _add_days(entry_date, horizon_days))

                event = {
                    "window_id": window_id,
                    "batch_id": batch_dir.name,
                    "row_index": row_index,
                    "symbol": _symbol_from_row(row),
                    "horizon": horizon,
                    "horizon_days": horizon_days,
                    "entry_date": entry_date,
                    "exit_date": exit_date,
                    "strategy_adjusted_return": adjusted,
                    "strategy_adjusted_mae": _strategy_adjusted_mae(row, adjusted),
                    "contract_return": _contract_return_from_row(row),
                    "source_path": str(outcome_path),
                }
                events.append(
                    _stamp_stress_event_matrix_metadata(
                        event,
                        source_row=row,
                        outcome_path=outcome_path,
                        row_index=row_index,
                        window_id=window_id,
                    )
                )

    return events, warnings


def build_horizon_stress_summary(
    events: list[dict[str, Any]],
    *,
    horizon: str,
    portfolio_risk_budget_pct: float,
    max_risk_per_trade_pct: float,
    min_return_cap: float | None,
    max_return_cap: float | None,
) -> dict[str, Any]:
    selected = [
        event
        for event in events
        if str(event["horizon"]) == str(horizon)
        and event["symbol"] != "UNKNOWN"
    ]

    by_entry: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in selected:
        by_entry[event["entry_date"]].append(event)

    trade_events: list[dict[str, Any]] = []

    for entry_date, cohort in by_entry.items():
        cohort_size = len(cohort)
        risk_fraction = min(max_risk_per_trade_pct, portfolio_risk_budget_pct / cohort_size) if cohort_size else 0.0

        for event in cohort:
            raw_return = float(event["strategy_adjusted_return"])
            raw_mae = float(event["strategy_adjusted_mae"])

            capped_return = _clamp(raw_return, min_return_cap, max_return_cap)
            capped_mae = _clamp(raw_mae, min_return_cap, max_return_cap)

            trade_events.append(
                {
                    **event,
                    "risk_fraction": round(risk_fraction, 10),
                    "capped_strategy_adjusted_return": round(capped_return, 10),
                    "capped_strategy_adjusted_mae": round(capped_mae, 10),
                    "portfolio_return_contribution": round(risk_fraction * capped_return, 10),
                    "portfolio_mae_contribution": round(risk_fraction * capped_mae, 10),
                    "was_exit_return_capped": capped_return != raw_return,
                    "was_mae_capped": capped_mae != raw_mae,
                }
            )

    if not trade_events:
        return {
            "horizon": str(horizon),
            "trade_count": 0,
            "status": "blocked",
            "blocked_reason": "no_trade_events",
            "matrix_metadata_stress_summary": _matrix_metadata_summary([]),
            "exact_matrix_cell_ready_record_count": 0,
            "matrix_metadata_needs_review_record_count": 0,
            "ready_to_build_exact_matrix_edge_summary": False,
            "recommended_next_step": "populate_matrix_metadata_before_stress_edge_attribution",
        }

    min_entry = min(event["entry_date"] for event in trade_events)
    max_exit = max(event["exit_date"] for event in trade_events)

    exposure_rows: list[dict[str, Any]] = []

    for day in _date_range(min_entry, max_exit):
        active = [
            event
            for event in trade_events
            if event["entry_date"] <= day and event["exit_date"] > day
        ]

        active_risk = sum(event["risk_fraction"] for event in active)
        active_mae_stress = sum(event["portfolio_mae_contribution"] for event in active)

        exposure_rows.append(
            {
                "date": day,
                "active_trade_count": len(active),
                "active_risk_fraction": round(active_risk, 10),
                "active_mae_stress_fraction": round(active_mae_stress, 10),
            }
        )

    worst_mae_trade = min(trade_events, key=lambda event: event["portfolio_mae_contribution"])
    worst_exit_trade = min(trade_events, key=lambda event: event["portfolio_return_contribution"])
    max_active_risk_row = max(exposure_rows, key=lambda row: row["active_risk_fraction"])
    max_active_trade_row = max(exposure_rows, key=lambda row: row["active_trade_count"])
    worst_active_mae_row = min(exposure_rows, key=lambda row: row["active_mae_stress_fraction"])

    symbol_stress: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in trade_events:
        symbol_stress[event["symbol"]].append(event)

    symbol_rows = []
    for symbol, rows in symbol_stress.items():
        symbol_rows.append(
            {
                "symbol": symbol,
                "trade_count": len(rows),
                "total_mae_contribution": round(sum(row["portfolio_mae_contribution"] for row in rows), 10),
                "worst_mae_contribution": round(min(row["portfolio_mae_contribution"] for row in rows), 10),
                "mae_capped_count": sum(1 for row in rows if row["was_mae_capped"]),
                "exit_capped_count": sum(1 for row in rows if row["was_exit_return_capped"]),
            }
        )

    matrix_metadata_stress_summary = _matrix_metadata_summary(trade_events)

    return {
        "horizon": str(horizon),
        "status": "ready",
        "trade_count": len(trade_events),
        "active_day_count": len(exposure_rows),
        "max_active_trade_count": max_active_trade_row["active_trade_count"],
        "max_active_trade_date": max_active_trade_row["date"],
        "max_active_risk_fraction": max_active_risk_row["active_risk_fraction"],
        "max_active_risk_date": max_active_risk_row["date"],
        "worst_active_mae_stress_fraction": worst_active_mae_row["active_mae_stress_fraction"],
        "worst_active_mae_stress_date": worst_active_mae_row["date"],
        "exit_return_capped_trade_count": sum(1 for event in trade_events if event["was_exit_return_capped"]),
        "mae_capped_trade_count": sum(1 for event in trade_events if event["was_mae_capped"]),
        "worst_mae_trade": worst_mae_trade,
        "worst_exit_trade": worst_exit_trade,
        "top_symbol_mae_stress": sorted(symbol_rows, key=lambda row: row["total_mae_contribution"])[:25],
        "matrix_metadata_stress_summary": matrix_metadata_stress_summary,
        "exact_matrix_cell_ready_record_count": matrix_metadata_stress_summary.get("exact_matrix_cell_ready_record_count", 0),
        "matrix_metadata_needs_review_record_count": matrix_metadata_stress_summary.get("needs_review_record_count", 0),
        "ready_to_build_exact_matrix_edge_summary": matrix_metadata_stress_summary.get("ready_to_build_exact_matrix_edge_summary", False),
        "recommended_next_step": matrix_metadata_stress_summary.get("recommended_next_step"),
        "stress_interpretation": (
            "MAE stress estimates active intraperiod portfolio pressure by applying each active "
            "trade's strategy-adjusted max adverse excursion. It is a stress proxy, not a broker "
            "fill or intraday mark-to-market equity curve."
        ),
    }


def build_portfolio_equity_stress_diagnostics(
    *,
    decoded_window_roots: list[Path],
    period_id: str | None,
    horizons: list[str],
    portfolio_risk_budget_pct: float,
    max_risk_per_trade_pct: float,
    min_return_cap: float | None,
    max_return_cap: float | None,
) -> dict[str, Any]:
    events, warnings = load_stress_events(decoded_window_roots)

    horizon_summaries = [
        build_horizon_stress_summary(
            events,
            horizon=horizon,
            portfolio_risk_budget_pct=portfolio_risk_budget_pct,
            max_risk_per_trade_pct=max_risk_per_trade_pct,
            min_return_cap=min_return_cap,
            max_return_cap=max_return_cap,
        )
        for horizon in horizons
    ]

    matrix_metadata_stress_summary = _matrix_metadata_summary(events)

    return {
        "adapter_type": "portfolio_equity_stress_diagnostics_builder",
        "artifact_type": "signalforge_portfolio_equity_stress_diagnostics",
        "schema_version": "signalforge_portfolio_equity_stress_diagnostics.v1",
        "period_id": period_id,
        "status": "ready" if events and not warnings else "needs_review",
        "is_ready": bool(events) and not warnings,
        "decoded_window_count": len(decoded_window_roots),
        "source_outcome_event_count": len(events),
        "horizon_count": len(horizon_summaries),
        "horizon_stress_summaries": horizon_summaries,
        "portfolio_risk_budget_pct": portfolio_risk_budget_pct,
        "max_risk_per_trade_pct": max_risk_per_trade_pct,
        "min_return_cap": min_return_cap,
        "max_return_cap": max_return_cap,
        "matrix_metadata_stress_summary": matrix_metadata_stress_summary,
        "exact_matrix_cell_ready_record_count": matrix_metadata_stress_summary.get("exact_matrix_cell_ready_record_count", 0),
        "matrix_metadata_needs_review_record_count": matrix_metadata_stress_summary.get("needs_review_record_count", 0),
        "ready_to_build_exact_matrix_edge_summary": matrix_metadata_stress_summary.get("ready_to_build_exact_matrix_edge_summary", False),
        "recommended_next_step": matrix_metadata_stress_summary.get("recommended_next_step"),
        "warnings": warnings,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "automatic_action": None,
        "automatic_close_order": None,
        "automatic_defense_order": None,
        "automatic_roll_order": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
    }
