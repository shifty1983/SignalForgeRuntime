from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.position_maintenance.defense_candidate_builder import (
    EXCLUDED_ACTIONS,
    build_options_strategy_defense_candidates,
)
from src.position_maintenance.strategy_playbook import (
    build_options_strategy_maintenance_playbooks,
)


VALID_DEFENSE_REVIEW_STATUSES = {
    "ready",
    "needs_review",
    "blocked",
}

URGENCY_RANK = {"high": 0, "medium": 1, "low": 2}


def build_options_strategy_defense_review(
    positions: Sequence[Mapping[str, Any]] | None,
    *,
    plan_date: str,
    market_regime: str | None = None,
    regime_options_policy: Mapping[str, Any] | None = None,
    asset_behavior_options_policy: Mapping[str, Any] | None = None,
    option_behavior_options_policy: Mapping[str, Any] | None = None,
    max_candidates_per_position: int | None = None,
) -> dict[str, Any]:
    """
    Build an options-strategy-specific maintenance/defense review.

    This is a manual review artifact only. It builds strategy playbooks and
    defense candidates, but it does not create order intents, route orders,
    submit orders, model fills, perform live execution, or automatically defend
    positions.
    """

    errors = _validate_inputs(
        positions=positions,
        plan_date=plan_date,
        max_candidates_per_position=max_candidates_per_position,
    )
    if errors:
        return _blocked_review(
            plan_date=plan_date,
            market_regime=market_regime,
            blocked_reasons=errors,
        )

    assert positions is not None

    playbook_set = build_options_strategy_maintenance_playbooks(
        positions,
        plan_date=plan_date,
        market_regime=market_regime,
        regime_options_policy=regime_options_policy,
        asset_behavior_options_policy=asset_behavior_options_policy,
        option_behavior_options_policy=option_behavior_options_policy,
    )
    candidate_set = build_options_strategy_defense_candidates(
        playbook_set,
        plan_date=plan_date,
        max_candidates_per_position=max_candidates_per_position,
    )

    playbooks = _list_of_mappings(playbook_set.get("playbooks"))
    base_candidates = _list_of_mappings(candidate_set.get("candidates"))
    blocked_items = _list_of_mappings(candidate_set.get("blocked_items"))
    candidates = _with_fallback_manual_review_candidates(
        playbooks=playbooks,
        candidates=base_candidates,
        blocked_items=blocked_items,
    )
    monitor_items = _monitor_items_from_playbooks(playbooks)
    status = _review_status(
        playbook_set=playbook_set,
        candidate_set=candidate_set,
        candidates=candidates,
        blocked_items=blocked_items,
    )

    return {
        "artifact_type": "options_strategy_defense_review",
        "status": status,
        "is_ready": status == "ready",
        "plan_date": plan_date,
        "review_mode": "manual_review_only",
        "market_regime": _string_or_none(market_regime),
        "position_count": len(_position_list(positions)),
        "playbook_count": _safe_int(playbook_set.get("playbook_count")),
        "candidate_count": len(candidates),
        "manual_review_count": len(candidates),
        "monitor_item_count": len(monitor_items),
        "blocked_count": len(blocked_items),
        "review_candidates": candidates,
        "monitor_items": monitor_items,
        "blocked_items": blocked_items,
        "strategy_summary": _strategy_summary(playbooks=playbooks, candidates=candidates),
        "urgency_summary": _urgency_summary(candidates=candidates, monitor_items=monitor_items),
        "playbook_set": playbook_set,
        "defense_candidate_set": candidate_set,
        "warnings": _dedupe_strings(
            [
                *_strings(playbook_set.get("warnings")),
                *_strings(candidate_set.get("warnings")),
            ]
        ),
        "blocked_reasons": _dedupe_strings(
            [
                *_strings(playbook_set.get("blocked_reasons")),
                *_strings(candidate_set.get("blocked_reasons")),
            ]
        ),
        "requires_manual_approval": True,
        "order_intent": None,
        "automatic_action": None,
        "excluded": list(EXCLUDED_ACTIONS),
    }


def _validate_inputs(
    *,
    positions: Sequence[Mapping[str, Any]] | None,
    plan_date: str,
    max_candidates_per_position: int | None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan_date, str) or not plan_date.strip():
        errors.append("plan_date is required")
    if positions is None:
        errors.append("positions are required")
    elif isinstance(positions, (str, bytes)) or not isinstance(positions, Sequence):
        errors.append("positions must be a sequence")
    elif not all(isinstance(position, Mapping) for position in positions):
        errors.append("positions must contain only mappings")
    if max_candidates_per_position is not None:
        if not isinstance(max_candidates_per_position, int):
            errors.append("max_candidates_per_position must be an integer when provided")
        elif max_candidates_per_position < 0:
            errors.append("max_candidates_per_position must be greater than or equal to zero")
    return errors


