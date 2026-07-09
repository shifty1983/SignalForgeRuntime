# Auto-promoted by Stage 40C7B.
# Core engine for Stage 23 selected trade sequence construction.
# Backtesting should call this module instead of owning selected-trade-sequence logic.

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable


DATE_FIELDS = (
    "decision_date",
    "selection_date",
    "as_of_date",
    "trade_date",
    "entry_date",
    "date",
    "snapshot_date",
    "source_row.decision_date",
    "source_row.as_of_date",
    "source_row.trade_date",
)

SYMBOL_FIELDS = (
    "symbol",
    "underlying",
    "ticker",
    "source_row.symbol",
    "source_row.underlying",
    "source_row.ticker",
)

STRATEGY_FIELDS = (
    "selected_strategy",
    "selected_strategy_name",
    "strategy",
    "strategy_name",
    "candidate_strategy",
    "best_strategy",
    "recommended_strategy",
    "selection.selected_strategy",
    "selection.strategy",
    "selected_candidate.strategy",
    "selected_candidate.strategy_name",
    "selected_candidate.selected_strategy",
    "strategy_selection.selected_strategy",
    "strategy_selection.strategy",
    "source_row.selected_strategy",
    "source_row.strategy",
    "source_row.strategy_name",
)

# Important:
# Do not include expectancy/average fields here.
# Portfolio reconstruction needs realized trade outcome, not historical average expectancy.
REALIZED_RETURN_FIELDS = (
    "strategy_adjusted_return",
    "realized_return",
    "realized_strategy_return",
    "realized_strategy_adjusted_return",
    "selected_strategy_return",
    "selected_strategy_adjusted_return",
    "selected_strategy_realized_return",
    "selected_strategy_realized_adjusted_return",
    "strategy_return",
    "contract_return",
    "contract_outcome_return",
    "outcome_return",
    "actual_return",
    "trade_return",
    "return",
    "return_pct",
    "pnl_pct",
    "strategy_pnl_pct",
    "selected_strategy_pnl_pct",
    "outcome.strategy_adjusted_return",
    "outcome.realized_return",
    "outcome.return",
    "contract_outcome.strategy_adjusted_return",
    "contract_outcome.realized_return",
    "contract_outcome.return",
    "selected_outcome.strategy_adjusted_return",
    "selected_outcome.realized_return",
    "selected_outcome.return",
    "selected_candidate.strategy_adjusted_return",
    "selected_candidate.realized_return",
    "selected_candidate.return",
    "strategy_outcome.strategy_adjusted_return",
    "strategy_outcome.realized_return",
    "strategy_outcome.return",
    "source_row.strategy_adjusted_return",
    "source_row.realized_return",
    "source_row.selected_strategy_adjusted_return",
    "source_row.outcome.strategy_adjusted_return",
    "source_row.contract_outcome.strategy_adjusted_return",
)

EXPECTANCY_ASOF_FIELDS = (
    "expectancy_asof_date",
    "expectancy_window_end",
    "expectancy_training_end",
    "training_window_end",
    "lookback_end",
    "edge_asof_date",
    "source_row.expectancy_asof_date",
    "source_row.expectancy_window_end",
    "source_row.training_window_end",
)

DATA_STATE_FIELDS = (
    "data_state",
    "source_data_state",
    "contract_outcome_state",
    "option_data_state",
    "source_row.data_state",
)


@dataclass(frozen=True)
class PortfolioSelectedTradeSequenceResult:
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


def _get_by_path(row: dict[str, Any], path: str) -> Any:
    current: Any = row
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        if part not in current:
            return None
        current = current[part]
    return current


