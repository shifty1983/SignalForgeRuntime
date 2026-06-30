from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


MISSING_VALUE = "__missing__"

DEFAULT_STRATEGY_POLICY: Dict[str, Any] = {
    "policy_name": "default_full_defined_risk_strategy_universe_policy",
    "policy_version": "3.0",
    "eligible_data_states": ["complete"],
    "required_eligibility_flags": [
        "is_tradable",
        "eligible_for_strategy_selection",
        "eligible_for_option_strategy_selection",
    ],
    "enforce_strategy_family_eligibility": True,
    "allowed_strategy_family_statuses": [
        "favored",
        "favored_constrained",
        "allowed",
        "allowed_constrained",
    ],
    "strategy_family_eligibility_aliases": {
        "long_premium": ["directional_long_premium"],
        "neutral_income": ["defined_risk_neutral"],
        "term_structure": ["wait_for_clearer_options_edge"],
        "stock_overlay": ["protective_put_spread"],
    },
    "blocked_option_liquidity_states": ["illiquid_or_sparse"],
    "excluded_strategies": [
        "protective_put",
        "collar",
        "covered_call",
    ],
    "excluded_strategy_reasons": {
        "protective_put": "underlying_position_strategy_excluded_from_current_backtest",
        "collar": "underlying_position_strategy_excluded_from_current_backtest",
        "covered_call": "underlying_position_strategy_excluded_from_current_backtest"
    },
    "holding_period_days": [5, 10, 21, 45],
    "risk_overlays": [
        {
            "risk_overlay": "defined_risk_cap_m1_p1",
            "risk_overlay_rank": 1,
        }
    ],
    "strategies": [
        {
            "strategy": "long_call",
            "strategy_family": "long_premium",
            "strategy_structure": "single_leg_option",
            "strategy_direction": "bullish",
            "premium_profile": "debit",
            "defined_risk": True,
            "requires_underlying_position": False,
            "requires_term_structure": False,
            "candidate_rank": 1,
            "allowed_asset_behavior_states": ["constructive", "sample_limited"],
            "allowed_option_iv_levels": ["low", "moderate"],
            "allowed_option_liquidity_states": ["liquid", "moderate_liquidity"],
            "allowed_holding_period_days": [5, 10, 21, 45],
        },
        {
            "strategy": "long_put",
            "strategy_family": "long_premium",
            "strategy_structure": "single_leg_option",
            "strategy_direction": "bearish",
            "premium_profile": "debit",
            "defined_risk": True,
            "requires_underlying_position": False,
            "requires_term_structure": False,
            "candidate_rank": 2,
            "allowed_asset_behavior_states": ["defensive", "sample_limited"],
            "allowed_option_iv_levels": ["low", "moderate"],
            "allowed_option_liquidity_states": ["liquid", "moderate_liquidity"],
            "allowed_holding_period_days": [5, 10, 21, 45],
        },
        {
            "strategy": "bull_call_debit_spread",
            "strategy_family": "debit_spread",
            "strategy_structure": "vertical_spread",
            "strategy_direction": "bullish",
            "premium_profile": "debit",
            "defined_risk": True,
            "requires_underlying_position": False,
            "requires_term_structure": False,
            "candidate_rank": 3,
            "allowed_asset_behavior_states": ["constructive", "sample_limited"],
            "allowed_option_iv_levels": ["low", "moderate"],
            "allowed_option_liquidity_states": ["liquid", "moderate_liquidity"],
            "allowed_holding_period_days": [5, 10, 21, 45],
        },
        {
            "strategy": "bear_put_debit_spread",
            "strategy_family": "debit_spread",
            "strategy_structure": "vertical_spread",
            "strategy_direction": "bearish",
            "premium_profile": "debit",
            "defined_risk": True,
            "requires_underlying_position": False,
            "requires_term_structure": False,
            "candidate_rank": 4,
            "allowed_asset_behavior_states": ["defensive", "sample_limited"],
            "allowed_option_iv_levels": ["low", "moderate"],
            "allowed_option_liquidity_states": ["liquid", "moderate_liquidity"],
            "allowed_holding_period_days": [5, 10, 21, 45],
        },
        {
            "strategy": "put_credit_spread",
            "strategy_family": "credit_spread",
            "strategy_structure": "vertical_spread",
            "strategy_direction": "bullish",
            "premium_profile": "credit",
            "defined_risk": True,
            "requires_underlying_position": False,
            "requires_term_structure": False,
            "candidate_rank": 5,
            "allowed_asset_behavior_states": ["constructive", "neutral", "sample_limited"],
            "allowed_option_iv_levels": ["moderate", "high"],
            "allowed_option_liquidity_states": ["liquid", "moderate_liquidity"],
            "allowed_holding_period_days": [5, 10, 21, 45],
        },
        {
            "strategy": "call_credit_spread",
            "strategy_family": "credit_spread",
            "strategy_structure": "vertical_spread",
            "strategy_direction": "bearish",
            "premium_profile": "credit",
            "defined_risk": True,
            "requires_underlying_position": False,
            "requires_term_structure": False,
            "candidate_rank": 6,
            "allowed_asset_behavior_states": ["defensive", "neutral", "sample_limited"],
            "allowed_option_iv_levels": ["moderate", "high"],
            "allowed_option_liquidity_states": ["liquid", "moderate_liquidity"],
            "allowed_holding_period_days": [5, 10, 21, 45],
        },
        {
            "strategy": "iron_condor",
            "strategy_family": "neutral_income",
            "strategy_structure": "multi_leg_spread",
            "strategy_direction": "neutral",
            "premium_profile": "credit",
            "defined_risk": True,
            "requires_underlying_position": False,
            "requires_term_structure": False,
            "candidate_rank": 7,
            "allowed_asset_behavior_states": ["neutral", "sample_limited"],
            "allowed_option_iv_levels": ["moderate", "high"],
            "allowed_option_liquidity_states": ["liquid", "moderate_liquidity"],
            "allowed_holding_period_days": [10, 21, 45],
        },
        {
            "strategy": "iron_butterfly",
            "strategy_family": "neutral_income",
            "strategy_structure": "multi_leg_spread",
            "strategy_direction": "neutral",
            "premium_profile": "credit",
            "defined_risk": True,
            "requires_underlying_position": False,
            "requires_term_structure": False,
            "candidate_rank": 8,
            "allowed_asset_behavior_states": ["neutral", "sample_limited"],
            "allowed_option_iv_levels": ["moderate", "high"],
            "allowed_option_liquidity_states": ["liquid", "moderate_liquidity"],
            "allowed_holding_period_days": [10, 21, 45],
        },
        {
            "strategy": "calendar_spread",
            "strategy_family": "term_structure",
            "strategy_structure": "calendar_spread",
            "strategy_direction": "neutral",
            "premium_profile": "debit",
            "defined_risk": True,
            "requires_underlying_position": False,
            "requires_term_structure": True,
            "candidate_rank": 9,
            "allowed_asset_behavior_states": ["neutral", "sample_limited"],
            "allowed_option_iv_levels": ["low", "moderate"],
            "allowed_option_liquidity_states": ["liquid", "moderate_liquidity"],
            "allowed_holding_period_days": [21, 45],
        },
        {
            "strategy": "diagonal_spread",
            "strategy_family": "term_structure",
            "strategy_structure": "diagonal_spread",
            "strategy_direction": "directional",
            "premium_profile": "debit",
            "defined_risk": True,
            "requires_underlying_position": False,
            "requires_term_structure": True,
            "candidate_rank": 10,
            "allowed_asset_behavior_states": ["constructive", "defensive", "sample_limited"],
            "allowed_option_iv_levels": ["low", "moderate"],
            "allowed_option_liquidity_states": ["liquid", "moderate_liquidity"],
            "allowed_holding_period_days": [21, 45],
        },
        {
            "strategy": "protective_put",
            "strategy_family": "stock_overlay",
            "strategy_structure": "stock_plus_option",
            "strategy_direction": "hedged_bullish",
            "premium_profile": "debit",
            "defined_risk": True,
            "requires_underlying_position": True,
            "requires_term_structure": False,
            "candidate_rank": 11,
            "allowed_asset_behavior_states": ["constructive", "neutral", "defensive", "sample_limited"],
            "allowed_option_iv_levels": ["low", "moderate", "high"],
            "allowed_option_liquidity_states": ["liquid", "moderate_liquidity"],
            "allowed_holding_period_days": [5, 10, 21, 45],
        },
        {
            "strategy": "collar",
            "strategy_family": "stock_overlay",
            "strategy_structure": "stock_plus_option_spread",
            "strategy_direction": "hedged_bullish",
            "premium_profile": "mixed",
            "defined_risk": True,
            "requires_underlying_position": True,
            "requires_term_structure": False,
            "candidate_rank": 12,
            "allowed_asset_behavior_states": ["constructive", "neutral", "defensive", "sample_limited"],
            "allowed_option_iv_levels": ["moderate", "high"],
            "allowed_option_liquidity_states": ["liquid", "moderate_liquidity"],
            "allowed_holding_period_days": [5, 10, 21, 45],
        },
        {
            "strategy": "covered_call",
            "strategy_family": "stock_overlay",
            "strategy_structure": "stock_plus_short_call",
            "strategy_direction": "neutral_to_bullish",
            "premium_profile": "credit",
            "defined_risk": False,
            "requires_underlying_position": True,
            "requires_term_structure": False,
            "candidate_rank": 13,
            "allowed_asset_behavior_states": ["constructive", "neutral", "sample_limited"],
            "allowed_option_iv_levels": ["moderate", "high"],
            "allowed_option_liquidity_states": ["liquid", "moderate_liquidity"],
            "allowed_holding_period_days": [5, 10, 21, 45],
        },
    ],
}


