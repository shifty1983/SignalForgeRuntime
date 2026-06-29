from __future__ import annotations

from typing import Any, Mapping


POSITIVE_BREADTH = {
    "broad_strength",
    "breadth_strength",
    "risk_on_breadth",
    "strong_breadth",
}

NEGATIVE_BREADTH = {
    "broad_weakness",
    "breadth_weakness",
    "risk_off_breadth",
    "weak_breadth",
    "breadth_collapse",
}

LEADER_STATES = {
    "market_leader",
    "sector_leader",
    "emerging_leader",
}

LAGGARD_STATES = {
    "market_laggard",
    "sector_laggard",
    "improving_laggard",
}

POSITIVE_RELATIVE_STATES = {
    "strong_outperformer",
    "outperformer",
    "sector_leader",
    "sector_outperformer",
}

NEGATIVE_RELATIVE_STATES = {
    "strong_underperformer",
    "underperformer",
    "sector_laggard",
    "sector_underperformer",
}

POSITIVE_PARTICIPATION = {
    "accumulation",
    "institutional_participation",
    "confirmed_move",
    "volume_expansion",
    "volume_breakout",
}

NEGATIVE_PARTICIPATION = {
    "distribution",
    "unconfirmed_move",
    "volume_contraction",
}


def build_breadth_participation_profile(
    *,
    breadth_regime: Any | None = None,
    relative_strength_state: Any | None = None,
    relative_strength_trend: Any | None = None,
    sector_relative_state: Any | None = None,
    leadership_state: Any | None = None,
    volume_confirmation: Any | None = None,
    participation_state: Any | None = None,
    trend_quality: Any | None = None,
    behavior: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify whether an asset is participating in the prevailing market breadth.

    The breadth layer answers whether the market is broadly strong or weak. This
    asset-level profile answers whether a specific asset is leading that breadth,
    participating with it, lagging it, or failing to participate.

    Callers may pass explicit arguments, or a row-shaped ``behavior`` mapping
    containing the same field names.
    """

    source = dict(behavior or {})

    breadth = _clean(breadth_regime if breadth_regime is not None else source.get("breadth_regime"))
    rs_state = _clean(
        relative_strength_state
        if relative_strength_state is not None
        else source.get("relative_strength_state")
    )
    rs_trend = _clean(
        relative_strength_trend
        if relative_strength_trend is not None
        else source.get("relative_strength_trend")
    )
    sector_state = _clean(
        sector_relative_state
        if sector_relative_state is not None
        else source.get("sector_relative_state")
    )
    leader = _clean(leadership_state if leadership_state is not None else source.get("leadership_state"))
    volume = _clean(
        volume_confirmation
        if volume_confirmation is not None
        else source.get("volume_confirmation")
    )
    participation = _clean(
        participation_state
        if participation_state is not None
        else source.get("participation_state")
    )
    trend = _clean(trend_quality if trend_quality is not None else source.get("trend_quality"))

    score = _breadth_participation_score(
        breadth=breadth,
        relative_strength_state=rs_state,
        relative_strength_trend=rs_trend,
        sector_relative_state=sector_state,
        leadership_state=leader,
        volume_confirmation=volume,
        participation_state=participation,
        trend_quality=trend,
    )

    state = _breadth_participation_state(score=score, breadth=breadth, leadership_state=leader)
    alignment = _breadth_alignment(breadth=breadth, state=state, score=score)
    breadth_leadership = _breadth_leadership_state(
        state=state,
        leadership_state=leader,
        relative_strength_state=rs_state,
        sector_relative_state=sector_state,
    )

    return {
        "breadth_regime": breadth or None,
        "breadth_participation_score": round(score, 4),
        "breadth_participation": state,
        "breadth_alignment": alignment,
        "breadth_leadership": breadth_leadership,
    }


def _breadth_participation_score(
    *,
    breadth: str,
    relative_strength_state: str,
    relative_strength_trend: str,
    sector_relative_state: str,
    leadership_state: str,
    volume_confirmation: str,
    participation_state: str,
    trend_quality: str,
) -> float:
    score = 0.50

    if breadth in POSITIVE_BREADTH:
        score += 0.10
    elif breadth in NEGATIVE_BREADTH:
        score -= 0.10

    if leadership_state in LEADER_STATES:
        score += 0.22
    elif leadership_state == "weakening_leader":
        score += 0.06
    elif leadership_state in LAGGARD_STATES:
        score -= 0.18

    if relative_strength_state in POSITIVE_RELATIVE_STATES:
        score += 0.12
    elif relative_strength_state in NEGATIVE_RELATIVE_STATES:
        score -= 0.12

    if sector_relative_state in POSITIVE_RELATIVE_STATES:
        score += 0.08
    elif sector_relative_state in NEGATIVE_RELATIVE_STATES:
        score -= 0.08

    if "improving" in relative_strength_trend or "strengthening" in relative_strength_trend:
        score += 0.08
    elif "deteriorating" in relative_strength_trend or "weakening" in relative_strength_trend:
        score -= 0.08

    if volume_confirmation in POSITIVE_PARTICIPATION or participation_state in POSITIVE_PARTICIPATION:
        score += 0.08
    elif volume_confirmation in NEGATIVE_PARTICIPATION or participation_state in NEGATIVE_PARTICIPATION:
        score -= 0.08

    if trend_quality in {"strong_trend", "trend_accelerating"}:
        score += 0.06
    elif trend_quality in {"choppy_trend", "trend_breakdown", "weak_trend"}:
        score -= 0.06

    return max(0.0, min(1.0, score))


def _breadth_participation_state(*, score: float, breadth: str, leadership_state: str) -> str:
    if score >= 0.78:
        return "breadth_leader"

    if score >= 0.58:
        return "breadth_participant"

    if score <= 0.28:
        return "breadth_laggard"

    if breadth in POSITIVE_BREADTH and leadership_state in LAGGARD_STATES:
        return "breadth_nonparticipant"

    if score < 0.45:
        return "breadth_nonparticipant"

    return "breadth_participant"


def _breadth_alignment(*, breadth: str, state: str, score: float) -> str:
    positive_asset = state in {"breadth_leader", "breadth_participant"}
    negative_asset = state in {"breadth_laggard", "breadth_nonparticipant"}

    if breadth in POSITIVE_BREADTH and positive_asset:
        return "aligned_with_breadth"

    if breadth in NEGATIVE_BREADTH and negative_asset:
        return "aligned_with_breadth"

    if breadth in POSITIVE_BREADTH and negative_asset:
        return "diverging_from_breadth"

    if breadth in NEGATIVE_BREADTH and positive_asset:
        return "diverging_from_breadth"

    if score >= 0.70 or score <= 0.35:
        return "asset_specific_breadth_signal"

    return "neutral_breadth_alignment"


def _breadth_leadership_state(
    *,
    state: str,
    leadership_state: str,
    relative_strength_state: str,
    sector_relative_state: str,
) -> str:
    if state == "breadth_leader":
        return "leading_breadth"

    if state == "breadth_laggard":
        return "lagging_breadth"

    if state == "breadth_nonparticipant":
        return "not_participating_in_breadth"

    if leadership_state == "improving_laggard" or "improving" in relative_strength_state:
        return "improving_breadth_participation"

    if leadership_state == "weakening_leader" or "deteriorating" in sector_relative_state:
        return "weakening_breadth_participation"

    return "participating_in_breadth"


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()
