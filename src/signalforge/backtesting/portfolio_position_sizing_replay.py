from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class PortfolioPositionSizingReplayResult:
    rows: list[dict[str, Any]]
    summary: dict[str, Any]


def read_json(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8-sig") as f:
        for line_number, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc

            if not isinstance(value, dict):
                raise ValueError(f"Expected object at {path}:{line_number}")

            rows.append(value)

    return rows


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace(",", "")
    if not text:
        return None

    had_percent = "%" in text
    text = text.replace("%", "")

    try:
        parsed = float(text)
    except ValueError:
        return None

    if had_percent:
        return parsed / 100.0

    return parsed


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float) and value.is_integer():
        return int(value)

    text = str(value).strip()
    if not text:
        return None

    try:
        return int(text)
    except ValueError:
        return None


def _get_by_path(row: dict[str, Any], path: str) -> Any:
    current: Any = row

    for part in path.split("."):
        if not isinstance(current, dict):
            return None

        if part not in current:
            return None

        current = current[part]

    return current


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if value is None:
        return False

    text = str(value).strip().lower()
    return text in {"true", "1", "yes", "y"}




EXECUTION_REALISM_FIELDS = (
    "bid_price",
    "ask_price",
    "mid_price",
    "mark_price",
    "entry_bid",
    "entry_ask",
    "entry_mid",
    "entry_mark",
    "exit_bid",
    "exit_ask",
    "exit_mid",
    "exit_mark",
    "spread_pct",
    "bid_ask_spread_pct",
    "option_spread_pct",
    "entry_spread_pct",
    "exit_spread_pct",
    "spread_width_pct",
    "spread_dollars",
    "bid_ask_spread_dollars",
    "option_spread_dollars",
    "entry_spread_dollars",
    "exit_spread_dollars",
    "spread_width_dollars",
    "round_trip_spread_cost_dollars",
    "contract_count",
    "contract_quantity",
    "fallback_contract_count",
    "contract_count_source",
    "option_symbol",
    "option_symbols",
    "open_interest",
    "volume",
    "quote_count",
    "liquidity_state",
    "option_liquidity_state",
    "selected_legs",
    "entry_legs",
    "exit_legs",
    "selected_entry_legs",
    "selected_exit_legs",
    "option_legs",
    "execution_realism_payload",
    "selected_construction_quality",
    "construction_quality",
    "leg_construction_quality",
    "selected_construction_quality_reason",
    "construction_quality_reason",
    "leg_construction_quality_reason",
    "construction_quality_source",
    "construction_quality_reason_source",
)


def _extract_execution_realism_fields(sequence_row: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    source = sequence_row.get("source_row") if isinstance(sequence_row.get("source_row"), dict) else {}

    for field in EXECUTION_REALISM_FIELDS:
        value = sequence_row.get(field)
        if value in (None, "", [], {}) and source:
            value = source.get(field)
        if value not in (None, "", [], {}):
            output[field] = value

    if "contract_count" not in output:
        output["contract_count"] = 1.0
        output["contract_quantity"] = 1.0
        output["fallback_contract_count"] = 1.0
        output["contract_count_source"] = "fallback_contract_count"

    return output


def _execution_realism_coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    sized = [row for row in rows if row.get("sizing_state") == "sized"]
    denominator = len(sized)

    def pct(predicate: Any) -> float | None:
        if denominator == 0:
            return None
        return sum(1 for row in sized if predicate(row)) / denominator

    return {
        "scoped_sized_row_count": denominator,
        "bid_ask_coverage": pct(lambda row: row.get("bid_price") not in (None, "") and row.get("ask_price") not in (None, "")),
        "spread_coverage": pct(lambda row: row.get("spread_pct") not in (None, "") or row.get("spread_dollars") not in (None, "")),
        "leg_payload_coverage": pct(lambda row: any(row.get(key) not in (None, "", [], {}) for key in ("selected_legs", "entry_legs", "exit_legs", "option_legs"))),
        "contract_count_coverage": pct(lambda row: row.get("contract_count") not in (None, "")),
        "option_symbol_coverage": pct(lambda row: row.get("option_symbol") not in (None, "", [], {}) or row.get("option_symbols") not in (None, "", [], {})),
        "liquidity_coverage": pct(lambda row: any(row.get(key) not in (None, "", [], {}) for key in ("liquidity_state", "option_liquidity_state", "open_interest", "volume", "quote_count"))),
    }


def _sequence_sort_key(row: dict[str, Any]) -> tuple[int, str, str, str]:
    sequence_index = _coerce_int(row.get("sequence_index"))

    return (
        sequence_index if sequence_index is not None else 999999999,
        str(row.get("decision_date") or "9999-12-31"),
        str(row.get("symbol") or "ZZZ_UNKNOWN_SYMBOL"),
        str(row.get("selected_strategy") or "ZZZ_UNKNOWN_STRATEGY"),
    )


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, list):
        return [str(item) for item in value if item is not None and item != ""]

    return [str(value)]


