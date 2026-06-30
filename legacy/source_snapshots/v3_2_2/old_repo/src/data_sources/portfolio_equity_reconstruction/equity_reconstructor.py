from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from math import sqrt
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Iterable
import json
import re

from src.signalforge.engines.strategy_selection.historical_replay_matrix_metadata_stamp import (
    MATRIX_CELL_KEY_KEY,
    MATRIX_METADATA_KEY,
    MATRIX_METADATA_MISSING_FIELDS_KEY,
    MATRIX_METADATA_SOURCE_REFS_KEY,
    MATRIX_METADATA_STATE_KEY,
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


def write_json(path: str | Path, payload: Any) -> None:
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

    value = datetime.strptime(match.group(1), "%Y%m%d").date()
    return value.isoformat()


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

    underlying = row.get("underlying")
    if isinstance(underlying, dict):
        for name in names:
            if name in underlying and underlying.get(name) not in (None, ""):
                return underlying.get(name)

    return None


def _symbol_from_row(row: dict[str, Any]) -> str:
    value = _first_present(
        row,
        [
            "symbol",
            "underlying_symbol",
            "asset_symbol",
            "ticker",
            "root_symbol",
            "canonical_symbol",
        ],
    )

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
            "outcome_horizon",
        ],
    )

    if value is None or value == "":
        return "unknown"

    number = _number(value)
    if number is not None:
        return str(int(number))

    match = re.search(r"\d+", str(value))
    if match:
        return match.group(0)

    return str(value)


def _date_from_row(row: dict[str, Any], fallback_date: str) -> str:
    value = _first_present(
        row,
        [
            "entry_date",
            "quote_date",
            "signal_date",
            "as_of_date",
            "snapshot_date",
            "evaluation_date",
            "replay_date",
            "date",
            "timestamp",
        ],
    )

    if value in (None, ""):
        return fallback_date

    text = str(value).strip()
    if "T" in text:
        text = text.split("T", 1)[0]

    try:
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError:
        return fallback_date


def _add_days(date_text: str, days: int) -> str:
    value = datetime.fromisoformat(date_text).date()
    return (value + timedelta(days=days)).isoformat()


def _exit_date_from_row(row: dict[str, Any], entry_date: str, horizon_days: int) -> str:
    value = _first_present(
        row,
        [
            "exit_date",
            "outcome_date",
            "target_date",
            "horizon_date",
        ],
    )

    if value not in (None, ""):
        text = str(value).strip()
        if "T" in text:
            text = text.split("T", 1)[0]

        try:
            return datetime.fromisoformat(text).date().isoformat()
        except ValueError:
            pass

    return _add_days(entry_date, horizon_days) if horizon_days else entry_date



def _matrix_source_ref(path: str | Path, row_index: int, field: str) -> str:
    return f"{path}#row_{row_index}:{field}"


def _matrix_source_refs_for_outcome_row(
    *,
    outcome_path: str | Path,
    row_index: int,
    row: dict[str, Any],
    event: dict[str, Any],
) -> dict[str, Any]:
    refs: dict[str, Any] = {}

    if event.get("symbol") not in (None, "", "UNKNOWN"):
        refs["symbol"] = _matrix_source_ref(outcome_path, row_index, "symbol")
    if event.get("horizon_days") not in (None, "", 0):
        refs["horizon_days"] = _matrix_source_ref(outcome_path, row_index, "horizon_days")
    if event.get("window_id") not in (None, ""):
        refs["replay_window_id"] = "decoded_window_root"

    metadata = row.get(MATRIX_METADATA_KEY)
    if isinstance(metadata, dict):
        for field in REQUIRED_MATRIX_METADATA_FIELDS:
            if metadata.get(field) not in (None, "", [], {}):
                refs.setdefault(field, _matrix_source_ref(outcome_path, row_index, f"matrix_metadata.{field}"))

    return refs


