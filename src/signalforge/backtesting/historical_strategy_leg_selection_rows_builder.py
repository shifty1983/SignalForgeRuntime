from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


BUY = "buy"
SELL = "sell"


def _as_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        value = float(value)
        if math.isnan(value):
            return None
        return value
    except Exception:
        return None


def _as_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def _as_date(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value)
    if len(text) >= 10:
        return text[:10]
    return None


def _median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return float(statistics.median(values))


def _norm_symbol(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    return str(value).upper()


def read_jsonl(path: str | Path) -> Iterable[Dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8", errors="ignore") as handle:
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


def _candidate_key(row: Mapping[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    symbol = _norm_symbol(row.get("symbol"))
    date = _as_date(row.get("date") or row.get("decision_date"))
    return symbol, date


def _option_key(row: Mapping[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    symbol = _norm_symbol(row.get("underlying_symbol") or row.get("underlying") or row.get("symbol"))
    date = _as_date(row.get("quote_date") or row.get("date") or row.get("snapshot_date"))
    return symbol, date


def _right(row: Mapping[str, Any]) -> Optional[str]:
    value = row.get("option_right") or row.get("right")
    if value in (None, ""):
        return None

    text = str(value).lower()
    if text in {"c", "call"}:
        return "call"
    if text in {"p", "put"}:
        return "put"
    return text


def _mid(row: Mapping[str, Any]) -> Optional[float]:
    mid = _as_float(row.get("mid_price") or row.get("mid"))
    if mid is not None and mid > 0:
        return mid

    bid = _as_float(row.get("bid"))
    ask = _as_float(row.get("ask"))

    if bid is not None and ask is not None and ask > 0 and bid >= 0:
        return (bid + ask) / 2.0

    return None


def _valid_option(row: Mapping[str, Any], *, max_spread_pct: float) -> bool:
    if not row.get("option_symbol"):
        return False

    if _right(row) not in {"call", "put"}:
        return False

    if _as_date(row.get("expiration")) is None:
        return False

    if _as_float(row.get("strike")) is None:
        return False

    if _mid(row) is None:
        return False

    bid = _as_float(row.get("bid"))
    ask = _as_float(row.get("ask"))

    if bid is None or ask is None or ask <= 0 or bid < 0 or ask < bid:
        return False

    spread_pct = _as_float(row.get("spread_pct"))
    if spread_pct is not None and spread_pct > max_spread_pct:
        return False

    return True


def _dte(row: Mapping[str, Any]) -> Optional[int]:
    return _as_int(row.get("dte"))


def _strike(row: Mapping[str, Any]) -> Optional[float]:
    return _as_float(row.get("strike"))


def _delta_abs(row: Mapping[str, Any]) -> Optional[float]:
    delta = _as_float(row.get("delta"))
    if delta is None:
        return None
    return abs(delta)


def _atm_score(row: Mapping[str, Any]) -> float:
    moneyness = _as_float(row.get("moneyness"))
    if moneyness is not None:
        return abs(moneyness - 1.0)

    strike = _strike(row)
    underlying = _as_float(row.get("underlying_price"))
    if strike is not None and underlying not in (None, 0):
        return abs(strike - underlying) / underlying

    delta = _delta_abs(row)
    if delta is not None:
        return abs(delta - 0.50)

    return 999999.0


def _delta_score(row: Mapping[str, Any], target_abs_delta: float) -> float:
    delta = _delta_abs(row)
    if delta is None:
        return _atm_score(row)
    return abs(delta - target_abs_delta)


def _group_by_expiration(options: List[Mapping[str, Any]]) -> Dict[str, List[Mapping[str, Any]]]:
    groups: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)

    for option in options:
        expiration = _as_date(option.get("expiration"))
        if expiration:
            groups[expiration].append(option)

    return groups


def _expiration_dte(options: List[Mapping[str, Any]]) -> Optional[int]:
    values = [_dte(option) for option in options]
    values = [value for value in values if value is not None]
    if not values:
        return None
    return int(round(_median([float(value) for value in values]) or 0))


def _select_expiration_group(
    options: List[Mapping[str, Any]],
    *,
    holding_period_days: int,
    exit_buffer_days: int,
) -> Tuple[Optional[str], List[Mapping[str, Any]], Optional[str]]:
    groups = _group_by_expiration(options)

    eligible: List[Tuple[int, str, List[Mapping[str, Any]]]] = []
    min_required_dte = holding_period_days + exit_buffer_days

    for expiration, group in groups.items():
        dte = _expiration_dte(group)
        if dte is None:
            continue
        if dte < min_required_dte:
            continue
        eligible.append((abs(dte - min_required_dte), expiration, group))

    if not eligible:
        return None, [], "no_expiration_with_enough_dte"

    eligible.sort(key=lambda item: (item[0], item[1]))
    _, expiration, group = eligible[0]
    return expiration, list(group), None


def _filter_right(options: List[Mapping[str, Any]], right: str) -> List[Mapping[str, Any]]:
    return [option for option in options if _right(option) == right and _strike(option) is not None]


def _find_next_higher(options: List[Mapping[str, Any]], base_strike: float) -> Optional[Mapping[str, Any]]:
    higher = [option for option in options if (_strike(option) is not None and _strike(option) > base_strike)]
    if not higher:
        return None
    return sorted(higher, key=lambda option: (_strike(option) or 0))[0]


def _find_next_lower(options: List[Mapping[str, Any]], base_strike: float) -> Optional[Mapping[str, Any]]:
    lower = [option for option in options if (_strike(option) is not None and _strike(option) < base_strike)]
    if not lower:
        return None
    return sorted(lower, key=lambda option: (_strike(option) or 0), reverse=True)[0]


def _best_atm(options: List[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    if not options:
        return None
    return sorted(options, key=lambda option: (_atm_score(option), _strike(option) or 0))[0]


def _best_delta(options: List[Mapping[str, Any]], target_abs_delta: float) -> Optional[Mapping[str, Any]]:
    if not options:
        return None
    return sorted(options, key=lambda option: (_delta_score(option, target_abs_delta), _atm_score(option), _strike(option) or 0))[0]


def _leg(
    *,
    action: str,
    quantity: int,
    option: Mapping[str, Any],
    role: str,
) -> Dict[str, Any]:
    bid = _as_float(option.get("bid"))
    ask = _as_float(option.get("ask"))
    mid = _mid(option)

    return {
        "role": role,
        "action": action,
        "quantity": quantity,
        "option_symbol": option.get("option_symbol"),
        "option_right": _right(option),
        "expiration": _as_date(option.get("expiration")),
        "dte": _dte(option),
        "strike": _strike(option),
        "bid": bid,
        "ask": ask,
        "mid_price": mid,
        "delta": _as_float(option.get("delta")),
        "gamma": _as_float(option.get("gamma")),
        "theta": _as_float(option.get("theta")),
        "vega": _as_float(option.get("vega")),
        "implied_volatility": _as_float(option.get("implied_volatility")),
        "volume": _as_int(option.get("volume")),
        "open_interest": _as_int(option.get("open_interest")),
        "spread_pct": _as_float(option.get("spread_pct")),
    }


def _net_mid_debit(legs: List[Mapping[str, Any]]) -> Optional[float]:
    total = 0.0

    for leg in legs:
        mid = _as_float(leg.get("mid_price"))
        quantity = _as_int(leg.get("quantity")) or 1

        if mid is None:
            return None

        if leg.get("action") == BUY:
            total += mid * quantity
        elif leg.get("action") == SELL:
            total -= mid * quantity
        else:
            return None

    return total


def _selection_payload(
    *,
    candidate: Mapping[str, Any],
    legs: List[Mapping[str, Any]],
    selection_rule: str,
    assumptions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    net_mid_debit = _net_mid_debit(legs)
    net_mid_credit = -net_mid_debit if net_mid_debit is not None and net_mid_debit < 0 else None

    return {
        "leg_selection_state": "selected",
        "leg_selection_block_reasons": [],
        "selection_rule": selection_rule,
        "selection_assumptions": assumptions or [],
        "selected_leg_count": len(legs),
        "selected_legs": legs,
        "entry_net_mid_debit": net_mid_debit,
        "entry_net_mid_credit": net_mid_credit,
        "data_state": "complete",
    }


def _blocked_payload(*, reason: str) -> Dict[str, Any]:
    return {
        "leg_selection_state": "blocked",
        "leg_selection_block_reasons": [reason],
        "selection_rule": None,
        "selection_assumptions": [],
        "selected_leg_count": 0,
        "selected_legs": [],
        "entry_net_mid_debit": None,
        "entry_net_mid_credit": None,
        "data_state": "partial_leg_selection_missing",
    }


def _select_single_long(
    *,
    candidate: Mapping[str, Any],
    options: List[Mapping[str, Any]],
    right: str,
    holding_period_days: int,
    exit_buffer_days: int,
) -> Dict[str, Any]:
    _, group, reason = _select_expiration_group(
        options,
        holding_period_days=holding_period_days,
        exit_buffer_days=exit_buffer_days,
    )
    if reason:
        return _blocked_payload(reason=reason)

    right_options = _filter_right(group, right)
    option = _best_delta(right_options, 0.50)

    if not option:
        return _blocked_payload(reason=f"no_{right}_contract_available")

    return _selection_payload(
        candidate=candidate,
        legs=[_leg(action=BUY, quantity=1, option=option, role=f"long_{right}")],
        selection_rule=f"long_{right}_target_50_delta_nearest_expiration",
    )


def _select_vertical_debit(
    *,
    candidate: Mapping[str, Any],
    options: List[Mapping[str, Any]],
    strategy: str,
    right: str,
    holding_period_days: int,
    exit_buffer_days: int,
) -> Dict[str, Any]:
    _, group, reason = _select_expiration_group(
        options,
        holding_period_days=holding_period_days,
        exit_buffer_days=exit_buffer_days,
    )
    if reason:
        return _blocked_payload(reason=reason)

    right_options = _filter_right(group, right)
    long_option = _best_delta(right_options, 0.50)

    if not long_option:
        return _blocked_payload(reason=f"no_{right}_long_leg_available")

    long_strike = _strike(long_option)
    if long_strike is None:
        return _blocked_payload(reason="long_leg_missing_strike")

    if strategy == "bull_call_debit_spread":
        short_option = _find_next_higher(right_options, long_strike)
        short_role = "short_higher_strike_call"
    elif strategy == "bear_put_debit_spread":
        short_option = _find_next_lower(right_options, long_strike)
        short_role = "short_lower_strike_put"
    else:
        return _blocked_payload(reason="unsupported_vertical_debit_strategy")

    if not short_option:
        return _blocked_payload(reason="no_valid_short_vertical_leg_available")

    return _selection_payload(
        candidate=candidate,
        legs=[
            _leg(action=BUY, quantity=1, option=long_option, role=f"long_{right}_debit_leg"),
            _leg(action=SELL, quantity=1, option=short_option, role=short_role),
        ],
        selection_rule=f"{strategy}_atm_long_next_strike_short",
    )


def _select_vertical_credit(
    *,
    candidate: Mapping[str, Any],
    options: List[Mapping[str, Any]],
    strategy: str,
    right: str,
    holding_period_days: int,
    exit_buffer_days: int,
) -> Dict[str, Any]:
    _, group, reason = _select_expiration_group(
        options,
        holding_period_days=holding_period_days,
        exit_buffer_days=exit_buffer_days,
    )
    if reason:
        return _blocked_payload(reason=reason)

    right_options = _filter_right(group, right)
    short_option = _best_delta(right_options, 0.30)

    if not short_option:
        return _blocked_payload(reason=f"no_{right}_short_leg_available")

    short_strike = _strike(short_option)
    if short_strike is None:
        return _blocked_payload(reason="short_leg_missing_strike")

    if strategy == "put_credit_spread":
        long_option = _find_next_lower(right_options, short_strike)
        long_role = "long_lower_strike_put_protection"
    elif strategy == "call_credit_spread":
        long_option = _find_next_higher(right_options, short_strike)
        long_role = "long_higher_strike_call_protection"
    else:
        return _blocked_payload(reason="unsupported_vertical_credit_strategy")

    if not long_option:
        return _blocked_payload(reason="no_valid_protection_leg_available")

    return _selection_payload(
        candidate=candidate,
        legs=[
            _leg(action=SELL, quantity=1, option=short_option, role=f"short_{right}_credit_leg"),
            _leg(action=BUY, quantity=1, option=long_option, role=long_role),
        ],
        selection_rule=f"{strategy}_30_delta_short_next_strike_protection",
    )


def _select_iron_condor(
    *,
    candidate: Mapping[str, Any],
    options: List[Mapping[str, Any]],
    holding_period_days: int,
    exit_buffer_days: int,
) -> Dict[str, Any]:
    _, group, reason = _select_expiration_group(
        options,
        holding_period_days=holding_period_days,
        exit_buffer_days=exit_buffer_days,
    )
    if reason:
        return _blocked_payload(reason=reason)

    calls = _filter_right(group, "call")
    puts = _filter_right(group, "put")

    short_put = _best_delta(puts, 0.20)
    short_call = _best_delta(calls, 0.20)

    if not short_put or not short_call:
        return _blocked_payload(reason="missing_short_iron_condor_legs")

    short_put_strike = _strike(short_put)
    short_call_strike = _strike(short_call)

    if short_put_strike is None or short_call_strike is None:
        return _blocked_payload(reason="short_iron_condor_leg_missing_strike")

    if short_put_strike >= short_call_strike:
        return _blocked_payload(reason="invalid_iron_condor_short_strike_order")

    long_put = _find_next_lower(puts, short_put_strike)
    long_call = _find_next_higher(calls, short_call_strike)

    if not long_put or not long_call:
        return _blocked_payload(reason="missing_iron_condor_wing_protection")

    return _selection_payload(
        candidate=candidate,
        legs=[
            _leg(action=BUY, quantity=1, option=long_put, role="long_put_wing"),
            _leg(action=SELL, quantity=1, option=short_put, role="short_put"),
            _leg(action=SELL, quantity=1, option=short_call, role="short_call"),
            _leg(action=BUY, quantity=1, option=long_call, role="long_call_wing"),
        ],
        selection_rule="iron_condor_20_delta_shorts_next_strike_wings",
    )


def _select_iron_butterfly(
    *,
    candidate: Mapping[str, Any],
    options: List[Mapping[str, Any]],
    holding_period_days: int,
    exit_buffer_days: int,
) -> Dict[str, Any]:
    _, group, reason = _select_expiration_group(
        options,
        holding_period_days=holding_period_days,
        exit_buffer_days=exit_buffer_days,
    )
    if reason:
        return _blocked_payload(reason=reason)

    calls = _filter_right(group, "call")
    puts = _filter_right(group, "put")

    common_strikes = sorted({ _strike(call) for call in calls if _strike(call) is not None } & { _strike(put) for put in puts if _strike(put) is not None })

    if not common_strikes:
        return _blocked_payload(reason="no_common_call_put_strike_for_butterfly_body")

    body_strike = sorted(common_strikes, key=lambda strike: abs(strike - (_as_float(group[0].get("underlying_price")) or strike)))[0]

    short_call = next((option for option in calls if _strike(option) == body_strike), None)
    short_put = next((option for option in puts if _strike(option) == body_strike), None)

    if not short_call or not short_put:
        return _blocked_payload(reason="missing_butterfly_body_contracts")

    long_put = _find_next_lower(puts, body_strike)
    long_call = _find_next_higher(calls, body_strike)

    if not long_put or not long_call:
        return _blocked_payload(reason="missing_butterfly_wings")

    return _selection_payload(
        candidate=candidate,
        legs=[
            _leg(action=BUY, quantity=1, option=long_put, role="long_put_wing"),
            _leg(action=SELL, quantity=1, option=short_put, role="short_put_body"),
            _leg(action=SELL, quantity=1, option=short_call, role="short_call_body"),
            _leg(action=BUY, quantity=1, option=long_call, role="long_call_wing"),
        ],
        selection_rule="iron_butterfly_atm_short_body_next_strike_wings",
    )


def _term_expirations(candidate: Mapping[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    option_behavior = candidate.get("option_behavior")
    if not isinstance(option_behavior, Mapping):
        option_behavior = {}

    front = _as_date(option_behavior.get("front_expiration"))
    back = _as_date(option_behavior.get("back_expiration"))

    return front, back


def _options_for_expiration(options: List[Mapping[str, Any]], expiration: str, right: Optional[str] = None) -> List[Mapping[str, Any]]:
    result = [option for option in options if _as_date(option.get("expiration")) == expiration]
    if right:
        result = [option for option in result if _right(option) == right]
    return result


def _front_back_available_for_exit(
    *,
    front_options: List[Mapping[str, Any]],
    holding_period_days: int,
    exit_buffer_days: int,
) -> bool:
    dte = _expiration_dte(front_options)
    if dte is None:
        return False
    return dte >= holding_period_days + exit_buffer_days


def _select_calendar(
    *,
    candidate: Mapping[str, Any],
    options: List[Mapping[str, Any]],
    holding_period_days: int,
    exit_buffer_days: int,
) -> Dict[str, Any]:
    front_expiration, back_expiration = _term_expirations(candidate)

    if not front_expiration or not back_expiration:
        return _blocked_payload(reason="missing_term_structure_front_back_expirations")

    for right in ["call", "put"]:
        front_options = _options_for_expiration(options, front_expiration, right)
        back_options = _options_for_expiration(options, back_expiration, right)

        if not front_options or not back_options:
            continue

        if not _front_back_available_for_exit(
            front_options=front_options,
            holding_period_days=holding_period_days,
            exit_buffer_days=exit_buffer_days,
        ):
            return _blocked_payload(reason="front_calendar_expiration_before_exit_horizon")

        common_strikes = sorted(
            { _strike(option) for option in front_options if _strike(option) is not None }
            & { _strike(option) for option in back_options if _strike(option) is not None }
        )

        if not common_strikes:
            continue

        underlying_price = _as_float(front_options[0].get("underlying_price") or back_options[0].get("underlying_price"))
        target_strike = sorted(common_strikes, key=lambda strike: abs(strike - (underlying_price or strike)))[0]

        short_front = next((option for option in front_options if _strike(option) == target_strike), None)
        long_back = next((option for option in back_options if _strike(option) == target_strike), None)

        if short_front and long_back:
            return _selection_payload(
                candidate=candidate,
                legs=[
                    _leg(action=SELL, quantity=1, option=short_front, role=f"short_front_{right}"),
                    _leg(action=BUY, quantity=1, option=long_back, role=f"long_back_{right}"),
                ],
                selection_rule=f"calendar_spread_same_strike_atm_{right}_front_short_back_long",
            )

    return _blocked_payload(reason="no_same_strike_front_back_calendar_pair")


def _select_diagonal(
    *,
    candidate: Mapping[str, Any],
    options: List[Mapping[str, Any]],
    holding_period_days: int,
    exit_buffer_days: int,
) -> Dict[str, Any]:
    front_expiration, back_expiration = _term_expirations(candidate)

    if not front_expiration or not back_expiration:
        return _blocked_payload(reason="missing_term_structure_front_back_expirations")

    asset_behavior = candidate.get("asset_behavior")
    asset_state = candidate.get("asset_behavior_state")
    if isinstance(asset_behavior, Mapping):
        asset_state = asset_behavior.get("state") or asset_state

    if asset_state in {"constructive", "sample_limited"}:
        right = "call"
        short_front_finder = _find_next_higher
        short_role = "short_front_higher_strike_call"
        assumption = "sample_limited_defaults_to_call_diagonal" if asset_state == "sample_limited" else None
    elif asset_state == "defensive":
        right = "put"
        short_front_finder = _find_next_lower
        short_role = "short_front_lower_strike_put"
        assumption = None
    else:
        return _blocked_payload(reason="diagonal_requires_directional_asset_behavior")

    front_options = _options_for_expiration(options, front_expiration, right)
    back_options = _options_for_expiration(options, back_expiration, right)

    if not front_options or not back_options:
        return _blocked_payload(reason=f"missing_front_or_back_{right}_options_for_diagonal")

    if not _front_back_available_for_exit(
        front_options=front_options,
        holding_period_days=holding_period_days,
        exit_buffer_days=exit_buffer_days,
    ):
        return _blocked_payload(reason="front_diagonal_expiration_before_exit_horizon")

    long_back = _best_delta(back_options, 0.50)

    if not long_back:
        return _blocked_payload(reason=f"no_back_{right}_long_leg_for_diagonal")

    long_strike = _strike(long_back)
    if long_strike is None:
        return _blocked_payload(reason="diagonal_long_leg_missing_strike")

    short_front = short_front_finder(front_options, long_strike)

    if not short_front:
        return _blocked_payload(reason=f"no_front_{right}_short_leg_for_diagonal")

    assumptions = [assumption] if assumption else []

    return _selection_payload(
        candidate=candidate,
        legs=[
            _leg(action=BUY, quantity=1, option=long_back, role=f"long_back_{right}"),
            _leg(action=SELL, quantity=1, option=short_front, role=short_role),
        ],
        selection_rule=f"diagonal_spread_directional_{right}_back_atm_front_otm",
        assumptions=assumptions,
    )


def select_legs_for_candidate(
    *,
    candidate: Mapping[str, Any],
    options: List[Mapping[str, Any]],
    max_spread_pct: float,
    exit_buffer_days: int,
) -> Dict[str, Any]:
    strategy = str(candidate.get("strategy") or "")
    holding_period_days = _as_int(candidate.get("holding_period_days"))

    if holding_period_days is None:
        return _blocked_payload(reason="candidate_missing_holding_period_days")

    valid_options = [
        option
        for option in options
        if _valid_option(option, max_spread_pct=max_spread_pct)
    ]

    if not valid_options:
        return _blocked_payload(reason="no_valid_option_rows_for_symbol_date")

    if strategy == "long_call":
        return _select_single_long(
            candidate=candidate,
            options=valid_options,
            right="call",
            holding_period_days=holding_period_days,
            exit_buffer_days=exit_buffer_days,
        )

    if strategy == "long_put":
        return _select_single_long(
            candidate=candidate,
            options=valid_options,
            right="put",
            holding_period_days=holding_period_days,
            exit_buffer_days=exit_buffer_days,
        )

    if strategy == "bull_call_debit_spread":
        return _select_vertical_debit(
            candidate=candidate,
            options=valid_options,
            strategy=strategy,
            right="call",
            holding_period_days=holding_period_days,
            exit_buffer_days=exit_buffer_days,
        )

    if strategy == "bear_put_debit_spread":
        return _select_vertical_debit(
            candidate=candidate,
            options=valid_options,
            strategy=strategy,
            right="put",
            holding_period_days=holding_period_days,
            exit_buffer_days=exit_buffer_days,
        )

    if strategy == "put_credit_spread":
        return _select_vertical_credit(
            candidate=candidate,
            options=valid_options,
            strategy=strategy,
            right="put",
            holding_period_days=holding_period_days,
            exit_buffer_days=exit_buffer_days,
        )

    if strategy == "call_credit_spread":
        return _select_vertical_credit(
            candidate=candidate,
            options=valid_options,
            strategy=strategy,
            right="call",
            holding_period_days=holding_period_days,
            exit_buffer_days=exit_buffer_days,
        )

    if strategy == "iron_condor":
        return _select_iron_condor(
            candidate=candidate,
            options=valid_options,
            holding_period_days=holding_period_days,
            exit_buffer_days=exit_buffer_days,
        )

    if strategy == "iron_butterfly":
        return _select_iron_butterfly(
            candidate=candidate,
            options=valid_options,
            holding_period_days=holding_period_days,
            exit_buffer_days=exit_buffer_days,
        )

    if strategy == "calendar_spread":
        return _select_calendar(
            candidate=candidate,
            options=valid_options,
            holding_period_days=holding_period_days,
            exit_buffer_days=exit_buffer_days,
        )

    if strategy == "diagonal_spread":
        return _select_diagonal(
            candidate=candidate,
            options=valid_options,
            holding_period_days=holding_period_days,
            exit_buffer_days=exit_buffer_days,
        )

    return _blocked_payload(reason=f"unsupported_strategy:{strategy}")


def _load_candidate_rows(path: str | Path) -> List[Dict[str, Any]]:
    return list(read_jsonl(path))


def _build_option_index(
    *,
    option_rows_path: str | Path,
    needed_symbol_dates: set[Tuple[str, str]],
) -> Tuple[Dict[Tuple[str, str], List[Dict[str, Any]]], Dict[str, Any]]:
    index: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    source_row_count = 0
    indexed_row_count = 0
    rejected_counts: Counter[str] = Counter()

    for row in read_jsonl(option_rows_path):
        source_row_count += 1

        symbol, date = _option_key(row)

        if not symbol:
            rejected_counts["missing_underlying_symbol"] += 1
            continue

        if not date:
            rejected_counts["missing_quote_date"] += 1
            continue

        key = (symbol, date)

        if key not in needed_symbol_dates:
            continue

        index[key].append(row)
        indexed_row_count += 1

    stats = {
        "source_option_row_count": source_row_count,
        "indexed_option_row_count": indexed_row_count,
        "indexed_symbol_date_count": len(index),
        "option_index_rejected_counts": dict(sorted(rejected_counts.items())),
    }

    return dict(index), stats


def build_historical_strategy_leg_selection_rows(
    *,
    candidate_rows: List[Mapping[str, Any]],
    option_index: Mapping[Tuple[str, str], List[Mapping[str, Any]]],
    max_spread_pct: float = 0.50,
    exit_buffer_days: int = 1,
    emit_blocked_rows: bool = False,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    output_rows: List[Dict[str, Any]] = []

    selected_count = 0
    blocked_count = 0
    missing_option_group_count = 0

    strategy_selected_counts: Counter[str] = Counter()
    strategy_blocked_counts: Counter[str] = Counter()
    block_reason_counts: Counter[str] = Counter()
    selection_rule_counts: Counter[str] = Counter()
    selected_leg_count_distribution: Counter[str] = Counter()

    duplicate_ids = 0
    seen_ids: set[str] = set()

    for candidate in candidate_rows:
        symbol, date = _candidate_key(candidate)
        strategy = str(candidate.get("strategy") or "missing")
        candidate_id = str(
            candidate.get("strategy_candidate_id")
            or candidate.get("candidate_row_id")
            or candidate.get("decision_row_id")
            or f"{date}_{symbol}_{strategy}_{candidate.get('strategy_instance')}"
        )

        if candidate_id in seen_ids:
            duplicate_ids += 1
        seen_ids.add(candidate_id)

        options = option_index.get((symbol, date), []) if symbol and date else []

        if not options:
            selection = _blocked_payload(reason="missing_option_rows_for_candidate_symbol_date")
            missing_option_group_count += 1
        else:
            selection = select_legs_for_candidate(
                candidate=candidate,
                options=list(options),
                max_spread_pct=max_spread_pct,
                exit_buffer_days=exit_buffer_days,
            )

        state = selection["leg_selection_state"]

        if state == "selected":
            selected_count += 1
            strategy_selected_counts[strategy] += 1
            selection_rule_counts[str(selection.get("selection_rule"))] += 1
            selected_leg_count_distribution[str(selection.get("selected_leg_count"))] += 1
        else:
            blocked_count += 1
            strategy_blocked_counts[strategy] += 1
            for reason in selection.get("leg_selection_block_reasons") or ["unknown"]:
                block_reason_counts[str(reason)] += 1

        if state == "selected" or emit_blocked_rows:
            row = dict(candidate)
            row.update(
                {
                    "adapter_type": "historical_strategy_leg_selection_rows_builder",
                    "artifact_type": "signalforge_historical_strategy_leg_selection_row",
                    "contract": "historical_strategy_leg_selection_rows",
                    "leg_selection_id": f"{candidate_id}__legs",
                    "source_strategy_candidate_id": candidate_id,
                }
            )
            row.update(selection)
            output_rows.append(row)

    blockers: List[str] = []

    if not output_rows:
        blockers.append("no_leg_selection_rows_written")

    if selected_count == 0:
        blockers.append("no_selected_leg_rows")

    if duplicate_ids:
        blockers.append("duplicate_source_candidate_ids")

    summary: Dict[str, Any] = {
        "adapter_type": "historical_strategy_leg_selection_rows_builder",
        "artifact_type": "signalforge_historical_strategy_leg_selection_rows",
        "contract": "historical_strategy_leg_selection_rows",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "input_candidate_row_count": len(candidate_rows),
        "output_row_count": len(output_rows),
        "selected_leg_row_count": selected_count,
        "blocked_leg_row_count": blocked_count,
        "emit_blocked_rows": emit_blocked_rows,
        "missing_option_group_count": missing_option_group_count,
        "unique_selected_strategies": len(strategy_selected_counts),
        "strategy_selected_counts": dict(sorted(strategy_selected_counts.items())),
        "strategy_blocked_counts": dict(sorted(strategy_blocked_counts.items())),
        "block_reason_counts": dict(sorted(block_reason_counts.items())),
        "selection_rule_counts": dict(sorted(selection_rule_counts.items())),
        "selected_leg_count_distribution": dict(sorted(selected_leg_count_distribution.items())),
        "validation": {
            "duplicate_source_candidate_ids": duplicate_ids,
        },
        "parameters": {
            "max_spread_pct": max_spread_pct,
            "exit_buffer_days": exit_buffer_days,
        },
        "paths": {},
    }

    return output_rows, summary


def build_historical_strategy_leg_selection_rows_artifact(
    *,
    strategy_candidate_rows_path: str | Path,
    option_rows_path: str | Path,
    output_dir: str | Path,
    max_spread_pct: float = 0.50,
    exit_buffer_days: int = 1,
    emit_blocked_rows: bool = False,
) -> Dict[str, Any]:
    output_path = Path(output_dir)

    rows_path = output_path / "signalforge_historical_strategy_leg_selection_rows.jsonl"
    summary_path = output_path / "signalforge_historical_strategy_leg_selection_rows_summary.json"

    candidate_rows = _load_candidate_rows(strategy_candidate_rows_path)

    needed_symbol_dates = {
        key
        for key in (_candidate_key(row) for row in candidate_rows)
        if key[0] and key[1]
    }

    option_index, option_index_stats = _build_option_index(
        option_rows_path=option_rows_path,
        needed_symbol_dates=needed_symbol_dates,
    )

    rows, summary = build_historical_strategy_leg_selection_rows(
        candidate_rows=candidate_rows,
        option_index=option_index,
        max_spread_pct=max_spread_pct,
        exit_buffer_days=exit_buffer_days,
        emit_blocked_rows=emit_blocked_rows,
    )

    summary.update(option_index_stats)
    summary["needed_symbol_date_count"] = len(needed_symbol_dates)
    summary["paths"] = {
        "strategy_candidate_rows_path": str(strategy_candidate_rows_path),
        "option_rows_path": str(option_rows_path),
        "rows_path": str(rows_path),
        "summary_path": str(summary_path),
    }

    write_jsonl(rows_path, rows)
    write_json(summary_path, summary)

    return summary




