"""Reusable candidate-filter and block-reason decision helpers.

Backtesting owns historical replay orchestration.
This module owns reusable candidate filter/block-reason logic used by
historical replay, paper candidate evaluation, and future live evaluation.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Sequence

MISSING_VALUE = "__missing__"

def _normalise_text(value: Any) -> str:
    if value in (None, ""):
        return MISSING_VALUE

    return str(value).strip() or MISSING_VALUE

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

def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}

def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return []

def _research_context_from_decision_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "regime": _as_dict(row.get("regime")),
        "asset_behavior": _as_dict(row.get("asset_behavior")),
        "option_behavior": _as_dict(row.get("option_behavior")),
        "regime_asset_options_alignment": _as_dict(row.get("regime_asset_options_alignment")),
        "strategy_family_eligibility": _as_dict(row.get("strategy_family_eligibility")),
        "strategy_family_statuses": _as_dict(row.get("strategy_family_statuses")),
        "favored_strategy_families": _as_list(row.get("favored_strategy_families")),
        "allowed_strategy_families": _as_list(row.get("allowed_strategy_families")),
        "discouraged_strategy_families": _as_list(row.get("discouraged_strategy_families")),
        "blocked_strategy_families": _as_list(row.get("blocked_strategy_families")),
        "review_required_strategy_families": _as_list(row.get("review_required_strategy_families")),
        "strategy_family_eligibility_handoff": row.get("strategy_family_eligibility_handoff"),
    }

def _eligibility(row: Mapping[str, Any]) -> Mapping[str, Any]:
    eligibility = row.get("eligibility")
    return eligibility if isinstance(eligibility, Mapping) else {}

def _flag_is_true(row: Mapping[str, Any], flag_name: str) -> bool:
    return bool(_eligibility(row).get(flag_name))

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

def _normalise_symbol(value: Any) -> str:
    if value in (None, ""):
        return MISSING_VALUE

    return str(value).strip().upper() or MISSING_VALUE

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

def _candidate_state(reasons: Sequence[str]) -> str:
    return "available" if not reasons else "blocked"