def _stamp_outcome_event_matrix_metadata(
    *,
    outcome_path: str | Path,
    row_index: int,
    row: dict[str, Any],
    event: dict[str, Any],
) -> dict[str, Any]:
    event_with_existing_metadata = dict(event)
    if isinstance(row.get(MATRIX_METADATA_KEY), dict):
        event_with_existing_metadata[MATRIX_METADATA_KEY] = row[MATRIX_METADATA_KEY]

    return stamp_matrix_metadata(
        event_with_existing_metadata,
        source_refs=_matrix_source_refs_for_outcome_row(
            outcome_path=outcome_path,
            row_index=row_index,
            row=row,
            event=event,
        ),
    )


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

    ready_count = int(coverage.get("exact_matrix_cell_ready_record_count") or 0)
    needs_review_count = int(coverage.get("needs_review_record_count") or 0)
    ready_to_build = bool(coverage.get("ready_to_build_exact_matrix_edge_summary"))

    if not records:
        state = "blocked"
        recommended_next_step = "provide_portfolio_reconstruction_records"
    elif ready_to_build:
        state = "ready"
        recommended_next_step = "patch_portfolio_candidate_selection_summary_matrix_metadata"
    else:
        state = "needs_review"
        recommended_next_step = "populate_matrix_metadata_before_portfolio_edge_attribution"

    return {
        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
        "matrix_cell_key_fields": list(REQUIRED_MATRIX_METADATA_FIELDS),
        "matrix_metadata_state": state,
        "total_record_count": len(records),
        "exact_matrix_cell_ready_record_count": ready_count,
        "needs_review_record_count": needs_review_count,
        "ready_to_build_exact_matrix_edge_summary": ready_to_build,
        "mapped_required_field_counts": coverage.get("mapped_required_field_counts") or {},
        "missing_required_field_counts": coverage.get("missing_required_field_counts") or {},
        "missing_field_counts": {k: v for k, v in sorted(missing_field_counts.items()) if v},
        "matrix_cell_count": len(matrix_cell_counts),
        "matrix_cell_counts": dict(sorted(matrix_cell_counts.items())),
        "blocked_reasons": sorted(dict.fromkeys(blocked_reasons)),
        "recommended_next_step": recommended_next_step,
    }

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


def _strategy_adjustment_policy_from_row(row: dict[str, Any]) -> str:
    value = _first_present(
        row,
        [
            "strategy_adjustment_policy",
            "strategy_adjustment",
            "adjustment_policy",
            "strategy_family",
            "option_strategy_family",
        ],
    )

    if value in (None, ""):
        return "invert_short_premium_contract_mark"

    return str(value).strip()


def _strategy_adjusted_return_from_row(row: dict[str, Any]) -> float | None:
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

    raw_contract_return = _contract_return_from_row(row)
    if raw_contract_return is None:
        return None

    policy = _strategy_adjustment_policy_from_row(row).lower()

    if (
        "invert_short_premium_contract_mark" in policy
        or "defined_risk_short_premium" in policy
        or policy == ""
    ):
        return -raw_contract_return

    return raw_contract_return


def _clamp(value: float, lower: float | None, upper: float | None) -> float:
    result = value

    if lower is not None and result < lower:
        result = lower

    if upper is not None and result > upper:
        result = upper

    return result