def _mean(values: list[float]) -> float | None:
    if not values:
        return None

    return sum(values) / len(values)


def _breakdown_by(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        key = str(row.get(field) or "UNKNOWN")
        grouped[key].append(row)

    result: dict[str, dict[str, Any]] = {}

    for key, group_rows in sorted(grouped.items()):
        pnls = [float(row["realized_pnl_dollars"]) for row in group_rows]
        returns = [float(row["realized_return"]) for row in group_rows]
        wins = [pnl for pnl in pnls if pnl > 0]
        losses = [pnl for pnl in pnls if pnl < 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))

        result[key] = {
            "trade_count": len(group_rows),
            "winning_trade_count": len(wins),
            "losing_trade_count": len(losses),
            "win_rate": len(wins) / len(group_rows) if group_rows else None,
            "total_pnl_dollars": sum(pnls),
            "average_realized_return": _mean(returns),
            "gross_profit_dollars": gross_profit,
            "gross_loss_dollars": gross_loss,
            "profit_factor": gross_profit / gross_loss if gross_loss > 0 else None,
        }

    return result


def build_portfolio_position_sizing_replay(
    *,
    selected_trade_sequence_rows: list[dict[str, Any]],
    selected_trade_sequence_summary: dict[str, Any],
    output_dir: str | Path,
    starting_equity: float = 100000.0,
    risk_per_trade_pct: float = 0.01,
    max_trade_risk_dollars: float = 1000.0,
    min_realized_return: float = -1.0,
    max_realized_return: float = 10.0,
) -> PortfolioPositionSizingReplayResult:
    output_dir = Path(output_dir)

    blockers: list[str] = []

    sequence_summary_ready = bool(selected_trade_sequence_summary.get("is_ready"))
    if not sequence_summary_ready:
        blockers.append("selected_trade_sequence_summary_not_ready")

    if not selected_trade_sequence_rows:
        blockers.append("no_selected_trade_sequence_rows")

    if starting_equity <= 0:
        blockers.append("invalid_starting_equity")

    if risk_per_trade_pct <= 0 or risk_per_trade_pct > 1:
        blockers.append("invalid_risk_per_trade_pct")

    if max_trade_risk_dollars <= 0:
        blockers.append("invalid_max_trade_risk_dollars")

    if not math.isfinite(min_realized_return):
        blockers.append("invalid_min_realized_return")

    if not math.isfinite(max_realized_return):
        blockers.append("invalid_max_realized_return")

    if min_realized_return >= max_realized_return:
        blockers.append("invalid_realized_return_bounds")

    sequenced_rows = sorted(selected_trade_sequence_rows, key=_sequence_sort_key)

    replay_rows: list[dict[str, Any]] = []
    current_equity = float(starting_equity)

    leakage_flag_counts: Counter[str] = Counter()
    return_bound_violation_counts: Counter[str] = Counter()
    non_positive_equity_rows: list[dict[str, Any]] = []

    for replay_index, sequence_row in enumerate(sequenced_rows, start=1):
        sequence_row_usable = bool(sequence_row.get("portfolio_usable"))
        realized_return = _coerce_float(sequence_row.get("realized_return"))
        execution_realism = _extract_execution_realism_fields(sequence_row)

        selection_uses_future_rows = _truthy(
            _get_by_path(sequence_row, "source_row.selection_uses_future_rows")
        )
        selection_uses_current_row_outcome = _truthy(
            _get_by_path(sequence_row, "source_row.selection_uses_current_row_outcome")
        )
        selection_uses_realized_outcome = _truthy(
            _get_by_path(sequence_row, "source_row.selection_uses_realized_outcome")
        )

        selected_outcome_availability_date = _get_by_path(
            sequence_row,
            "source_row.selected_outcome_availability_date",
        )
        if selected_outcome_availability_date in (None, ""):
            selected_outcome_availability_date = sequence_row.get("outcome_availability_date")

        portfolio_realization_date = selected_outcome_availability_date
        realization_date_source = "source_row.selected_outcome_availability_date"
        if portfolio_realization_date in (None, ""):
            portfolio_realization_date = sequence_row.get("decision_date")
            realization_date_source = "decision_date_fallback"

        if sequence_row_usable and realization_date_source == "decision_date_fallback":
            # A usable selected trade should be realized on the date its outcome became
            # available, not on the entry/decision date. Fallback is only acceptable
            # for skipped/no-trade rows.
            sizing_skip_reasons = ["missing_outcome_availability_date_for_portfolio_realization"]
        else:
            sizing_skip_reasons = []

        if selection_uses_future_rows:
            leakage_flag_counts["selection_uses_future_rows"] += 1

        if selection_uses_current_row_outcome:
            leakage_flag_counts["selection_uses_current_row_outcome"] += 1

        if selection_uses_realized_outcome:
            leakage_flag_counts["selection_uses_realized_outcome"] += 1

        inherited_skip_reasons = _as_list(sequence_row.get("portfolio_skip_reasons"))

        if not sequence_row_usable:
            sizing_skip_reasons.append("sequence_row_not_portfolio_usable")
            sizing_skip_reasons.extend(inherited_skip_reasons)

        if sequence_row_usable and realized_return is None:
            sizing_skip_reasons.append("missing_realized_return")

        if sequence_row_usable and realized_return is not None:
            if not math.isfinite(realized_return):
                sizing_skip_reasons.append("non_finite_realized_return")
                return_bound_violation_counts["non_finite_realized_return"] += 1
            elif realized_return < min_realized_return:
                sizing_skip_reasons.append("realized_return_below_min_bound")
                return_bound_violation_counts["realized_return_below_min_bound"] += 1
            elif realized_return > max_realized_return:
                sizing_skip_reasons.append("realized_return_above_max_bound")
                return_bound_violation_counts["realized_return_above_max_bound"] += 1

        if sequence_row_usable and current_equity <= 0:
            sizing_skip_reasons.append("portfolio_equity_depleted_before_trade")

        if sequence_row_usable and selection_uses_future_rows:
            sizing_skip_reasons.append("selection_uses_future_rows")

        if sequence_row_usable and selection_uses_current_row_outcome:
            sizing_skip_reasons.append("selection_uses_current_row_outcome")

        if sequence_row_usable and selection_uses_realized_outcome:
            sizing_skip_reasons.append("selection_uses_realized_outcome")

        can_size = (
            sequence_row_usable
            and realized_return is not None
            and math.isfinite(realized_return)
            and min_realized_return <= realized_return <= max_realized_return
            and current_equity > 0
            and not sizing_skip_reasons
        )

        if can_size:
            equity_before_trade = current_equity
            risk_budget_dollars = max(equity_before_trade * risk_per_trade_pct, 0.0)
            position_risk_dollars = min(risk_budget_dollars, max_trade_risk_dollars)
            realized_pnl_dollars = position_risk_dollars * realized_return
            equity_after_trade = equity_before_trade + realized_pnl_dollars
            current_equity = equity_after_trade

            sizing_state = "sized"

            replay_row = {
                "position_sizing_id": f"portfolio_position_sizing_{replay_index:08d}",
                "replay_index": replay_index,
                "sizing_state": sizing_state,
                "sizing_skip_reasons": [],
                "sequence_id": sequence_row.get("sequence_id"),
                "sequence_index": sequence_row.get("sequence_index"),
                "trade_key": sequence_row.get("trade_key"),
                "decision_date": sequence_row.get("decision_date"),
                "outcome_availability_date": selected_outcome_availability_date,
                "portfolio_realization_date": portfolio_realization_date,
                "realization_date_source": realization_date_source,
                "symbol": sequence_row.get("symbol"),
                "selected_strategy": sequence_row.get("selected_strategy"),
                "realized_return": realized_return,
                "equity_before_trade": equity_before_trade,
                "risk_per_trade_pct": risk_per_trade_pct,
                "risk_budget_dollars": risk_budget_dollars,
                "max_trade_risk_dollars": max_trade_risk_dollars,
                "min_realized_return": min_realized_return,
                "max_realized_return": max_realized_return,
                "compounding": True,
                "position_risk_dollars": position_risk_dollars,
                "realized_pnl_dollars": realized_pnl_dollars,
                "equity_after_trade": equity_after_trade,
                "selection_state": _get_by_path(sequence_row, "source_row.selection_state"),
                "selected_outcome_state": _get_by_path(
                    sequence_row,
                    "source_row.selected_outcome_state",
                ),
                "selected_expectancy_state": _get_by_path(
                    sequence_row,
                    "source_row.selected_expectancy_state",
                ),
                "selected_expectancy_score": _get_by_path(
                    sequence_row,
                    "source_row.selected_expectancy_score",
                ),
                "selected_expectancy_sample_count": _get_by_path(
                    sequence_row,
                    "source_row.selected_expectancy_sample_count",
                ),
                "source_sequence_reference": {
                    "original_index": sequence_row.get("original_index"),
                    "source_fields": sequence_row.get("source_fields", {}),
                },
                **execution_realism,
            }

            if equity_after_trade <= 0:
                non_positive_equity_rows.append(replay_row)

            replay_rows.append(replay_row)

        else:
            replay_rows.append(
                {
                    "position_sizing_id": f"portfolio_position_sizing_{replay_index:08d}",
                    "replay_index": replay_index,
                    "sizing_state": "skipped",
                    "sizing_skip_reasons": sizing_skip_reasons,
                    "sequence_id": sequence_row.get("sequence_id"),
                    "sequence_index": sequence_row.get("sequence_index"),
                    "trade_key": sequence_row.get("trade_key"),
                    "decision_date": sequence_row.get("decision_date"),
                    "outcome_availability_date": selected_outcome_availability_date,
                    "portfolio_realization_date": portfolio_realization_date,
                    "realization_date_source": realization_date_source,
                    "symbol": sequence_row.get("symbol"),
                    "selected_strategy": sequence_row.get("selected_strategy"),
                    "realized_return": realized_return,
                    "equity_before_trade": None,
                    "risk_per_trade_pct": risk_per_trade_pct,
                    "risk_budget_dollars": None,
                    "max_trade_risk_dollars": max_trade_risk_dollars,
                    "position_risk_dollars": None,
                    "realized_pnl_dollars": None,
                    "equity_after_trade": None,
                    "selection_state": _get_by_path(sequence_row, "source_row.selection_state"),
                    "selected_outcome_state": _get_by_path(
                        sequence_row,
                        "source_row.selected_outcome_state",
                    ),
                    "selected_expectancy_state": _get_by_path(
                        sequence_row,
                        "source_row.selected_expectancy_state",
                    ),
                    "selected_expectancy_score": _get_by_path(
                        sequence_row,
                        "source_row.selected_expectancy_score",
                    ),
                    "selected_expectancy_sample_count": _get_by_path(
                        sequence_row,
                        "source_row.selected_expectancy_sample_count",
                    ),
                    "source_sequence_reference": {
                        "original_index": sequence_row.get("original_index"),
                        "source_fields": sequence_row.get("source_fields", {}),
                    },
                    **execution_realism,
                }
            )

    sized_rows = [row for row in replay_rows if row["sizing_state"] == "sized"]
    skipped_rows = [row for row in replay_rows if row["sizing_state"] == "skipped"]

    if selected_trade_sequence_rows and not sized_rows:
        blockers.append("no_sized_trades")

    if leakage_flag_counts:
        blockers.append("selection_leakage_flags_detected")

    if non_positive_equity_rows:
        blockers.append("non_positive_equity_after_sizing")


    legacy_v3_2_2_row_excluded_fields = {
        "contract_count",
        "contract_count_source",
        "contract_quantity",
        "fallback_contract_count",
        "outcome_availability_date",
        "portfolio_realization_date",
        "realization_date_source",
        "option_liquidity_state",
    }

    for replay_row in replay_rows:
        for excluded_field in legacy_v3_2_2_row_excluded_fields:
            replay_row.pop(excluded_field, None)

    output_rows_path = output_dir / "signalforge_portfolio_position_sizing_replay.jsonl"
    output_summary_path = (
        output_dir / "signalforge_portfolio_position_sizing_replay_summary.json"
    )

    pnls = [float(row["realized_pnl_dollars"]) for row in sized_rows]
    realized_returns = [float(row["realized_return"]) for row in sized_rows]
    position_risks = [float(row["position_risk_dollars"]) for row in sized_rows]

    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    flats = [pnl for pnl in pnls if pnl == 0]

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))

    valid_dates = [row["decision_date"] for row in sized_rows if row.get("decision_date")]
    valid_realization_dates = [
        row["portfolio_realization_date"]
        for row in sized_rows
        if row.get("portfolio_realization_date")
    ]
    realization_date_source_counts = Counter(
        str(row.get("realization_date_source") or "missing") for row in replay_rows
    )

    sizing_skip_reason_counts = Counter(
        reason for row in skipped_rows for reason in row["sizing_skip_reasons"]
    )

    unique_symbols = sorted({row["symbol"] for row in sized_rows if row.get("symbol")})
    unique_strategies = sorted(
        {
            row["selected_strategy"]
            for row in sized_rows
            if row.get("selected_strategy")
        }
    )

    summary = {
        "adapter_type": "portfolio_position_sizing_replay_builder",
        "artifact_type": "signalforge_portfolio_position_sizing_replay",
        "contract": "portfolio_position_sizing_replay",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "input_sequence_row_count": len(selected_trade_sequence_rows),
        "sized_trade_count": len(sized_rows),
        "skipped_sequence_row_count": len(skipped_rows),
        "sizing_skip_reason_counts": dict(sorted(sizing_skip_reason_counts.items())),
        "execution_realism_coverage": _execution_realism_coverage(replay_rows),
        "leakage_flag_counts": dict(sorted(leakage_flag_counts.items())),
        "return_bound_violation_counts": dict(
            sorted(return_bound_violation_counts.items())
        ),
        "non_positive_equity_row_count": len(non_positive_equity_rows),
        "capital_model": {
            "starting_equity": starting_equity,
            "ending_equity": current_equity,
            "risk_per_trade_pct": risk_per_trade_pct,
            "max_trade_risk_dollars": max_trade_risk_dollars,
            "min_realized_return": min_realized_return,
            "max_realized_return": max_realized_return,
            "compounding": True,
            "position_risk_formula": (
                "min(current_equity * risk_per_trade_pct, max_trade_risk_dollars)"
            ),
            "realized_pnl_formula": "position_risk_dollars * realized_return",
        },
        "performance_preview": {
            "total_pnl_dollars": sum(pnls),
            "total_return_pct": (current_equity - starting_equity) / starting_equity
            if starting_equity > 0
            else None,
            "winning_trade_count": len(wins),
            "losing_trade_count": len(losses),
            "flat_trade_count": len(flats),
            "win_rate": len(wins) / len(sized_rows) if sized_rows else None,
            "gross_profit_dollars": gross_profit,
            "gross_loss_dollars": gross_loss,
            "profit_factor": gross_profit / gross_loss if gross_loss > 0 else None,
            "largest_win_dollars": max(wins) if wins else None,
            "largest_loss_dollars": min(losses) if losses else None,
            "average_realized_return": _mean(realized_returns),
            "average_position_risk_dollars": _mean(position_risks),
            "min_position_risk_dollars": min(position_risks) if position_risks else None,
            "max_position_risk_dollars": max(position_risks) if position_risks else None,
        },
        "unique_symbol_count": len(unique_symbols),
        "unique_strategy_count": len(unique_strategies),
        "unique_symbols_sample": unique_symbols[:25],
        "unique_strategies": unique_strategies,
        "date_range": {
            "start": min(valid_dates) if valid_dates else None,
            "end": max(valid_dates) if valid_dates else None,
        },
        "realization_date_range": {
            "start": min(valid_realization_dates) if valid_realization_dates else None,
            "end": max(valid_realization_dates) if valid_realization_dates else None,
        },
        "realization_date_source_counts": dict(sorted(realization_date_source_counts.items())),
        "breakdowns": {
            "by_strategy": _breakdown_by(sized_rows, "selected_strategy"),
            "by_symbol_sample": dict(
                list(_breakdown_by(sized_rows, "symbol").items())[:25]
            ),
        },
        "depends_on": {
            "selected_trade_sequence_rows": "portfolio_selected_trade_sequence",
            "selected_trade_sequence_summary": (
                "portfolio_selected_trade_sequence_summary"
            ),
        },
        "paths": {
            "rows_path": str(output_rows_path),
            "summary_path": str(output_summary_path),
        },
        "explicit_exclusions": [
            "new_strategy_selection_logic",
            "new_expectancy_calculation",
            "parameter_optimization",
            "broker_execution",
            "live_orders",
            "slippage_modeling",
            "contract_quantity_selection",
            "option_chain_selection",
            "open_position_overlap_modeling",
            "max_concurrent_position_enforcement",
            "portfolio_equity_curve",
            "drawdown_metrics",
            "cagr",
        ],
    }

    write_jsonl(output_rows_path, replay_rows)
    write_json(output_summary_path, summary)

    return PortfolioPositionSizingReplayResult(rows=replay_rows, summary=summary)


def build_from_paths(
    *,
    selected_trade_sequence_rows_path: str | Path,
    selected_trade_sequence_summary_path: str | Path,
    output_dir: str | Path,
    starting_equity: float = 100000.0,
    risk_per_trade_pct: float = 0.01,
    max_trade_risk_dollars: float = 1000.0,
    min_realized_return: float = -1.0,
    max_realized_return: float = 10.0,
) -> PortfolioPositionSizingReplayResult:
    selected_trade_sequence_rows = read_jsonl(selected_trade_sequence_rows_path)
    selected_trade_sequence_summary = read_json(selected_trade_sequence_summary_path)

    return build_portfolio_position_sizing_replay(
        selected_trade_sequence_rows=selected_trade_sequence_rows,
        selected_trade_sequence_summary=selected_trade_sequence_summary,
        output_dir=output_dir,
        starting_equity=starting_equity,
        risk_per_trade_pct=risk_per_trade_pct,
        max_trade_risk_dollars=max_trade_risk_dollars,
        min_realized_return=min_realized_return,
        max_realized_return=max_realized_return,
    )

