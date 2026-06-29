from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Mapping, Optional


def _as_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    except Exception:
        return None


def read_jsonl(path: str | Path) -> Iterable[Dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8-sig", errors="ignore") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc
            if isinstance(payload, dict):
                yield payload


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _derive_realized_return(selection_row: Mapping[str, Any], source: Mapping[str, Any]) -> Optional[float]:
    return _as_float(
        _first_present(
            selection_row.get("selected_strategy_adjusted_return"),
            selection_row.get("selected_strategy_return"),
            source.get("strategy_adjusted_return"),
            source.get("strategy_return"),
            source.get("realized_return"),
        )
    )


def _derive_exclusion_reason(selection_row: Mapping[str, Any], source: Mapping[str, Any]) -> str:
    for key in (
        "portfolio_exclusion_reason",
        "selected_data_state",
        "selected_outcome_state",
        "data_state",
        "outcome_state",
    ):
        value = selection_row.get(key)
        if value not in (None, "", "complete"):
            return str(value)

    for key in ("portfolio_exclusion_reason", "data_state", "outcome_state"):
        value = source.get(key)
        if value not in (None, "", "complete"):
            return str(value)

    return "selected_trade_not_portfolio_reconstructable"




EXECUTION_REALISM_FIELD_NAMES = (
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
)


def _flatten_payload(payload: Any, prefix: str = "", *, max_list_items: int = 8) -> List[tuple[str, Any]]:
    output: List[tuple[str, Any]] = []

    if isinstance(payload, Mapping):
        if prefix:
            output.append((prefix, payload))
        for key, value in payload.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            output.extend(_flatten_payload(value, child_prefix, max_list_items=max_list_items))
        return output

    if isinstance(payload, list):
        if prefix:
            output.append((prefix, payload))
        for item in payload[:max_list_items]:
            child_prefix = f"{prefix}[*]" if prefix else "[*]"
            output.extend(_flatten_payload(item, child_prefix, max_list_items=max_list_items))
        return output

    if prefix:
        output.append((prefix, payload))
    return output


def _path_contains(path: str, *needles: str) -> bool:
    lowered = path.lower().replace(".", "_")
    return all(needle.lower() in lowered for needle in needles)


def _path_contains_any(path: str, needles: tuple[str, ...]) -> bool:
    lowered = path.lower().replace(".", "_")
    return any(needle.lower() in lowered for needle in needles)


def _first_numeric_path(payloads: List[Mapping[str, Any]], *, required: tuple[str, ...], prefer_any: tuple[str, ...] = (), reject_any: tuple[str, ...] = ()) -> tuple[Any, str | None]:
    candidates: List[tuple[str, Any]] = []
    for payload in payloads:
        for path, value in _flatten_payload(payload):
            if not all(_path_contains(path, needle) for needle in required):
                continue
            if reject_any and _path_contains_any(path, reject_any):
                continue
            parsed = _as_float(value)
            if parsed is not None:
                candidates.append((path, parsed))

    if not candidates:
        return None, None

    if prefer_any:
        preferred = [item for item in candidates if _path_contains_any(item[0], prefer_any)]
        if preferred:
            return preferred[0][1], preferred[0][0]

    return candidates[0][1], candidates[0][0]


def _first_present_path(payloads: List[Mapping[str, Any]], *, required_any: tuple[str, ...], reject_any: tuple[str, ...] = ()) -> tuple[Any, str | None]:
    for payload in payloads:
        for path, value in _flatten_payload(payload):
            if not _path_contains_any(path, required_any):
                continue
            if reject_any and _path_contains_any(path, reject_any):
                continue
            if value not in (None, "", [], {}):
                return value, path
    return None, None


def _direct_first(payloads: List[Mapping[str, Any]], keys: tuple[str, ...]) -> tuple[Any, str | None]:
    for payload_index, payload in enumerate(payloads):
        for key in keys:
            value = payload.get(key)
            if value not in (None, "", [], {}):
                prefix = "source_candidate" if payload_index == 0 else "selection_row"
                return value, f"{prefix}.{key}"
    return None, None


def _extract_execution_realism(selection_row: Mapping[str, Any], source: Mapping[str, Any]) -> Dict[str, Any]:
    payloads: List[Mapping[str, Any]] = [source, selection_row]
    source_paths: Dict[str, str] = {}

    def add_numeric(output: Dict[str, Any], target: str, *, required: tuple[str, ...], prefer_any: tuple[str, ...] = (), reject_any: tuple[str, ...] = ()) -> None:
        value, path = _first_numeric_path(payloads, required=required, prefer_any=prefer_any, reject_any=reject_any)
        if value is not None:
            output[target] = value
            if path:
                source_paths[target] = path

    def add_direct(output: Dict[str, Any], target: str, keys: tuple[str, ...]) -> None:
        value, path = _direct_first(payloads, keys)
        if value not in (None, "", [], {}):
            output[target] = value
            if path:
                source_paths[target] = path

    execution: Dict[str, Any] = {}

    add_numeric(execution, "bid_price", required=("bid",), reject_any=("forbidden",))
    add_numeric(execution, "ask_price", required=("ask",), reject_any=("mask",))
    add_numeric(execution, "mid_price", required=("mid",))
    add_numeric(execution, "mark_price", required=("mark",))

    add_numeric(execution, "entry_bid", required=("entry", "bid"), reject_any=("forbidden",))
    add_numeric(execution, "entry_ask", required=("entry", "ask"), reject_any=("mask",))
    add_numeric(execution, "entry_mid", required=("entry", "mid"))
    add_numeric(execution, "entry_mark", required=("entry", "mark"))
    add_numeric(execution, "exit_bid", required=("exit", "bid"), reject_any=("forbidden",))
    add_numeric(execution, "exit_ask", required=("exit", "ask"), reject_any=("mask",))
    add_numeric(execution, "exit_mid", required=("exit", "mid"))
    add_numeric(execution, "exit_mark", required=("exit", "mark"))

    add_numeric(execution, "spread_pct", required=("spread",), prefer_any=("pct", "percent", "ratio"))
    add_numeric(execution, "spread_dollars", required=("spread",), prefer_any=("dollar", "amount", "cost", "width"))

    if "spread_pct" in execution:
        execution["bid_ask_spread_pct"] = execution["spread_pct"]
        execution["option_spread_pct"] = execution["spread_pct"]
        execution["entry_spread_pct"] = execution["spread_pct"]
        source_paths["bid_ask_spread_pct"] = source_paths.get("spread_pct", "derived_from_spread_pct")
        source_paths["option_spread_pct"] = source_paths.get("spread_pct", "derived_from_spread_pct")
        source_paths["entry_spread_pct"] = source_paths.get("spread_pct", "derived_from_spread_pct")

    if "spread_dollars" in execution:
        execution["bid_ask_spread_dollars"] = execution["spread_dollars"]
        execution["option_spread_dollars"] = execution["spread_dollars"]
        execution["entry_spread_dollars"] = execution["spread_dollars"]
        execution["spread_width_dollars"] = execution["spread_dollars"]
        source_paths["bid_ask_spread_dollars"] = source_paths.get("spread_dollars", "derived_from_spread_dollars")
        source_paths["option_spread_dollars"] = source_paths.get("spread_dollars", "derived_from_spread_dollars")
        source_paths["entry_spread_dollars"] = source_paths.get("spread_dollars", "derived_from_spread_dollars")
        source_paths["spread_width_dollars"] = source_paths.get("spread_dollars", "derived_from_spread_dollars")

    contract_count, contract_path = _first_numeric_path(
        payloads,
        required=("contract_count",),
    )
    if contract_count is None:
        contract_count, contract_path = _first_numeric_path(payloads, required=("contract_quantity",))
    if contract_count is None:
        contract_count, contract_path = _first_numeric_path(payloads, required=("quantity",))
    if contract_count is None:
        contract_count, contract_path = _first_numeric_path(payloads, required=("contracts",))

    if contract_count is None or contract_count <= 0:
        execution["contract_count"] = 1.0
        execution["contract_quantity"] = 1.0
        execution["fallback_contract_count"] = 1.0
        execution["contract_count_source"] = "fallback_contract_count"
        source_paths["contract_count"] = "fallback_contract_count"
        source_paths["contract_quantity"] = "fallback_contract_count"
    else:
        execution["contract_count"] = contract_count
        execution["contract_quantity"] = contract_count
        execution["contract_count_source"] = contract_path or "contract_count_field"
        if contract_path:
            source_paths["contract_count"] = contract_path
            source_paths["contract_quantity"] = contract_path

    add_direct(execution, "selected_legs", ("selected_legs", "legs", "strategy_legs", "option_legs", "entry_legs"))
    add_direct(execution, "entry_legs", ("entry_legs", "selected_entry_legs", "legs", "selected_legs"))
    add_direct(execution, "exit_legs", ("exit_legs", "selected_exit_legs"))
    add_direct(execution, "selected_entry_legs", ("selected_entry_legs", "entry_legs", "legs", "selected_legs"))
    add_direct(execution, "selected_exit_legs", ("selected_exit_legs", "exit_legs"))
    add_direct(execution, "option_legs", ("option_legs", "legs", "selected_legs", "entry_legs"))

    option_symbol, option_symbol_path = _first_present_path(
        payloads,
        required_any=("option_symbol", "contract_symbol", "occ_symbol", "option_contract"),
    )
    if option_symbol not in (None, "", [], {}):
        execution["option_symbol"] = option_symbol
        if isinstance(option_symbol, list):
            execution["option_symbols"] = option_symbol
        if option_symbol_path:
            source_paths["option_symbol"] = option_symbol_path

    add_numeric(execution, "open_interest", required=("open_interest",))
    add_numeric(execution, "volume", required=("volume",))
    add_numeric(execution, "quote_count", required=("quote_count",))
    add_direct(execution, "liquidity_state", ("liquidity_state", "option_liquidity_state", "selected_liquidity_state"))
    add_direct(execution, "option_liquidity_state", ("option_liquidity_state", "liquidity_state", "selected_option_liquidity_state"))

    execution["execution_realism_payload"] = {
        "version": "execution_realism_handoff_v1",
        "source_paths": dict(sorted(source_paths.items())),
        "has_bid_and_ask": "bid_price" in execution and "ask_price" in execution,
        "has_spread": "spread_pct" in execution or "spread_dollars" in execution,
        "has_leg_payload": any(key in execution for key in ("selected_legs", "entry_legs", "exit_legs", "option_legs")),
        "has_contract_count": "contract_count" in execution,
    }

    return execution



def _extract_construction_quality(selection_row: Mapping[str, Any], source: Mapping[str, Any]) -> Dict[str, Any]:
    payloads: List[Mapping[str, Any]] = [source, selection_row]

    quality, quality_path = _direct_first(
        payloads,
        (
            "selected_construction_quality",
            "construction_quality",
            "leg_construction_quality",
        ),
    )
    if quality in (None, "", [], {}):
        quality, quality_path = _first_present_path(
            payloads,
            required_any=("construction_quality",),
            reject_any=("reason",),
        )

    reason, reason_path = _direct_first(
        payloads,
        (
            "selected_construction_quality_reason",
            "construction_quality_reason",
            "leg_construction_quality_reason",
        ),
    )
    if reason in (None, "", [], {}):
        reason, reason_path = _first_present_path(
            payloads,
            required_any=("construction_quality_reason",),
        )

    output: Dict[str, Any] = {}
    if quality not in (None, "", [], {}):
        output["selected_construction_quality"] = str(quality)
        output["construction_quality"] = str(quality)
        output["leg_construction_quality"] = str(quality)
        output["construction_quality_source"] = quality_path or "construction_quality_field"

    if reason not in (None, "", [], {}):
        output["selected_construction_quality_reason"] = str(reason)
        output["construction_quality_reason"] = str(reason)
        output["leg_construction_quality_reason"] = str(reason)
        output["construction_quality_reason_source"] = reason_path or "construction_quality_reason_field"

    return output

def _execution_realism_coverage(rows: List[Mapping[str, Any]]) -> Dict[str, Any]:
    scoped = [row for row in rows if row.get("selection_state") == "selected" or row.get("is_selected_trade") is True]
    denominator = len(scoped)

    def pct(predicate: Any) -> float | None:
        if denominator == 0:
            return None
        return sum(1 for row in scoped if predicate(row)) / denominator

    return {
        "scoped_selected_row_count": denominator,
        "bid_ask_coverage": pct(lambda row: row.get("bid_price") not in (None, "") and row.get("ask_price") not in (None, "")),
        "spread_coverage": pct(lambda row: row.get("spread_pct") not in (None, "") or row.get("spread_dollars") not in (None, "")),
        "leg_payload_coverage": pct(lambda row: any(row.get(key) not in (None, "", [], {}) for key in ("selected_legs", "entry_legs", "exit_legs", "option_legs"))),
        "contract_count_coverage": pct(lambda row: row.get("contract_count") not in (None, "")),
        "option_symbol_coverage": pct(lambda row: row.get("option_symbol") not in (None, "", [], {}) or row.get("option_symbols") not in (None, "", [], {})),
        "liquidity_coverage": pct(lambda row: any(row.get(key) not in (None, "", [], {}) for key in ("liquidity_state", "option_liquidity_state", "open_interest", "volume", "quote_count"))),
    }


def _selected_row(selection_row: Mapping[str, Any]) -> Dict[str, Any]:
    source = selection_row.get("source_candidate")
    if not isinstance(source, Mapping):
        source = {}

    row = dict(selection_row)
    execution_realism = _extract_execution_realism(selection_row, source)
    construction_quality_payload = _extract_construction_quality(selection_row, source)

    selected_data_state = str(_first_present(selection_row.get("selected_data_state"), source.get("data_state"), "missing"))
    selected_outcome_state = str(_first_present(selection_row.get("selected_outcome_state"), source.get("outcome_state"), "missing"))
    realized_return = _derive_realized_return(selection_row, source)
    outcome_date = _first_present(
        selection_row.get("selected_outcome_availability_date"),
        source.get("outcome_availability_date"),
        source.get("outcome_date"),
        source.get("target_exit_date"),
    )

    is_complete = (
        selected_data_state == "complete"
        and selected_outcome_state == "complete"
        and realized_return is not None
        and outcome_date not in (None, "")
    )

    row.update(
        {
            "adapter_type": "selected_strategy_outcome_rows_builder",
            "artifact_type": "signalforge_selected_strategy_outcome_row",
            "contract": "selected_strategy_outcome_rows",
            "selected_strategy_outcome_id": f"{selection_row.get('selected_candidate_id') or selection_row.get('decision_row_id')}__selected_outcome",
            "is_selected_trade": True,
            "data_state": "complete" if is_complete else selected_data_state,
            "outcome_state": "complete" if is_complete else selected_outcome_state,
            "realized_return": realized_return if is_complete else None,
            "is_portfolio_reconstructable": bool(is_complete),
            "selected_outcome_availability_date": outcome_date,
            "selected_target_exit_date": _first_present(source.get("target_exit_date"), selection_row.get("selected_target_exit_date")),
            "selected_outcome_date": _first_present(source.get("outcome_date"), selection_row.get("selected_outcome_date"), outcome_date),
            "selected_strategy_pnl": _first_present(source.get("strategy_pnl"), selection_row.get("selected_strategy_pnl")),
            "selected_risk_capital": _first_present(source.get("risk_capital"), selection_row.get("selected_risk_capital")),
            "selected_entry_net_mid_debit": _first_present(source.get("entry_net_mid_debit"), selection_row.get("selected_entry_net_mid_debit")),
            "selected_entry_net_mid_credit": _first_present(source.get("entry_net_mid_credit"), selection_row.get("selected_entry_net_mid_credit")),
            "selected_exit_strategy_value": _first_present(source.get("exit_strategy_value"), selection_row.get("selected_exit_strategy_value")),
            "portfolio_exclusion_reason": None,
            **construction_quality_payload,
            **execution_realism,
        }
    )

    if not is_complete:
        row["portfolio_exclusion_reason"] = _derive_exclusion_reason(selection_row, source)

    return row


def _no_trade_row(selection_row: Mapping[str, Any]) -> Dict[str, Any]:
    row = dict(selection_row)
    row.update(
        {
            "adapter_type": "selected_strategy_outcome_rows_builder",
            "artifact_type": "signalforge_selected_strategy_outcome_row",
            "contract": "selected_strategy_outcome_rows",
            "selected_strategy_outcome_id": f"{selection_row.get('decision_row_id')}__no_trade",
            "is_selected_trade": False,
            "data_state": "no_trade",
            "outcome_state": "no_trade",
            "realized_return": None,
            "is_portfolio_reconstructable": False,
            "portfolio_exclusion_reason": "no_trade",
            "selected_outcome_availability_date": None,
        }
    )
    return row


def build_selected_strategy_outcome_rows_artifact(
    *,
    strategy_selection_rows_path: str | Path,
    output_dir: str | Path,
) -> Dict[str, Any]:
    output_path = Path(output_dir)
    rows_path = output_path / "signalforge_selected_strategy_outcome_rows.jsonl"
    summary_path = output_path / "signalforge_selected_strategy_outcome_rows_summary.json"

    input_rows = list(read_jsonl(strategy_selection_rows_path))
    output_rows: List[Dict[str, Any]] = []

    selection_state_counts: Counter[str] = Counter()
    data_state_counts: Counter[str] = Counter()
    outcome_state_counts: Counter[str] = Counter()
    selected_strategy_counts: Counter[str] = Counter()
    partial_reason_counts: Counter[str] = Counter()

    selected_count = 0
    no_trade_count = 0
    complete_selected_count = 0
    partial_selected_count = 0
    reconstructable_count = 0
    invalid_selection_state_count = 0

    realized_returns: List[float] = []

    for selection_row in input_rows:
        state = str(selection_row.get("selection_state") or "missing")
        selection_state_counts[state] += 1

        if state == "selected":
            selected_count += 1
            row = _selected_row(selection_row)
            selected_strategy_counts[str(row.get("selected_strategy") or "missing")] += 1

            if row.get("is_portfolio_reconstructable") is True:
                complete_selected_count += 1
                reconstructable_count += 1
                value = _as_float(row.get("realized_return"))
                if value is not None:
                    realized_returns.append(value)
            else:
                partial_selected_count += 1
                partial_reason_counts[str(row.get("portfolio_exclusion_reason") or "missing")] += 1

        elif state == "no_trade":
            no_trade_count += 1
            row = _no_trade_row(selection_row)
        else:
            invalid_selection_state_count += 1
            row = dict(selection_row)
            row.update(
                {
                    "adapter_type": "selected_strategy_outcome_rows_builder",
                    "artifact_type": "signalforge_selected_strategy_outcome_row",
                    "contract": "selected_strategy_outcome_rows",
                    "is_selected_trade": False,
                    "data_state": "invalid_selection_state",
                    "outcome_state": "invalid_selection_state",
                    "realized_return": None,
                    "is_portfolio_reconstructable": False,
                    "portfolio_exclusion_reason": "invalid_selection_state",
                }
            )

        data_state_counts[str(row.get("data_state") or "missing")] += 1
        outcome_state_counts[str(row.get("outcome_state") or "missing")] += 1
        output_rows.append(row)

    blockers: List[str] = []
    if not output_rows:
        blockers.append("no_selected_strategy_outcome_rows_written")
    if invalid_selection_state_count:
        blockers.append("invalid_selection_state_rows")
    if selected_count and complete_selected_count == 0:
        blockers.append("no_complete_selected_trade_rows")

    summary: Dict[str, Any] = {
        "adapter_type": "selected_strategy_outcome_rows_builder",
        "artifact_type": "signalforge_selected_strategy_outcome_rows",
        "contract": "selected_strategy_outcome_rows",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "input_selection_row_count": len(input_rows),
        "output_row_count": len(output_rows),
        "selected_row_count": selected_count,
        "no_trade_row_count": no_trade_count,
        "complete_selected_trade_count": complete_selected_count,
        "partial_selected_trade_count": partial_selected_count,
        "portfolio_reconstructable_trade_count": reconstructable_count,
        "invalid_selection_state_count": invalid_selection_state_count,
        "selection_state_counts": dict(sorted(selection_state_counts.items())),
        "data_state_counts": dict(sorted(data_state_counts.items())),
        "outcome_state_counts": dict(sorted(outcome_state_counts.items())),
        "selected_strategy_counts": dict(sorted(selected_strategy_counts.items())),
        "partial_reason_counts": dict(sorted(partial_reason_counts.items())),
        "execution_realism_coverage": _execution_realism_coverage(output_rows),
        "realized_return_summary": {
            "count": len(realized_returns),
            "average": mean(realized_returns) if realized_returns else None,
            "median": median(realized_returns) if realized_returns else None,
            "min": min(realized_returns) if realized_returns else None,
            "max": max(realized_returns) if realized_returns else None,
            "win_rate": (sum(1 for value in realized_returns if value > 0) / len(realized_returns)) if realized_returns else None,
        },
        "paths": {
            "strategy_selection_rows_path": str(strategy_selection_rows_path),
            "rows_path": str(rows_path),
            "summary_path": str(summary_path),
        },
    }

    write_jsonl(rows_path, output_rows)
    write_json(summary_path, summary)

    return summary