def _blocked_review(
    *,
    plan_date: str,
    market_regime: str | None,
    blocked_reasons: Sequence[str],
) -> dict[str, Any]:
    return {
        "artifact_type": "options_strategy_defense_review",
        "status": "blocked",
        "is_ready": False,
        "plan_date": _string_or_none(plan_date),
        "review_mode": "manual_review_only",
        "market_regime": _string_or_none(market_regime),
        "position_count": 0,
        "playbook_count": 0,
        "candidate_count": 0,
        "manual_review_count": 0,
        "monitor_item_count": 0,
        "blocked_count": 0,
        "review_candidates": [],
        "monitor_items": [],
        "blocked_items": [],
        "strategy_summary": {},
        "urgency_summary": {"high": 0, "medium": 0, "low": 0},
        "playbook_set": None,
        "defense_candidate_set": None,
        "warnings": [],
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "requires_manual_approval": True,
        "order_intent": None,
        "automatic_action": None,
        "excluded": list(EXCLUDED_ACTIONS),
    }


def _review_status(
    *,
    playbook_set: Mapping[str, Any],
    candidate_set: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    blocked_items: Sequence[Mapping[str, Any]],
) -> str:
    if _clean(playbook_set.get("status")) == "blocked" or _clean(candidate_set.get("status")) == "blocked":
        return "blocked"
    if candidates or blocked_items:
        return "needs_review"
    if _clean(playbook_set.get("status")) == "needs_review" or _clean(candidate_set.get("status")) == "needs_review":
        return "needs_review"
    return "ready"


def _with_fallback_manual_review_candidates(
    *,
    playbooks: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    blocked_items: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    existing_position_ids = {
        _string_or_none(candidate.get("position_id"))
        for candidate in candidates
    }
    blocked_position_ids = {
        _string_or_none(item.get("position_id"))
        for item in blocked_items
    }
    fallback_candidates: list[dict[str, Any]] = []
    for playbook in playbooks:
        position_id = _string_or_none(playbook.get("position_id"))
        if _clean(playbook.get("status")) != "needs_review":
            continue
        if position_id in existing_position_ids or position_id in blocked_position_ids:
            continue
        fallback_candidates.append(
            {
                "candidate_type": "manual_review",
                "review_action_type": "policy_or_context_review",
                "action": "review_position_context_before_adjustment",
                "symbol": _string_or_none(playbook.get("symbol")),
                "position_id": position_id,
                "strategy": _clean(playbook.get("strategy")),
                "strategy_family": _string_or_none(playbook.get("strategy_family")),
                "urgency": _clean(playbook.get("urgency")) or "medium",
                "review_triggers": _strings(playbook.get("review_triggers")),
                "reason": "position requires manual review but has no direct defense action",
                "risk_guardrails": ["maintain_defined_risk", "manual_approval_required"],
                "requires_manual_approval": True,
                "order_intent": None,
                "automatic_action": None,
            }
        )
    return [*candidates, *sorted(
        fallback_candidates,
        key=lambda item: (
            URGENCY_RANK.get(str(item.get("urgency", "medium")), 9),
            str(item.get("symbol") or ""),
            str(item.get("position_id") or ""),
            str(item.get("action") or ""),
        ),
    )]


def _monitor_items_from_playbooks(playbooks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    monitor_items: list[dict[str, Any]] = []
    for playbook in playbooks:
        if _clean(playbook.get("status")) != "ready":
            continue
        monitor_items.append(
            {
                "symbol": _string_or_none(playbook.get("symbol")),
                "position_id": _string_or_none(playbook.get("position_id")),
                "strategy": _clean(playbook.get("strategy")),
                "strategy_family": _string_or_none(playbook.get("strategy_family")),
                "urgency": _clean(playbook.get("urgency")) or "low",
                "monitoring_rules": _list_of_mappings(playbook.get("monitoring_rules")),
                "primary_management_objective": _string_or_none(
                    playbook.get("primary_management_objective")
                ),
                "requires_manual_approval": True,
                "order_intent": None,
                "automatic_action": None,
            }
        )
    return sorted(
        monitor_items,
        key=lambda item: (
            URGENCY_RANK.get(str(item.get("urgency", "low")), 9),
            str(item.get("symbol") or ""),
            str(item.get("position_id") or ""),
        ),
    )


def _strategy_summary(
    *,
    playbooks: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    summary: dict[str, dict[str, int]] = {}
    for playbook in playbooks:
        strategy = _clean(playbook.get("strategy")) or "unknown"
        summary.setdefault(
            strategy,
            {"position_count": 0, "candidate_count": 0, "blocked_count": 0},
        )
        summary[strategy]["position_count"] += 1
        if _clean(playbook.get("status")) == "blocked":
            summary[strategy]["blocked_count"] += 1
    for candidate in candidates:
        strategy = _clean(candidate.get("strategy")) or "unknown"
        summary.setdefault(
            strategy,
            {"position_count": 0, "candidate_count": 0, "blocked_count": 0},
        )
        summary[strategy]["candidate_count"] += 1
    return {key: summary[key] for key in sorted(summary)}


def _urgency_summary(
    *,
    candidates: Sequence[Mapping[str, Any]],
    monitor_items: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    summary = {"high": 0, "medium": 0, "low": 0}
    for item in [*candidates, *monitor_items]:
        urgency = _clean(item.get("urgency")) or "medium"
        if urgency not in summary:
            summary["medium"] += 1
            continue
        summary[urgency] += 1
    return summary


def _position_list(positions: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [position for position in positions if isinstance(position, Mapping)]


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