def read_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc

            if not isinstance(payload, dict):
                raise ValueError(f"Expected object at line {line_number}, got {type(payload).__name__}")

            rows.append(payload)

    return rows


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


def load_strategy_policy(path: Optional[str | Path]) -> Dict[str, Any]:
    if path is None:
        return json.loads(json.dumps(DEFAULT_STRATEGY_POLICY))

    with Path(path).open("r", encoding="utf-8") as handle:
        policy = json.load(handle)

    if not isinstance(policy, dict):
        raise ValueError("Strategy policy must be a JSON object.")

    return policy


def _normalise_symbol(value: Any) -> str:
    if value in (None, ""):
        return MISSING_VALUE

    return str(value).strip().upper() or MISSING_VALUE


def _normalise_text(value: Any) -> str:
    if value in (None, ""):
        return MISSING_VALUE

    return str(value).strip() or MISSING_VALUE


def _nested_state(value: Any) -> str:
    if isinstance(value, Mapping):
        state = value.get("state")
        if state not in (None, ""):
            return _normalise_text(state)

        source_state = value.get("source_state")
        if source_state not in (None, ""):
            return _normalise_text(source_state)

        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    return _normalise_text(value)


def _nested_source_date(value: Any) -> Optional[str]:
    if isinstance(value, Mapping):
        source_date = value.get("source_date")
        if source_date not in (None, ""):
            return str(source_date)

    return None


