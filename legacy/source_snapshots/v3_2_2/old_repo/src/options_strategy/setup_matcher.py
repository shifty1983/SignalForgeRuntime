from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from src.signalforge.engines.strategy_selection.historical_replay_matrix_metadata_stamp import (
    matrix_metadata_coverage,
    stamp_matrix_metadata,
)

from src.options_strategy.catalog import (
    OptionStrategyDefinition,
    build_option_strategy_catalog,
    validate_defined_risk_catalog,
)


@dataclass(frozen=True)
class OptionStrategySetupInput:
    """
    Input context for mapping setup/behavior into defined-risk option strategies.

    This matcher only recommends strategy families. It does not choose contracts,
    strikes, expirations, size, orders, fills, or maintenance actions.
    """

    symbol: str
    market_regime: str
    asset_behavior: str
    option_behavior: Mapping[str, Any]
    setup_family: str | None = None
    has_underlying_position: bool = False
    max_candidates: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OptionStrategyCandidateMatch:
    strategy: str
    display_name: str
    direction: str
    setup_families: tuple[str, ...]
    risk_profile: str
    score: float
    matched_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    best_setups: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "display_name": self.display_name,
            "direction": self.direction,
            "setup_families": list(self.setup_families),
            "risk_profile": self.risk_profile,
            "score": self.score,
            "matched_reasons": list(self.matched_reasons),
            "warnings": list(self.warnings),
            "best_setups": list(self.best_setups),
        }


@dataclass(frozen=True)
class RejectedOptionStrategy:
    strategy: str
    display_name: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "display_name": self.display_name,
            "reasons": list(self.reasons),
        }


def match_defined_risk_option_strategies(
    setup: OptionStrategySetupInput,
    *,
    catalog: tuple[OptionStrategyDefinition, ...] | None = None,
    minimum_score: float = 2.0,
) -> dict[str, Any]:
    """
    Match regime + asset behavior + option behavior into strategy candidates.

    Output statuses:
    - ready: at least one strategy family matched the setup
    - blocked: the input shape or option behavior blocks strategy generation
    - needs_review: no strong strategy family matched, but input is usable
    """
    active_catalog = catalog or build_option_strategy_catalog()
    validate_defined_risk_catalog(active_catalog)

    input_errors = _validate_setup_input(setup)
    if input_errors:
        return _blocked_report(setup=setup, blocking_reasons=input_errors)

    global_blockers = _global_blockers(setup.option_behavior)
    if global_blockers:
        return _blocked_report(setup=setup, blocking_reasons=global_blockers)

    matches: list[OptionStrategyCandidateMatch] = []
    rejected: list[RejectedOptionStrategy] = []

    for definition in active_catalog:
        evaluation = _evaluate_definition(setup=setup, definition=definition)

        if evaluation["blocked_reasons"]:
            rejected.append(
                RejectedOptionStrategy(
                    strategy=definition.strategy,
                    display_name=definition.display_name,
                    reasons=tuple(evaluation["blocked_reasons"]),
                )
            )
            continue

        if evaluation["score"] >= minimum_score:
            matches.append(
                OptionStrategyCandidateMatch(
                    strategy=definition.strategy,
                    display_name=definition.display_name,
                    direction=definition.direction,
                    setup_families=definition.setup_families,
                    risk_profile=definition.risk_profile,
                    score=float(evaluation["score"]),
                    matched_reasons=tuple(evaluation["matched_reasons"]),
                    warnings=tuple(evaluation["warnings"]),
                    best_setups=definition.best_setups,
                )
            )
        else:
            rejected.append(
                RejectedOptionStrategy(
                    strategy=definition.strategy,
                    display_name=definition.display_name,
                    reasons=tuple(evaluation["rejection_reasons"]),
                )
            )

    ranked_matches = sorted(
        matches,
        key=lambda candidate: (-candidate.score, candidate.strategy),
    )

    if setup.max_candidates is not None:
        ranked_matches = ranked_matches[: setup.max_candidates]

    candidate_rows = [
        _stamp_setup_matcher_matrix_metadata(setup=setup, candidate=candidate.to_dict())
        for candidate in ranked_matches
    ]
    matrix_metadata_summary = matrix_metadata_coverage(candidate_rows)

    status = "ready" if ranked_matches else "needs_review"

    return {
        "status": status,
        "symbol": setup.symbol,
        "market_regime": setup.market_regime,
        "asset_behavior": setup.asset_behavior,
        "setup_family": setup.setup_family,
        "candidate_count": len(ranked_matches),
        "rejected_count": len(rejected),
        "candidates": candidate_rows,
        "rejected_strategies": [item.to_dict() for item in rejected],
        "warnings": _dedupe_preserve_order(
            warning
            for candidate in ranked_matches
            for warning in candidate.warnings
        ),
        "blocking_reasons": [],
        "metadata": dict(setup.metadata),
        "matrix_metadata_envelope_key": "matrix_metadata",
        "matrix_metadata_setup_matcher_summary": matrix_metadata_summary,
        "exact_matrix_cell_ready_record_count": matrix_metadata_summary[
            "exact_matrix_cell_ready_record_count"
        ],
        "matrix_metadata_needs_review_record_count": matrix_metadata_summary[
            "needs_review_record_count"
        ],
        "ready_to_build_exact_matrix_edge_summary": matrix_metadata_summary[
            "ready_to_build_exact_matrix_edge_summary"
        ],
        "recommended_next_step": (
            "build_exact_matrix_edge_summary"
            if matrix_metadata_summary["ready_to_build_exact_matrix_edge_summary"]
            else "continue_matrix_metadata_source_dimension_stamping"
        ),
    }


