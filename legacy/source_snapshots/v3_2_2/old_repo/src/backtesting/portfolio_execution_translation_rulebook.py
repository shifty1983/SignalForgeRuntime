"""Portfolio execution translation rulebook.

This builder creates a paper-trading/live-translation rulebook for the strategy
families selected by the portfolio replay. It does not score performance and does
not change strategy selection. Its purpose is to turn strategy names into
explicit order-intent, entry, exit, close, defense, and broker-capability rules
that can be consumed by deployment-readiness and paper-trading harnesses.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Set, Tuple

ADAPTER_TYPE = "portfolio_execution_translation_rulebook_builder"
ARTIFACT_TYPE = "signalforge_portfolio_execution_translation_rulebook"
CONTRACT = "portfolio_execution_translation_rulebook"
OUTPUT_BASENAME = "signalforge_portfolio_execution_translation_rulebook"

DEFAULT_STRATEGIES = (
    "bear_put_debit_spread",
    "bull_call_debit_spread",
    "calendar_spread",
    "call_credit_spread",
    "diagonal_spread",
    "iron_butterfly",
    "iron_condor",
    "long_call",
    "long_put",
    "put_credit_spread",
)

STRATEGY_FIELD_CANDIDATES = (
    "strategy",
    "strategy_name",
    "selected_strategy",
    "top_strategy",
    "candidate_strategy",
    "strategy_id",
)

REQUIRED_BROKER_CAPABILITIES = (
    "option_chain_quotes",
    "option_contract_selection",
    "limit_orders",
    "multi_leg_option_orders",
    "combo_close_orders",
    "paper_trading",
    "order_status_polling",
    "position_snapshot",
    "option_position_snapshot",
    "buying_power_or_margin_preview",
)

GLOBAL_MANUAL_REVIEW_RULES = (
    {
        "rule_id": "missing_or_stale_quote_manual_review",
        "trigger": "option quote, greeks, bid/ask, or chain snapshot is missing or stale at order-decision time",
        "required_action": "Do not submit the order automatically. Refresh quotes or skip the candidate.",
        "applies_to": "all_strategies",
        "severity": "warning",
    },
    {
        "rule_id": "spread_width_manual_review",
        "trigger": "bid/ask spread width exceeds the configured liquidity policy threshold",
        "required_action": "Do not route automatically. Reduce size, adjust limit, or skip after manual review.",
        "applies_to": "all_strategies",
        "severity": "warning",
    },
    {
        "rule_id": "broker_rejection_manual_review",
        "trigger": "broker rejects the multi-leg order, margin preview, or contract selection",
        "required_action": "Do not retry blindly. Capture rejection reason and require manual review.",
        "applies_to": "all_strategies",
        "severity": "warning",
    },
    {
        "rule_id": "position_size_policy_manual_review",
        "trigger": "computed quantity is zero, negative, above configured max risk, or conflicts with buying-power preview",
        "required_action": "Block the order until sizing policy and account constraints are reconciled.",
        "applies_to": "all_strategies",
        "severity": "warning",
    },
)


@dataclass(frozen=True)
class InputPathSet:
    strategy_selection_rows: Optional[Path] = None
    selected_trade_sequence_summary: Optional[Path] = None
    readiness_execution_gap_audit: Optional[Path] = None
    readiness_summary: Optional[Path] = None


@dataclass
class BuildResult:
    review: Dict[str, Any]
    summary: Dict[str, Any]
    strategy_rules: List[Dict[str, Any]]
    broker_capability_matrix: List[Dict[str, Any]]
    manual_review_rules: List[Dict[str, Any]]
    readiness_bridge: Dict[str, Any]
    blockers: List[Dict[str, Any]]
    unmapped_strategies: List[Dict[str, Any]]


def build_portfolio_execution_translation_rulebook(
    *,
    inputs: InputPathSet,
    output_dir: Path,
    include_default_supported_strategies: bool = False,
) -> BuildResult:
    """Build the execution translation rulebook and write artifacts."""

    output_dir.mkdir(parents=True, exist_ok=True)
    input_status = _collect_input_status(inputs)
    observed_strategies = _collect_strategy_names(inputs)
    if include_default_supported_strategies:
        observed_strategies.update(DEFAULT_STRATEGIES)

    strategy_rules: List[Dict[str, Any]] = []
    unmapped_strategies: List[Dict[str, Any]] = []
    blockers: List[Dict[str, Any]] = []

    for strategy in sorted(observed_strategies):
        rule = _build_strategy_rule(strategy)
        if rule["readiness_state"] == "unmapped":
            unmapped = {
                "strategy": strategy,
                "readiness_state": "blocked",
                "reason": "Strategy was observed in portfolio artifacts but has no execution translation rule.",
                "recommended_action": "Add a strategy template with entry, close, defense, and broker capability mapping before paper trading.",
            }
            unmapped_strategies.append(unmapped)
            blockers.append(
                {
                    "blocker_type": "unmapped_strategy_execution_rule",
                    "severity": "blocker",
                    "field": strategy,
                    "affected_stage": "execution_translation_rulebook",
                    "reason": unmapped["reason"],
                    "recommended_action": unmapped["recommended_action"],
                }
            )
        strategy_rules.append(rule)

    broker_capability_matrix = _build_broker_capability_matrix(strategy_rules)
    manual_review_rules = _build_manual_review_rules(strategy_rules)
    readiness_bridge = _build_readiness_bridge(strategy_rules, unmapped_strategies)

    mapped_strategy_count = sum(1 for row in strategy_rules if row["readiness_state"] != "unmapped")
    unmapped_strategy_count = len(unmapped_strategies)
    paper_supported_strategy_count = sum(1 for row in strategy_rules if row.get("paper_trade_supported") is True)
    live_supported_strategy_count = sum(1 for row in strategy_rules if row.get("live_trade_supported") is True)
    close_rule_mapped_strategy_count = sum(1 for row in strategy_rules if row.get("close_rule_available") is True)
    defense_rule_mapped_strategy_count = sum(1 for row in strategy_rules if row.get("defense_rule_available") is True)
    broker_capability_warning_count = sum(1 for row in broker_capability_matrix if row.get("readiness_state") != "paper_ready")
    blocker_count = len(blockers)

    rulebook_readiness_state = "blocked_for_unmapped_strategy" if blocker_count else "ready_for_paper_trading_rule_translation"

    summary = {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": ARTIFACT_TYPE,
        "contract": CONTRACT,
        "is_ready": blocker_count == 0,
        "rulebook_readiness_state": rulebook_readiness_state,
        "input_strategy_count": len(observed_strategies),
        "mapped_strategy_count": mapped_strategy_count,
        "unmapped_strategy_count": unmapped_strategy_count,
        "paper_supported_strategy_count": paper_supported_strategy_count,
        "live_supported_strategy_count": live_supported_strategy_count,
        "close_rule_mapped_strategy_count": close_rule_mapped_strategy_count,
        "defense_rule_mapped_strategy_count": defense_rule_mapped_strategy_count,
        "broker_capability_warning_count": broker_capability_warning_count,
        "manual_review_rule_count": len(manual_review_rules),
        "blocker_count": blocker_count,
        "execution_gap_resolution": {
            "unmapped_exit_logic_resolved_for_mapped_strategies": blocker_count == 0,
            "close_rules_available": close_rule_mapped_strategy_count == mapped_strategy_count and mapped_strategy_count > 0,
            "defense_rules_available": defense_rule_mapped_strategy_count == mapped_strategy_count and mapped_strategy_count > 0,
            "paper_trade_supported": paper_supported_strategy_count == mapped_strategy_count and mapped_strategy_count > 0,
            "live_trade_supported": live_supported_strategy_count == mapped_strategy_count and mapped_strategy_count > 0,
        },
        "recommended_next_step": "wire_rulebook_into_portfolio_deployment_readiness_review_or_paper_trading_shadow_replay",
        "paths": _output_paths(output_dir),
        "input_status": input_status,
    }

    review = {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": ARTIFACT_TYPE,
        "contract": CONTRACT,
        "summary": summary,
        "strategy_rules": strategy_rules,
        "broker_capability_matrix": broker_capability_matrix,
        "manual_review_rules": manual_review_rules,
        "readiness_bridge": readiness_bridge,
        "blockers": blockers,
        "unmapped_strategies": unmapped_strategies,
    }

    _write_json(output_dir / f"{OUTPUT_BASENAME}.json", review)
    _write_json(output_dir / f"{OUTPUT_BASENAME}_summary.json", summary)
    _write_jsonl(output_dir / f"{OUTPUT_BASENAME}_strategy_rules.jsonl", strategy_rules)
    _write_jsonl(output_dir / f"{OUTPUT_BASENAME}_broker_capability_matrix.jsonl", broker_capability_matrix)
    _write_jsonl(output_dir / f"{OUTPUT_BASENAME}_manual_review_rules.jsonl", manual_review_rules)
    _write_json(output_dir / f"{OUTPUT_BASENAME}_readiness_bridge.json", readiness_bridge)
    _write_jsonl(output_dir / f"{OUTPUT_BASENAME}_blockers.jsonl", blockers)
    _write_jsonl(output_dir / f"{OUTPUT_BASENAME}_unmapped_strategies.jsonl", unmapped_strategies)

    return BuildResult(
        review=review,
        summary=summary,
        strategy_rules=strategy_rules,
        broker_capability_matrix=broker_capability_matrix,
        manual_review_rules=manual_review_rules,
        readiness_bridge=readiness_bridge,
        blockers=blockers,
        unmapped_strategies=unmapped_strategies,
    )


def _collect_input_status(inputs: InputPathSet) -> Dict[str, Dict[str, Any]]:
    status: Dict[str, Dict[str, Any]] = {}
    for name, path in inputs.__dict__.items():
        if path is None:
            status[name] = {
                "provided": False,
                "exists": False,
                "path": None,
                "readiness_state": "not_provided",
            }
            continue
        exists = path.exists()
        status[name] = {
            "provided": True,
            "exists": exists,
            "path": str(path),
            "size_bytes": path.stat().st_size if exists else None,
            "readiness_state": "available" if exists else "missing",
        }
    return status


def _collect_strategy_names(inputs: InputPathSet) -> Set[str]:
    strategies: Set[str] = set()

    for path in (
        inputs.strategy_selection_rows,
        inputs.readiness_execution_gap_audit,
        inputs.selected_trade_sequence_summary,
        inputs.readiness_summary,
    ):
        if not path or not path.exists():
            continue
        for record in _iter_records_from_path(path):
            if isinstance(record, Mapping):
                strategies.update(_extract_strategy_values_from_mapping(record))

    cleaned = {str(s).strip() for s in strategies if s is not None and str(s).strip()}
    cleaned = {s for s in cleaned if s.lower() not in {"none", "null", "nan", "unknown", "unknown_strategy"}}
    return cleaned


def _extract_strategy_values_from_mapping(mapping: Mapping[str, Any]) -> Set[str]:
    values: Set[str] = set()
    flat = _flatten_mapping(mapping)
    for key, value in flat.items():
        key_l = key.lower().split(".")[-1]
        if key_l in STRATEGY_FIELD_CANDIDATES or key_l.endswith("strategy"):
            if isinstance(value, str) and value.strip():
                values.add(value.strip())
    return values


def _build_strategy_rule(strategy: str) -> Dict[str, Any]:
    s = _normalize_strategy(strategy)
    template = _strategy_template(s)
    if template is None:
        return {
            "strategy": strategy,
            "normalized_strategy": s,
            "readiness_state": "unmapped",
            "paper_trade_supported": False,
            "live_trade_supported": False,
            "close_rule_available": False,
            "defense_rule_available": False,
            "manual_review_required": True,
            "execution_gaps": ["unmapped_strategy_execution_rule"],
        }

    required_capabilities = _required_capabilities_for_rule(template)
    entry_rule = {
        "entry_order_type": template["entry_order_type"],
        "order_intent": template["order_intent"],
        "pricing_basis": "net_debit_or_credit_limit_based_on_current_bid_ask_midpoint_and_configured_price_improvement_policy",
        "quantity_source": "portfolio_position_sizing_replay_or_live_risk_budget",
        "submit_condition": "all_required_contracts_present_quotes_fresh_liquidity_policy_passes_buying_power_preview_passes",
        "manual_submit_allowed": True,
        "automatic_submit_allowed": False,
    }
    close_rule = {
        "close_rule_available": True,
        "close_order_type": "multi_leg_limit_close_order" if template["required_legs"] > 1 else "single_leg_limit_close_order",
        "primary_time_exit": "close_on_or_before_target_exit_date_if_position_is_open",
        "profit_take_rule": "configured_strategy_profit_target_or_manual_review_close",
        "risk_exit_rule": "configured_max_loss_or_signal_invalidated_close",
        "expiration_risk_rule": template["expiration_risk_rule"],
        "liquidity_exit_rule": "manual_review_if_spread_or_quote_quality_degrades_before_close",
        "automatic_close_allowed": False,
        "paper_close_allowed": True,
    }
    defense_rule = {
        "defense_rule_available": True,
        "automatic_roll_supported": False,
        "automatic_defense_order_allowed": False,
        "manual_review_triggers": template["manual_review_triggers"],
        "default_defense_action": "hold_or_close_after_manual_review_no_automatic_roll",
    }
    broker_translation = {
        "broker_supported": "paper_ready_pending_account_specific_permissions",
        "required_capabilities": required_capabilities,
        "unsupported_live_assumptions": [
            "live broker permissions, margin treatment, and routing behavior are not proven by backtest artifacts",
            "automatic live submission remains disabled until paper-trading shadow replay passes",
        ],
        "order_payload_shape": template["order_payload_shape"],
    }

    return {
        "strategy": strategy,
        "normalized_strategy": s,
        "strategy_family": template["strategy_family"],
        "directional_bias": template["directional_bias"],
        "option_structure": template["option_structure"],
        "required_legs": template["required_legs"],
        "required_option_legs": template["required_option_legs"],
        "net_price_type": template["net_price_type"],
        "max_risk_defined": template["max_risk_defined"],
        "order_intent_available": True,
        "entry_rule": entry_rule,
        "close_rule": close_rule,
        "defense_rule": defense_rule,
        "broker_translation": broker_translation,
        "close_rule_available": True,
        "defense_rule_available": True,
        "manual_review_required": False,
        "paper_trade_supported": True,
        "live_trade_supported": False,
        "readiness_state": "paper_ready",
        "execution_gaps": [],
    }


def _strategy_template(strategy: str) -> Optional[Dict[str, Any]]:
    templates = {
        "bear_put_debit_spread": {
            "strategy_family": "vertical_debit_spread",
            "directional_bias": "bearish",
            "option_structure": "defined_risk_put_debit_spread",
            "required_legs": 2,
            "required_option_legs": [
                {"role": "long_put", "relative_strike": "higher_strike", "side": "buy_to_open"},
                {"role": "short_put", "relative_strike": "lower_strike", "side": "sell_to_open"},
            ],
            "net_price_type": "debit",
            "order_intent": "open_put_debit_spread",
            "entry_order_type": "multi_leg_net_debit_limit_order",
            "order_payload_shape": "two_leg_vertical_put_spread_combo_order",
            "max_risk_defined": True,
            "expiration_risk_rule": "close_before_expiration_or_before_short_put_assignment_risk_window",
            "manual_review_triggers": ["short_put_assignment_risk", "wide_spread", "missing_quote", "near_expiration"],
        },
        "bull_call_debit_spread": {
            "strategy_family": "vertical_debit_spread",
            "directional_bias": "bullish",
            "option_structure": "defined_risk_call_debit_spread",
            "required_legs": 2,
            "required_option_legs": [
                {"role": "long_call", "relative_strike": "lower_strike", "side": "buy_to_open"},
                {"role": "short_call", "relative_strike": "higher_strike", "side": "sell_to_open"},
            ],
            "net_price_type": "debit",
            "order_intent": "open_call_debit_spread",
            "entry_order_type": "multi_leg_net_debit_limit_order",
            "order_payload_shape": "two_leg_vertical_call_spread_combo_order",
            "max_risk_defined": True,
            "expiration_risk_rule": "close_before_expiration_or_before_short_call_assignment_risk_window",
            "manual_review_triggers": ["short_call_assignment_risk", "wide_spread", "missing_quote", "near_expiration"],
        },
        "put_credit_spread": {
            "strategy_family": "vertical_credit_spread",
            "directional_bias": "bullish_or_neutral",
            "option_structure": "defined_risk_put_credit_spread",
            "required_legs": 2,
            "required_option_legs": [
                {"role": "short_put", "relative_strike": "higher_strike", "side": "sell_to_open"},
                {"role": "long_put", "relative_strike": "lower_strike", "side": "buy_to_open"},
            ],
            "net_price_type": "credit",
            "order_intent": "open_put_credit_spread",
            "entry_order_type": "multi_leg_net_credit_limit_order",
            "order_payload_shape": "two_leg_vertical_put_spread_combo_order",
            "max_risk_defined": True,
            "expiration_risk_rule": "close_before_expiration_or_before_short_put_assignment_risk_window",
            "manual_review_triggers": ["short_put_assignment_risk", "wide_spread", "missing_quote", "near_expiration"],
        },
        "call_credit_spread": {
            "strategy_family": "vertical_credit_spread",
            "directional_bias": "bearish_or_neutral",
            "option_structure": "defined_risk_call_credit_spread",
            "required_legs": 2,
            "required_option_legs": [
                {"role": "short_call", "relative_strike": "lower_strike", "side": "sell_to_open"},
                {"role": "long_call", "relative_strike": "higher_strike", "side": "buy_to_open"},
            ],
            "net_price_type": "credit",
            "order_intent": "open_call_credit_spread",
            "entry_order_type": "multi_leg_net_credit_limit_order",
            "order_payload_shape": "two_leg_vertical_call_spread_combo_order",
            "max_risk_defined": True,
            "expiration_risk_rule": "close_before_expiration_or_before_short_call_assignment_risk_window",
            "manual_review_triggers": ["short_call_assignment_risk", "wide_spread", "missing_quote", "near_expiration"],
        },
        "calendar_spread": {
            "strategy_family": "calendar_spread",
            "directional_bias": "neutral_or_directional_by_strike_selection",
            "option_structure": "defined_risk_same_strike_different_expiration_spread",
            "required_legs": 2,
            "required_option_legs": [
                {"role": "short_near_term_option", "relative_expiration": "near_term", "side": "sell_to_open"},
                {"role": "long_far_term_option", "relative_expiration": "far_term", "side": "buy_to_open"},
            ],
            "net_price_type": "debit",
            "order_intent": "open_calendar_spread",
            "entry_order_type": "multi_leg_net_debit_limit_order",
            "order_payload_shape": "two_leg_calendar_combo_order",
            "max_risk_defined": True,
            "expiration_risk_rule": "close_or_review_before_near_term_short_option_expiration",
            "manual_review_triggers": ["near_term_short_option_expiration", "assignment_risk", "wide_spread", "missing_quote"],
        },
        "diagonal_spread": {
            "strategy_family": "diagonal_spread",
            "directional_bias": "directional_by_strike_and_delta_selection",
            "option_structure": "defined_risk_different_strike_different_expiration_spread",
            "required_legs": 2,
            "required_option_legs": [
                {"role": "short_near_term_option", "relative_expiration": "near_term", "side": "sell_to_open"},
                {"role": "long_far_term_option", "relative_expiration": "far_term", "side": "buy_to_open"},
            ],
            "net_price_type": "debit_or_credit_policy_defined",
            "order_intent": "open_diagonal_spread",
            "entry_order_type": "multi_leg_net_limit_order",
            "order_payload_shape": "two_leg_diagonal_combo_order",
            "max_risk_defined": True,
            "expiration_risk_rule": "close_or_review_before_near_term_short_option_expiration",
            "manual_review_triggers": ["near_term_short_option_expiration", "assignment_risk", "wide_spread", "missing_quote"],
        },
        "iron_condor": {
            "strategy_family": "iron_condor",
            "directional_bias": "neutral_range_bound",
            "option_structure": "defined_risk_four_leg_credit_spread_combination",
            "required_legs": 4,
            "required_option_legs": [
                {"role": "short_put", "side": "sell_to_open"},
                {"role": "long_put", "side": "buy_to_open"},
                {"role": "short_call", "side": "sell_to_open"},
                {"role": "long_call", "side": "buy_to_open"},
            ],
            "net_price_type": "credit",
            "order_intent": "open_iron_condor",
            "entry_order_type": "multi_leg_net_credit_limit_order",
            "order_payload_shape": "four_leg_iron_condor_combo_order",
            "max_risk_defined": True,
            "expiration_risk_rule": "close_before_expiration_or_before_short_leg_assignment_risk_window",
            "manual_review_triggers": ["short_call_assignment_risk", "short_put_assignment_risk", "wide_spread", "missing_quote", "near_expiration"],
        },
        "iron_butterfly": {
            "strategy_family": "iron_butterfly",
            "directional_bias": "neutral_pin_or_range_bound",
            "option_structure": "defined_risk_three_or_four_leg_credit_structure",
            "required_legs": 3,
            "required_option_legs": [
                {"role": "long_wing_option", "side": "buy_to_open"},
                {"role": "short_body_options", "side": "sell_to_open"},
                {"role": "long_wing_option", "side": "buy_to_open"},
            ],
            "net_price_type": "credit",
            "order_intent": "open_iron_butterfly",
            "entry_order_type": "multi_leg_net_credit_limit_order",
            "order_payload_shape": "three_or_four_leg_iron_butterfly_combo_order",
            "max_risk_defined": True,
            "expiration_risk_rule": "close_before_expiration_or_before_short_leg_assignment_risk_window",
            "manual_review_triggers": ["short_leg_assignment_risk", "wide_spread", "missing_quote", "near_expiration"],
        },
        "long_call": {
            "strategy_family": "single_leg_long_option",
            "directional_bias": "bullish",
            "option_structure": "defined_risk_long_call",
            "required_legs": 1,
            "required_option_legs": [{"role": "long_call", "side": "buy_to_open"}],
            "net_price_type": "debit",
            "order_intent": "open_long_call",
            "entry_order_type": "single_leg_debit_limit_order",
            "order_payload_shape": "single_leg_option_order",
            "max_risk_defined": True,
            "expiration_risk_rule": "close_or_allow_expiration_only_under_explicit_policy",
            "manual_review_triggers": ["wide_spread", "missing_quote", "near_expiration"],
        },
        "long_put": {
            "strategy_family": "single_leg_long_option",
            "directional_bias": "bearish",
            "option_structure": "defined_risk_long_put",
            "required_legs": 1,
            "required_option_legs": [{"role": "long_put", "side": "buy_to_open"}],
            "net_price_type": "debit",
            "order_intent": "open_long_put",
            "entry_order_type": "single_leg_debit_limit_order",
            "order_payload_shape": "single_leg_option_order",
            "max_risk_defined": True,
            "expiration_risk_rule": "close_or_allow_expiration_only_under_explicit_policy",
            "manual_review_triggers": ["wide_spread", "missing_quote", "near_expiration"],
        },
    }
    return templates.get(strategy)


def _required_capabilities_for_rule(rule: Mapping[str, Any]) -> List[str]:
    capabilities = list(REQUIRED_BROKER_CAPABILITIES)
    if int(rule.get("required_legs") or 0) == 1:
        capabilities = [c for c in capabilities if c not in {"multi_leg_option_orders", "combo_close_orders"}]
        capabilities.append("single_leg_option_orders")
        capabilities.append("single_leg_close_orders")
    if any("short" in str(leg.get("role", "")) for leg in rule.get("required_option_legs", [])):
        capabilities.extend(["short_option_permissions", "assignment_risk_monitoring"])
    return sorted(set(capabilities))


def _build_broker_capability_matrix(strategy_rules: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    required_by: Dict[str, Set[str]] = defaultdict(set)
    for rule in strategy_rules:
        if rule.get("readiness_state") == "unmapped":
            continue
        strategy = str(rule.get("strategy"))
        for capability in rule.get("broker_translation", {}).get("required_capabilities", []):
            required_by[str(capability)].add(strategy)

    rows: List[Dict[str, Any]] = []
    for capability in sorted(required_by):
        strategy_names = sorted(required_by[capability])
        readiness_state = "paper_ready"
        proof_required = "paper_trading_proof"
        if capability in {"short_option_permissions", "assignment_risk_monitoring", "buying_power_or_margin_preview"}:
            readiness_state = "manual_review_required"
            proof_required = "broker_account_permission_and_paper_order_test"
        rows.append(
            {
                "capability": capability,
                "required_by_strategy_count": len(strategy_names),
                "required_by_strategies": strategy_names,
                "readiness_state": readiness_state,
                "proof_required": proof_required,
                "notes": "Capability must be verified against the actual paper/live brokerage integration before live deployment.",
            }
        )
    return rows


def _build_manual_review_rules(strategy_rules: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    rows = [dict(row) for row in GLOBAL_MANUAL_REVIEW_RULES]
    short_leg_strategies: List[str] = []
    expiration_sensitive_strategies: List[str] = []
    for rule in strategy_rules:
        if rule.get("readiness_state") == "unmapped":
            continue
        strategy = str(rule.get("strategy"))
        legs = rule.get("required_option_legs", [])
        if any("short" in str(leg.get("role", "")) for leg in legs if isinstance(leg, Mapping)):
            short_leg_strategies.append(strategy)
        expiration_sensitive_strategies.append(strategy)

    if short_leg_strategies:
        rows.append(
            {
                "rule_id": "short_option_assignment_manual_review",
                "trigger": "strategy contains one or more short option legs and assignment/exercise risk window is reached",
                "required_action": "Close, reduce, or manually approve holding the position; do not auto-roll without a separate rule.",
                "applies_to": sorted(short_leg_strategies),
                "severity": "warning",
            }
        )
    if expiration_sensitive_strategies:
        rows.append(
            {
                "rule_id": "expiration_window_manual_review",
                "trigger": "position is inside configured expiration-risk window and is still open",
                "required_action": "Close using the mapped close order or explicitly approve holding through expiration behavior.",
                "applies_to": sorted(expiration_sensitive_strategies),
                "severity": "warning",
            }
        )
    return rows


def _build_readiness_bridge(
    strategy_rules: Sequence[Mapping[str, Any]],
    unmapped_strategies: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    mapped = [row for row in strategy_rules if row.get("readiness_state") != "unmapped"]
    mapped_names = sorted(str(row.get("strategy")) for row in mapped)
    gap_resolution = {}
    for row in mapped:
        strategy = str(row.get("strategy"))
        gap_resolution[strategy] = {
            "resolved_gaps": ["unmapped_exit_logic"],
            "close_rules_available": row.get("close_rule_available") is True,
            "defense_rules_available": row.get("defense_rule_available") is True,
            "paper_trade_supported": row.get("paper_trade_supported") is True,
            "live_trade_supported": row.get("live_trade_supported") is True,
            "readiness_state": row.get("readiness_state"),
        }
    return {
        "execution_rulebook_available": True,
        "close_rules_available": bool(mapped) and all(row.get("close_rule_available") is True for row in mapped),
        "defense_rules_available": bool(mapped) and all(row.get("defense_rule_available") is True for row in mapped),
        "paper_trade_supported": bool(mapped) and all(row.get("paper_trade_supported") is True for row in mapped),
        "live_trade_supported": bool(mapped) and all(row.get("live_trade_supported") is True for row in mapped),
        "mapped_strategies": mapped_names,
        "unmapped_strategies": [str(row.get("strategy")) for row in unmapped_strategies],
        "readiness_review_execution_gap_resolution": gap_resolution,
        "recommended_readiness_review_use": "Use this bridge to treat mapped strategies as having close/defense rules for paper-trading readiness; keep live deployment blocked until broker-specific paper order tests pass.",
    }


def _normalize_strategy(strategy: str) -> str:
    return str(strategy).strip().lower().replace("-", "_").replace(" ", "_")


def _iter_records_from_path(path: Path) -> Iterator[Any]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
        return

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return
    if isinstance(data, list):
        yield from data
    elif isinstance(data, Mapping):
        yielded = False
        for value in data.values():
            if isinstance(value, list):
                for item in value:
                    yield item
                yielded = True
        if not yielded:
            yield data


def _flatten_mapping(mapping: Mapping[str, Any], prefix: str = "") -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    for key, value in mapping.items():
        field = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            flat.update(_flatten_mapping(value, field))
        elif isinstance(value, list):
            flat[field] = f"list[{len(value)}]"
            for idx, item in enumerate(value[:5]):
                if isinstance(item, Mapping):
                    flat.update(_flatten_mapping(item, f"{field}[{idx}]"))
        else:
            flat[field] = value
    return flat


def _output_paths(output_dir: Path) -> Dict[str, str]:
    return {
        "review_path": str(output_dir / f"{OUTPUT_BASENAME}.json"),
        "summary_path": str(output_dir / f"{OUTPUT_BASENAME}_summary.json"),
        "strategy_rules_path": str(output_dir / f"{OUTPUT_BASENAME}_strategy_rules.jsonl"),
        "broker_capability_matrix_path": str(output_dir / f"{OUTPUT_BASENAME}_broker_capability_matrix.jsonl"),
        "manual_review_rules_path": str(output_dir / f"{OUTPUT_BASENAME}_manual_review_rules.jsonl"),
        "readiness_bridge_path": str(output_dir / f"{OUTPUT_BASENAME}_readiness_bridge.json"),
        "blockers_path": str(output_dir / f"{OUTPUT_BASENAME}_blockers.jsonl"),
        "unmapped_strategies_path": str(output_dir / f"{OUTPUT_BASENAME}_unmapped_strategies.jsonl"),
    }


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")