def _eligibility(row: Mapping[str, Any]) -> Mapping[str, Any]:
    eligibility = row.get("eligibility")
    return eligibility if isinstance(eligibility, Mapping) else {}


def _flag_is_true(row: Mapping[str, Any], flag_name: str) -> bool:
    return bool(_eligibility(row).get(flag_name))


def _has_underlying_position(row: Mapping[str, Any]) -> bool:
    if bool(row.get("has_underlying_position")):
        return True

    eligibility = _eligibility(row)
    if bool(eligibility.get("has_underlying_position")):
        return True

    position = row.get("position")
    if isinstance(position, Mapping):
        return bool(position.get("has_underlying_position"))

    return False


def _has_term_structure_behavior(row: Mapping[str, Any]) -> bool:
    option_behavior = row.get("option_behavior")

    if isinstance(option_behavior, Mapping):
        for key in (
            "term_structure_state",
            "term_structure",
            "term_structure_behavior",
            "front_back_iv_spread",
        ):
            if option_behavior.get(key) not in (None, ""):
                return True

    for key in (
        "term_structure_state",
        "term_structure",
        "term_structure_behavior",
        "front_back_iv_spread",
    ):
        if row.get(key) not in (None, ""):
            return True

    return False




def _strategy_family_statuses(row: Mapping[str, Any]) -> Mapping[str, str]:
    statuses = row.get("strategy_family_statuses")

    if not isinstance(statuses, Mapping):
        eligibility = row.get("strategy_family_eligibility")
        if isinstance(eligibility, Mapping):
            statuses = eligibility.get("strategy_family_statuses")

    if not isinstance(statuses, Mapping):
        return {}

    out: Dict[str, str] = {}
    for key, value in statuses.items():
        family = _normalise_text(key)
        status = _normalise_text(value)
        if family != MISSING_VALUE and status != MISSING_VALUE:
            out[family] = status

    return out


def _strategy_family_status_aliases(
    *,
    policy: Mapping[str, Any],
    strategy_family: str,
) -> List[str]:
    family = _normalise_text(strategy_family)
    candidates: List[str] = []

    if family != MISSING_VALUE:
        candidates.append(family)

    aliases = policy.get("strategy_family_eligibility_aliases")
    if not isinstance(aliases, Mapping):
        return candidates

    alias_value = aliases.get(family)
    if alias_value is None:
        alias_value = aliases.get(family.lower())

    if isinstance(alias_value, str):
        alias_items = [alias_value]
    elif isinstance(alias_value, Sequence) and not isinstance(alias_value, (str, bytes)):
        alias_items = list(alias_value)
    else:
        alias_items = []

    for item in alias_items:
        alias = _normalise_text(item)
        if alias != MISSING_VALUE and alias not in candidates:
            candidates.append(alias)

    return candidates


def _strategy_family_status(
    row: Mapping[str, Any],
    strategy_family: str,
    *,
    policy: Mapping[str, Any] | None = None,
) -> str:
    family = _normalise_text(strategy_family)
    if family == MISSING_VALUE:
        return MISSING_VALUE

    statuses = _strategy_family_statuses(row)

    lookup = {
        _normalise_text(key).lower(): value
        for key, value in statuses.items()
    }

    candidates = (
        _strategy_family_status_aliases(policy=policy, strategy_family=family)
        if policy is not None
        else [family]
    )

    for candidate in candidates:
        direct = _normalise_text(candidate)

        if direct in statuses:
            return statuses[direct]

        lowered = direct.lower()
        if lowered in lookup:
            return lookup[lowered]

    return MISSING_VALUE

