"""Build historical strategy leg-selection rows from SignalForge expectancy candidate rows.

Input grain:
    decision_date + symbol + strategy + holding_period_days

Output grain:
    selected trade structure at the same grain, with concrete option legs.

This adapter performs no broker calls, no order routing, no fills, no live
execution, and no slippage modeling. It selects point-in-time option contracts
from the raw QuantConnect option-chain research export for research/backtest
use only.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


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

SUPPORTED_STRATEGIES = {
    "long_call",
    "long_put",
    "bull_call_debit_spread",
    "bear_put_debit_spread",
    "put_credit_spread",
    "call_credit_spread",
    "iron_condor",
    "iron_butterfly",
    "calendar_spread",
    "diagonal_spread",
}


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":")))
            f.write("\n")
            count += 1
    return count


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out: dict[str, Any] = {}
            for key in fields:
                value = row.get(key)
                if isinstance(value, (dict, list)):
                    out[key] = json.dumps(value, sort_keys=True, separators=(",", ":"))
                else:
                    out[key] = value
            writer.writerow(out)


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _date(row: dict[str, Any]) -> str:
    return _text(row.get("decision_date") or row.get("quote_date") or row.get("date"))


def _symbol(row: dict[str, Any]) -> str:
    return _text(row.get("symbol") or row.get("underlying_symbol"))


def _right(row: dict[str, Any]) -> str:
    return _text(row.get("option_right")).lower()


def _strike(row: dict[str, Any]) -> float | None:
    return _num(row.get("strike"))


def _dte(row: dict[str, Any]) -> int | None:
    value = _num(row.get("dte"))
    if value is None:
        return None
    return int(round(value))


def _mid(row: dict[str, Any]) -> float | None:
    mid = _num(row.get("mid_price"))
    if mid is not None and mid > 0:
        return mid
    bid = _num(row.get("bid"))
    ask = _num(row.get("ask"))
    if bid is not None and ask is not None and bid >= 0 and ask > 0 and ask >= bid:
        return (bid + ask) / 2
    return None


def _spread_pct(row: dict[str, Any]) -> float | None:
    spread = _num(row.get("spread_pct"))
    if spread is not None:
        return spread
    bid = _num(row.get("bid"))
    ask = _num(row.get("ask"))
    mid = _mid(row)
    if bid is None or ask is None or mid is None or mid <= 0:
        return None
    return max(0.0, ask - bid) / mid


def _valid_contract(row: dict[str, Any], max_spread_pct: float, min_open_interest: int, min_volume: int) -> bool:
    if _right(row) not in {"call", "put"}:
        return False
    if _strike(row) is None or _dte(row) is None:
        return False
    mid = _mid(row)
    if mid is None or mid <= 0:
        return False
    bid = _num(row.get("bid"))
    ask = _num(row.get("ask"))
    if bid is None or ask is None or bid < 0 or ask <= 0 or ask < bid:
        return False
    spread = _spread_pct(row)
    if spread is None or spread > max_spread_pct:
        return False
    oi = _num(row.get("open_interest")) or 0
    vol = _num(row.get("volume")) or 0
    if oi < min_open_interest and vol < min_volume:
        return False
    return True


def _leg(row: dict[str, Any], *, action: str, quantity: int, role: str) -> dict[str, Any]:
    return {
        "action": action,
        "quantity": quantity,
        "role": role,
        "option_symbol": row.get("option_symbol"),
        "option_right": _right(row),
        "strike": _strike(row),
        "expiration": row.get("expiration"),
        "dte": _dte(row),
        "bid": _num(row.get("bid")),
        "ask": _num(row.get("ask")),
        "mid_price": _mid(row),
        "spread_pct": _spread_pct(row),
        "implied_volatility": _num(row.get("implied_volatility")),
        "delta": _num(row.get("delta")),
        "gamma": _num(row.get("gamma")),
        "theta": _num(row.get("theta")),
        "vega": _num(row.get("vega")),
        "open_interest": _num(row.get("open_interest")),
        "volume": _num(row.get("volume")),
    }


def _group_by_expiration(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        exp = row.get("expiration")
        if exp:
            groups[str(exp)].append(row)
    return dict(groups)


def _avg_dte(rows: list[dict[str, Any]]) -> float:
    values = [_dte(row) for row in rows]
    values = [v for v in values if v is not None]
    if not values:
        return 9999.0
    return sum(values) / len(values)


def _choose_expiration(rows: list[dict[str, Any]], target_dte: int, min_dte: int = 1, max_dte: int | None = None) -> str | None:
    groups = _group_by_expiration([row for row in rows if (_dte(row) or 0) >= min_dte and (max_dte is None or (_dte(row) or 0) <= max_dte)])
    if not groups:
        return None
    return min(groups, key=lambda exp: abs(_avg_dte(groups[exp]) - target_dte))


def _candidate_expirations(
    rows: list[dict[str, Any]],
    target_dte: int,
    min_dte: int = 1,
    max_dte: int | None = None,
    max_expirations: int = 4,
) -> list[str]:
    groups = _group_by_expiration([
        row
        for row in rows
        if (_dte(row) or 0) >= min_dte and (max_dte is None or (_dte(row) or 0) <= max_dte)
    ])
    if not groups:
        return []
    return sorted(groups, key=lambda exp: abs(_avg_dte(groups[exp]) - target_dte))[:max_expirations]


def _rank_by_delta(
    rows: list[dict[str, Any]],
    right: str,
    target_delta: float,
    expiration: str | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    candidates = [row for row in rows if _right(row) == right and (expiration is None or row.get("expiration") == expiration)]
    return sorted(candidates, key=lambda row: _contract_score(row, target_delta=target_delta))[:limit]


def _contract_score(row: dict[str, Any], target_delta: float | None = None, target_strike: float | None = None) -> tuple[float, float, float, float]:
    delta = _num(row.get("delta"))
    spread = _spread_pct(row) or 9.0
    oi = _num(row.get("open_interest")) or 0.0
    vol = _num(row.get("volume")) or 0.0
    strike = _strike(row)

    if target_delta is not None and delta is not None:
        primary = abs(delta - target_delta)
    elif target_strike is not None and strike is not None:
        primary = abs(strike - target_strike)
    else:
        primary = 999.0

    # Tie-breakers prefer tighter spreads and more displayed activity.
    return (primary, spread, -math.log1p(oi + vol), _mid(row) or 999.0)


def _choose_by_delta(rows: list[dict[str, Any]], right: str, target_delta: float, expiration: str | None = None) -> dict[str, Any] | None:
    candidates = [row for row in rows if _right(row) == right and (expiration is None or row.get("expiration") == expiration)]
    if not candidates:
        return None
    return min(candidates, key=lambda row: _contract_score(row, target_delta=target_delta))


def _choose_by_strike(rows: list[dict[str, Any]], right: str, target_strike: float, expiration: str | None = None) -> dict[str, Any] | None:
    candidates = [row for row in rows if _right(row) == right and (expiration is None or row.get("expiration") == expiration)]
    if not candidates:
        return None
    return min(candidates, key=lambda row: _contract_score(row, target_strike=target_strike))


def _choose_wing(rows: list[dict[str, Any]], *, right: str, expiration: str, anchor: dict[str, Any], direction: str) -> dict[str, Any] | None:
    anchor_strike = _strike(anchor)
    if anchor_strike is None:
        return None
    candidates = [row for row in rows if _right(row) == right and row.get("expiration") == expiration and _strike(row) is not None]
    if direction == "higher":
        candidates = [row for row in candidates if (_strike(row) or 0) > anchor_strike]
        return min(candidates, key=lambda row: (_strike(row) or 999999, _spread_pct(row) or 9)) if candidates else None
    if direction == "lower":
        candidates = [row for row in candidates if (_strike(row) or 0) < anchor_strike]
        return max(candidates, key=lambda row: (_strike(row) or -999999, -(_spread_pct(row) or 9))) if candidates else None
    return None


def _target_expiration_dte(holding_period_days: int) -> int:
    # Old artifacts often picked near-term expirations for 5/10d and 30-60d for longer holds.
    if holding_period_days <= 10:
        return 21
    if holding_period_days <= 21:
        return 35
    return 55


def _front_back_expirations(rows: list[dict[str, Any]], holding_period_days: int) -> tuple[str | None, str | None]:
    front_target = 21 if holding_period_days <= 21 else 35
    back_target = 45 if holding_period_days <= 21 else 70
    front = _choose_expiration(rows, target_dte=front_target, min_dte=max(5, holding_period_days))
    if front is None:
        return None, None
    front_dte = _avg_dte([row for row in rows if row.get("expiration") == front])
    back_candidates = [row for row in rows if (_dte(row) or 0) > front_dte + 7]
    back = _choose_expiration(back_candidates, target_dte=back_target, min_dte=int(front_dte + 8))
    return front, back


def _net_mid(legs: list[dict[str, Any]]) -> float:
    total = 0.0
    for leg in legs:
        mid = _num(leg.get("mid_price")) or 0.0
        qty = int(leg.get("quantity") or 1)
        if leg.get("action") == "buy":
            total -= mid * qty
        elif leg.get("action") == "sell":
            total += mid * qty
    return total


def _select_long(chain: list[dict[str, Any]], strategy: str, holding_period_days: int) -> tuple[list[dict[str, Any]] | None, str, list[str]]:
    right = "call" if strategy == "long_call" else "put"
    target_delta = 0.50 if right == "call" else -0.50
    target_dte = _target_expiration_dte(holding_period_days)
    exp = _choose_expiration(chain, target_dte=target_dte, min_dte=max(1, holding_period_days))
    if not exp:
        return None, f"{strategy}_target_50_delta_nearest_expiration", ["no_valid_expiration"]
    opt = _choose_by_delta(chain, right, target_delta, exp)
    if not opt:
        return None, f"{strategy}_target_50_delta_nearest_expiration", ["no_valid_contract"]
    role = strategy
    return [_leg(opt, action="buy", quantity=1, role=role)], f"{strategy}_target_50_delta_nearest_expiration", []


def _select_vertical(chain: list[dict[str, Any]], strategy: str, holding_period_days: int) -> tuple[list[dict[str, Any]] | None, str, list[str]]:
    target_dte = _target_expiration_dte(holding_period_days)
    expirations = _candidate_expirations(chain, target_dte=target_dte, min_dte=max(1, holding_period_days), max_expirations=4)
    if not expirations:
        return None, f"{strategy}_nearest_expiration_delta_width", ["no_valid_expiration"]

    sign_failures = 0
    attempted = 0

    for exp_idx, exp in enumerate(expirations):
        alt_suffix = "" if exp_idx == 0 else "_alternate_expiration"

        if strategy == "bull_call_debit_spread":
            for long in _rank_by_delta(chain, "call", 0.55, exp, limit=8):
                attempted += 1
                short = _choose_wing(chain, right="call", expiration=exp, anchor=long, direction="higher")
                if not short:
                    continue
                legs = [_leg(long, action="buy", quantity=1, role="long_call"), _leg(short, action="sell", quantity=1, role="short_call")]
                if _net_mid(legs) < 0:
                    return legs, f"bull_call_debit_spread_buy_55_delta_sell_next_higher_call{alt_suffix}", []
                sign_failures += 1

        elif strategy == "bear_put_debit_spread":
            for long in _rank_by_delta(chain, "put", -0.55, exp, limit=8):
                attempted += 1
                short = _choose_wing(chain, right="put", expiration=exp, anchor=long, direction="lower")
                if not short:
                    continue
                legs = [_leg(long, action="buy", quantity=1, role="long_put"), _leg(short, action="sell", quantity=1, role="short_put")]
                if _net_mid(legs) < 0:
                    return legs, f"bear_put_debit_spread_buy_55_delta_sell_next_lower_put{alt_suffix}", []
                sign_failures += 1

        elif strategy == "put_credit_spread":
            for short in _rank_by_delta(chain, "put", -0.30, exp, limit=8):
                attempted += 1
                long = _choose_wing(chain, right="put", expiration=exp, anchor=short, direction="lower")
                if not long:
                    continue
                legs = [_leg(short, action="sell", quantity=1, role="short_put"), _leg(long, action="buy", quantity=1, role="long_put")]
                if _net_mid(legs) > 0:
                    return legs, f"put_credit_spread_sell_30_delta_buy_next_lower_put{alt_suffix}", []
                sign_failures += 1

        elif strategy == "call_credit_spread":
            for short in _rank_by_delta(chain, "call", 0.30, exp, limit=8):
                attempted += 1
                long = _choose_wing(chain, right="call", expiration=exp, anchor=short, direction="higher")
                if not long:
                    continue
                legs = [_leg(short, action="sell", quantity=1, role="short_call"), _leg(long, action="buy", quantity=1, role="long_call")]
                if _net_mid(legs) > 0:
                    return legs, f"call_credit_spread_sell_30_delta_buy_next_higher_call{alt_suffix}", []
                sign_failures += 1

    if sign_failures:
        reason = "vertical_not_net_credit" if strategy in {"put_credit_spread", "call_credit_spread"} else "vertical_not_net_debit"
        return None, f"{strategy}_nearest_expiration_delta_width", [reason]
    if attempted:
        return None, f"{strategy}_nearest_expiration_delta_width", ["no_valid_vertical_wing"]
    return None, f"{strategy}_nearest_expiration_delta_width", ["no_valid_vertical_legs"]


def _select_iron_condor(chain: list[dict[str, Any]], holding_period_days: int) -> tuple[list[dict[str, Any]] | None, str, list[str]]:
    target_dte = _target_expiration_dte(holding_period_days)
    exp = _choose_expiration(chain, target_dte=target_dte, min_dte=max(1, holding_period_days))
    if not exp:
        return None, "iron_condor_sell_20_delta_wings", ["no_valid_expiration"]
    short_call = _choose_by_delta(chain, "call", 0.20, exp)
    long_call = _choose_wing(chain, right="call", expiration=exp, anchor=short_call, direction="higher") if short_call else None
    short_put = _choose_by_delta(chain, "put", -0.20, exp)
    long_put = _choose_wing(chain, right="put", expiration=exp, anchor=short_put, direction="lower") if short_put else None
    if not all([short_call, long_call, short_put, long_put]):
        return None, "iron_condor_sell_20_delta_wings", ["no_valid_iron_condor_legs"]
    legs = [
        _leg(short_put, action="sell", quantity=1, role="short_put"),
        _leg(long_put, action="buy", quantity=1, role="long_put"),
        _leg(short_call, action="sell", quantity=1, role="short_call"),
        _leg(long_call, action="buy", quantity=1, role="long_call"),
    ]
    if _net_mid(legs) <= 0:
        return None, "iron_condor_sell_20_delta_wings", ["iron_condor_not_net_credit"]
    return legs, "iron_condor_sell_20_delta_wings", []


def _select_iron_butterfly(chain: list[dict[str, Any]], holding_period_days: int) -> tuple[list[dict[str, Any]] | None, str, list[str]]:
    target_dte = _target_expiration_dte(holding_period_days)
    exp = _choose_expiration(chain, target_dte=target_dte, min_dte=max(1, holding_period_days))
    if not exp:
        return None, "iron_butterfly_sell_atm_buy_wings", ["no_valid_expiration"]
    exp_rows = [row for row in chain if row.get("expiration") == exp]
    underlying = next((_num(row.get("underlying_price")) for row in exp_rows if _num(row.get("underlying_price")) is not None), None)
    if underlying is None:
        return None, "iron_butterfly_sell_atm_buy_wings", ["missing_underlying_price"]
    atm_call = _choose_by_strike(exp_rows, "call", underlying, exp)
    if not atm_call:
        return None, "iron_butterfly_sell_atm_buy_wings", ["no_atm_call"]
    body_strike = _strike(atm_call)
    if body_strike is None:
        return None, "iron_butterfly_sell_atm_buy_wings", ["no_body_strike"]
    atm_put = _choose_by_strike(exp_rows, "put", body_strike, exp)
    long_call = _choose_wing(exp_rows, right="call", expiration=exp, anchor=atm_call, direction="higher")
    long_put = _choose_wing(exp_rows, right="put", expiration=exp, anchor=atm_put, direction="lower") if atm_put else None
    if not all([atm_put, long_call, long_put]):
        return None, "iron_butterfly_sell_atm_buy_wings", ["no_valid_iron_butterfly_legs"]
    legs = [
        _leg(atm_put, action="sell", quantity=1, role="short_put_body"),
        _leg(long_put, action="buy", quantity=1, role="long_put_wing"),
        _leg(atm_call, action="sell", quantity=1, role="short_call_body"),
        _leg(long_call, action="buy", quantity=1, role="long_call_wing"),
    ]
    if _net_mid(legs) <= 0:
        return None, "iron_butterfly_sell_atm_buy_wings", ["iron_butterfly_not_net_credit"]
    return legs, "iron_butterfly_sell_atm_buy_wings", []


def _select_calendar(chain: list[dict[str, Any]], holding_period_days: int) -> tuple[list[dict[str, Any]] | None, str, list[str]]:
    front_exp, back_exp = _front_back_expirations(chain, holding_period_days)
    if not front_exp or not back_exp:
        return None, "calendar_spread_sell_front_buy_back_atm_call", ["no_valid_front_back_expiration"]
    rows = [row for row in chain if row.get("expiration") in {front_exp, back_exp}]
    underlying = next((_num(row.get("underlying_price")) for row in rows if _num(row.get("underlying_price")) is not None), None)
    if underlying is None:
        return None, "calendar_spread_sell_front_buy_back_atm_call", ["missing_underlying_price"]
    front = _choose_by_strike(rows, "call", underlying, front_exp)
    if not front or _strike(front) is None:
        return None, "calendar_spread_sell_front_buy_back_atm_call", ["no_front_atm_call"]
    back = _choose_by_strike(rows, "call", _strike(front) or underlying, back_exp)
    if not back:
        return None, "calendar_spread_sell_front_buy_back_atm_call", ["no_matching_back_call"]
    legs = [_leg(front, action="sell", quantity=1, role="short_front_call"), _leg(back, action="buy", quantity=1, role="long_back_call")]
    if _net_mid(legs) >= 0:
        return None, "calendar_spread_sell_front_buy_back_atm_call", ["calendar_not_net_debit"]
    return legs, "calendar_spread_sell_front_buy_back_atm_call", []


def _select_diagonal(candidate: dict[str, Any], chain: list[dict[str, Any]], holding_period_days: int) -> tuple[list[dict[str, Any]] | None, str, list[str]]:
    front_exp, back_exp = _front_back_expirations(chain, holding_period_days)
    if not front_exp or not back_exp:
        return None, "diagonal_spread_buy_back_50_delta_sell_front_30_delta", ["no_valid_front_back_expiration"]
    asset_state = _text(candidate.get("asset_behavior_state"))
    direction = _text(candidate.get("strategy_direction"))
    bullish = direction == "bullish" or asset_state in {"constructive", "confirmed_uptrend", "developing_uptrend", "uptrend"}
    right = "call" if bullish else "put"
    back_target = 0.50 if right == "call" else -0.50
    front_target = 0.30 if right == "call" else -0.30
    rows = [row for row in chain if row.get("expiration") in {front_exp, back_exp}]
    back = _choose_by_delta(rows, right, back_target, back_exp)
    front = _choose_by_delta(rows, right, front_target, front_exp)
    if not back or not front:
        return None, "diagonal_spread_buy_back_50_delta_sell_front_30_delta", ["no_valid_diagonal_legs"]
    # For calls, sell front strike at or above back strike; for puts, at or below.
    b_strike = _strike(back)
    f_strike = _strike(front)
    if b_strike is not None and f_strike is not None:
        if right == "call" and f_strike < b_strike:
            front = _choose_wing(rows, right="call", expiration=front_exp, anchor=back, direction="higher") or front
        elif right == "put" and f_strike > b_strike:
            front = _choose_wing(rows, right="put", expiration=front_exp, anchor=back, direction="lower") or front
    legs = [_leg(front, action="sell", quantity=1, role=f"short_front_{right}"), _leg(back, action="buy", quantity=1, role=f"long_back_{right}")]
    if _net_mid(legs) >= 0:
        return None, "diagonal_spread_buy_back_50_delta_sell_front_30_delta", ["diagonal_not_net_debit"]
    return legs, "diagonal_spread_buy_back_50_delta_sell_front_30_delta", []


def _select_legs(candidate: dict[str, Any], chain: list[dict[str, Any]]) -> tuple[list[dict[str, Any]] | None, str, list[str]]:
    strategy = _text(candidate.get("strategy"))
    holding = int(candidate.get("holding_period_days") or 0)
    if strategy in {"long_call", "long_put"}:
        return _select_long(chain, strategy, holding)
    if strategy in {"bull_call_debit_spread", "bear_put_debit_spread", "put_credit_spread", "call_credit_spread"}:
        return _select_vertical(chain, strategy, holding)
    if strategy == "iron_condor":
        return _select_iron_condor(chain, holding)
    if strategy == "iron_butterfly":
        return _select_iron_butterfly(chain, holding)
    if strategy == "calendar_spread":
        return _select_calendar(chain, holding)
    if strategy == "diagonal_spread":
        return _select_diagonal(candidate, chain, holding)
    return None, f"{strategy}_unsupported", ["unsupported_strategy"]


def _chain_metrics(legs: list[dict[str, Any]]) -> dict[str, Any]:
    dtes = [_num(leg.get("dte")) for leg in legs if _num(leg.get("dte")) is not None]
    expirations = sorted({str(leg.get("expiration")) for leg in legs if leg.get("expiration")})
    ivs = [_num(leg.get("implied_volatility")) for leg in legs if _num(leg.get("implied_volatility")) is not None]
    front_exp = expirations[0] if expirations else None
    back_exp = expirations[-1] if len(expirations) > 1 else None
    front_ivs = [_num(leg.get("implied_volatility")) for leg in legs if leg.get("expiration") == front_exp and _num(leg.get("implied_volatility")) is not None]
    back_ivs = [_num(leg.get("implied_volatility")) for leg in legs if leg.get("expiration") == back_exp and _num(leg.get("implied_volatility")) is not None] if back_exp else []
    front_iv = sum(front_ivs) / len(front_ivs) if front_ivs else None
    back_iv = sum(back_ivs) / len(back_ivs) if back_ivs else None
    spread = None
    spread_pct = None
    shape = None
    state = "unavailable"
    if front_iv is not None and back_iv is not None:
        spread = front_iv - back_iv
        spread_pct = spread / back_iv if back_iv else None
        state = "available"
        if spread_pct is not None and spread_pct > 0.05:
            shape = "backwardated"
        elif spread_pct is not None and spread_pct < -0.05:
            shape = "contango"
        else:
            shape = "flat"
    return {
        "front_dte": int(min(dtes)) if dtes else None,
        "back_dte": int(max(dtes)) if len(set(dtes)) > 1 else None,
        "front_expiration": front_exp,
        "back_expiration": back_exp,
        "front_iv": front_iv,
        "back_iv": back_iv,
        "front_back_iv_spread": spread,
        "front_back_iv_spread_pct": spread_pct,
        "term_structure_state": state,
        "term_structure_shape": shape,
    }


def _net_fields(legs: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    net = _net_mid(legs)
    if net > 0:
        return None, net
    if net < 0:
        return abs(net), None
    return 0.0, 0.0


def _targeted_delta_specs(strategy: str, legs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []

    def add(role: str, target: float) -> None:
        for leg in legs:
            if leg.get("role") == role:
                delta = _num(leg.get("delta"))
                if delta is not None:
                    specs.append({
                        "role": role,
                        "target_delta": target,
                        "selected_delta": delta,
                        "delta_deviation": abs(abs(delta) - abs(target)),
                    })
                return

    if strategy == "long_call":
        add("long_call", 0.50)
    elif strategy == "long_put":
        add("long_put", -0.50)
    elif strategy == "bull_call_debit_spread":
        add("long_call", 0.55)
    elif strategy == "bear_put_debit_spread":
        add("long_put", -0.55)
    elif strategy == "put_credit_spread":
        add("short_put", -0.30)
    elif strategy == "call_credit_spread":
        add("short_call", 0.30)
    elif strategy == "iron_condor":
        add("short_put", -0.20)
        add("short_call", 0.20)
    elif strategy == "diagonal_spread":
        # Direction is reflected by the selected option right; target the back long leg and front short leg.
        for leg in legs:
            role = str(leg.get("role") or "")
            if role.startswith("long_back_"):
                delta = _num(leg.get("delta"))
                if delta is not None:
                    specs.append({"role": role, "target_delta": 0.50 if delta >= 0 else -0.50, "selected_delta": delta, "delta_deviation": abs(abs(delta) - 0.50)})
            elif role.startswith("short_front_"):
                delta = _num(leg.get("delta"))
                if delta is not None:
                    specs.append({"role": role, "target_delta": 0.30 if delta >= 0 else -0.30, "selected_delta": delta, "delta_deviation": abs(abs(delta) - 0.30)})
    return specs


def _iron_body_structure(legs: list[dict[str, Any]]) -> str | None:
    short_puts = [leg for leg in legs if leg.get("role") == "short_put_body"]
    short_calls = [leg for leg in legs if leg.get("role") == "short_call_body"]
    if not short_puts or not short_calls:
        return None
    put_strike = _num(short_puts[0].get("strike"))
    call_strike = _num(short_calls[0].get("strike"))
    if put_strike is None or call_strike is None:
        return None
    return "same_strike_iron_butterfly" if abs(put_strike - call_strike) < 1e-9 else "split_strike_iron_butterfly"


def _construction_quality(
    strategy: str,
    legs: list[dict[str, Any]],
    selection_rule: str,
    primary_delta_deviation: float,
    secondary_delta_deviation: float,
) -> dict[str, Any]:
    specs = _targeted_delta_specs(strategy, legs)
    deviations = [_num(spec.get("delta_deviation")) for spec in specs]
    deviations = [d for d in deviations if d is not None]
    max_dev = max(deviations) if deviations else None

    if max_dev is None:
        quality = "primary"
        reason = "structure_selected_without_delta_target"
    elif max_dev <= primary_delta_deviation:
        quality = "primary"
        reason = "target_delta_within_primary_tolerance"
    elif max_dev <= secondary_delta_deviation:
        quality = "secondary"
        reason = "target_delta_within_secondary_tolerance"
    else:
        quality = "fallback_review"
        reason = "target_delta_outside_secondary_tolerance"

    if "alternate_expiration" in selection_rule and quality == "primary":
        quality = "secondary"
        reason = "alternate_expiration_used"

    body_structure = _iron_body_structure(legs) if strategy == "iron_butterfly" else None
    return {
        "construction_quality": quality,
        "construction_quality_reason": reason,
        "targeted_delta_specs": specs,
        "max_delta_deviation": max_dev,
        "primary_delta_deviation_threshold": primary_delta_deviation,
        "secondary_delta_deviation_threshold": secondary_delta_deviation,
        "iron_body_structure": body_structure,
    }


def _build_selected_row(candidate: dict[str, Any], legs: list[dict[str, Any]], selection_rule: str, primary_delta_deviation: float, secondary_delta_deviation: float) -> dict[str, Any]:
    decision_date = _date(candidate)
    symbol = _symbol(candidate)
    candidate_id = _text(candidate.get("strategy_candidate_id") or f"{decision_date}_{symbol}_{candidate.get('strategy')}__{candidate.get('holding_period_days')}d")
    debit, credit = _net_fields(legs)
    metrics = _chain_metrics(legs)
    option_behavior = dict(candidate.get("option_behavior") or {})
    quality = _construction_quality(
        _text(candidate.get("strategy")),
        legs,
        selection_rule,
        primary_delta_deviation=primary_delta_deviation,
        secondary_delta_deviation=secondary_delta_deviation,
    )
    option_behavior.update({k: v for k, v in metrics.items() if v is not None})
    option_behavior.update({
        "source_date": decision_date,
        "source_state": "available",
        "state": candidate.get("option_behavior_state") or candidate.get("options_behavior_state"),
    })

    return {
        **candidate,
        "adapter_type": "historical_strategy_leg_selection_rows_builder",
        "artifact_type": "signalforge_historical_strategy_leg_selection_row",
        "contract": "historical_strategy_leg_selection_rows",
        "schema_version": "signalforge_historical_strategy_leg_selection_row.v3",
        "date": decision_date,
        "decision_date": decision_date,
        "quote_date": candidate.get("quote_date") or decision_date,
        "symbol": symbol,
        "source_strategy_candidate_id": candidate_id,
        "strategy_candidate_id": candidate_id,
        "leg_selection_id": f"{candidate_id}__legs",
        "leg_selection_state": "selected",
        "leg_selection_block_reasons": [],
        "data_state": "complete",
        "selected_leg_count": len(legs),
        "selected_legs": legs,
        "entry_net_mid_debit": debit,
        "entry_net_mid_credit": credit,
        "selection_rule": selection_rule,
        "construction_quality": quality.get("construction_quality"),
        "construction_quality_reason": quality.get("construction_quality_reason"),
        "targeted_delta_specs": quality.get("targeted_delta_specs"),
        "max_delta_deviation": quality.get("max_delta_deviation"),
        "primary_delta_deviation_threshold": quality.get("primary_delta_deviation_threshold"),
        "secondary_delta_deviation_threshold": quality.get("secondary_delta_deviation_threshold"),
        "iron_body_structure": quality.get("iron_body_structure"),
        "selection_assumptions": [
            "selected_from_point_in_time_qc_option_chain_snapshot",
            "entry_prices_are_mid_prices_not_fills",
            "no_order_routing_or_slippage_modeling",
        ],
        "option_behavior": option_behavior,
        "front_dte": metrics.get("front_dte"),
        "back_dte": metrics.get("back_dte"),
        "front_expiration": metrics.get("front_expiration"),
        "back_expiration": metrics.get("back_expiration"),
        "front_iv": metrics.get("front_iv"),
        "back_iv": metrics.get("back_iv"),
        "front_back_iv_spread": metrics.get("front_back_iv_spread"),
        "front_back_iv_spread_pct": metrics.get("front_back_iv_spread_pct"),
        "term_structure_state": metrics.get("term_structure_state"),
        "term_structure_shape": metrics.get("term_structure_shape"),
        "has_term_structure_behavior": metrics.get("term_structure_state") == "available" or bool(candidate.get("has_term_structure_behavior")),
        "is_trainable_candidate": True,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "automatic_action": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "automatic_strategy_change": None,
        "broker_order_id": None,
        "order_intent": "research_backtest_leg_selection_only",
    }


def build_leg_selection_rows(
    candidate_rows_path: Path,
    raw_option_input_path: Path,
    output_dir: Path,
    max_spread_pct: float,
    min_open_interest: int,
    min_volume: int,
    progress_every: int,
    primary_delta_deviation: float,
    secondary_delta_deviation: float,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    input_candidates: list[dict[str, Any]] = []
    required_pairs: set[tuple[str, str]] = set()
    input_strategy_counts: Counter[str] = Counter()
    input_family_counts: Counter[str] = Counter()
    input_date_set: set[str] = set()
    input_symbol_set: set[str] = set()
    skipped_unsupported = 0

    for row in _iter_jsonl(candidate_rows_path):
        strategy = _text(row.get("strategy"))
        if strategy not in SUPPORTED_STRATEGIES:
            skipped_unsupported += 1
            continue
        decision_date = _date(row)
        symbol = _symbol(row)
        if not decision_date or not symbol:
            skipped_unsupported += 1
            continue
        input_candidates.append(row)
        required_pairs.add((decision_date, symbol))
        input_strategy_counts[strategy] += 1
        input_family_counts[_text(row.get("strategy_family"), "unknown")] += 1
        input_date_set.add(decision_date)
        input_symbol_set.add(symbol)

    chains: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    raw_rows_seen = 0
    raw_rows_kept = 0
    raw_pairs_seen: set[tuple[str, str]] = set()

    for row in _iter_jsonl(raw_option_input_path):
        raw_rows_seen += 1
        if progress_every and raw_rows_seen % progress_every == 0:
            print(f"processed raw option rows: {raw_rows_seen}")
        pair = (_text(row.get("quote_date")), _text(row.get("underlying_symbol")))
        if pair not in required_pairs:
            continue
        raw_pairs_seen.add(pair)
        if not _valid_contract(row, max_spread_pct=max_spread_pct, min_open_interest=min_open_interest, min_volume=min_volume):
            continue
        chains[pair].append(row)
        raw_rows_kept += 1

    selected_rows: list[dict[str, Any]] = []
    blocked_reason_counts: Counter[str] = Counter()
    selected_strategy_counts: Counter[str] = Counter()
    selected_family_counts: Counter[str] = Counter()
    selected_leg_count_counts: Counter[str] = Counter()
    holding_period_counts: Counter[str] = Counter()
    premium_profile_counts: Counter[str] = Counter()
    data_state_counts: Counter[str] = Counter()
    replay_coverage_counts: Counter[str] = Counter()
    construction_quality_counts: Counter[str] = Counter()
    construction_quality_reason_counts: Counter[str] = Counter()
    iron_body_structure_counts: Counter[str] = Counter()
    selected_dates: set[str] = set()
    selected_symbols: set[str] = set()
    missing_chain_candidate_count = 0
    no_valid_contract_after_filter_candidate_count = 0
    blocked_candidate_count = 0

    for candidate in input_candidates:
        pair = (_date(candidate), _symbol(candidate))
        raw_pair_present = pair in raw_pairs_seen
        chain = chains.get(pair, [])
        if not raw_pair_present:
            missing_chain_candidate_count += 1
            blocked_candidate_count += 1
            blocked_reason_counts["raw_chain_absent_for_candidate_pair"] += 1
            continue
        if not chain:
            no_valid_contract_after_filter_candidate_count += 1
            blocked_candidate_count += 1
            blocked_reason_counts["no_valid_contracts_after_leg_filter"] += 1
            continue
        legs, rule, reasons = _select_legs(candidate, chain)
        if not legs:
            blocked_candidate_count += 1
            for reason in reasons or ["leg_selection_failed"]:
                blocked_reason_counts[reason] += 1
            continue
        out = _build_selected_row(
            candidate,
            legs,
            rule,
            primary_delta_deviation=primary_delta_deviation,
            secondary_delta_deviation=secondary_delta_deviation,
        )
        selected_rows.append(out)
        selected_dates.add(out["decision_date"])
        selected_symbols.add(out["symbol"])
        selected_strategy_counts[out.get("strategy") or "unknown"] += 1
        selected_family_counts[out.get("strategy_family") or "unknown"] += 1
        selected_leg_count_counts[str(out.get("selected_leg_count"))] += 1
        holding_period_counts[str(out.get("holding_period_days"))] += 1
        premium_profile_counts[out.get("premium_profile") or "unknown"] += 1
        data_state_counts[out.get("data_state") or "unknown"] += 1
        replay_coverage_counts[out.get("replay_coverage_state") or "unknown"] += 1
        construction_quality_counts[out.get("construction_quality") or "unknown"] += 1
        construction_quality_reason_counts[out.get("construction_quality_reason") or "unknown"] += 1
        if out.get("iron_body_structure"):
            iron_body_structure_counts[out.get("iron_body_structure") or "unknown"] += 1

    rows_path = output_dir / "signalforge_historical_strategy_leg_selection_rows.jsonl"
    csv_path = output_dir / "signalforge_historical_strategy_leg_selection_rows.csv"
    result_path = output_dir / "signalforge_historical_strategy_leg_selection_rows.json"
    summary_path = output_dir / "signalforge_historical_strategy_leg_selection_rows_summary.json"

    _write_jsonl(rows_path, selected_rows)
    _write_csv(csv_path, selected_rows)

    is_ready = bool(selected_rows)
    summary = {
        "adapter_type": "historical_strategy_leg_selection_rows_builder",
        "operation_type": "signalforge_historical_strategy_leg_selection_rows_cli",
        "artifact_type": "signalforge_historical_strategy_leg_selection_rows",
        "contract": "historical_strategy_leg_selection_rows",
        "schema_version": "signalforge_historical_strategy_leg_selection_rows_summary.v3",
        "status": "ready" if is_ready else "blocked",
        "is_ready": is_ready,
        "source_candidate_rows_path": str(candidate_rows_path),
        "source_raw_option_input_path": str(raw_option_input_path),
        "input_candidate_row_count": len(input_candidates) + skipped_unsupported,
        "supported_candidate_row_count": len(input_candidates),
        "unsupported_or_malformed_candidate_row_count": skipped_unsupported,
        "required_pair_count": len(required_pairs),
        "raw_option_row_count": raw_rows_seen,
        "raw_candidate_pair_count": len(raw_pairs_seen),
        "valid_contract_row_count": raw_rows_kept,
        "historical_strategy_leg_selection_row_count": len(selected_rows),
        "selected_candidate_count": len(selected_rows),
        "blocked_candidate_count": blocked_candidate_count,
        "missing_chain_candidate_count": missing_chain_candidate_count,
        "no_valid_contract_after_filter_candidate_count": no_valid_contract_after_filter_candidate_count,
        "input_date_count": len(input_date_set),
        "input_symbol_count": len(input_symbol_set),
        "selected_date_count": len(selected_dates),
        "selected_symbol_count": len(selected_symbols),
        "date_min": min(selected_dates) if selected_dates else None,
        "date_max": max(selected_dates) if selected_dates else None,
        "max_spread_pct": max_spread_pct,
        "min_open_interest": min_open_interest,
        "min_volume": min_volume,
        "input_strategy_counts": dict(sorted(input_strategy_counts.items())),
        "input_strategy_family_counts": dict(sorted(input_family_counts.items())),
        "selected_strategy_counts": dict(sorted(selected_strategy_counts.items())),
        "selected_strategy_family_counts": dict(sorted(selected_family_counts.items())),
        "selected_leg_count_counts": dict(sorted(selected_leg_count_counts.items(), key=lambda item: int(item[0]) if str(item[0]).isdigit() else 999)),
        "holding_period_counts": dict(sorted(holding_period_counts.items(), key=lambda item: int(item[0]) if str(item[0]).isdigit() else 999)),
        "premium_profile_counts": dict(sorted(premium_profile_counts.items())),
        "data_state_counts": dict(sorted(data_state_counts.items())),
        "replay_coverage_state_counts": dict(sorted(replay_coverage_counts.items())),
        "construction_quality_counts": dict(sorted(construction_quality_counts.items())),
        "construction_quality_reason_counts": dict(sorted(construction_quality_reason_counts.items())),
        "iron_body_structure_counts": dict(sorted(iron_body_structure_counts.items())),
        "primary_delta_deviation_threshold": primary_delta_deviation,
        "secondary_delta_deviation_threshold": secondary_delta_deviation,
        "blocked_reason_counts": dict(sorted(blocked_reason_counts.items())),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "paths": {
            "result": str(result_path),
            "summary": str(summary_path),
            "rows_jsonl": str(rows_path),
            "rows_csv": str(csv_path),
        },
        "next_step": "historical_walk_forward_expectancy",
    }

    result = {
        **summary,
        "leg_selection_rows": selected_rows[:100],
        "leg_selection_rows_preview_note": "Full selected leg rows are written to rows_jsonl and rows_csv. Result includes first 100 rows only to keep JSON compact.",
    }

    _write_json(result_path, result)
    _write_json(summary_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Build historical strategy leg-selection rows from candidate rows and raw QC option chains.")
    parser.add_argument("--candidate-rows", required=True, type=Path)
    parser.add_argument("--raw-option-input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-spread-pct", type=float, default=0.35)
    parser.add_argument("--min-open-interest", type=int, default=0)
    parser.add_argument("--min-volume", type=int, default=0)
    parser.add_argument("--primary-delta-deviation", type=float, default=0.15)
    parser.add_argument("--secondary-delta-deviation", type=float, default=0.30)
    parser.add_argument("--progress-every", type=int, default=500000)
    args = parser.parse_args()

    summary = build_leg_selection_rows(
        candidate_rows_path=args.candidate_rows,
        raw_option_input_path=args.raw_option_input,
        output_dir=args.output_dir,
        max_spread_pct=args.max_spread_pct,
        min_open_interest=args.min_open_interest,
        min_volume=args.min_volume,
        progress_every=args.progress_every,
        primary_delta_deviation=args.primary_delta_deviation,
        secondary_delta_deviation=args.secondary_delta_deviation,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("is_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