def _validate_setup_input(setup: OptionStrategySetupInput) -> list[str]:
    errors: list[str] = []

    if not setup.symbol or not setup.symbol.strip():
        errors.append("symbol is required")

    if not setup.market_regime or not setup.market_regime.strip():
        errors.append("market_regime is required")

    if not setup.asset_behavior or not setup.asset_behavior.strip():
        errors.append("asset_behavior is required")

    if not isinstance(setup.option_behavior, Mapping):
        errors.append("option_behavior must be a mapping")

    if setup.max_candidates is not None and setup.max_candidates < 1:
        errors.append("max_candidates must be at least 1 when provided")

    return errors


def _global_blockers(option_behavior: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []

    liquidity_behavior = option_behavior.get("liquidity_behavior")
    if liquidity_behavior == "untradable_liquidity":
        blockers.append("option chain has untradable liquidity")

    greek_behavior = option_behavior.get("greek_behavior")
    if greek_behavior == "high_greek_risk":
        blockers.append("option chain has high greek risk")

    return blockers


def _evaluate_definition(
    *,
    setup: OptionStrategySetupInput,
    definition: OptionStrategyDefinition,
) -> dict[str, Any]:
    score = 0.0
    matched_reasons: list[str] = []
    rejection_reasons: list[str] = []
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    required_context_errors = _required_context_errors(setup, definition)
    if required_context_errors:
        blocked_reasons.extend(required_context_errors)
        return {
            "score": score,
            "matched_reasons": matched_reasons,
            "rejection_reasons": rejection_reasons,
            "blocked_reasons": blocked_reasons,
            "warnings": warnings,
        }

    if _has_blocked_behavior(setup=setup, definition=definition):
        blocked_reasons.append("setup contains behavior explicitly blocked for strategy")
        return {
            "score": score,
            "matched_reasons": matched_reasons,
            "rejection_reasons": rejection_reasons,
            "blocked_reasons": blocked_reasons,
            "warnings": warnings,
        }

    if setup.market_regime in definition.preferred_regimes:
        score += 1.0
        matched_reasons.append(f"market regime matched: {setup.market_regime}")
    else:
        rejection_reasons.append(f"market regime not preferred: {setup.market_regime}")

    if setup.asset_behavior in definition.preferred_asset_behaviors:
        score += 2.0
        matched_reasons.append(f"asset behavior matched: {setup.asset_behavior}")
    else:
        rejection_reasons.append(f"asset behavior not preferred: {setup.asset_behavior}")

    if setup.setup_family is not None:
        if setup.setup_family in definition.setup_families:
            score += 1.0
            matched_reasons.append(f"setup family matched: {setup.setup_family}")
        else:
            rejection_reasons.append(f"setup family not preferred: {setup.setup_family}")

    behavior_score, behavior_matches, behavior_rejections, behavior_warnings = (
        _score_option_behavior_match(
            option_behavior=setup.option_behavior,
            preferred_option_behaviors=definition.preferred_option_behaviors,
        )
    )
    score += behavior_score
    matched_reasons.extend(behavior_matches)
    rejection_reasons.extend(behavior_rejections)
    warnings.extend(behavior_warnings)

    if not matched_reasons:
        rejection_reasons.append("no setup inputs matched strategy preferences")

    return {
        "score": score,
        "matched_reasons": matched_reasons,
        "rejection_reasons": rejection_reasons,
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
    }


def _required_context_errors(
    setup: OptionStrategySetupInput,
    definition: OptionStrategyDefinition,
) -> list[str]:
    errors: list[str] = []

    if (
        "has_underlying_position" in definition.required_context
        and not setup.has_underlying_position
    ):
        errors.append("requires existing underlying position")

    return errors


def _has_blocked_behavior(
    *,
    setup: OptionStrategySetupInput,
    definition: OptionStrategyDefinition,
) -> bool:
    option_behavior_values = {
        str(value)
        for value in setup.option_behavior.values()
        if value is not None
    }

    input_values = option_behavior_values | {
        setup.market_regime,
        setup.asset_behavior,
    }

    return any(blocked_value in input_values for blocked_value in definition.blocked_when)


def _score_option_behavior_match(
    *,
    option_behavior: Mapping[str, Any],
    preferred_option_behaviors: Mapping[str, Sequence[str]],
) -> tuple[float, list[str], list[str], list[str]]:
    score = 0.0
    matched_reasons: list[str] = []
    rejection_reasons: list[str] = []
    warnings: list[str] = []

    for key, preferred_values in preferred_option_behaviors.items():
        actual_value = option_behavior.get(key)

        if actual_value is None:
            warnings.append(f"missing option behavior input: {key}")
            continue

        if actual_value in preferred_values:
            score += 1.0
            matched_reasons.append(f"option behavior matched: {key}={actual_value}")
        else:
            rejection_reasons.append(
                f"option behavior not preferred: {key}={actual_value}"
            )

    return score, matched_reasons, rejection_reasons, warnings


def _blocked_report(
    *,
    setup: OptionStrategySetupInput,
    blocking_reasons: Sequence[str],
) -> dict[str, Any]:
    matrix_metadata_summary = matrix_metadata_coverage([])
    return {
        "status": "blocked",
        "symbol": setup.symbol,
        "market_regime": setup.market_regime,
        "asset_behavior": setup.asset_behavior,
        "setup_family": setup.setup_family,
        "candidate_count": 0,
        "rejected_count": 0,
        "candidates": [],
        "rejected_strategies": [],
        "warnings": [],
        "blocking_reasons": list(blocking_reasons),
        "metadata": dict(setup.metadata),
        "matrix_metadata_envelope_key": "matrix_metadata",
        "matrix_metadata_setup_matcher_summary": matrix_metadata_summary,
        "exact_matrix_cell_ready_record_count": 0,
        "matrix_metadata_needs_review_record_count": 0,
        "ready_to_build_exact_matrix_edge_summary": False,
        "recommended_next_step": "resolve_setup_matcher_blockers",
    }


def _stamp_setup_matcher_matrix_metadata(
    *,
    setup: OptionStrategySetupInput,
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    existing_metadata = setup.metadata.get("matrix_metadata") if isinstance(setup.metadata, Mapping) else None
    metadata: dict[str, Any] = dict(existing_metadata) if isinstance(existing_metadata, Mapping) else {}

    for key in ("horizon_days", "horizon", "target_horizon_days", "asset_class"):
        if key in setup.metadata and setup.metadata.get(key) is not None:
            metadata[key] = setup.metadata.get(key)

    metadata.update(
        {
            "symbol": setup.symbol,
            "regime_state": setup.market_regime,
            "asset_behavior_state": setup.asset_behavior,
            "strategy_id": candidate.get("strategy"),
            "strategy_family": candidate.get("strategy"),
            "strategy_direction": candidate.get("direction"),
            "risk_structure": candidate.get("risk_profile"),
        }
    )

    option_behavior_state = _explicit_option_behavior_state(setup.option_behavior)
    if option_behavior_state is not None:
        metadata["option_behavior_state"] = option_behavior_state

    return stamp_matrix_metadata(
        candidate,
        metadata,
        source_refs={
            "symbol": "option_strategy_setup_input.symbol",
            "regime_state": "option_strategy_setup_input.market_regime",
            "asset_behavior_state": "option_strategy_setup_input.asset_behavior",
            "option_behavior_state": "option_strategy_setup_input.option_behavior.explicit_state",
            "strategy_id": "option_strategy_definition.strategy",
            "strategy_family": "option_strategy_definition.strategy",
            "horizon_days": "option_strategy_setup_input.metadata.explicit_horizon",
        },
    )


def _explicit_option_behavior_state(option_behavior: Mapping[str, Any]) -> Any:
    if not isinstance(option_behavior, Mapping):
        return None
    for key in (
        "option_behavior_state",
        "options_behavior_state",
        "option_behavior_label",
        "option_state",
    ):
        value = option_behavior.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _dedupe_preserve_order(values: Sequence[str] | Any) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []

    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)

    return output

