from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from datetime import date, datetime
from pathlib import Path
import json
import re
from typing import Any


_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,15}$")


def normalize_symbol(value: Any) -> str:
    if value is None:
        return ""

    symbol = str(value).strip().upper()

    if symbol in {"", "NONE", "NULL", "NAN"}:
        return ""

    return symbol if _SYMBOL_RE.match(symbol) else ""


def parse_date(value: Any) -> date | None:
    if value is None:
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    text = str(value).strip()
    if not text:
        return None

    # Handles YYYY-MM-DD and ISO timestamps.
    text = text[:10]

    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def iso(value: date) -> str:
    return value.isoformat()


def _first_present(row: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key)
    return None


def _extract_state(value: Any, fallback_keys: list[str] | None = None) -> str | None:
    if value is None:
        return None

    if isinstance(value, str):
        return value

    if isinstance(value, dict):
        for key in ["state", "regime_state", "behavior_state", "decision_state", "classification"]:
            if value.get(key) is not None:
                return str(value.get(key))

        if fallback_keys:
            for key in fallback_keys:
                if value.get(key) is not None:
                    return str(value.get(key))

    return str(value)


def _records_from_payload(payload: Any, candidate_keys: list[str]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        for key in candidate_keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

        for key in [
            "rows",
            "records",
            "items",
            "data",
            "snapshots",
            "results",
            "decision_rows",
            "asset_behavior_rows",
            "option_behavior_rows",
            "regime_rows",
            "market_price_rows",
        ]:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

        if "date" in payload or "symbol" in payload:
            return [payload]

    return []


def load_records(path: str | Path, candidate_keys: list[str]) -> list[dict[str, Any]]:
    source = Path(path)

    if source.suffix.lower() == ".jsonl":
        rows: list[dict[str, Any]] = []
        for line in source.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append(item)
        return rows

    payload = json.loads(source.read_text(encoding="utf-8"))
    return _records_from_payload(payload, candidate_keys)


def load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def _symbols_from_value(value: Any) -> set[str]:
    symbols: set[str] = set()

    if value is None:
        return symbols

    if isinstance(value, str):
        for part in value.replace(";", ",").split(","):
            symbol = normalize_symbol(part)
            if symbol:
                symbols.add(symbol)
        return symbols

    if isinstance(value, (list, tuple, set)):
        for item in value:
            symbols.update(_symbols_from_value(item))
        return symbols

    if isinstance(value, dict):
        for key in [
            "symbol",
            "ticker",
            "underlying",
            "underlying_symbol",
            "market_symbol",
            "option_underlying",
        ]:
            symbol = normalize_symbol(value.get(key))
            if symbol:
                symbols.add(symbol)

        for key, item in value.items():
            key_symbol = normalize_symbol(key)
            if key_symbol:
                symbols.add(key_symbol)
            symbols.update(_symbols_from_value(item))

    return symbols


def _get_path(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _extract_symbols(payload: dict[str, Any], paths: list[str]) -> set[str]:
    symbols: set[str] = set()
    for path in paths:
        symbols.update(_symbols_from_value(_get_path(payload, path)))
    return symbols


def extract_inventory_sets(inventory_gate: dict[str, Any]) -> dict[str, set[str]]:
    return {
        "market_symbols": _extract_symbols(
            inventory_gate,
            [
                "market_symbols",
                "eligible_market_symbols",
                "tradable_market_symbols",
                "qc_market_symbols",
                "source_market_symbols",
                "inventory.market_symbols",
                "data_inventory.market_symbols",
                "symbol_inventory.market_symbols",
            ],
        ),
        "option_underlyings": _extract_symbols(
            inventory_gate,
            [
                "option_underlyings",
                "eligible_option_underlyings",
                "qc_option_underlyings",
                "underlying_symbols",
                "inventory.option_underlyings",
                "data_inventory.option_underlyings",
                "symbol_inventory.option_underlyings",
            ],
        ),
        "accepted_missing_option_behavior": _extract_symbols(
            inventory_gate,
            [
                "accepted_missing_option_behavior_symbols",
                "market_symbols_missing_option_behavior_symbols",
                "gap_classification.accepted_missing_option_behavior_symbols",
                "gap_classification.market_symbols_missing_option_behavior_symbols",
            ],
        ),
        "accepted_missing_contract_outcomes": _extract_symbols(
            inventory_gate,
            [
                "accepted_missing_contract_outcome_symbols",
                "accepted_missing_contract_outcomes_symbols",
                "option_underlyings_missing_contract_outcomes_symbols",
                "gap_classification.accepted_missing_contract_outcome_symbols",
                "gap_classification.accepted_missing_contract_outcomes_symbols",
                "gap_classification.option_underlyings_missing_contract_outcomes_symbols",
            ],
        ),
        "context_only_symbols": _extract_symbols(
            inventory_gate,
            [
                "context_only_symbols",
                "context_only_market_symbols",
                "accepted_context_only_symbols",
                "gap_classification.context_only_symbols",
                "gap_classification.accepted_context_only_symbols",
            ],
        ),
    }


def _row_date(row: dict[str, Any]) -> date | None:
    return parse_date(
        _first_present(
            row,
            [
                "date",
                "as_of_date",
                "decision_date",
                "snapshot_date",
                "timestamp",
                "time",
                "week_start",
                "week_end",
                "regime_date",
            ],
        )
    )


def _row_symbol(row: dict[str, Any]) -> str:
    return normalize_symbol(
        _first_present(
            row,
            [
                "symbol",
                "ticker",
                "underlying",
                "underlying_symbol",
                "market_symbol",
                "option_underlying",
            ],
        )
    )



def _extract_state_from_row(
    row: dict[str, Any],
    nested_keys: list[str],
    state_keys: list[str],
) -> str | None:
    for key in nested_keys:
        if key in row:
            state = _extract_state(row.get(key), fallback_keys=state_keys)
            if state:
                return state

    for key in state_keys:
        if row.get(key) is not None:
            state = _extract_state(row.get(key))
            if state:
                return state

    return None


def build_weekly_regime_index(regime_rows: list[dict[str, Any]]) -> dict[str, Any]:
    global_entries: dict[date, dict[str, Any]] = {}
    symbol_entries: dict[str, dict[date, dict[str, Any]]] = {}

    for row in regime_rows:
        row_dt = _row_date(row)
        if row_dt is None:
            continue

        symbol = _row_symbol(row)
        state = _extract_state_from_row(
            row,
            nested_keys=[
                "regime",
                "market_regime",
                "risk_regime",
            ],
            state_keys=[
                "regime_state",
                "aggregate_market_bias",
                "state",
                "classification",
                "decision_state",
            ],
        )

        entry = {
            "state": state,
            "source_state": "available" if state else "missing_state",
            "source_date": iso(row_dt),
        }

        if symbol:
            symbol_entries.setdefault(symbol, {})[row_dt] = entry
        else:
            global_entries[row_dt] = entry

    global_dates = sorted(global_entries)
    symbol_dates = {
        symbol: sorted(entries)
        for symbol, entries in symbol_entries.items()
    }

    return {
        "global_entries": global_entries,
        "global_dates": global_dates,
        "symbol_entries": symbol_entries,
        "symbol_dates": symbol_dates,
    }


def lookup_asof_weekly_regime(
    regime_index: dict[str, Any],
    row_date: date,
    symbol: str,
) -> dict[str, Any]:
    symbol_entries = regime_index["symbol_entries"].get(symbol, {})
    symbol_dates = regime_index["symbol_dates"].get(symbol, [])

    if symbol_dates:
        idx = bisect_right(symbol_dates, row_date) - 1
        if idx >= 0:
            regime_date = symbol_dates[idx]
            entry = dict(symbol_entries[regime_date])
            entry["asof_lag_days"] = (row_date - regime_date).days
            entry["asof_rule"] = "latest_weekly_regime_on_or_before_decision_date"
            return entry

    global_dates = regime_index["global_dates"]
    global_entries = regime_index["global_entries"]

    idx = bisect_right(global_dates, row_date) - 1
    if idx >= 0:
        regime_date = global_dates[idx]
        entry = dict(global_entries[regime_date])
        entry["asof_lag_days"] = (row_date - regime_date).days
        entry["asof_rule"] = "latest_weekly_regime_on_or_before_decision_date"
        return entry

    return {
        "state": None,
        "source_state": "missing",
        "source_date": None,
        "asof_lag_days": None,
        "asof_rule": "latest_weekly_regime_on_or_before_decision_date",
    }


def build_symbol_date_index(
    rows: list[dict[str, Any]],
    state_keys: list[str],
    nested_key: str,
) -> dict[tuple[str, date], dict[str, Any]]:
    index: dict[tuple[str, date], dict[str, Any]] = {}

    for row in rows:
        row_dt = _row_date(row)
        symbol = _row_symbol(row)

        if row_dt is None or not symbol:
            continue

        state = _extract_state_from_row(
            row,
            nested_keys=[nested_key],
            state_keys=state_keys,
        )

        index[(symbol, row_dt)] = {
            "state": state,
            "source_state": "available" if state else "missing_state",
            "source_date": iso(row_dt),
        }

    return index


def build_market_price_index(rows: list[dict[str, Any]]) -> set[tuple[str, date]]:
    index: set[tuple[str, date]] = set()

    for row in rows:
        row_dt = _row_date(row)
        symbol = _row_symbol(row)

        if row_dt and symbol:
            index.add((symbol, row_dt))

    return index


def build_historical_decision_rows(
    inventory_gate: dict[str, Any],
    regime_rows: list[dict[str, Any]],
    asset_behavior_rows: list[dict[str, Any]],
    option_behavior_rows: list[dict[str, Any]] | None,
    start_date: str,
    end_date: str,
    market_price_rows: list[dict[str, Any]] | None = None,
    symbol_overrides: list[str] | None = None,
) -> dict[str, Any]:
    start_dt = parse_date(start_date)
    end_dt = parse_date(end_date)

    if start_dt is None or end_dt is None:
        raise ValueError("start_date and end_date must be YYYY-MM-DD")

    inventory_sets = extract_inventory_sets(inventory_gate)

    allowed_symbols = {
        normalize_symbol(symbol)
        for symbol in (symbol_overrides or [])
        if normalize_symbol(symbol)
    }

    regime_index = build_weekly_regime_index(regime_rows)

    asset_index = build_symbol_date_index(
        asset_behavior_rows,
        state_keys=[
            "asset_behavior",
            "asset_behavior_state",
            "behavior_state",
            "asset_state",
            "state",
            "classification",
        ],
        nested_key="asset_behavior",
    )

    option_index = build_symbol_date_index(
        option_behavior_rows or [],
        state_keys=[
            "option_behavior",
            "option_behavior_state",
            "behavior_state",
            "option_state",
            "state",
            "classification",
        ],
        nested_key="option_behavior",
    )

    market_price_index = (
        build_market_price_index(market_price_rows)
        if market_price_rows is not None
        else None
    )

    decision_keys = sorted(
        (symbol, row_dt)
        for (symbol, row_dt) in asset_index
        if start_dt <= row_dt <= end_dt
        and (not allowed_symbols or symbol in allowed_symbols)
    )

    blockers: list[str] = []

    if not inventory_gate.get("is_ready", False):
        blockers.append("inventory_gate_not_ready")

    if not regime_rows:
        blockers.append("regime_rows_empty")

    if not asset_behavior_rows:
        blockers.append("asset_behavior_rows_empty")

    decision_rows: list[dict[str, Any]] = []

    market_symbols = inventory_sets["market_symbols"]
    accepted_missing_option_behavior = inventory_sets["accepted_missing_option_behavior"]
    accepted_missing_contract_outcomes = inventory_sets["accepted_missing_contract_outcomes"]
    context_only_symbols = inventory_sets["context_only_symbols"]

    for symbol, row_dt in decision_keys:
        row_blocks: list[str] = []

        regime = lookup_asof_weekly_regime(regime_index, row_dt, symbol)

        asset_behavior = asset_index.get(
            (symbol, row_dt),
            {
                "state": None,
                "source_state": "missing",
                "source_date": None,
            },
        )

        option_behavior = option_index.get((symbol, row_dt))

        if option_behavior is None:
            if symbol in accepted_missing_option_behavior:
                option_behavior = {
                    "state": None,
                    "source_state": "accepted_missing",
                    "source_date": None,
                }
                row_blocks.append("accepted_missing_option_behavior")
            else:
                option_behavior = {
                    "state": None,
                    "source_state": "missing",
                    "source_date": None,
                }
                row_blocks.append("missing_option_behavior")

        has_market_price = True

        if market_price_index is not None:
            has_market_price = (symbol, row_dt) in market_price_index
        elif market_symbols:
            has_market_price = symbol in market_symbols

        if not has_market_price:
            row_blocks.append("missing_market_price")

        if symbol in context_only_symbols:
            row_blocks.append("context_only_symbol")

        if regime["source_state"] != "available":
            row_blocks.append("missing_regime")

        if asset_behavior["source_state"] != "available":
            row_blocks.append("missing_asset_behavior")

        if symbol in accepted_missing_contract_outcomes:
            row_blocks.append("accepted_missing_contract_outcomes")

        if "context_only_symbol" in row_blocks:
            data_state = "context_only"
        elif "missing_market_price" in row_blocks:
            data_state = "blocked_missing_market_price"
        elif "missing_regime" in row_blocks:
            data_state = "blocked_missing_regime"
        elif "missing_asset_behavior" in row_blocks:
            data_state = "blocked_missing_asset_behavior"
        elif option_behavior["source_state"] != "available":
            data_state = "partial_option_missing"
        elif "accepted_missing_contract_outcomes" in row_blocks:
            data_state = "partial_contract_outcome_missing"
        else:
            data_state = "complete"

        is_tradable = data_state not in {
            "context_only",
            "blocked_missing_market_price",
            "blocked_missing_regime",
            "blocked_missing_asset_behavior",
        }

        eligible_for_asset_decision = (
            is_tradable
            and regime["source_state"] == "available"
            and asset_behavior["source_state"] == "available"
        )

        eligible_for_option_decision = (
            eligible_for_asset_decision
            and option_behavior["source_state"] == "available"
        )

        eligible_for_strategy_selection = eligible_for_asset_decision

        decision_rows.append(
            {
                "decision_row_id": f"{iso(row_dt)}_{symbol}",
                "date": iso(row_dt),
                "symbol": symbol,
                "regime": regime,
                "asset_behavior": asset_behavior,
                "option_behavior": option_behavior,
                "eligibility": {
                    "is_tradable": is_tradable,
                    "eligible_for_asset_decision": eligible_for_asset_decision,
                    "eligible_for_option_decision": eligible_for_option_decision,
                    "eligible_for_strategy_selection": eligible_for_strategy_selection,
                    "eligible_for_option_strategy_selection": eligible_for_option_decision,
                    "eligible_for_contract_outcome_validation": (
                        eligible_for_option_decision
                        and "accepted_missing_contract_outcomes" not in row_blocks
                    ),
                },
                "data_state": data_state,
                "blocks": sorted(set(row_blocks)),
            }
        )

    data_state_counts = Counter(row["data_state"] for row in decision_rows)
    rows_by_symbol = Counter(row["symbol"] for row in decision_rows)

    eligibility_counts = Counter()
    for row in decision_rows:
        eligibility = row["eligibility"]
        for key, value in eligibility.items():
            if value is True:
                eligibility_counts[key] += 1

    artifact = {
        "adapter_type": "historical_decision_rows_builder",
        "artifact_type": "signalforge_historical_decision_rows",
        "contract": "historical_decision_rows",
        "source_contract": inventory_gate.get("contract"),
        "start_date": iso(start_dt),
        "end_date": iso(end_dt),
        "regime_asof_rule": "latest_weekly_regime_on_or_before_decision_date",
        "is_ready": (
            not blockers
            and len(decision_rows) > 0
            and eligibility_counts["eligible_for_strategy_selection"] > 0
        ),
        "blocker_count": len(blockers),
        "blockers": blockers,
        "summary": {
            "decision_row_count": len(decision_rows),
            "data_state_counts": dict(sorted(data_state_counts.items())),
            "rows_by_symbol": dict(sorted(rows_by_symbol.items())),
            "eligibility_counts": dict(sorted(eligibility_counts.items())),
            "weekly_regime_source_count": len(regime_rows),
            "asset_behavior_source_count": len(asset_behavior_rows),
            "option_behavior_source_count": len(option_behavior_rows or []),
            "market_price_source_count": len(market_price_rows or []),
        },
        "decision_rows": decision_rows,
        "explicit_exclusions": [
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
        ],
    }

    return artifact


def write_historical_decision_rows(artifact: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    rows_path = output_path / "signalforge_historical_decision_rows.jsonl"
    summary_path = output_path / "signalforge_historical_decision_rows_summary.json"

    with rows_path.open("w", encoding="utf-8") as handle:
        for row in artifact["decision_rows"]:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    summary = {
        "adapter_type": artifact["adapter_type"],
        "artifact_type": "signalforge_historical_decision_rows_summary",
        "contract": artifact["contract"],
        "source_contract": artifact["source_contract"],
        "start_date": artifact["start_date"],
        "end_date": artifact["end_date"],
        "regime_asof_rule": artifact["regime_asof_rule"],
        "is_ready": artifact["is_ready"],
        "blocker_count": artifact["blocker_count"],
        "blockers": artifact["blockers"],
        "summary": artifact["summary"],
        "rows_path": str(rows_path),
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "rows_path": str(rows_path),
        "summary_path": str(summary_path),
    }
