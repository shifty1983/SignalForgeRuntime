from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.options_strategy.candidate_builder import (
    build_option_strategy_candidates_from_handoff,
)
from src.weekly_planning.option_trade_plan import EXCLUDED_ACTIONS


SOURCE_SCHEMA_VERSION = "weekly_option_trade_plan_source.v1"
ARTIFACT_TYPE = "weekly_option_trade_plan_source"

VALID_SOURCE_STATUSES = {
    "ready",
    "needs_review",
    "blocked",
}


def build_weekly_option_trade_plan_source_from_handoffs(
    option_behavior_strategy_handoffs: Sequence[Mapping[str, Any]] | None,
    *,
    plan_date: str,
    market_regime: str | Mapping[str, Any],
    setup_family: str | Mapping[str, Any] | None = None,
    has_underlying_positions: Sequence[str] | Mapping[str, Any] | None = None,
    portfolio_snapshot: Mapping[str, Any] | None = None,
    max_new_trades: int | None = None,
    max_candidates_per_symbol: int | None = 3,
    minimum_score: float = 2.0,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build a weekly option trade plan source from option-behavior handoffs.

    This composes the existing option behavior -> defined-risk strategy candidate
    builder into the weekend plan input shape. It does not build contracts,
    choose strikes/expirations, calculate EV, optimize portfolio sizing, call
    brokers, submit orders, model fills, or create maintenance/defense actions.
    """

    validation_errors = _validate_source_inputs(
        option_behavior_strategy_handoffs=option_behavior_strategy_handoffs,
        plan_date=plan_date,
        portfolio_snapshot=portfolio_snapshot,
        max_new_trades=max_new_trades,
        max_candidates_per_symbol=max_candidates_per_symbol,
    )
    if validation_errors:
        return _blocked_source(
            plan_date=plan_date,
            blocked_reasons=validation_errors,
            metadata=metadata,
        )

    assert option_behavior_strategy_handoffs is not None

    candidate_results: list[dict[str, Any]] = []
    warnings: list[str] = []
    blocked_reasons: list[str] = []

    for source_index, handoff in enumerate(
        _rank_handoffs(option_behavior_strategy_handoffs)
    ):
        symbol = _string_or_none(handoff.get("symbol"))
        resolved_market_regime = _resolve_string_context(
            market_regime,
            symbol=symbol,
            default_key="default",
        )
        resolved_setup_family = _resolve_optional_string_context(
            setup_family,
            symbol=symbol,
            default_key="default",
        )

        candidate_result = build_option_strategy_candidates_from_handoff(
            handoff,
            market_regime=resolved_market_regime or "",
            setup_family=resolved_setup_family,
            has_underlying_position=_has_underlying_position(
                has_underlying_positions,
                symbol=symbol,
            ),
            max_candidates=max_candidates_per_symbol,
            minimum_score=minimum_score,
            metadata={
                "source_builder_artifact_type": ARTIFACT_TYPE,
                "source_index": source_index,
                **dict(metadata or {}),
            },
        )
        candidate_results.append(candidate_result)
        warnings.extend(_strings(candidate_result.get("warnings")))
        blocked_reasons.extend(_strings(candidate_result.get("blocked_reasons")))

    status = _source_status(candidate_results=candidate_results, warnings=warnings)

    if not candidate_results:
        status = "blocked"
        blocked_reasons.append("no option behavior strategy handoffs were provided")

    return {
        "schema_version": SOURCE_SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "status": status,
        "is_ready": status == "ready",
        "plan_date": plan_date,
        "portfolio_snapshot": dict(portfolio_snapshot or {}),
        "max_new_trades": max_new_trades,
        "max_candidates_per_symbol": max_candidates_per_symbol,
        "option_strategy_candidate_results": candidate_results,
        "candidate_result_count": len(candidate_results),
        "ready_candidate_result_count": _count_status(candidate_results, "ready"),
        "needs_review_candidate_result_count": _count_status(
            candidate_results,
            "needs_review",
        ),
        "blocked_candidate_result_count": _count_status(candidate_results, "blocked"),
        "warnings": _dedupe_strings(warnings),
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "source_handoff_summaries": [
            _handoff_summary(handoff)
            for handoff in _rank_handoffs(option_behavior_strategy_handoffs)
        ],
        "excluded": EXCLUDED_ACTIONS,
        "metadata": dict(metadata or {}),
    }


def _validate_source_inputs(
    *,
    option_behavior_strategy_handoffs: Sequence[Mapping[str, Any]] | None,
    plan_date: str,
    portfolio_snapshot: Mapping[str, Any] | None,
    max_new_trades: int | None,
    max_candidates_per_symbol: int | None,
) -> list[str]:
    errors: list[str] = []

    if not isinstance(plan_date, str) or not plan_date.strip():
        errors.append("plan_date is required")

    if not isinstance(option_behavior_strategy_handoffs, Sequence) or isinstance(
        option_behavior_strategy_handoffs,
        (str, bytes),
    ):
        errors.append("option_behavior_strategy_handoffs must be a sequence")

    if portfolio_snapshot is not None and not isinstance(portfolio_snapshot, Mapping):
        errors.append("portfolio_snapshot must be a mapping when provided")

    if max_new_trades is not None and max_new_trades < 1:
        errors.append("max_new_trades must be at least 1 when provided")

    if max_candidates_per_symbol is not None and max_candidates_per_symbol < 1:
        errors.append("max_candidates_per_symbol must be at least 1 when provided")

    return errors


def _blocked_source(
    *,
    plan_date: str,
    blocked_reasons: Sequence[str],
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SOURCE_SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "status": "blocked",
        "is_ready": False,
        "plan_date": plan_date,
        "portfolio_snapshot": {},
        "max_new_trades": None,
        "max_candidates_per_symbol": None,
        "option_strategy_candidate_results": [],
        "candidate_result_count": 0,
        "ready_candidate_result_count": 0,
        "needs_review_candidate_result_count": 0,
        "blocked_candidate_result_count": 0,
        "warnings": [],
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "source_handoff_summaries": [],
        "excluded": EXCLUDED_ACTIONS,
        "metadata": dict(metadata or {}),
    }


def _rank_handoffs(
    handoffs: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    return sorted(
        [handoff for handoff in handoffs if isinstance(handoff, Mapping)],
        key=lambda handoff: (
            _string_or_none(handoff.get("symbol")) or "",
            _string_or_none(handoff.get("status")) or "",
            _string_or_none(handoff.get("artifact_type")) or "",
        ),
    )


def _source_status(
    *,
    candidate_results: Sequence[Mapping[str, Any]],
    warnings: Sequence[str],
) -> str:
    if not candidate_results:
        return "blocked"

    statuses = [_string_or_none(result.get("status")) for result in candidate_results]
    if any(status not in VALID_SOURCE_STATUSES for status in statuses):
        return "blocked"

    if any(status == "ready" for status in statuses):
        if warnings or any(status != "ready" for status in statuses):
            return "needs_review"
        return "ready"

    if any(status == "needs_review" for status in statuses):
        return "needs_review"

    return "blocked"


def _resolve_string_context(
    value: str | Mapping[str, Any],
    *,
    symbol: str | None,
    default_key: str,
) -> str | None:
    if isinstance(value, str):
        return _string_or_none(value)

    if isinstance(value, Mapping):
        if symbol and symbol in value:
            return _string_or_none(value.get(symbol))
        return _string_or_none(value.get(default_key))

    return None


def _resolve_optional_string_context(
    value: str | Mapping[str, Any] | None,
    *,
    symbol: str | None,
    default_key: str,
) -> str | None:
    if value is None:
        return None
    return _resolve_string_context(value, symbol=symbol, default_key=default_key)


def _has_underlying_position(
    has_underlying_positions: Sequence[str] | Mapping[str, Any] | None,
    *,
    symbol: str | None,
) -> bool:
    if not symbol:
        return False

    if isinstance(has_underlying_positions, Mapping):
        return bool(has_underlying_positions.get(symbol, False))

    if isinstance(has_underlying_positions, Sequence) and not isinstance(
        has_underlying_positions,
        (str, bytes),
    ):
        return symbol in set(
            item for item in has_underlying_positions if isinstance(item, str)
        )

    return False


def _handoff_summary(handoff: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": _string_or_none(handoff.get("artifact_type")),
        "status": _string_or_none(handoff.get("status")),
        "symbol": _string_or_none(handoff.get("symbol")),
        "warning_count": len(_strings(handoff.get("warnings"))),
        "blocked_reason_count": len(_strings(handoff.get("blocked_reasons"))),
    }


def _count_status(results: Sequence[Mapping[str, Any]], status: str) -> int:
    return sum(1 for result in results if result.get("status") == status)


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None

    return None


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()

    return tuple(item for item in value if isinstance(item, str) and item.strip())


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []

    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)

    return output