def load_replay_outcome_events(decoded_window_roots: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    warnings: list[str] = []

    for decoded_root in decoded_window_roots:
        window_id = _window_id_from_decoded_root(decoded_root)
        fallback_entry_date = _window_start_date(window_id)

        for batch_dir in sorted(decoded_root.glob("batch_*")):
            outcome_path = batch_dir / CONTRACT_OUTCOME_FILE

            if not outcome_path.exists():
                warnings.append(f"missing outcome file: {outcome_path}")
                continue

            payload = read_json(outcome_path)
            rows = _extract_rows(payload)

            for row_index, row in enumerate(rows):
                horizon = _horizon_from_row(row)
                horizon_days = _integer(horizon)
                entry_date = _date_from_row(row, fallback_entry_date)
                exit_date = _exit_date_from_row(row, entry_date, horizon_days)

                strategy_adjusted_return = _strategy_adjusted_return_from_row(row)
                if strategy_adjusted_return is None:
                    continue

                event = {
                    "window_id": window_id,
                    "batch_id": batch_dir.name,
                    "row_index": row_index,
                    "symbol": _symbol_from_row(row),
                    "horizon": horizon,
                    "horizon_days": horizon_days,
                    "entry_date": entry_date,
                    "exit_date": exit_date,
                    "strategy_adjusted_return": strategy_adjusted_return,
                    "contract_return": _contract_return_from_row(row),
                    "strategy_adjustment_policy": _strategy_adjustment_policy_from_row(row),
                    "source_path": str(outcome_path),
                }

                events.append(
                    _stamp_outcome_event_matrix_metadata(
                        outcome_path=outcome_path,
                        row_index=row_index,
                        row=row,
                        event=event,
                    )
                )

    return sorted(
        events,
        key=lambda row: (
            row["exit_date"],
            row["entry_date"],
            row["window_id"],
            row["batch_id"],
            row["symbol"],
            row["row_index"],
        ),
    ), warnings


def _max_drawdown(equity_values: list[float]) -> float:
    peak = None
    max_dd = 0.0

    for value in equity_values:
        if peak is None or value > peak:
            peak = value

        if peak and peak > 0:
            drawdown = (value / peak) - 1.0
            if drawdown < max_dd:
                max_dd = drawdown

    return round(max_dd, 6)


def _annualization_factor(date_values: list[str], observation_count: int) -> float | None:
    if len(date_values) < 2 or observation_count <= 1:
        return None

    start = datetime.fromisoformat(min(date_values)).date()
    end = datetime.fromisoformat(max(date_values)).date()
    days = (end - start).days

    if days <= 0:
        return None

    years = days / 365.25
    if years <= 0:
        return None

    return observation_count / years


def _annualized_return(starting_equity: float, ending_equity: float, date_values: list[str]) -> float | None:
    if starting_equity <= 0 or ending_equity <= 0 or len(date_values) < 2:
        return None

    start = datetime.fromisoformat(min(date_values)).date()
    end = datetime.fromisoformat(max(date_values)).date()
    years = (end - start).days / 365.25

    if years <= 0:
        return None

    return round((ending_equity / starting_equity) ** (1.0 / years) - 1.0, 6)


def _ratio_metrics(daily_returns: list[float], date_values: list[str]) -> dict[str, Any]:
    if not daily_returns:
        return {
            "mean_return": None,
            "volatility": None,
            "downside_deviation": None,
            "sharpe_ratio": None,
            "sortino_ratio": None,
        }

    avg = mean(daily_returns)
    vol = pstdev(daily_returns) if len(daily_returns) > 1 else 0.0
    downside = [value for value in daily_returns if value < 0]
    downside_dev = pstdev(downside) if len(downside) > 1 else 0.0

    factor = _annualization_factor(date_values, len(daily_returns))
    root_factor = sqrt(factor) if factor and factor > 0 else None

    sharpe = None
    if root_factor and vol > 0:
        sharpe = round((avg / vol) * root_factor, 6)

    sortino = None
    if root_factor and downside_dev > 0:
        sortino = round((avg / downside_dev) * root_factor, 6)

    return {
        "mean_return": round(avg, 6),
        "volatility": round(vol, 6),
        "downside_deviation": round(downside_dev, 6),
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
    }


def _profit_factor(trade_contributions: list[float]) -> float | None:
    gains = sum(value for value in trade_contributions if value > 0)
    losses = abs(sum(value for value in trade_contributions if value < 0))

    if losses == 0:
        return None if gains == 0 else 999.0

    return round(gains / losses, 6)


def _cap_label(min_return_cap: float | None, max_return_cap: float | None) -> str:
    if min_return_cap == -1.0 and max_return_cap == 1.0:
        return "cap_m1_p1"

    if min_return_cap is not None and max_return_cap is not None:
        if min_return_cap <= -999.0 and max_return_cap >= 999.0:
            return "tail_stress_uncapped_m999_p999"

    def format_cap(value: float | None, prefix: str) -> str:
        if value is None:
            return f"{prefix}none"

        text = str(value).replace("-", "m").replace(".", "p")
        return f"{prefix}{text}"

    return f"cap_{format_cap(min_return_cap, 'min_')}_{format_cap(max_return_cap, 'max_')}"


def _active_exposure_summary(trade_events: list[dict[str, Any]]) -> dict[str, Any]:
    if not trade_events:
        return {
            "active_day_count": 0,
            "max_active_trade_count": 0,
            "max_active_trade_date": None,
            "max_active_risk_fraction": 0.0,
            "max_active_risk_date": None,
            "average_active_trade_count": 0.0,
            "average_active_risk_fraction": 0.0,
            "active_exposure_rows": [],
        }

    dates = sorted(
        {
            date
            for event in trade_events
            for date in [event.get("entry_date"), event.get("exit_date")]
            if date
        }
    )

    exposure_rows: list[dict[str, Any]] = []

    for date in dates:
        active = [
            event
            for event in trade_events
            if event.get("entry_date") <= date and event.get("exit_date") > date
        ]

        active_risk = sum(float(event.get("risk_fraction") or 0.0) for event in active)

        exposure_rows.append(
            {
                "date": date,
                "active_trade_count": len(active),
                "active_risk_fraction": round(active_risk, 10),
            }
        )

    max_active_trade_row = max(
        exposure_rows,
        key=lambda row: row["active_trade_count"],
        default=None,
    )
    max_active_risk_row = max(
        exposure_rows,
        key=lambda row: row["active_risk_fraction"],
        default=None,
    )

    return {
        "active_day_count": len(exposure_rows),
        "max_active_trade_count": max_active_trade_row["active_trade_count"] if max_active_trade_row else 0,
        "max_active_trade_date": max_active_trade_row["date"] if max_active_trade_row else None,
        "max_active_risk_fraction": max_active_risk_row["active_risk_fraction"] if max_active_risk_row else 0.0,
        "max_active_risk_date": max_active_risk_row["date"] if max_active_risk_row else None,
        "average_active_trade_count": round(
            sum(row["active_trade_count"] for row in exposure_rows) / len(exposure_rows),
            6,
        ) if exposure_rows else 0.0,
        "average_active_risk_fraction": round(
            sum(row["active_risk_fraction"] for row in exposure_rows) / len(exposure_rows),
            10,
        ) if exposure_rows else 0.0,
        "active_exposure_rows": exposure_rows,
    }


def reconstruct_fixed_horizon_equity(
    events: list[dict[str, Any]],
    *,
    horizon: str,
    starting_equity: float,
    portfolio_risk_budget_pct: float,
    max_risk_per_trade_pct: float,
    min_return_cap: float | None,
    max_return_cap: float | None,
    excluded_symbols: set[str] | None = None,
) -> dict[str, Any]:
    excluded_symbols = excluded_symbols or set()

    scenario_id = f"fixed_horizon_{horizon}_defined_risk_{_cap_label(min_return_cap, max_return_cap)}"
    selected = [
        event
        for event in events
        if str(event["horizon"]) == str(horizon)
        and event["symbol"] not in excluded_symbols
        and event["symbol"] != "UNKNOWN"
    ]

    by_entry_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in selected:
        by_entry_date[event["entry_date"]].append(event)

    trade_events: list[dict[str, Any]] = []
    for entry_date, cohort in by_entry_date.items():
        cohort_size = len(cohort)
        risk_fraction = (
            min(max_risk_per_trade_pct, portfolio_risk_budget_pct / cohort_size)
            if cohort_size
            else 0.0
        )

        for event in cohort:
            raw_return = float(event["strategy_adjusted_return"])
            capped_return = _clamp(raw_return, min_return_cap, max_return_cap)
            contribution_return = risk_fraction * capped_return

            trade_events.append(
                {
                    **event,
                    "scenario_id": scenario_id,
                    "risk_fraction": round(risk_fraction, 10),
                    "raw_strategy_adjusted_return": round(raw_return, 10),
                    "capped_strategy_adjusted_return": round(capped_return, 10),
                    "portfolio_return_contribution": round(contribution_return, 10),
                    "was_return_capped": capped_return != raw_return,
                }
            )

    trade_events = sorted(
        trade_events,
        key=lambda row: (
            row["exit_date"],
            row["entry_date"],
            row["window_id"],
            row["symbol"],
            row["row_index"],
        ),
    )

    by_exit_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in trade_events:
        by_exit_date[event["exit_date"]].append(event)

    equity = starting_equity
    equity_curve: list[dict[str, Any]] = []
    daily_returns: list[float] = []

    for exit_date in sorted(by_exit_date):
        day_events = by_exit_date[exit_date]
        daily_return = sum(event["portfolio_return_contribution"] for event in day_events)
        start_equity = equity
        pnl = start_equity * daily_return
        equity = max(0.0, start_equity + pnl)
        daily_returns.append(daily_return)

        equity_curve.append(
            {
                "date": exit_date,
                "starting_equity": round(start_equity, 6),
                "ending_equity": round(equity, 6),
                "daily_return": round(daily_return, 10),
                "daily_pnl": round(pnl, 6),
                "trade_count": len(day_events),
                "gross_risk_fraction": round(sum(event["risk_fraction"] for event in day_events), 10),
            }
        )

    equity_values = [starting_equity] + [row["ending_equity"] for row in equity_curve]
    date_values = [row["date"] for row in equity_curve]

    exposure_summary = _active_exposure_summary(trade_events)

    trade_contributions = [event["portfolio_return_contribution"] for event in trade_events]
    wins = [value for value in trade_contributions if value > 0]
    losses = [value for value in trade_contributions if value < 0]

    total_return = (equity / starting_equity) - 1.0 if starting_equity else None
    max_dd = _max_drawdown(equity_values)
    annualized = _annualized_return(starting_equity, equity, date_values)
    ratios = _ratio_metrics(daily_returns, date_values)

    calmar = None
    if annualized is not None and max_dd < 0:
        calmar = round(annualized / abs(max_dd), 6)

    worst_trade = None
    if trade_events:
        worst_trade = sorted(
            trade_events,
            key=lambda row: row["portfolio_return_contribution"],
        )[0]

    matrix_metadata_trade_summary = _matrix_metadata_summary(trade_events)

    summary = {
        "scenario_id": scenario_id,
        "horizon": str(horizon),
        "starting_equity": round(starting_equity, 6),
        "ending_equity": round(equity, 6),
        "total_return": round(total_return, 6) if total_return is not None else None,
        "annualized_return": annualized,
        "max_drawdown": max_dd,
        "calmar_ratio": calmar,
        **ratios,
        "trade_count": len(trade_events),
        "exit_day_count": len(equity_curve),
        "win_rate": round(len(wins) / len(trade_events), 6) if trade_events else None,
        "average_win_contribution": round(mean(wins), 10) if wins else None,
        "average_loss_contribution": round(mean(losses), 10) if losses else None,
        "profit_factor": _profit_factor(trade_contributions),
        "tail_capped_trade_count": sum(1 for event in trade_events if event["was_return_capped"]),
        "active_day_count": exposure_summary["active_day_count"],
        "max_active_trade_count": exposure_summary["max_active_trade_count"],
        "max_active_trade_date": exposure_summary["max_active_trade_date"],
        "max_active_risk_fraction": exposure_summary["max_active_risk_fraction"],
        "max_active_risk_date": exposure_summary["max_active_risk_date"],
        "average_active_trade_count": exposure_summary["average_active_trade_count"],
        "average_active_risk_fraction": exposure_summary["average_active_risk_fraction"],
        "exposure_summary": exposure_summary,
        "worst_trade": worst_trade,
        "portfolio_risk_budget_pct": portfolio_risk_budget_pct,
        "max_risk_per_trade_pct": max_risk_per_trade_pct,
        "min_return_cap": min_return_cap,
        "max_return_cap": max_return_cap,
        "excluded_symbols": sorted(excluded_symbols),
        "matrix_metadata_reconstruction_summary": matrix_metadata_trade_summary,
        "exact_matrix_cell_ready_record_count": matrix_metadata_trade_summary.get("exact_matrix_cell_ready_record_count", 0),
        "matrix_metadata_needs_review_record_count": matrix_metadata_trade_summary.get("needs_review_record_count", 0),
        "ready_to_build_exact_matrix_edge_summary": matrix_metadata_trade_summary.get("ready_to_build_exact_matrix_edge_summary", False),
        "curve_interpretation": (
            "Realized exit-date synthetic equity curve using one fixed horizon per signal. "
            "This is not intraday mark-to-market and does not model broker fills or slippage."
        ),
    }

    return {
        "summary": summary,
        "equity_curve": equity_curve,
        "trade_events": trade_events,
    }


def build_portfolio_equity_reconstruction(
    *,
    decoded_window_roots: list[Path],
    period_id: str | None,
    horizons: list[str],
    starting_equity: float,
    portfolio_risk_budget_pct: float,
    max_risk_per_trade_pct: float,
    min_return_cap: float | None,
    max_return_cap: float | None,
    excluded_symbols: set[str] | None = None,
) -> dict[str, Any]:
    events, warnings = load_replay_outcome_events(decoded_window_roots)

    scenario_results = [
        reconstruct_fixed_horizon_equity(
            events,
            horizon=horizon,
            starting_equity=starting_equity,
            portfolio_risk_budget_pct=portfolio_risk_budget_pct,
            max_risk_per_trade_pct=max_risk_per_trade_pct,
            min_return_cap=min_return_cap,
            max_return_cap=max_return_cap,
            excluded_symbols=excluded_symbols,
        )
        for horizon in horizons
    ]

    scenario_summaries = [result["summary"] for result in scenario_results]
    matrix_metadata_reconstruction_summary = _matrix_metadata_summary(events)

    return {
        "adapter_type": "portfolio_equity_reconstruction_builder",
        "artifact_type": "signalforge_portfolio_equity_reconstruction",
        "schema_version": "signalforge_portfolio_equity_reconstruction.v1",
        "period_id": period_id,
        "status": "ready" if events and not warnings else "needs_review",
        "is_ready": bool(events) and not warnings,
        "decoded_window_count": len(decoded_window_roots),
        "source_outcome_event_count": len(events),
        "scenario_count": len(scenario_summaries),
        "scenario_summaries": scenario_summaries,
        "matrix_metadata_reconstruction_summary": matrix_metadata_reconstruction_summary,
        "exact_matrix_cell_ready_record_count": matrix_metadata_reconstruction_summary.get("exact_matrix_cell_ready_record_count", 0),
        "matrix_metadata_needs_review_record_count": matrix_metadata_reconstruction_summary.get("needs_review_record_count", 0),
        "ready_to_build_exact_matrix_edge_summary": matrix_metadata_reconstruction_summary.get("ready_to_build_exact_matrix_edge_summary", False),
        "recommended_next_step": matrix_metadata_reconstruction_summary.get("recommended_next_step"),
        "warnings": warnings,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "automatic_action": None,
        "automatic_close_order": None,
        "automatic_defense_order": None,
        "automatic_roll_order": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "scenario_results": scenario_results,
    }