def _strategy_family_gate_block_reasons(
    *,
    row: Mapping[str, Any],
    strategy_family: str,
    policy: Mapping[str, Any],
) -> List[str]:
    if not bool(policy.get("enforce_strategy_family_eligibility", True)):
        return []

    family = _normalise_text(strategy_family)
    if family == MISSING_VALUE:
        return ["missing_strategy_family"]

    statuses = _strategy_family_statuses(row)
    if not statuses:
        return ["missing_strategy_family_statuses"]

    status = _strategy_family_status(row, family, policy=policy)

    if status == MISSING_VALUE:
        return [f"missing_strategy_family_status:{family}"]

    allowed_statuses = set(
        _normalise_text(item)
        for item in (
            policy.get("allowed_strategy_family_statuses")
            or ["favored", "favored_constrained", "allowed", "allowed_constrained"]
        )
    )

    if status not in allowed_statuses:
        return [f"strategy_family_status_not_allowed:{family}:{status}"]

    return []

def _parse_option_behavior(option_behavior_state: str) -> Dict[str, str]:
    lowered = option_behavior_state.lower()

    if lowered.startswith("iv_low"):
        iv_level = "low"
    elif lowered.startswith("iv_moderate"):
        iv_level = "moderate"
    elif lowered.startswith("iv_high"):
        iv_level = "high"
    else:
        iv_level = MISSING_VALUE

    if "illiquid_or_sparse" in lowered:
        liquidity_state = "illiquid_or_sparse"
    elif "moderate_liquidity" in lowered:
        liquidity_state = "moderate_liquidity"
    elif lowered.endswith("_liquid") or "_liquid" in lowered:
        liquidity_state = "liquid"
    else:
        liquidity_state = MISSING_VALUE

    return {
        "option_iv_level": iv_level,
        "option_liquidity_state": liquidity_state,
    }


def _decision_row_block_reasons(
    row: Mapping[str, Any],
    *,
    strategy_policy: Mapping[str, Any],
) -> List[str]:
    reasons: List[str] = []

    symbol = _normalise_symbol(row.get("symbol"))
    decision_date = _normalise_text(row.get("date") or row.get("decision_date"))

    if symbol == MISSING_VALUE:
        reasons.append("missing_symbol")

    if decision_date == MISSING_VALUE:
        reasons.append("missing_decision_date")

    eligible_data_states = set(strategy_policy.get("eligible_data_states") or ["complete"])
    source_data_state = str(row.get("data_state") or MISSING_VALUE)

    if source_data_state not in eligible_data_states:
        reasons.append(f"source_data_state_not_eligible:{source_data_state}")

    for required_flag in strategy_policy.get("required_eligibility_flags") or []:
        if not _flag_is_true(row, str(required_flag)):
            reasons.append(f"eligibility_flag_false:{required_flag}")

    regime_state = _nested_state(row.get("regime"))
    asset_behavior_state = _nested_state(row.get("asset_behavior"))
    option_behavior_state = _nested_state(row.get("option_behavior"))

    if regime_state == MISSING_VALUE:
        reasons.append("missing_regime_state")

    if asset_behavior_state == MISSING_VALUE:
        reasons.append("missing_asset_behavior_state")

    if option_behavior_state == MISSING_VALUE:
        reasons.append("missing_option_behavior_state")

    parsed_option_behavior = _parse_option_behavior(option_behavior_state)

    if parsed_option_behavior["option_iv_level"] == MISSING_VALUE:
        reasons.append("missing_option_iv_level")

    if parsed_option_behavior["option_liquidity_state"] == MISSING_VALUE:
        reasons.append("missing_option_liquidity_state")

    return reasons


def _strategy_definition_block_reasons(strategy: Mapping[str, Any]) -> List[str]:
    reasons: List[str] = []

    required_fields = [
        "strategy",
        "strategy_family",
        "strategy_structure",
        "strategy_direction",
        "premium_profile",
        "candidate_rank",
    ]

    for field_name in required_fields:
        if _normalise_text(strategy.get(field_name)) == MISSING_VALUE:
            reasons.append(f"missing_{field_name}")

    return reasons