def _first_present_with_path(
    row: dict[str, Any],
    fields: tuple[str, ...],
) -> tuple[Any, str | None]:
    for field in fields:
        value = _get_by_path(row, field)
        if value is not None and value != "":
            return value, field

    return None, None


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    text = str(value).strip()
    if not text:
        return None

    normalized = text.replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        pass

    for fmt in ("%Y%m%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    return None


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


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _collect_data_states(row: dict[str, Any]) -> list[str]:
    states: list[str] = []

    for field in DATA_STATE_FIELDS:
        value = _get_by_path(row, field)
        if value is None or value == "":
            continue

        if isinstance(value, list):
            states.extend(str(item) for item in value if item is not None and item != "")
        else:
            states.append(str(value))

    return states


def _has_contract_outcome_missing_state(row: dict[str, Any]) -> bool:
    states = _collect_data_states(row)
    joined = " ".join(states).lower()

    contract_terms = (
        "contract_outcome_missing",
        "partial_contract_outcome_missing",
        "missing_contract_outcome",
    )

    return any(term in joined for term in contract_terms)




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


def _extract_execution_realism_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Promote execution-realism and selected-candidate payloads into sequence rows.

    Strategy-selection rows keep the full selected candidate under source_candidate.
    Portfolio sequence rows keep the selection row under source_row.  Search both
    shapes so selected legs and enriched context remain visible downstream.
    """

    def non_empty(value: Any) -> bool:
        return value not in (None, "", [], {})

    def as_dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def get_path(source: dict[str, Any], dotted_path: str) -> Any:
        current: Any = source
        for part in dotted_path.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    output: dict[str, Any] = {}

    source_row = as_dict(row.get("source_row"))
    selection_row = source_row or row

    source_candidate = as_dict(row.get("source_candidate"))
    nested_source_candidate = as_dict(selection_row.get("source_candidate"))

    sources: list[dict[str, Any]] = [row]
    if source_row:
        sources.append(source_row)
    if source_candidate:
        sources.append(source_candidate)
    if nested_source_candidate and nested_source_candidate is not source_candidate:
        sources.append(nested_source_candidate)

    for field in EXECUTION_REALISM_FIELDS:
        output_key = field.split(".")[-1]
        for source in sources:
            value = get_path(source, field)
            if non_empty(value):
                output[output_key] = value
                break

    promotion_fields = {
        "selected_strategy_adjusted_return": (
            "selected_strategy_adjusted_return",
            "strategy_adjusted_return",
        ),
        "selected_outcome_availability_date": (
            "selected_outcome_availability_date",
            "outcome_availability_date",
        ),
        "selected_outcome_state": (
            "selected_outcome_state",
            "outcome_state",
        ),
        "selected_quote_outcome_id": (
            "selected_quote_outcome_id",
            "quote_outcome_id",
        ),
        "selected_leg_selection_id": (
            "selected_leg_selection_id",
            "leg_selection_id",
        ),
        "selected_data_state": (
            "selected_data_state",
            "data_state",
        ),
        "regime": ("regime",),
        "asset_behavior": ("asset_behavior",),
        "option_behavior": ("option_behavior",),
        "research_context": ("research_context",),
        "strategy_family_statuses": ("strategy_family_statuses",),
        "strategy_family_eligibility": ("strategy_family_eligibility",),
        "term_structure_state": ("term_structure_state",),
        "term_structure_shape": ("term_structure_shape",),
        "front_back_iv_spread": ("front_back_iv_spread",),
        "front_back_iv_spread_pct": ("front_back_iv_spread_pct",),
    }

    for output_key, candidate_fields in promotion_fields.items():
        if non_empty(output.get(output_key)):
            continue
        for source in sources:
            for field in candidate_fields:
                value = get_path(source, field)
                if non_empty(value):
                    output[output_key] = value
                    break
            if non_empty(output.get(output_key)):
                break

    selected_legs = output.get("selected_legs")
    if isinstance(selected_legs, list) and selected_legs:
        option_symbols = [
            leg.get("option_symbol")
            for leg in selected_legs
            if isinstance(leg, dict) and leg.get("option_symbol") not in (None, "")
        ]
        if option_symbols and not non_empty(output.get("option_symbols")):
            output["option_symbols"] = option_symbols
        if not non_empty(output.get("selected_leg_count")):
            output["selected_leg_count"] = len(selected_legs)

    if non_empty(output.get("selected_outcome_availability_date")) and not non_empty(output.get("portfolio_realization_date")):
        output["portfolio_realization_date"] = output["selected_outcome_availability_date"]

    return output

def _execution_realism_coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scoped_rows = [row for row in rows if row.get("portfolio_usable") is True]

    def pct(predicate: Any) -> float:
        if not scoped_rows:
            return 0.0
        return sum(1 for row in scoped_rows if predicate(row)) / len(scoped_rows)

    def legs(row: dict[str, Any]) -> list[dict[str, Any]]:
        for key in ("selected_legs", "entry_legs", "exit_legs", "option_legs"):
            value = row.get(key)
            if isinstance(value, list) and value:
                return [leg for leg in value if isinstance(leg, dict)]
        return []

    def has_bid_ask(row: dict[str, Any]) -> bool:
        if row.get("bid_price") not in (None, "") and row.get("ask_price") not in (None, ""):
            return True
        return any(
            leg.get("bid") not in (None, "") and leg.get("ask") not in (None, "")
            for leg in legs(row)
        )

    def has_liquidity(row: dict[str, Any]) -> bool:
        if row.get("open_interest") not in (None, "") or row.get("volume") not in (None, ""):
            return True
        return any(
            leg.get("open_interest") not in (None, "") or leg.get("volume") not in (None, "")
            for leg in legs(row)
        )

    def has_spread(row: dict[str, Any]) -> bool:
        if row.get("spread_pct") not in (None, "") or row.get("bid_ask_spread_pct") not in (None, ""):
            return True
        return any(
            leg.get("spread_pct") not in (None, "")
            or leg.get("bid_ask_spread_pct") not in (None, "")
            for leg in legs(row)
        )

    def has_option_symbol(row: dict[str, Any]) -> bool:
        if row.get("option_symbol") not in (None, "", [], {}) or row.get("option_symbols") not in (None, "", [], {}):
            return True
        return any(leg.get("option_symbol") not in (None, "") for leg in legs(row))

    def has_contract_count(row: dict[str, Any]) -> bool:
        if row.get("contract_count") not in (None, "") or row.get("selected_leg_count") not in (None, ""):
            return True
        return bool(legs(row))

    return {
        "scoped_portfolio_usable_row_count": len(scoped_rows),
        "bid_ask_coverage": pct(has_bid_ask),
        "liquidity_coverage": pct(has_liquidity),
        "spread_coverage": pct(has_spread),
        "option_symbol_coverage": pct(has_option_symbol),
        "contract_count_coverage": pct(has_contract_count),
        "leg_payload_coverage": pct(lambda row: bool(legs(row))),
    }

def _extract_trade(row: dict[str, Any], original_index: int) -> dict[str, Any]:
    raw_date, date_source_field = _first_present_with_path(row, DATE_FIELDS)
    parsed_date = _parse_date(raw_date)

    raw_symbol, symbol_source_field = _first_present_with_path(row, SYMBOL_FIELDS)
    symbol = _string_or_none(raw_symbol)

    raw_strategy, strategy_source_field = _first_present_with_path(row, STRATEGY_FIELDS)
    strategy = _string_or_none(raw_strategy)

    raw_return, realized_return_source_field = _first_present_with_path(
        row,
        REALIZED_RETURN_FIELDS,
    )
    realized_return = _coerce_float(raw_return)

    expectancy_asof_raw, expectancy_asof_source_field = _first_present_with_path(
        row,
        EXPECTANCY_ASOF_FIELDS,
    )
    expectancy_asof_date = _parse_date(expectancy_asof_raw)

    skip_reasons: list[str] = []

    selection_state = _string_or_none(row.get("selection_state"))
    data_state = _string_or_none(row.get("data_state"))
    outcome_state = _string_or_none(row.get("outcome_state"))
    is_selected_trade = row.get("is_selected_trade")
    is_portfolio_reconstructable = row.get("is_portfolio_reconstructable")

    is_no_trade = (
        selection_state == "no_trade"
        or is_selected_trade is False
        or data_state == "no_trade"
        or outcome_state == "no_trade"
    )

    if parsed_date is None:
        skip_reasons.append("missing_or_invalid_decision_date")

    if symbol is None:
        skip_reasons.append("missing_symbol")

    if is_no_trade:
        skip_reasons.append("no_trade")
    else:
        if strategy is None:
            skip_reasons.append("missing_selected_strategy")

        if realized_return is None:
            skip_reasons.append("missing_realized_return")

        if is_portfolio_reconstructable is False:
            skip_reasons.append("portfolio_not_reconstructable")

        if data_state not in (None, "complete"):
            skip_reasons.append("data_state_not_complete")

        if outcome_state not in (None, "complete"):
            skip_reasons.append("outcome_state_not_complete")

        if _has_contract_outcome_missing_state(row):
            skip_reasons.append("contract_outcome_missing")

    if (
        parsed_date is not None
        and expectancy_asof_date is not None
        and expectancy_asof_date > parsed_date
    ):
        skip_reasons.append("future_expectancy_asof_date")

    trade_key = "|".join(
        [
            parsed_date.isoformat() if parsed_date else "UNKNOWN_DATE",
            symbol or "UNKNOWN_SYMBOL",
            strategy or "UNKNOWN_STRATEGY",
        ]
    )

    execution_realism = _extract_execution_realism_fields(row)

    return {
        "original_index": original_index,
        "decision_date": parsed_date.isoformat() if parsed_date else None,
        "symbol": symbol,
        "selected_strategy": strategy,
        "realized_return": realized_return,
        "expectancy_asof_date": expectancy_asof_date.isoformat()
        if expectancy_asof_date
        else None,
        "trade_key": trade_key,
        "selection_state": selection_state,
        "data_state": data_state,
        "outcome_state": outcome_state,
        "is_selected_trade": is_selected_trade,
        "is_portfolio_reconstructable": is_portfolio_reconstructable,
        "portfolio_usable": len(skip_reasons) == 0,
        "portfolio_skip_reasons": skip_reasons,
        "source_fields": {
            "decision_date": date_source_field,
            "symbol": symbol_source_field,
            "selected_strategy": strategy_source_field,
            "realized_return": realized_return_source_field,
            "expectancy_asof_date": expectancy_asof_source_field,
        },
        "source_row": row,
        **execution_realism,
    }


def _count_source_fields(
    rows: list[dict[str, Any]],
    source_field_name: str,
) -> dict[str, int]:
    counts = Counter(
        row.get("source_fields", {}).get(source_field_name) or "missing"
        for row in rows
    )
    return dict(sorted(counts.items()))


def build_portfolio_selected_trade_sequence(
    *,
    strategy_selection_rows: list[dict[str, Any]],
    strategy_selection_summary: dict[str, Any],
    output_dir: str | Path,
) -> PortfolioSelectedTradeSequenceResult:
    output_dir = Path(output_dir)

    blockers: list[str] = []

    summary_ready = bool(strategy_selection_summary.get("is_ready"))
    if not summary_ready:
        blockers.append("strategy_selection_summary_not_ready")

    if not strategy_selection_rows:
        blockers.append("no_strategy_selection_rows")

    extracted_rows = [
        _extract_trade(row, original_index=index)
        for index, row in enumerate(strategy_selection_rows)
    ]

    duplicate_counter = Counter(row["trade_key"] for row in extracted_rows)
    duplicate_trade_keys = sorted(
        trade_key for trade_key, count in duplicate_counter.items() if count > 1
    )

    if duplicate_trade_keys:
        blockers.append("duplicate_symbol_date_strategy_trade_keys")

    future_expectancy_rows = [
        row
        for row in extracted_rows
        if "future_expectancy_asof_date" in row["portfolio_skip_reasons"]
    ]

    if future_expectancy_rows:
        blockers.append("future_expectancy_asof_date_detected")

    invalid_date_rows = [
        row
        for row in extracted_rows
        if "missing_or_invalid_decision_date" in row["portfolio_skip_reasons"]
    ]

    if invalid_date_rows:
        blockers.append("missing_or_invalid_decision_dates_detected")

    usable_rows = [row for row in extracted_rows if row["portfolio_usable"]]

    if strategy_selection_rows and not usable_rows:
        blockers.append("no_portfolio_usable_selected_trades")

    def sort_key(row: dict[str, Any]) -> tuple[str, str, str, int]:
        return (
            row["decision_date"] or "9999-12-31",
            row["symbol"] or "ZZZ_UNKNOWN_SYMBOL",
            row["selected_strategy"] or "ZZZ_UNKNOWN_STRATEGY",
            row["original_index"],
        )

    sequenced_rows = sorted(extracted_rows, key=sort_key)

    for sequence_index, row in enumerate(sequenced_rows, start=1):
        row["sequence_index"] = sequence_index
        row["sequence_id"] = f"portfolio_selected_trade_{sequence_index:08d}"


    legacy_v3_2_2_row_excluded_fields = {
        "contract_count",
        "contract_count_source",
        "contract_quantity",
        "data_state",
        "fallback_contract_count",
        "is_portfolio_reconstructable",
        "is_selected_trade",
        "option_liquidity_state",
        "outcome_state",
        "selection_state",
    }

    for sequenced_row in sequenced_rows:
        skip_reasons = sequenced_row.get("portfolio_skip_reasons")
        if isinstance(skip_reasons, list) and "no_trade" in skip_reasons:
            legacy_skip_reasons = []

            if sequenced_row.get("selected_strategy") in (None, ""):
                legacy_skip_reasons.append("missing_selected_strategy")

            if sequenced_row.get("realized_return") in (None, ""):
                legacy_skip_reasons.append("missing_realized_return")

            if legacy_skip_reasons:
                sequenced_row["portfolio_skip_reasons"] = legacy_skip_reasons

        for excluded_field in legacy_v3_2_2_row_excluded_fields:
            sequenced_row.pop(excluded_field, None)

    output_rows_path = output_dir / "signalforge_portfolio_selected_trade_sequence.jsonl"
    output_summary_path = (
        output_dir / "signalforge_portfolio_selected_trade_sequence_summary.json"
    )

    unique_symbols = sorted(
        {row["symbol"] for row in sequenced_rows if row["symbol"] is not None}
    )
    unique_strategies = sorted(
        {
            row["selected_strategy"]
            for row in sequenced_rows
            if row["selected_strategy"] is not None
        }
    )

    valid_dates = [
        row["decision_date"] for row in sequenced_rows if row["decision_date"] is not None
    ]

    skip_reason_counts = Counter(
        reason
        for row in sequenced_rows
        for reason in row["portfolio_skip_reasons"]
    )

    selection_state_counts = Counter(
        str(row.get("selection_state") or "missing") for row in sequenced_rows
    )
    data_state_counts = Counter(
        str(row.get("data_state") or "missing") for row in sequenced_rows
    )
    outcome_state_counts = Counter(
        str(row.get("outcome_state") or "missing") for row in sequenced_rows
    )

    summary = {
        "adapter_type": "portfolio_selected_trade_sequence_builder",
        "artifact_type": "signalforge_portfolio_selected_trade_sequence",
        "contract": "portfolio_selected_trade_sequence",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "input_selection_row_count": len(strategy_selection_rows),
        "sequenced_trade_count": len(sequenced_rows),
        "portfolio_usable_trade_count": len(usable_rows),
        "portfolio_skipped_trade_count": len(sequenced_rows) - len(usable_rows),
        "skip_reason_counts": dict(sorted(skip_reason_counts.items())),
        "selection_state_counts": dict(sorted(selection_state_counts.items())),
        "data_state_counts": dict(sorted(data_state_counts.items())),
        "outcome_state_counts": dict(sorted(outcome_state_counts.items())),
        "execution_realism_coverage": _execution_realism_coverage(sequenced_rows),
        "source_field_usage_counts": {
            "decision_date": _count_source_fields(sequenced_rows, "decision_date"),
            "symbol": _count_source_fields(sequenced_rows, "symbol"),
            "selected_strategy": _count_source_fields(
                sequenced_rows,
                "selected_strategy",
            ),
            "realized_return": _count_source_fields(
                sequenced_rows,
                "realized_return",
            ),
            "expectancy_asof_date": _count_source_fields(
                sequenced_rows,
                "expectancy_asof_date",
            ),
        },
        "duplicate_trade_key_count": len(duplicate_trade_keys),
        "duplicate_trade_keys_sample": duplicate_trade_keys[:25],
        "future_expectancy_row_count": len(future_expectancy_rows),
        "invalid_date_row_count": len(invalid_date_rows),
        "unique_symbol_count": len(unique_symbols),
        "unique_strategy_count": len(unique_strategies),
        "unique_symbols_sample": unique_symbols[:25],
        "unique_strategies": unique_strategies,
        "date_range": {
            "start": min(valid_dates) if valid_dates else None,
            "end": max(valid_dates) if valid_dates else None,
        },
        "depends_on": {
            "selected_strategy_outcome_rows": "selected_strategy_outcome_rows",
            "selected_strategy_outcome_summary": "selected_strategy_outcome_rows_summary",
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
            "position_sizing",
            "portfolio_equity_curve",
            "drawdown_metrics",
            "return_metrics",
        ],
    }

    write_jsonl(output_rows_path, sequenced_rows)
    write_json(output_summary_path, summary)

    return PortfolioSelectedTradeSequenceResult(rows=sequenced_rows, summary=summary)


def build_from_paths(
    *,
    strategy_selection_rows_path: str | Path,
    strategy_selection_summary_path: str | Path,
    output_dir: str | Path,
) -> PortfolioSelectedTradeSequenceResult:
    strategy_selection_rows = read_jsonl(strategy_selection_rows_path)
    strategy_selection_summary = read_json(strategy_selection_summary_path)

    return build_portfolio_selected_trade_sequence(
        strategy_selection_rows=strategy_selection_rows,
        strategy_selection_summary=strategy_selection_summary,
        output_dir=output_dir,
    )
