from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import date, datetime
from typing import Any

from src.signalforge.engines.regime.options_policy import build_regime_options_policy_from_row

try:
    from src.signalforge.engines.regime.asset_class_policy import build_regime_asset_class_policy_from_row
except Exception:  # pragma: no cover - optional module during staged builds
    build_regime_asset_class_policy_from_row = None  # type: ignore[assignment]


EXCLUDED_ACTIONS = [
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


def build_signalforge_fred_weekly_regime_pipeline(
    source: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    max_macro_lookback_months: int = 18,
    periods: int | None = None,
    weekly_lookback_days: int | None = None,
    **_: Any,
) -> dict[str, Any]:
    """
    Build the weekly regime planning context.

    Design:
    - completed/refined macro base determines the macro regime label
    - latest weekly row determines current risk/rates/liquidity/volatility overlay
    - policy_regime_label feeds options and asset-class policy
    - no broker API calls, order routing, order submission, fills, live execution,
      or slippage modeling are performed
    """

    source_errors = _source_errors(source)
    if source_errors:
        return _blocked_result(source_errors)

    rows = _extract_regime_rows(source)
    if not rows:
        return _blocked_result(["source rows are required"])

    rows = sorted(rows, key=lambda row: _date_key(row.get("date")))

    weekly_overlay_row = _normalize_weekly_overlay_row(rows[-1])
    as_of_date = _string(weekly_overlay_row.get("date"))

    macro_base_row, macro_base_reason = _select_macro_base_row(
        rows=rows,
        as_of_date=as_of_date,
        max_macro_lookback_months=max_macro_lookback_months,
    )

    source_macro_regime_label = _canonical_macro_regime_label(
        _string(macro_base_row.get("regime_label")) or "neutral_mixed"
    )
    composite_macro_regime = _composite_macro_regime_from_row(
        macro_base_row=macro_base_row,
        fallback_label=source_macro_regime_label,
    )
    composite_macro_regime_score = _float_or_none(macro_base_row.get("macro_regime_score"))
    composite_macro_regime_confidence = _float_or_none(
        macro_base_row.get("macro_regime_confidence")
    )
    composite_macro_regime_drivers = _string_or_none(
        macro_base_row.get("macro_regime_drivers")
    )
    refined_macro_regime_label = _canonical_macro_regime_label(
        _refined_macro_regime_label(macro_base_row)
    )

    policy_regime_label = _policy_regime_label(
        macro_regime_label=refined_macro_regime_label,
        weekly_overlay_row=weekly_overlay_row,
    )

    weekly_planning_label, weekly_review_reasons = _weekly_planning_label(
        macro_regime_label=refined_macro_regime_label,
        policy_regime_label=policy_regime_label,
        weekly_overlay_row=weekly_overlay_row,
    )

    policy_context = _policy_context(
        macro_base_row=macro_base_row,
        weekly_overlay_row=weekly_overlay_row,
        refined_macro_regime_label=refined_macro_regime_label,
        source_macro_regime_label=source_macro_regime_label,
        policy_regime_label=policy_regime_label,
        weekly_planning_label=weekly_planning_label,
        macro_base_reason=macro_base_reason,
    )

    latest_regime_options_policy = build_regime_options_policy_from_row(policy_context)

    latest_regime_asset_class_policy = None
    if build_regime_asset_class_policy_from_row is not None:
        latest_regime_asset_class_policy = build_regime_asset_class_policy_from_row(
            policy_context
        )

    requires_manual_approval = _requires_manual_approval(
        weekly_review_reasons=weekly_review_reasons,
        options_policy=latest_regime_options_policy,
        asset_class_policy=latest_regime_asset_class_policy,
    )

    warnings = []
    if source_macro_regime_label != refined_macro_regime_label:
        warnings.append(
            "macro regime label refined from component regimes for weekly planning"
        )

    status = "ready"

    return {
        "artifact_type": "signalforge_fred_weekly_regime_pipeline",
        "schema_version": "signalforge_fred_weekly_regime_pipeline.v2",
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": requires_manual_approval,
        "as_of_date": as_of_date,
        "macro_regime_label": refined_macro_regime_label,
        "macro_regime": composite_macro_regime,
        "macro_regime_score": composite_macro_regime_score,
        "macro_regime_confidence": composite_macro_regime_confidence,
        "macro_regime_drivers": composite_macro_regime_drivers,
        "source_macro_regime_label": source_macro_regime_label,
        "macro_regime_source_date": _string(macro_base_row.get("date")),
        "macro_base_selection_reason": macro_base_reason,
        "policy_regime_label": policy_regime_label,
        "weekly_planning_label": weekly_planning_label,
        "weekly_review_reasons": weekly_review_reasons,
        "weekly_overlay_date": as_of_date,
        "weekly_risk_environment": _string_or_none(
            weekly_overlay_row.get("risk_environment")
        ),
        "weekly_rates_regime": _string_or_none(weekly_overlay_row.get("rates_regime")),
        "weekly_liquidity_regime": _string_or_none(
            weekly_overlay_row.get("liquidity_regime")
        ),
        "weekly_volatility_regime": _string_or_none(
            weekly_overlay_row.get("volatility_regime")
        ),
        "weekly_event_risk": bool(weekly_overlay_row.get("event_risk", False)),
        "latest_macro_regime_row": dict(macro_base_row),
        "latest_weekly_overlay_row": dict(weekly_overlay_row),
        "latest_regime_options_policy": latest_regime_options_policy,
        "latest_regime_asset_class_policy": latest_regime_asset_class_policy,
        "regime_row_count": len(rows),
        "source_artifact_summary": _source_artifact_summary(source),
        "warnings": _dedupe(warnings),
        "blocked_reasons": [],
        "excluded": EXCLUDED_ACTIONS,
    }


def _source_errors(source: Any) -> list[str]:
    if not isinstance(source, Mapping) and not isinstance(source, Sequence):
        return ["source must be a mapping or sequence of regime rows"]

    if isinstance(source, Sequence) and isinstance(source, (str, bytes)):
        return ["source must not be a string"]

    return []

def _normalize_weekly_overlay_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """
    Backward-compatible weekly overlay normalizer.

    Preferred input is a fully classified regime row. If older tests or source
    artifacts provide only source_series_values, infer the weekly overlay fields
    from the available FRED values.
    """
    output = dict(row)

    source_values = output.get("source_series_values")
    if not isinstance(source_values, Mapping):
        source_values = {}

    if not output.get("risk_environment"):
        output["risk_environment"] = _inferred_risk_environment(source_values)

    if not output.get("volatility_regime"):
        output["volatility_regime"] = _inferred_volatility_regime(source_values)

    if not output.get("liquidity_regime"):
        output["liquidity_regime"] = _inferred_liquidity_regime(source_values)

    if not output.get("rates_regime"):
        output["rates_regime"] = _inferred_rates_regime(source_values)

    return output


def _inferred_risk_environment(source_values: Mapping[str, Any]) -> str:
    high_yield_spread = _float(source_values.get("BAMLH0A0HYM2"))
    vix = _float(source_values.get("VIXCLS"))
    nfci = _float(source_values.get("NFCI"))
    anfci = _float(source_values.get("ANFCI"))

    if high_yield_spread >= 4.0 or vix >= 25.0 or nfci > 0.0 or anfci > 0.0:
        return "risk_off"

    if high_yield_spread > 0.0 and high_yield_spread < 4.0 and vix > 0.0 and vix <= 20.0 and nfci <= 0.0:
        return "risk_on"

    return "risk_neutral"


def _inferred_volatility_regime(source_values: Mapping[str, Any]) -> str:
    vix = _float(source_values.get("VIXCLS"))

    if vix >= 25.0:
        return "volatility_expansion"

    if vix > 0.0 and vix <= 20.0:
        return "volatility_compression"

    return "volatility_neutral"


def _inferred_liquidity_regime(source_values: Mapping[str, Any]) -> str:
    nfci = _float(source_values.get("NFCI"))
    anfci = _float(source_values.get("ANFCI"))

    if nfci > 0.0 or anfci > 0.0:
        return "liquidity_contracting"

    if nfci < 0.0 or anfci < 0.0:
        return "liquidity_expanding"

    return "liquidity_neutral"


def _inferred_rates_regime(source_values: Mapping[str, Any]) -> str:
    dgs10 = _float(source_values.get("DGS10"))
    dgs2 = _float(source_values.get("DGS2"))
    fedfunds = _float(source_values.get("FEDFUNDS"))

    if dgs10 > 0.0 and fedfunds > 0.0:
        if dgs10 > fedfunds:
            return "rates_rising"
        if dgs10 < fedfunds:
            return "rates_falling"

    if dgs10 > 0.0 and dgs2 > 0.0:
        if dgs10 > dgs2:
            return "rates_rising"
        if dgs10 < dgs2:
            return "rates_falling"

    return "rates_stable"


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_regime_rows(
    source: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(source, Mapping):
        candidates = source.get("regime_rows")
        if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
            return []
        return [dict(row) for row in candidates if isinstance(row, Mapping)]

    return [dict(row) for row in source if isinstance(row, Mapping)]


def _select_macro_base_row(
    *,
    rows: Sequence[Mapping[str, Any]],
    as_of_date: str,
    max_macro_lookback_months: int,
) -> tuple[dict[str, Any], str]:
    latest_date = _parse_date(as_of_date)
    latest_month_start = date(latest_date.year, latest_date.month, 1)
    max_lookback_days = max(max_macro_lookback_months, 1) * 31

    completed_rows = [
        dict(row)
        for row in rows
        if _parse_date(_string(row.get("date"))) < latest_month_start
    ]

    if not completed_rows:
        completed_rows = [dict(row) for row in rows]

    recent_completed_rows = [
        row
        for row in completed_rows
        if (latest_date - _parse_date(_string(row.get("date")))).days <= max_lookback_days
    ]

    search_rows = recent_completed_rows or completed_rows

    strong_rows = [
        row
        for row in search_rows
        if _has_directional_macro_signal(row)
        and _string(row.get("regime_label")) not in {"", "mixed"}
    ]

    if strong_rows:
        return strong_rows[-1], "latest_completed_month_with_explicit_non_mixed_macro_label"

    directional_rows = [row for row in search_rows if _has_directional_macro_signal(row)]
    if directional_rows:
        return directional_rows[-1], "latest_completed_month_with_directional_macro_components"

    return search_rows[-1], "latest_completed_month_fallback"


def _has_directional_macro_signal(row: Mapping[str, Any]) -> bool:
    growth_regime = _string(row.get("growth_regime"))
    inflation_regime = _string(row.get("inflation_regime"))

    return (
        growth_regime in {"growth_expansion", "growth_contraction"}
        or inflation_regime in {"inflation_rising", "inflation_falling"}
    )


def _refined_macro_regime_label(row: Mapping[str, Any]) -> str:
    """
    Refine the simple growth/inflation label using the full macro component stack.

    This keeps V1 deterministic but avoids treating missing/unchanged weekly growth
    prints as an automatic mixed regime when rates/liquidity/risk are clearly
    defensive or supportive.
    """

    source_label = _string(row.get("regime_label"))
    if source_label and source_label != "mixed":
        return source_label

    growth = _string(row.get("growth_regime"))
    inflation = _string(row.get("inflation_regime"))
    rates = _string(row.get("rates_regime"))
    liquidity = _string(row.get("liquidity_regime"))
    risk = _string(row.get("risk_environment"))
    volatility = _string(row.get("volatility_regime"))

    growth_positive = growth == "growth_expansion"
    growth_negative = growth == "growth_contraction"
    growth_neutral = growth in {"", "growth_neutral"}

    inflation_rising = inflation == "inflation_rising"
    inflation_falling = inflation == "inflation_falling"
    inflation_stable = inflation in {"", "inflation_stable"}

    supportive_conditions = (
        risk == "risk_on"
        and liquidity == "liquidity_expanding"
        and volatility != "volatility_expansion"
    )

    defensive_conditions = (
        risk == "risk_off"
        or liquidity == "liquidity_contracting"
        or volatility == "volatility_expansion"
    )

    tightening_conditions = rates == "rates_rising"

    if growth_positive and inflation_falling:
        return "goldilocks"

    if growth_positive and inflation_rising:
        return "overheating"

    if growth_negative and inflation_rising:
        return "stagflation"

    if growth_negative and inflation_falling:
        return "deflationary_slowdown"

    if growth_neutral and inflation_falling and defensive_conditions:
        return "deflationary_slowdown"

    if growth_neutral and inflation_stable and defensive_conditions and tightening_conditions:
        return "deflationary_slowdown"

    if growth_neutral and inflation_rising and defensive_conditions:
        return "stagflation"

    if growth_neutral and inflation_rising and supportive_conditions:
        return "overheating"

    if growth_neutral and inflation_falling and supportive_conditions:
        return "goldilocks"

    return "mixed"


def _canonical_macro_regime_label(label: str) -> str:
    text = _string(label)

    legacy_map = {
        "overheating": "late_cycle_overheating",
        "mixed": "neutral_mixed",
        "neutral": "neutral_mixed",
        "range_bound": "neutral_mixed",
    }

    return legacy_map.get(text, text or "neutral_mixed")


def _composite_macro_regime_from_row(
    *,
    macro_base_row: Mapping[str, Any],
    fallback_label: str,
) -> str | None:
    value = _string_or_none(macro_base_row.get("macro_regime"))

    if not value:
        return fallback_label

    if "|" in value:
        return fallback_label

    return _canonical_macro_regime_label(value)


def _policy_regime_label(
    *,
    macro_regime_label: str,
    weekly_overlay_row: Mapping[str, Any],
) -> str:
    if bool(weekly_overlay_row.get("event_risk", False)):
        return "event_risk"

    risk = _string(weekly_overlay_row.get("risk_environment"))
    liquidity = _string(weekly_overlay_row.get("liquidity_regime"))
    volatility = _string(weekly_overlay_row.get("volatility_regime"))

    if macro_regime_label not in {"mixed", "neutral_mixed"}:
        return macro_regime_label

    if risk == "risk_off" or volatility == "volatility_expansion":
        return "risk_off"

    if (
        risk == "risk_on"
        and liquidity == "liquidity_expanding"
        and volatility != "volatility_expansion"
    ):
        return "risk_on"

    return "mixed"


def _weekly_planning_label(
    *,
    macro_regime_label: str,
    policy_regime_label: str,
    weekly_overlay_row: Mapping[str, Any],
) -> tuple[str, list[str]]:
    parts = [macro_regime_label]
    review_reasons: list[str] = []

    if policy_regime_label != macro_regime_label:
        parts.append(policy_regime_label)
        review_reasons.append(f"weekly policy overlay shifted to {policy_regime_label}")

    risk = _string(weekly_overlay_row.get("risk_environment"))
    liquidity = _string(weekly_overlay_row.get("liquidity_regime"))
    volatility = _string(weekly_overlay_row.get("volatility_regime"))
    rates = _string(weekly_overlay_row.get("rates_regime"))

    if risk == "risk_off":
        parts.append("risk_off_review")
        review_reasons.append("weekly risk environment is risk_off")

    if volatility == "volatility_expansion":
        parts.append("volatility_review")
        review_reasons.append("weekly volatility is expanding")

    if liquidity == "liquidity_contracting":
        parts.append("liquidity_review")
        review_reasons.append("weekly liquidity is contracting")

    if rates == "rates_rising":
        parts.append("rates_review")
        review_reasons.append("weekly rates are rising")

    if bool(weekly_overlay_row.get("event_risk", False)):
        parts.append("event_risk_review")
        review_reasons.append("event risk flag is active")

    return "_with_".join(_dedupe(parts)), _dedupe(review_reasons)


def _policy_context(
    *,
    macro_base_row: Mapping[str, Any],
    weekly_overlay_row: Mapping[str, Any],
    refined_macro_regime_label: str,
    source_macro_regime_label: str,
    policy_regime_label: str,
    weekly_planning_label: str,
    macro_base_reason: str,
) -> dict[str, Any]:
    context = deepcopy(dict(macro_base_row))

    context["regime_label"] = policy_regime_label
    context["macro_regime_label"] = refined_macro_regime_label
    context["macro_regime"] = macro_base_row.get("macro_regime")
    context["macro_regime_score"] = macro_base_row.get("macro_regime_score")
    context["macro_regime_confidence"] = macro_base_row.get("macro_regime_confidence")
    context["macro_regime_drivers"] = macro_base_row.get("macro_regime_drivers")
    context["source_macro_regime_label"] = source_macro_regime_label
    context["weekly_planning_label"] = weekly_planning_label

    for key in (
        "risk_environment",
        "rates_regime",
        "liquidity_regime",
        "volatility_regime",
        "event_risk",
    ):
        if key in weekly_overlay_row:
            context[key] = weekly_overlay_row[key]

    metadata = context.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}

    context["metadata"] = {
        **dict(metadata),
        "macro_regime_label": refined_macro_regime_label,
        "macro_regime": macro_base_row.get("macro_regime"),
        "macro_regime_score": macro_base_row.get("macro_regime_score"),
        "macro_regime_confidence": macro_base_row.get("macro_regime_confidence"),
        "macro_regime_drivers": macro_base_row.get("macro_regime_drivers"),
        "source_macro_regime_label": source_macro_regime_label,
        "policy_regime_label": policy_regime_label,
        "weekly_planning_label": weekly_planning_label,
        "macro_regime_source_date": _string(macro_base_row.get("date")),
        "weekly_overlay_date": _string(weekly_overlay_row.get("date")),
        "macro_base_selection_reason": macro_base_reason,
    }

    return context


def _requires_manual_approval(
    *,
    weekly_review_reasons: Sequence[str],
    options_policy: Mapping[str, Any],
    asset_class_policy: Mapping[str, Any] | None,
) -> bool:
    if weekly_review_reasons:
        return True

    if _string(options_policy.get("status")) != "ready":
        return True

    if isinstance(asset_class_policy, Mapping):
        if _string(asset_class_policy.get("status")) != "ready":
            return True

    return False


def _source_artifact_summary(source: Any) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {}

    return {
        "artifact_type": source.get("artifact_type"),
        "schema_version": source.get("schema_version"),
        "status": source.get("status"),
        "regime_row_count": len(_extract_regime_rows(source)),
        "latest_date": source.get("latest_date") or source.get("as_of_date"),
        "warning_count": len(_list(source.get("warnings"))),
        "blocker_count": len(_list(source.get("blocked_reasons"))),
    }


def _blocked_result(blocked_reasons: Sequence[str]) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_fred_weekly_regime_pipeline",
        "schema_version": "signalforge_fred_weekly_regime_pipeline.v2",
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "as_of_date": None,
        "macro_regime_label": None,
        "macro_regime": None,
        "macro_regime_score": None,
        "macro_regime_confidence": None,
        "macro_regime_drivers": None,
        "source_macro_regime_label": None,
        "macro_regime_source_date": None,
        "macro_base_selection_reason": None,
        "policy_regime_label": None,
        "weekly_planning_label": None,
        "weekly_review_reasons": [],
        "weekly_overlay_date": None,
        "weekly_risk_environment": None,
        "weekly_rates_regime": None,
        "weekly_liquidity_regime": None,
        "weekly_volatility_regime": None,
        "weekly_event_risk": False,
        "latest_macro_regime_row": {},
        "latest_weekly_overlay_row": {},
        "latest_regime_options_policy": {},
        "latest_regime_asset_class_policy": {},
        "regime_row_count": 0,
        "source_artifact_summary": {},
        "warnings": [],
        "blocked_reasons": list(blocked_reasons),
        "excluded": EXCLUDED_ACTIONS,
    }


def _parse_date(value: str) -> date:
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def _date_key(value: Any) -> tuple[int, int, int]:
    parsed = _parse_date(_string(value))
    return parsed.year, parsed.month, parsed.day


def _string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _string_or_none(value: Any) -> str | None:
    text = _string(value)
    return text or None


def _list(value: Any) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return list(value)


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []

    for value in values:
        text = _string(value)
        if text and text not in seen:
            seen.add(text)
            output.append(text)

    return output


