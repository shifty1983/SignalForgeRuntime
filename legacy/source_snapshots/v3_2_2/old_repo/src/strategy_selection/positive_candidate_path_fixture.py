from __future__ import annotations

from collections import Counter
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


POSITIVE_CANDIDATE_PATH_FIXTURE_SCHEMA_VERSION = (
    "signalforge_positive_candidate_path_fixture.v1"
)

COVERED_CAPABILITIES = [
    "positive_candidate_path_fixture",
    "positive_expected_value_fixture",
    "candidate_review_branch_fixture",
    "final_review_branch_fixture",
    "contract_readiness_branch_fixture",
]

DEFAULT_SYMBOLS = ["SPY", "QQQ"]


def build_signalforge_positive_candidate_path_fixture(
    *,
    symbols: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Build a deterministic Strategy Family Eligibility fixture that promotes candidates.

    This fixture is intentionally separate from the real regime/asset/options path.
    Its purpose is to prove the downstream positive branch:

    strategy-family eligibility -> EV -> candidate review -> final review -> contract readiness

    The fixture does not contain market data, choose contracts, call a broker, submit
    orders, model fills, model slippage, or authorize any automatic strategy change.
    """

    normalized_symbols = _normalize_symbols(DEFAULT_SYMBOLS if symbols is None else symbols)
    blocked_reasons = [] if normalized_symbols else ["no symbols supplied"]
    items = [
        _fixture_item(symbol=symbol, index=index)
        for index, symbol in enumerate(normalized_symbols)
    ]
    summary = _summary(items)
    status = "ready" if items else "blocked"

    return {
        "artifact_type": "signalforge_strategy_family_eligibility",
        "fixture_artifact_type": "signalforge_positive_candidate_path_fixture",
        "schema_version": POSITIVE_CANDIDATE_PATH_FIXTURE_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "positive_candidate_path_fixture",
        "adapter_type": "positive_candidate_path_fixture_builder",
        "review_scope": "positive_candidate_branch_fixture_not_trade_selection_or_execution",
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": [
            "strategy_family_eligibility",
            "expected_value_scoring",
            "candidate_selection_review",
            "candidate_final_review_export",
            "contract_selection_readiness",
        ],
        "fixture_policy": {
            "fixture_type": "deterministic_branch_fixture",
            "market_data_source": "none",
            "production_decision_use": "pipeline_branch_testing_only",
            "intended_ev_state": "positive_or_marginal_expected_value_for_sample_symbols",
            "intended_candidate_review_state": "candidate_review_queue_populated",
            "intended_final_review_state": "final_review_queue_populated",
            "intended_contract_readiness_state": "contract_readiness_queue_populated_when_option_rows_are_supplied",
        },
        "fixture_parameters": {
            "symbols": normalized_symbols,
            "symbol_count": len(normalized_symbols),
            "ready_fixture_symbol_count": len(items),
        },
        "strategy_family_eligibility_items": items,
        "eligibility_items": items,
        "positive_candidate_path_fixture_summary": summary,
        "strategy_family_eligibility_summary": summary,
        "next_build_recommendations": [
            {
                "capability": "expected_value_scoring_positive_branch",
                "priority": "high",
                "recommendation": "Run Expected Value Scoring on this fixture, then run candidate review, final review export, and contract readiness with production-ready option rows.",
            }
        ],
        "blocked_reasons": blocked_reasons,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _fixture_item(*, symbol: str, index: int) -> dict[str, Any]:
    # First symbol is a clean positive EV candidate. Later symbols are constrained
    # but still expected to remain marginal/positive, which tests both review queues.
    constrained = index > 0
    handoff = (
        "constrained_for_expected_value_scoring"
        if constrained
        else "ready_for_expected_value_scoring"
    )
    risk_flags = ["controlled_gamma_review"] if constrained else []
    constraint_flags = ["defined_risk_only"] if constrained else []
    risk_review_reasons = ["fixture_constrained_candidate_review"] if constrained else []

    return {
        "artifact_type": "strategy_family_eligibility_item",
        "symbol": symbol,
        "coverage_status": "constrained" if constrained else "ready",
        "strategy_family_eligibility_handoff": handoff,
        "expected_value_handoff_status": handoff,
        "data_review_required": False,
        "hard_blocked": False,
        "manual_review_required": True,
        "ev_scoreable": True,
        "risk_adjustment_required": constrained,
        "macro_regime": "fixture_supportive_regime",
        "weekly_planning_label": "fixture_positive_candidate_review",
        "asset_behavior_state": "fixture_uptrend_quality_confirmed",
        "options_behavior_state": "defined_risk_short_premium_candidate",
        "premium_bias": "short_premium_bias",
        "strategy_environment_bias": "defined_risk_short_premium_environment",
        "favored_strategy_families": ["defined_risk_short_premium"],
        "allowed_strategy_families": [
            "defined_risk_short_premium",
            "credit_spread",
            "defined_risk_only",
        ],
        "discouraged_strategy_families": [],
        "blocked_strategy_families": [
            "naked_short_premium",
            "short_premium_without_hedge",
        ],
        "risk_flags": risk_flags,
        "constraint_flags": constraint_flags,
        "data_review_reasons": [],
        "hard_block_reasons": [],
        "risk_review_reasons": risk_review_reasons,
        "needs_review_reasons": sorted(set(risk_flags + constraint_flags + risk_review_reasons)),
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    coverage_counts = Counter(item.get("coverage_status") for item in items)
    handoff_counts = Counter(item.get("expected_value_handoff_status") for item in items)
    favored_counts = Counter(
        family for item in items for family in item.get("favored_strategy_families", [])
    )
    allowed_counts = Counter(
        family for item in items for family in item.get("allowed_strategy_families", [])
    )
    blocked_counts = Counter(
        family for item in items for family in item.get("blocked_strategy_families", [])
    )
    risk_counts = Counter(flag for item in items for flag in item.get("risk_flags", []))
    constraint_counts = Counter(
        flag for item in items for flag in item.get("constraint_flags", [])
    )

    return {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "symbol_count": len(items),
        "ready_symbol_count": coverage_counts.get("ready", 0),
        "constrained_symbol_count": coverage_counts.get("constrained", 0),
        "ev_eligible_symbol_count": len(items),
        "risk_adjusted_ev_symbol_count": coverage_counts.get("constrained", 0),
        "data_review_symbol_count": 0,
        "blocked_symbol_count": 0,
        "needs_review_symbol_count": 0,
        "manual_review_symbol_count": len(items),
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "handoff_counts": dict(sorted(handoff_counts.items())),
        "favored_strategy_family_counts": dict(sorted(favored_counts.items())),
        "allowed_strategy_family_counts": dict(sorted(allowed_counts.items())),
        "blocked_strategy_family_counts": dict(sorted(blocked_counts.items())),
        "risk_flag_counts": dict(sorted(risk_counts.items())),
        "constraint_flag_counts": dict(sorted(constraint_counts.items())),
        "expected_positive_branch_counts": {
            "expected_ev_scoreable_symbols": len(items),
            "expected_candidate_review_symbols": len(items),
            "expected_final_review_symbols": len(items),
        },
    }


def _normalize_symbols(symbols: list[str] | tuple[str, ...]) -> list[str]:
    normalized: list[str] = []
    for symbol in symbols:
        text = str(symbol).strip().upper()
        if text and text not in normalized:
            normalized.append(text)
    return normalized