def _strategy_context_block_reasons(
    *,
    row: Mapping[str, Any],
    strategy: Mapping[str, Any],
    asset_behavior_state: str,
    option_iv_level: str,
    option_liquidity_state: str,
    holding_period_days: int,
    policy: Mapping[str, Any],
) -> List[str]:
    reasons: List[str] = []

    strategy_name = strategy.get("strategy")
    strategy_family = _normalise_text(strategy.get("strategy_family"))

    reasons.extend(
        _strategy_family_gate_block_reasons(
            row=row,
            strategy_family=strategy_family,
            policy=policy,
        )
    )

    blocked_liquidity_states = set(policy.get("blocked_option_liquidity_states") or [])
    if option_liquidity_state in blocked_liquidity_states:
        reasons.append(f"blocked_option_liquidity_state:{option_liquidity_state}")

    allowed_asset_states = set(strategy.get("allowed_asset_behavior_states") or [])
    if allowed_asset_states and asset_behavior_state not in allowed_asset_states:
        reasons.append(
            f"strategy_asset_behavior_not_allowed:{strategy_name}:{asset_behavior_state}"
        )

    allowed_iv_levels = set(strategy.get("allowed_option_iv_levels") or [])
    if allowed_iv_levels and option_iv_level not in allowed_iv_levels:
        reasons.append(
            f"strategy_option_iv_not_allowed:{strategy_name}:{option_iv_level}"
        )

    allowed_liquidity_states = set(strategy.get("allowed_option_liquidity_states") or [])
    if allowed_liquidity_states and option_liquidity_state not in allowed_liquidity_states:
        reasons.append(
            f"strategy_option_liquidity_not_allowed:{strategy_name}:{option_liquidity_state}"
        )

    allowed_holding_periods = set(strategy.get("allowed_holding_period_days") or [])
    if allowed_holding_periods and holding_period_days not in allowed_holding_periods:
        reasons.append(
            f"strategy_horizon_not_allowed:{strategy_name}:{holding_period_days}"
        )

    if bool(strategy.get("requires_underlying_position")) and not _has_underlying_position(row):
        reasons.append(f"requires_underlying_position:{strategy_name}")

    if bool(strategy.get("requires_term_structure")) and not _has_term_structure_behavior(row):
        reasons.append(f"requires_term_structure_behavior:{strategy_name}")

    return reasons


def _candidate_id(
    *,
    decision_row_id: str,
    strategy_instance: str,
) -> str:
    safe_strategy_instance = strategy_instance.replace(" ", "_")
    return f"{decision_row_id}_{safe_strategy_instance}"


def _strategy_instance(
    *,
    strategy: str,
    holding_period_days: int,
    risk_overlay: str,
) -> str:
    return f"{strategy}__{holding_period_days}d__{risk_overlay}"


def _candidate_state(reasons: Sequence[str]) -> str:
    return "available" if not reasons else "blocked"


