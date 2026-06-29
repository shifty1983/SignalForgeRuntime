"""Build historical expectancy candidate rows from SignalForge historical strategy-family eligibility rows.

This adapter intentionally emits a compatibility shape close to the older
`signalforge_historical_strategy_candidate_row` contract while preserving the
new replay coverage gate and regime/asset/options alignment metadata.

Input grain:
    quote_date + symbol eligibility row

Output grain:
    decision_date + symbol + strategy + holding_period_days

No broker calls, order routing, fills, live execution, or slippage modeling are
performed here. This is a research/backtest candidate-generation artifact only.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass
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

DEFAULT_EXCLUDED_FAMILIES = {
    "defined_risk_only",
    "manual_review_only",
    "wait_for_clearer_options_edge",
}

DEFAULT_ELIGIBLE_COVERAGE_STATES = {
    "full_coverage_core",
    "eligible",
}


@dataclass(frozen=True)
class StrategyDefinition:
    strategy: str
    strategy_family: str
    strategy_structure: str
    strategy_direction: str
    premium_profile: str
    candidate_rank: int
    holding_periods: tuple[int, ...]
    defined_risk: bool = True
    requires_term_structure: bool = False
    requires_underlying_position: bool = False

    def instance(self, holding_period_days: int, risk_overlay: str) -> str:
        return f"{self.strategy}__{holding_period_days}d__{risk_overlay}"


STRATEGY_DEFINITIONS: dict[str, StrategyDefinition] = {
    "long_call": StrategyDefinition(
        strategy="long_call",
        strategy_family="long_premium",
        strategy_structure="single_leg_option",
        strategy_direction="bullish",
        premium_profile="debit",
        candidate_rank=1,
        holding_periods=(5, 10, 21, 45),
    ),
    "long_put": StrategyDefinition(
        strategy="long_put",
        strategy_family="long_premium",
        strategy_structure="single_leg_option",
        strategy_direction="bearish",
        premium_profile="debit",
        candidate_rank=2,
        holding_periods=(5, 10, 21, 45),
    ),
    "bull_call_debit_spread": StrategyDefinition(
        strategy="bull_call_debit_spread",
        strategy_family="debit_spread",
        strategy_structure="vertical_spread",
        strategy_direction="bullish",
        premium_profile="debit",
        candidate_rank=3,
        holding_periods=(5, 10, 21, 45),
    ),
    "bear_put_debit_spread": StrategyDefinition(
        strategy="bear_put_debit_spread",
        strategy_family="debit_spread",
        strategy_structure="vertical_spread",
        strategy_direction="bearish",
        premium_profile="debit",
        candidate_rank=4,
        holding_periods=(5, 10, 21, 45),
    ),
    "put_credit_spread": StrategyDefinition(
        strategy="put_credit_spread",
        strategy_family="credit_spread",
        strategy_structure="vertical_spread",
        strategy_direction="bullish",
        premium_profile="credit",
        candidate_rank=5,
        holding_periods=(5, 10, 21, 45),
    ),
    "call_credit_spread": StrategyDefinition(
        strategy="call_credit_spread",
        strategy_family="credit_spread",
        strategy_structure="vertical_spread",
        strategy_direction="bearish",
        premium_profile="credit",
        candidate_rank=6,
        holding_periods=(5, 10, 21, 45),
    ),
    "iron_condor": StrategyDefinition(
        strategy="iron_condor",
        strategy_family="neutral_income",
        strategy_structure="multi_leg_defined_risk",
        strategy_direction="neutral",
        premium_profile="credit",
        candidate_rank=7,
        holding_periods=(10, 21, 45),
    ),
    "iron_butterfly": StrategyDefinition(
        strategy="iron_butterfly",
        strategy_family="neutral_income",
        strategy_structure="multi_leg_defined_risk",
        strategy_direction="neutral",
        premium_profile="credit",
        candidate_rank=8,
        holding_periods=(10, 21, 45),
    ),
    "calendar_spread": StrategyDefinition(
        strategy="calendar_spread",
        strategy_family="term_structure",
        strategy_structure="calendar_spread",
        strategy_direction="neutral",
        premium_profile="debit",
        candidate_rank=9,
        holding_periods=(21, 45),
        requires_term_structure=True,
    ),
    "diagonal_spread": StrategyDefinition(
        strategy="diagonal_spread",
        strategy_family="term_structure",
        strategy_structure="diagonal_spread",
        strategy_direction="directional",
        premium_profile="debit",
        candidate_rank=10,
        holding_periods=(21, 45),
        requires_term_structure=True,
    ),
    # Disabled by default unless --include-protective-put-spread is supplied.
    # This requires an existing underlying position and should normally be a
    # portfolio-construction/defense candidate, not an independent expectancy row.
    "protective_put_spread": StrategyDefinition(
        strategy="protective_put_spread",
        strategy_family="protective_put_spread",
        strategy_structure="vertical_spread_with_underlying",
        strategy_direction="defensive",
        premium_profile="debit",
        candidate_rank=11,
        holding_periods=(21, 45),
        requires_underlying_position=True,
    ),
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


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

    # CSV stores list/dict fields as compact JSON strings.
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = {}
            for key in fieldnames:
                value = row.get(key)
                if isinstance(value, (dict, list)):
                    out[key] = json.dumps(value, sort_keys=True, separators=(",", ":"))
                else:
                    out[key] = value
            writer.writerow(out)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        if not value.strip():
            return []
        if "," in value:
            return [item.strip() for item in value.split(",") if item.strip()]
        return [value]
    return [value]


def _parse_csv_set(value: str | None, default: set[str]) -> set[str]:
    if value is None:
        return set(default)
    return {item.strip() for item in value.split(",") if item.strip()}


def _nested_get(data: dict[str, Any], *paths: str) -> Any:
    """Return first non-null value from dotted paths."""
    for path in paths:
        current: Any = data
        found = True
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                found = False
                break
            current = current[part]
        if found and current is not None:
            return current
    return None


def _normalize_term_structure_state(value: Any) -> str:
    if value is None:
        return "unavailable"
    text = str(value)
    if text in {"term_structure_not_available", "skew_not_available", "not_available", "missing"}:
        return "unavailable"
    if text.endswith("_term_structure") or text in {"contango", "backwardation", "flat"}:
        return "available"
    if text in {"available", "unavailable"}:
        return text
    return "available"


def _term_structure_shape(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    if text in {"term_structure_not_available", "not_available", "missing", "unavailable"}:
        return None
    if text == "contango_term_structure":
        return "contango"
    if text == "backwardated_term_structure":
        return "backwardated"
    if text == "flat_term_structure":
        return "flat"
    return text


def _iv_level(row: dict[str, Any]) -> str | None:
    # Prefer explicit values if future builders include them.
    explicit = _nested_get(row, "option_iv_level", "asset_options_alignment.option_iv_level")
    if explicit:
        return str(explicit)

    iv_rank_state = _nested_get(row, "iv_rank_state", "asset_options_alignment.iv_rank_state")
    iv_pct_state = _nested_get(row, "iv_percentile_state", "asset_options_alignment.iv_percentile_state")
    text = str(iv_rank_state or iv_pct_state or "")
    if "high" in text:
        return "high"
    if "low" in text:
        return "low"
    if "normal" in text or "moderate" in text:
        return "moderate"
    return None


def _liquidity_state(row: dict[str, Any]) -> str | None:
    explicit = _nested_get(row, "option_liquidity_state", "liquidity_state", "asset_options_alignment.liquidity_state")
    if explicit:
        text = str(explicit)
        if text == "liquid_options":
            return "liquid"
        if text == "moderate_liquidity_review":
            return "moderate_liquidity"
        if text == "illiquid_options":
            return "illiquid"
        return text
    return None


def _option_behavior_state(row: dict[str, Any]) -> str:
    state = str(row.get("options_behavior_state") or row.get("option_behavior_state") or "unknown_options_context")
    iv = _iv_level(row)
    liq = _liquidity_state(row)
    if iv and liq:
        return f"iv_{iv}_{liq}"
    return state


def _is_directional_constructive(asset_state: str) -> bool:
    return asset_state in {"constructive", "confirmed_uptrend", "developing_uptrend", "uptrend"}


def _is_directional_defensive(asset_state: str) -> bool:
    return asset_state in {"defensive", "confirmed_downtrend", "developing_downtrend", "downtrend"}


def _is_neutral(asset_state: str) -> bool:
    return asset_state in {"neutral", "choppy_neutral", "mixed_or_transitioning"}


def _strategies_for_row(
    row: dict[str, Any],
    include_protective_put_spread: bool,
    term_structure_expansion_mode: str,
) -> list[StrategyDefinition]:
    allowed = set(str(x) for x in _as_list(row.get("allowed_strategy_families")))
    discouraged = set(str(x) for x in _as_list(row.get("discouraged_strategy_families")))
    blocked = set(str(x) for x in _as_list(row.get("blocked_strategy_families")))
    asset_state = str(row.get("asset_behavior_state") or "")

    strategies: list[StrategyDefinition] = []

    # Long premium candidates are directional, with asset behavior selecting call vs put.
    if "directional_long_premium" in allowed:
        if _is_directional_constructive(asset_state):
            strategies.append(STRATEGY_DEFINITIONS["long_call"])
        elif _is_directional_defensive(asset_state):
            strategies.append(STRATEGY_DEFINITIONS["long_put"])

    # Debit spreads mirror directional long premium but are defined-risk verticals.
    if "debit_spread" in allowed:
        if _is_directional_constructive(asset_state):
            strategies.append(STRATEGY_DEFINITIONS["bull_call_debit_spread"])
        elif _is_directional_defensive(asset_state):
            strategies.append(STRATEGY_DEFINITIONS["bear_put_debit_spread"])

    # Credit spreads are always defined-risk. Direction chooses put/call credit spread;
    # neutral contexts can score both sides.
    if "credit_spread" in allowed or "defined_risk_short_premium" in allowed:
        if _is_directional_constructive(asset_state):
            strategies.append(STRATEGY_DEFINITIONS["put_credit_spread"])
        elif _is_directional_defensive(asset_state):
            strategies.append(STRATEGY_DEFINITIONS["call_credit_spread"])
        elif _is_neutral(asset_state):
            strategies.append(STRATEGY_DEFINITIONS["put_credit_spread"])
            strategies.append(STRATEGY_DEFINITIONS["call_credit_spread"])

    # Neutral income only when the alignment explicitly says neutral income is valid.
    if "defined_risk_neutral" in allowed:
        strategies.append(STRATEGY_DEFINITIONS["iron_condor"])
        strategies.append(STRATEGY_DEFINITIONS["iron_butterfly"])

    # Long-gamma is mapped to old-compatible term-structure candidates.
    #
    # The current eligibility rows do not always carry explicit term_structure_state,
    # even when long_gamma is allowed by the options layer. The prior enriched candidate
    # artifact emitted calendar/diagonal rows from this long-gamma family, so the default
    # mode below uses long_gamma itself as the candidate-generation proxy. Use
    # --term-structure-expansion-mode require_term_structure_metadata to restore the
    # stricter behavior.
    term_state_raw = _nested_get(
        row,
        "term_structure_state",
        "asset_options_alignment.term_structure_state",
        "asset_options_alignment.term_structure_behavior_state",
    )
    term_state = _normalize_term_structure_state(term_state_raw)
    allow_term_structure_candidates = (
        "long_gamma" in allowed
        and (
            term_structure_expansion_mode == "long_gamma_allowed"
            or term_state == "available"
        )
    )
    if allow_term_structure_candidates:
        if _is_neutral(asset_state):
            strategies.append(STRATEGY_DEFINITIONS["calendar_spread"])
        elif _is_directional_constructive(asset_state) or _is_directional_defensive(asset_state):
            strategies.append(STRATEGY_DEFINITIONS["diagonal_spread"])

    if include_protective_put_spread and "protective_put_spread" in allowed:
        strategies.append(STRATEGY_DEFINITIONS["protective_put_spread"])

    # Deduplicate while preserving rank order.
    unique: dict[str, StrategyDefinition] = {definition.strategy: definition for definition in strategies}
    ordered = sorted(unique.values(), key=lambda definition: definition.candidate_rank)

    return [
        definition for definition in ordered
        if definition.strategy_family not in blocked
        and definition.strategy_family not in discouraged
    ]


def _build_candidate_row(
    source: dict[str, Any],
    definition: StrategyDefinition,
    holding_period_days: int,
    risk_overlay: str,
    risk_overlay_rank: int,
    strategy_policy_name: str,
    strategy_policy_version: str,
    term_structure_expansion_mode: str,
) -> dict[str, Any]:
    decision_date = str(source.get("quote_date") or source.get("as_of_date") or source.get("date"))
    symbol = str(source.get("symbol"))
    decision_row_id = f"{decision_date}_{symbol}"
    strategy_instance = definition.instance(holding_period_days, risk_overlay)
    candidate_id = f"{decision_row_id}_{strategy_instance}"

    term_raw = _nested_get(
        source,
        "term_structure_state",
        "asset_options_alignment.term_structure_state",
        "asset_options_alignment.term_structure_behavior_state",
    )
    term_state = _normalize_term_structure_state(term_raw)
    term_structure_candidate_basis = "explicit_term_structure_metadata"
    if (
        definition.requires_term_structure
        and term_state == "unavailable"
        and term_structure_expansion_mode == "long_gamma_allowed"
        and "long_gamma" in set(str(x) for x in _as_list(source.get("allowed_strategy_families")))
    ):
        term_state = "inferred_from_long_gamma"
        term_structure_candidate_basis = "long_gamma_allowed_without_explicit_term_structure_metadata"
    elif term_state == "unavailable":
        term_structure_candidate_basis = "unavailable"

    term_shape = _term_structure_shape(_nested_get(
        source,
        "term_structure_shape",
        "asset_options_alignment.term_structure_shape",
        "asset_options_alignment.term_structure_state",
        "asset_options_alignment.term_structure_behavior_state",
    ))

    iv_level = _iv_level(source)
    liquidity = _liquidity_state(source)
    option_behavior_state = _option_behavior_state(source)

    option_behavior = {
        "source_date": decision_date,
        "source_state": "available" if source.get("options_behavior_state") else "unknown",
        "state": option_behavior_state,
        "term_structure_source_date": decision_date,
        "term_structure_state": term_state,
        "term_structure_shape": term_shape,
        "term_structure_candidate_basis": term_structure_candidate_basis,
        "front_dte": _nested_get(source, "front_dte", "asset_options_alignment.front_dte"),
        "front_expiration": _nested_get(source, "front_expiration", "asset_options_alignment.front_expiration"),
        "front_iv": _nested_get(source, "front_iv", "asset_options_alignment.front_iv"),
        "back_dte": _nested_get(source, "back_dte", "asset_options_alignment.back_dte"),
        "back_expiration": _nested_get(source, "back_expiration", "asset_options_alignment.back_expiration"),
        "back_iv": _nested_get(source, "back_iv", "asset_options_alignment.back_iv"),
        "front_back_iv_spread": _nested_get(source, "front_back_iv_spread", "asset_options_alignment.front_back_iv_spread"),
        "front_back_iv_spread_pct": _nested_get(source, "front_back_iv_spread_pct", "asset_options_alignment.front_back_iv_spread_pct"),
    }

    # Remove nulls from the nested option behavior, while preserving old top-level keys as nulls.
    option_behavior = {k: v for k, v in option_behavior.items() if v is not None}

    compatibility_eligibility = {
        "is_tradable": True,
        "eligible_for_asset_decision": True,
        "eligible_for_option_decision": True,
        "eligible_for_option_strategy_selection": True,
        "eligible_for_strategy_selection": True,
        "eligible_for_contract_outcome_validation": True,
        "eligible_for_expected_value_scoring": bool(source.get("ev_eligible")),
    }

    candidate_row = {
        "adapter_type": "historical_expectancy_candidate_rows_builder",
        "artifact_type": "signalforge_historical_strategy_candidate_row",
        "contract": "historical_expectancy_candidate_rows",
        "schema_version": "signalforge_historical_expectancy_candidate_row.v1",
        "date": decision_date,
        "decision_date": decision_date,
        "quote_date": decision_date,
        "symbol": symbol,
        "decision_row_id": decision_row_id,
        "strategy_candidate_id": candidate_id,
        "strategy_candidate_state": "available",
        "strategy_candidate_reason": "ev_eligible_under_replay_coverage_strategy_family_policy",
        "strategy_candidate_block_reasons": [],
        "is_trainable_candidate": True,
        "ev_eligible": True,
        "expected_value_handoff_status": source.get("expected_value_handoff_status"),
        "data_state": "complete" if source.get("coverage_status") == "ready" else str(source.get("coverage_status") or "review"),
        "source_decision_data_state": source.get("coverage_status"),
        "coverage_status": source.get("coverage_status"),
        "strategy": definition.strategy,
        "strategy_family": definition.strategy_family,
        "strategy_instance": strategy_instance,
        "strategy_structure": definition.strategy_structure,
        "strategy_direction": definition.strategy_direction,
        "candidate_rank": definition.candidate_rank,
        "holding_period_days": holding_period_days,
        "defined_risk": definition.defined_risk,
        "premium_profile": definition.premium_profile,
        "requires_term_structure": definition.requires_term_structure,
        "has_term_structure_behavior": term_state in {"available", "inferred_from_long_gamma"},
        "term_structure_candidate_basis": term_structure_candidate_basis,
        "requires_underlying_position": definition.requires_underlying_position,
        "has_underlying_position": False,
        "risk_overlay": risk_overlay,
        "risk_overlay_rank": risk_overlay_rank,
        "strategy_policy_name": strategy_policy_name,
        "strategy_policy_version": strategy_policy_version,
        "eligibility": compatibility_eligibility,
        "blocks": [],
        "asset_behavior_state": source.get("asset_behavior_state"),
        "asset_behavior_source_date": source.get("quote_date") or source.get("as_of_date"),
        "regime_state": source.get("macro_regime") or source.get("regime_state"),
        "macro_regime": source.get("macro_regime"),
        "regime_source_date": _nested_get(source, "source_refs.regime_date", "regime_source_date"),
        "weekly_planning_label": source.get("weekly_planning_label"),
        "strategy_environment_bias": source.get("strategy_environment_bias"),
        "option_behavior_state": option_behavior_state,
        "options_behavior_state": source.get("options_behavior_state"),
        "option_behavior_source_date": source.get("quote_date") or source.get("as_of_date"),
        "option_iv_level": iv_level,
        "option_liquidity_state": liquidity,
        "premium_bias": source.get("premium_bias"),
        "term_structure_state": term_state,
        "term_structure_shape": term_shape,
        "term_structure_candidate_basis": term_structure_candidate_basis,
        "front_dte": _nested_get(source, "front_dte", "asset_options_alignment.front_dte"),
        "front_expiration": _nested_get(source, "front_expiration", "asset_options_alignment.front_expiration"),
        "front_iv": _nested_get(source, "front_iv", "asset_options_alignment.front_iv"),
        "back_dte": _nested_get(source, "back_dte", "asset_options_alignment.back_dte"),
        "back_expiration": _nested_get(source, "back_expiration", "asset_options_alignment.back_expiration"),
        "back_iv": _nested_get(source, "back_iv", "asset_options_alignment.back_iv"),
        "front_back_iv_spread": _nested_get(source, "front_back_iv_spread", "asset_options_alignment.front_back_iv_spread"),
        "front_back_iv_spread_pct": _nested_get(source, "front_back_iv_spread_pct", "asset_options_alignment.front_back_iv_spread_pct"),
        "option_behavior": option_behavior,
        "allowed_strategy_families": source.get("allowed_strategy_families", []),
        "blocked_strategy_families": source.get("blocked_strategy_families", []),
        "favored_strategy_families": source.get("favored_strategy_families", []),
        "discouraged_strategy_families": source.get("discouraged_strategy_families", []),
        "constraint_flags": source.get("constraint_flags", []),
        "risk_flags": source.get("risk_flags", []),
        "replay_coverage_state": source.get("replay_coverage_state"),
        "replay_option_coverage_pct": source.get("replay_option_coverage_pct"),
        "replay_aligned_date_count": source.get("replay_aligned_date_count"),
        "replay_missing_date_count": source.get("replay_missing_date_count"),
        "replay_target_date_count": source.get("replay_target_date_count"),
        "symbol_policy_role": source.get("symbol_policy_role"),
        "source_refs": source.get("source_refs", {}),
        "source_eligibility_row": {
            "quote_date": source.get("quote_date"),
            "symbol": source.get("symbol"),
            "expected_value_handoff_status": source.get("expected_value_handoff_status"),
            "replay_coverage_state": source.get("replay_coverage_state"),
        },
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "automatic_action": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "automatic_strategy_change": None,
        "broker_order_id": None,
        "order_intent": "research_backtest_candidate_only",
    }

    return candidate_row


def build_candidate_rows(
    eligibility_rows_path: Path,
    output_dir: Path,
    eligible_coverage_states: set[str],
    excluded_families: set[str],
    risk_overlay: str,
    risk_overlay_rank: int,
    strategy_policy_name: str,
    strategy_policy_version: str,
    include_protective_put_spread: bool,
    term_structure_expansion_mode: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    input_row_count = 0
    ev_eligible_input_row_count = 0
    skipped_not_ev_eligible = 0
    skipped_coverage_state = 0
    skipped_no_strategy = 0
    skipped_excluded_only = 0

    candidate_rows: list[dict[str, Any]] = []
    input_dates: set[str] = set()
    input_symbols: set[str] = set()
    emitted_dates: set[str] = set()
    emitted_symbols: set[str] = set()

    coverage_state_input_counts: Counter[str] = Counter()
    coverage_state_emitted_counts: Counter[str] = Counter()
    strategy_counts: Counter[str] = Counter()
    strategy_family_counts: Counter[str] = Counter()
    holding_period_counts: Counter[str] = Counter()
    asset_behavior_counts: Counter[str] = Counter()
    options_behavior_counts: Counter[str] = Counter()
    macro_regime_counts: Counter[str] = Counter()
    premium_profile_counts: Counter[str] = Counter()

    for row in _iter_jsonl(eligibility_rows_path):
        input_row_count += 1
        decision_date = str(row.get("quote_date") or row.get("as_of_date") or row.get("date") or "")
        symbol = str(row.get("symbol") or "")
        if decision_date:
            input_dates.add(decision_date)
        if symbol:
            input_symbols.add(symbol)

        coverage_state = str(row.get("replay_coverage_state") or "unknown")
        coverage_state_input_counts[coverage_state] += 1

        if not bool(row.get("ev_eligible")):
            skipped_not_ev_eligible += 1
            continue

        ev_eligible_input_row_count += 1

        if coverage_state not in eligible_coverage_states:
            skipped_coverage_state += 1
            continue

        allowed = set(str(x) for x in _as_list(row.get("allowed_strategy_families")))
        candidate_relevant = allowed - excluded_families
        if not candidate_relevant:
            skipped_excluded_only += 1
            continue

        definitions = _strategies_for_row(row, include_protective_put_spread, term_structure_expansion_mode)
        if not definitions:
            skipped_no_strategy += 1
            continue

        for definition in definitions:
            for holding_period_days in definition.holding_periods:
                candidate = _build_candidate_row(
                    source=row,
                    definition=definition,
                    holding_period_days=holding_period_days,
                    risk_overlay=risk_overlay,
                    risk_overlay_rank=risk_overlay_rank,
                    strategy_policy_name=strategy_policy_name,
                    strategy_policy_version=strategy_policy_version,
                    term_structure_expansion_mode=term_structure_expansion_mode,
                )
                candidate_rows.append(candidate)
                emitted_dates.add(candidate["decision_date"])
                emitted_symbols.add(candidate["symbol"])
                coverage_state_emitted_counts[coverage_state] += 1
                strategy_counts[definition.strategy] += 1
                strategy_family_counts[definition.strategy_family] += 1
                holding_period_counts[str(holding_period_days)] += 1
                asset_behavior_counts[str(row.get("asset_behavior_state"))] += 1
                options_behavior_counts[str(row.get("options_behavior_state"))] += 1
                macro_regime_counts[str(row.get("macro_regime") or row.get("regime_state"))] += 1
                premium_profile_counts[definition.premium_profile] += 1

    rows_path = output_dir / "signalforge_historical_expectancy_candidate_rows.jsonl"
    csv_path = output_dir / "signalforge_historical_expectancy_candidate_rows.csv"
    result_path = output_dir / "signalforge_historical_expectancy_candidate_rows.json"
    summary_path = output_dir / "signalforge_historical_expectancy_candidate_rows_summary.json"

    _write_jsonl(rows_path, candidate_rows)
    _write_csv(csv_path, candidate_rows)

    is_ready = bool(candidate_rows)
    summary = {
        "adapter_type": "historical_expectancy_candidate_rows_builder",
        "operation_type": "signalforge_historical_expectancy_candidate_rows_cli",
        "artifact_type": "signalforge_historical_expectancy_candidate_rows",
        "contract": "historical_expectancy_candidate_rows",
        "schema_version": "signalforge_historical_expectancy_candidate_rows_summary.v1",
        "status": "ready" if is_ready else "blocked",
        "is_ready": is_ready,
        "source_eligibility_rows_path": str(eligibility_rows_path),
        "input_eligibility_row_count": input_row_count,
        "ev_eligible_input_row_count": ev_eligible_input_row_count,
        "historical_expectancy_candidate_row_count": len(candidate_rows),
        "input_date_count": len(input_dates),
        "input_symbol_count": len(input_symbols),
        "emitted_date_count": len(emitted_dates),
        "emitted_symbol_count": len(emitted_symbols),
        "skipped_not_ev_eligible_row_count": skipped_not_ev_eligible,
        "skipped_ineligible_coverage_state_row_count": skipped_coverage_state,
        "skipped_excluded_only_row_count": skipped_excluded_only,
        "skipped_no_strategy_mapping_row_count": skipped_no_strategy,
        "eligible_coverage_states": sorted(eligible_coverage_states),
        "excluded_strategy_families": sorted(excluded_families),
        "strategy_policy_name": strategy_policy_name,
        "strategy_policy_version": strategy_policy_version,
        "risk_overlay": risk_overlay,
        "risk_overlay_rank": risk_overlay_rank,
        "term_structure_expansion_mode": term_structure_expansion_mode,
        "strategy_counts": dict(sorted(strategy_counts.items())),
        "strategy_family_counts": dict(sorted(strategy_family_counts.items())),
        "holding_period_counts": dict(sorted(holding_period_counts.items(), key=lambda item: int(item[0]))),
        "premium_profile_counts": dict(sorted(premium_profile_counts.items())),
        "coverage_state_input_counts": dict(sorted(coverage_state_input_counts.items())),
        "coverage_state_emitted_candidate_counts": dict(sorted(coverage_state_emitted_counts.items())),
        "asset_behavior_state_candidate_counts": dict(sorted(asset_behavior_counts.items())),
        "options_behavior_state_candidate_counts": dict(sorted(options_behavior_counts.items())),
        "macro_regime_candidate_counts": dict(sorted(macro_regime_counts.items())),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "paths": {
            "result": str(result_path),
            "summary": str(summary_path),
            "rows_jsonl": str(rows_path),
            "rows_csv": str(csv_path),
        },
        "next_step": "historical_expectancy_scoring",
    }

    result = {
        **summary,
        "candidate_rows": candidate_rows[:100],
        "candidate_rows_preview_note": "Full candidate rows are written to rows_jsonl and rows_csv. Result includes first 100 rows only to keep the JSON artifact compact.",
    }

    _write_json(result_path, result)
    _write_json(summary_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Build historical expectancy candidate rows from historical strategy-family eligibility rows.")
    parser.add_argument("--eligibility-rows", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--eligible-coverage-states", default=",".join(sorted(DEFAULT_ELIGIBLE_COVERAGE_STATES)))
    parser.add_argument("--excluded-strategy-families", default=",".join(sorted(DEFAULT_EXCLUDED_FAMILIES)))
    parser.add_argument("--risk-overlay", default="defined_risk_cap_m1_p1")
    parser.add_argument("--risk-overlay-rank", type=int, default=1)
    parser.add_argument("--strategy-policy-name", default="historical_replay_defined_risk_strategy_family_policy")
    parser.add_argument("--strategy-policy-version", default="4.0")
    parser.add_argument("--include-protective-put-spread", action="store_true")
    parser.add_argument(
        "--term-structure-expansion-mode",
        choices=("long_gamma_allowed", "require_term_structure_metadata"),
        default="long_gamma_allowed",
        help=(
            "long_gamma_allowed emits calendar/diagonal candidates whenever long_gamma is allowed; "
            "require_term_structure_metadata emits them only when explicit term-structure metadata is present."
        ),
    )
    args = parser.parse_args()

    summary = build_candidate_rows(
        eligibility_rows_path=args.eligibility_rows,
        output_dir=args.output_dir,
        eligible_coverage_states=_parse_csv_set(args.eligible_coverage_states, DEFAULT_ELIGIBLE_COVERAGE_STATES),
        excluded_families=_parse_csv_set(args.excluded_strategy_families, DEFAULT_EXCLUDED_FAMILIES),
        risk_overlay=args.risk_overlay,
        risk_overlay_rank=args.risk_overlay_rank,
        strategy_policy_name=args.strategy_policy_name,
        strategy_policy_version=args.strategy_policy_version,
        include_protective_put_spread=args.include_protective_put_spread,
        term_structure_expansion_mode=args.term_structure_expansion_mode,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("is_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