def build_historical_strategy_candidate_rows(
    *,
    decision_rows: Sequence[Mapping[str, Any]],
    strategy_policy: Optional[Mapping[str, Any]] = None,
    emit_blocked_rows: bool = False,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    policy = dict(strategy_policy or DEFAULT_STRATEGY_POLICY)
    excluded_strategies = set(policy.get("excluded_strategies") or [])
    strategies = [
        strategy
        for strategy in list(policy.get("strategies") or [])
        if strategy.get("strategy") not in excluded_strategies
    ]
    holding_periods = list(policy.get("holding_period_days") or [])
    risk_overlays = list(policy.get("risk_overlays") or [])

    output_rows: List[Dict[str, Any]] = []

    decision_data_state_counts: Counter[str] = Counter()
    decision_block_reason_counts: Counter[str] = Counter()
    strategy_definition_block_reason_counts: Counter[str] = Counter()
    strategy_context_block_reason_counts: Counter[str] = Counter()
    strategy_candidate_state_counts: Counter[str] = Counter()
    regime_counts: Counter[str] = Counter()
    asset_behavior_counts: Counter[str] = Counter()
    option_behavior_counts: Counter[str] = Counter()
    option_iv_level_counts: Counter[str] = Counter()
    option_liquidity_state_counts: Counter[str] = Counter()
    strategy_counts: Counter[str] = Counter()
    available_strategy_counts: Counter[str] = Counter()
    blocked_strategy_counts: Counter[str] = Counter()
    strategy_instance_counts: Counter[str] = Counter()
    available_strategy_instance_counts: Counter[str] = Counter()
    strategy_family_counts: Counter[str] = Counter()
    strategy_family_status_counts: Counter[str] = Counter()
    holding_period_counts: Counter[str] = Counter()
    risk_overlay_counts: Counter[str] = Counter()

    eligible_decision_row_count = 0
    blocked_decision_row_count = 0
    decision_rows_with_at_least_one_available_candidate = 0
    decision_rows_with_no_available_strategy_candidates = 0
    duplicate_candidate_id_count = 0
    seen_candidate_ids: set[str] = set()

    for row in decision_rows:
        source_data_state = str(row.get("data_state") or MISSING_VALUE)
        decision_data_state_counts[source_data_state] += 1

        decision_reasons = _decision_row_block_reasons(row, strategy_policy=policy)

        if decision_reasons:
            blocked_decision_row_count += 1
            for reason in decision_reasons:
                decision_block_reason_counts[reason] += 1
            continue

        eligible_decision_row_count += 1

        symbol = _normalise_symbol(row.get("symbol"))
        decision_date = _normalise_text(row.get("date") or row.get("decision_date"))
        decision_row_id = _normalise_text(row.get("decision_row_id"))

        if decision_row_id == MISSING_VALUE:
            decision_row_id = f"{decision_date}_{symbol}"

        regime = row.get("regime")
        asset_behavior = row.get("asset_behavior")
        option_behavior = row.get("option_behavior")

        regime_state = _nested_state(regime)
        asset_behavior_state = _nested_state(asset_behavior)
        option_behavior_state = _nested_state(option_behavior)

        parsed_option_behavior = _parse_option_behavior(option_behavior_state)
        option_iv_level = parsed_option_behavior["option_iv_level"]
        option_liquidity_state = parsed_option_behavior["option_liquidity_state"]

        has_underlying_position = _has_underlying_position(row)
        has_term_structure_behavior = _has_term_structure_behavior(row)

        regime_counts[regime_state] += 1
        asset_behavior_counts[asset_behavior_state] += 1
        option_behavior_counts[option_behavior_state] += 1
        option_iv_level_counts[option_iv_level] += 1
        option_liquidity_state_counts[option_liquidity_state] += 1

        available_for_decision = 0

        for strategy in strategies:
            definition_reasons = _strategy_definition_block_reasons(strategy)

            if definition_reasons:
                for reason in definition_reasons:
                    strategy_definition_block_reason_counts[reason] += 1
                continue

            strategy_name = _normalise_text(strategy.get("strategy"))
            strategy_family = _normalise_text(strategy.get("strategy_family"))
            strategy_structure = _normalise_text(strategy.get("strategy_structure"))
            strategy_direction = _normalise_text(strategy.get("strategy_direction"))
            premium_profile = _normalise_text(strategy.get("premium_profile"))
            defined_risk = bool(strategy.get("defined_risk"))

            for holding_period_days in holding_periods:
                try:
                    horizon = int(holding_period_days)
                except (TypeError, ValueError):
                    strategy_context_block_reason_counts[
                        f"invalid_holding_period_days:{holding_period_days}"
                    ] += 1
                    continue

                for risk_overlay in risk_overlays:
                    risk_overlay_name = _normalise_text(risk_overlay.get("risk_overlay"))

                    if risk_overlay_name == MISSING_VALUE:
                        strategy_context_block_reason_counts["missing_risk_overlay"] += 1
                        continue

                    context_reasons = _strategy_context_block_reasons(
                        row=row,
                        strategy=strategy,
                        asset_behavior_state=asset_behavior_state,
                        option_iv_level=option_iv_level,
                        option_liquidity_state=option_liquidity_state,
                        holding_period_days=horizon,
                        policy=policy,
                    )

                    for reason in context_reasons:
                        strategy_context_block_reason_counts[reason] += 1

                    state = _candidate_state(context_reasons)
                    is_trainable_candidate = state == "available"

                    strategy_instance = _strategy_instance(
                        strategy=strategy_name,
                        holding_period_days=horizon,
                        risk_overlay=risk_overlay_name,
                    )

                    strategy_candidate_id = _candidate_id(
                        decision_row_id=decision_row_id,
                        strategy_instance=strategy_instance,
                    )

                    if strategy_candidate_id in seen_candidate_ids:
                        duplicate_candidate_id_count += 1
                        continue

                    seen_candidate_ids.add(strategy_candidate_id)

                    if is_trainable_candidate:
                        available_for_decision += 1

                    strategy_candidate_state_counts[state] += 1
                    strategy_counts[strategy_name] += 1
                    strategy_instance_counts[strategy_instance] += 1
                    strategy_family_status = _strategy_family_status(row, strategy_family, policy=policy)

                    strategy_family_counts[strategy_family] += 1
                    strategy_family_status_counts[strategy_family_status] += 1
                    holding_period_counts[str(horizon)] += 1
                    risk_overlay_counts[risk_overlay_name] += 1

                    if is_trainable_candidate:
                        available_strategy_counts[strategy_name] += 1
                        available_strategy_instance_counts[strategy_instance] += 1
                    else:
                        blocked_strategy_counts[strategy_name] += 1
                        
                    if not is_trainable_candidate and not emit_blocked_rows:
                        continue

                    output_rows.append(
                        {
                            "adapter_type": "historical_strategy_candidate_rows_builder",
                            "artifact_type": "signalforge_historical_strategy_candidate_row",
                            "contract": "historical_strategy_candidate_rows",
                            "strategy_candidate_id": strategy_candidate_id,
                            "decision_row_id": decision_row_id,
                            "symbol": symbol,
                            "date": decision_date,
                            "decision_date": decision_date,
                            "strategy": strategy_name,
                            "strategy_instance": strategy_instance,
                            "strategy_family": strategy_family,
                            "strategy_family_status": strategy_family_status,
                            "strategy_structure": strategy_structure,
                            "strategy_direction": strategy_direction,
                            "premium_profile": premium_profile,
                            "defined_risk": defined_risk,
                            "requires_underlying_position": bool(strategy.get("requires_underlying_position")),
                            "requires_term_structure": bool(strategy.get("requires_term_structure")),
                            "has_underlying_position": has_underlying_position,
                            "has_term_structure_behavior": has_term_structure_behavior,
                            "holding_period_days": horizon,
                            "risk_overlay": risk_overlay_name,
                            "risk_overlay_rank": risk_overlay.get("risk_overlay_rank"),
                            "candidate_rank": strategy.get("candidate_rank"),
                            "strategy_candidate_state": state,
                            "strategy_candidate_block_reasons": context_reasons,
                            "strategy_candidate_reason": (
                                "decision_context_eligible_under_full_strategy_universe_policy"
                                if is_trainable_candidate
                                else "blocked_by_strategy_context_policy"
                            ),
                            "is_trainable_candidate": is_trainable_candidate,
                            "strategy_policy_name": policy.get("policy_name"),
                            "strategy_policy_version": policy.get("policy_version"),
                            "regime_state": regime_state,
                            "regime_source_date": _nested_source_date(regime),
                            "asset_behavior_state": asset_behavior_state,
                            "asset_behavior_source_date": _nested_source_date(asset_behavior),
                            "option_behavior_state": option_behavior_state,
                            "option_behavior_source_date": _nested_source_date(option_behavior),
                            "option_iv_level": option_iv_level,
                            "option_liquidity_state": option_liquidity_state,
                            "eligibility": row.get("eligibility"),
                            "blocks": row.get("blocks"),
                            "source_decision_data_state": source_data_state,
                            "data_state": "complete",
                        }
                    )

        if available_for_decision:
            decision_rows_with_at_least_one_available_candidate += 1
        else:
            decision_rows_with_no_available_strategy_candidates += 1

    output_rows.sort(
        key=lambda item: (
            item["decision_date"],
            item["symbol"],
            item.get("candidate_rank") or 999999,
            item["strategy"],
            item["holding_period_days"],
            item["risk_overlay"],
        )
    )

    rows_missing_strategy = sum(
        1 for row in output_rows if _normalise_text(row.get("strategy")) == MISSING_VALUE
    )
    rows_missing_strategy_instance = sum(
        1 for row in output_rows if _normalise_text(row.get("strategy_instance")) == MISSING_VALUE
    )
    rows_missing_regime = sum(
        1 for row in output_rows if _normalise_text(row.get("regime_state")) == MISSING_VALUE
    )
    rows_missing_asset_behavior = sum(
        1 for row in output_rows if _normalise_text(row.get("asset_behavior_state")) == MISSING_VALUE
    )
    rows_missing_option_behavior = sum(
        1 for row in output_rows if _normalise_text(row.get("option_behavior_state")) == MISSING_VALUE
    )
    rows_missing_option_iv_level = sum(
        1 for row in output_rows if _normalise_text(row.get("option_iv_level")) == MISSING_VALUE
    )
    rows_missing_option_liquidity_state = sum(
        1 for row in output_rows
        if _normalise_text(row.get("option_liquidity_state")) == MISSING_VALUE
    )

    available_candidate_row_count = strategy_candidate_state_counts.get("available", 0)
    blocked_candidate_row_count = strategy_candidate_state_counts.get("blocked", 0)

    blockers: List[str] = []

    if not strategies:
        blockers.append("strategy_policy_has_no_strategies")

    if not holding_periods:
        blockers.append("strategy_policy_has_no_holding_periods")

    if not risk_overlays:
        blockers.append("strategy_policy_has_no_risk_overlays")

    if not output_rows:
        blockers.append("no_strategy_candidate_rows_created")

    if available_candidate_row_count == 0:
        blockers.append("no_available_strategy_candidate_rows_created")

    if duplicate_candidate_id_count:
        blockers.append("duplicate_strategy_candidate_ids")

    if strategy_definition_block_reason_counts:
        blockers.append("strategy_policy_contains_invalid_strategy_definitions")

    if rows_missing_strategy:
        blockers.append("rows_missing_strategy")

    if rows_missing_strategy_instance:
        blockers.append("rows_missing_strategy_instance")

    if rows_missing_regime:
        blockers.append("rows_missing_regime")

    if rows_missing_asset_behavior:
        blockers.append("rows_missing_asset_behavior")

    if rows_missing_option_behavior:
        blockers.append("rows_missing_option_behavior")

    if rows_missing_option_iv_level:
        blockers.append("rows_missing_option_iv_level")

    if rows_missing_option_liquidity_state:
        blockers.append("rows_missing_option_liquidity_state")

    summary: Dict[str, Any] = {
        "adapter_type": "historical_strategy_candidate_rows_builder",
        "artifact_type": "signalforge_historical_strategy_candidate_rows",
        "contract": "historical_strategy_candidate_rows",
        "is_ready": len(blockers) == 0,
        "emit_blocked_rows": emit_blocked_rows,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "input_decision_row_count": len(decision_rows),
        "eligible_decision_row_count": eligible_decision_row_count,
        "blocked_decision_row_count": blocked_decision_row_count,
        "decision_rows_with_at_least_one_available_candidate": decision_rows_with_at_least_one_available_candidate,
        "decision_rows_with_no_available_strategy_candidates": decision_rows_with_no_available_strategy_candidates,
        "candidate_row_count": len(output_rows),
        "available_candidate_row_count": available_candidate_row_count,
        "blocked_candidate_row_count": blocked_candidate_row_count,
        "unique_symbols": len({row["symbol"] for row in output_rows}),
        "unique_dates": len({row["decision_date"] for row in output_rows}),
        "unique_strategies": len(strategy_counts),
        "unique_available_strategies": len(available_strategy_counts),
        "unique_strategy_instances": len(strategy_instance_counts),
        "unique_available_strategy_instances": len(available_strategy_instance_counts),
        "unique_holding_periods": len({row["holding_period_days"] for row in output_rows}),
        "decision_data_state_counts": dict(sorted(decision_data_state_counts.items())),
        "decision_block_reason_counts": dict(sorted(decision_block_reason_counts.items())),
        "strategy_definition_block_reason_counts": dict(
            sorted(strategy_definition_block_reason_counts.items())
        ),
        "strategy_context_block_reason_counts": dict(
            sorted(strategy_context_block_reason_counts.items())
        ),
        "strategy_candidate_state_counts": dict(sorted(strategy_candidate_state_counts.items())),
        "regime_state_counts": dict(sorted(regime_counts.items())),
        "asset_behavior_state_counts": dict(sorted(asset_behavior_counts.items())),
        "option_behavior_state_counts": dict(sorted(option_behavior_counts.items())),
        "option_iv_level_counts": dict(sorted(option_iv_level_counts.items())),
        "option_liquidity_state_counts": dict(sorted(option_liquidity_state_counts.items())),
        "strategy_counts": dict(sorted(strategy_counts.items())),
        "available_strategy_counts": dict(sorted(available_strategy_counts.items())),
        "blocked_strategy_counts": dict(sorted(blocked_strategy_counts.items())),
        "strategy_instance_counts": dict(sorted(strategy_instance_counts.items())),
        "available_strategy_instance_counts": dict(sorted(available_strategy_instance_counts.items())),
        "strategy_family_counts": dict(sorted(strategy_family_counts.items())),
        "strategy_family_status_counts": dict(sorted(strategy_family_status_counts.items())),
        "holding_period_counts": dict(sorted(holding_period_counts.items())),
        "risk_overlay_counts": dict(sorted(risk_overlay_counts.items())),
        "validation": {
            "duplicate_candidate_id_count": duplicate_candidate_id_count,
            "rows_missing_strategy": rows_missing_strategy,
            "rows_missing_strategy_instance": rows_missing_strategy_instance,
            "rows_missing_regime": rows_missing_regime,
            "rows_missing_asset_behavior": rows_missing_asset_behavior,
            "rows_missing_option_behavior": rows_missing_option_behavior,
            "rows_missing_option_iv_level": rows_missing_option_iv_level,
            "rows_missing_option_liquidity_state": rows_missing_option_liquidity_state,
        },
        "strategy_policy": {
            "policy_name": policy.get("policy_name"),
            "excluded_strategies": sorted(excluded_strategies),
            "excluded_strategy_reasons": policy.get("excluded_strategy_reasons") or {},
            "policy_version": policy.get("policy_version"),
            "eligible_data_states": policy.get("eligible_data_states"),
            "required_eligibility_flags": policy.get("required_eligibility_flags"),
            "enforce_strategy_family_eligibility": policy.get("enforce_strategy_family_eligibility", True),
            "allowed_strategy_family_statuses": policy.get("allowed_strategy_family_statuses"),
            "blocked_option_liquidity_states": policy.get("blocked_option_liquidity_states"),
            "holding_period_days": policy.get("holding_period_days"),
            "risk_overlays": policy.get("risk_overlays"),
            "strategy_count": len(strategies),
            "strategies": strategies,
        },
        "training_policy": {
            "trainable_strategy_candidate_state": "available",
            "blocked_strategy_candidates_are_trainable": False,
            "expectancy_key": "strategy_instance",
        },
        "explicit_exclusions": [
            "strategy_expectancy",
            "strategy_selection",
            "contract_outcome",
            "contract_return",
            "strategy_adjusted_return",
            "portfolio_reconstruction",
            "broker_order_routing",
            "live_execution",
        ],
        "paths": {},
    }

    return output_rows, summary


def build_historical_strategy_candidate_rows_artifact(
    *,
    decision_rows_path: str | Path,
    output_dir: str | Path,
    strategy_policy_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    output_path = Path(output_dir)

    rows_path = output_path / "signalforge_historical_strategy_candidate_rows.jsonl"
    summary_path = output_path / "signalforge_historical_strategy_candidate_rows_summary.json"

    decision_rows = read_jsonl(decision_rows_path)
    strategy_policy = load_strategy_policy(strategy_policy_path)

    rows, summary = build_historical_strategy_candidate_rows(
        decision_rows=decision_rows,
        strategy_policy=strategy_policy,
         emit_blocked_rows=False,
    )

    summary["paths"] = {
        "decision_rows_path": str(decision_rows_path),
        "strategy_policy_path": str(strategy_policy_path) if strategy_policy_path else None,
        "rows_path": str(rows_path),
        "summary_path": str(summary_path),
    }

    write_jsonl(rows_path, rows)
    write_json(summary_path, summary)

    return summary




