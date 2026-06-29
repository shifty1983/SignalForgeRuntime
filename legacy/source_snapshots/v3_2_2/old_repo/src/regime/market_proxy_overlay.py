from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any


EXCLUDED_ACTIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
    "automatic_maintenance_actions",
    "automatic_defense_actions",
]

SUPPORTED_PROXY_GROUPS = {
    "equity_risk",
    "credit_risk",
    "duration",
    "commodities",
    "dollar",
    "volatility",
}

ROW_COLLECTION_KEYS = [
    "normalized_payloads",
    "payloads",
    "accepted_payloads",
    "accepted_rows",
    "valid_rows",
    "market_price_history",
    "price_rows",
    "rows",
    "data",
    "items",
    "records",
]


@dataclass(frozen=True)
class ProxyGroupConfig:
    name: str
    primary_symbols: tuple[str, ...]
    comparison_symbols: tuple[str, ...] = ()
    positive_label: str = "positive"
    negative_label: str = "negative"
    neutral_label: str = "neutral"
    risk_weight: float = 0.0
    invert_for_score: bool = False


PROXY_GROUPS: tuple[ProxyGroupConfig, ...] = (
    ProxyGroupConfig(
        name="equity_risk",
        primary_symbols=("SPY", "QQQ", "IWM", "RSP"),
        positive_label="confirming_risk_on",
        negative_label="warning_risk_off",
        neutral_label="equity_neutral",
        risk_weight=1.0,
    ),
    ProxyGroupConfig(
        name="credit_risk",
        primary_symbols=("HYG", "JNK"),
        comparison_symbols=("LQD", "IEF", "SHY"),
        positive_label="credit_risk_improving",
        negative_label="credit_risk_worsening",
        neutral_label="credit_neutral",
        risk_weight=1.0,
    ),
    ProxyGroupConfig(
        name="duration",
        primary_symbols=("TLT", "IEF"),
        comparison_symbols=("SHY", "SGOV", "BIL"),
        positive_label="duration_bid_rates_relief",
        negative_label="duration_pressure_rates_risk",
        neutral_label="duration_neutral",
        risk_weight=0.0,
    ),
    ProxyGroupConfig(
        name="commodities",
        primary_symbols=("DBC", "GLD", "SLV", "USO", "XLE", "XLB"),
        positive_label="commodity_strength_inflation_pressure",
        negative_label="commodity_weakness_disinflationary",
        neutral_label="commodity_neutral",
        risk_weight=0.0,
    ),
    ProxyGroupConfig(
        name="dollar",
        primary_symbols=("UUP", "DXY", "DX-Y.NYB"),
        positive_label="dollar_strengthening_tightening_pressure",
        negative_label="dollar_weakening_risk_supportive",
        neutral_label="dollar_neutral",
        risk_weight=-0.5,
    ),
    ProxyGroupConfig(
        name="volatility",
        primary_symbols=("VIXY", "VIXM", "VXX", "UVXY"),
        positive_label="volatility_compression_risk_supportive",
        negative_label="volatility_expansion_risk_review",
        neutral_label="volatility_neutral",
        risk_weight=1.0,
        invert_for_score=True,
    ),
)


def build_regime_market_proxy_overlay(
    market_price_history: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
    *,
    regime_context: Mapping[str, Any] | None = None,
    as_of_date: str | date | datetime | None = None,
    lookback_days: int = 20,
    neutral_threshold: float = 0.0025,
    min_required_groups: int = 4,
) -> dict[str, Any]:
    """
    Build a cross-asset market proxy overlay from normalized market price rows.

    The overlay is a regime confirmation layer only. It does not classify individual
    symbols for trading, choose contracts, choose strikes/expirations, submit orders,
    model fills, or create automatic maintenance/defense actions.
    """

    input_errors = _input_errors(
        market_price_history=market_price_history,
        lookback_days=lookback_days,
        neutral_threshold=neutral_threshold,
        min_required_groups=min_required_groups,
    )
    if input_errors:
        return _blocked_overlay(blocked_reasons=input_errors)

    rows = _extract_price_rows(market_price_history)
    series_by_symbol = _build_series_by_symbol(rows)

    if not series_by_symbol:
        return _blocked_overlay(blocked_reasons=["no usable market price history rows"])

    latest_date = _resolve_as_of_date(series_by_symbol, as_of_date)
    if latest_date is None:
        return _blocked_overlay(blocked_reasons=["unable to resolve as_of_date"])

    proxy_details: dict[str, dict[str, Any]] = {}
    missing_groups: list[str] = []

    for config in PROXY_GROUPS:
        detail = _build_proxy_group_detail(
            config=config,
            series_by_symbol=series_by_symbol,
            as_of_date=latest_date,
            lookback_days=lookback_days,
            neutral_threshold=neutral_threshold,
        )
        if detail is None:
            missing_groups.append(config.name)
            continue
        proxy_details[config.name] = detail

    if not proxy_details:
        return _blocked_overlay(
            as_of_date=latest_date.isoformat(),
            blocked_reasons=["no supported market proxy groups could be calculated"],
        )

    available_group_count = len(proxy_details)
    warnings: list[str] = []
    blocked_reasons: list[str] = []

    if missing_groups:
        warnings.append(
            "missing market proxy groups: " + ", ".join(sorted(missing_groups))
        )

    if available_group_count < min_required_groups:
        warnings.append(
            f"only {available_group_count} market proxy groups available; "
            f"minimum required is {min_required_groups}"
        )

    aggregate = _aggregate_market_confirmation(proxy_details)
    context_summary = _regime_context_summary(regime_context)
    confirmation = _market_confirmation(
        aggregate_bias=aggregate["aggregate_market_bias"],
        context_bias=context_summary.get("context_risk_bias"),
    )

    if confirmation == "market_contradicts_regime":
        warnings.append("market proxies contradict current regime risk bias")

    status = _overlay_status(
        available_group_count=available_group_count,
        min_required_groups=min_required_groups,
        warnings=warnings,
    )

    return {
        "artifact_type": "regime_market_proxy_overlay",
        "schema_version": "signalforge_regime_market_proxy_overlay.v1",
        "status": status,
        "is_ready": status == "ready",
        "as_of_date": latest_date.isoformat(),
        "lookback_days": lookback_days,
        "available_group_count": available_group_count,
        "missing_groups": sorted(missing_groups),
        "market_confirmation": confirmation,
        "aggregate_market_bias": aggregate["aggregate_market_bias"],
        "aggregate_market_score": aggregate["aggregate_market_score"],
        "proxy_summary": {
            name: detail["classification"] for name, detail in sorted(proxy_details.items())
        },
        "proxy_details": dict(sorted(proxy_details.items())),
        "source_symbol_count": len(series_by_symbol),
        "source_symbols": sorted(series_by_symbol),
        "source_regime_context": context_summary,
        "requires_manual_approval": status != "ready" or confirmation == "market_contradicts_regime",
        "warnings": _dedupe_strings(warnings),
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "excluded": EXCLUDED_ACTIONS,
    }


def apply_market_proxy_overlay_to_weekly_regime(
    *,
    weekly_regime: Mapping[str, Any] | None,
    market_proxy_overlay: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    Attach a market proxy overlay to an existing weekly regime artifact.

    This preserves the FRED macro/planning labels and adds confirmation metadata.
    It never rewrites the core macro regime label.
    """

    if not isinstance(weekly_regime, Mapping):
        return {
            "artifact_type": "weekly_regime_with_market_proxy_overlay",
            "status": "blocked",
            "is_ready": False,
            "warnings": [],
            "blocked_reasons": ["weekly_regime must be a mapping"],
            "excluded": EXCLUDED_ACTIONS,
        }

    if not isinstance(market_proxy_overlay, Mapping):
        return {
            "artifact_type": "weekly_regime_with_market_proxy_overlay",
            "status": "blocked",
            "is_ready": False,
            "warnings": [],
            "blocked_reasons": ["market_proxy_overlay must be a mapping"],
            "excluded": EXCLUDED_ACTIONS,
        }

    combined = dict(weekly_regime)
    combined["artifact_type"] = "weekly_regime_with_market_proxy_overlay"
    combined["market_proxy_overlay"] = dict(market_proxy_overlay)
    combined["market_confirmation"] = market_proxy_overlay.get("market_confirmation")
    combined["aggregate_market_bias"] = market_proxy_overlay.get("aggregate_market_bias")
    combined["aggregate_market_score"] = market_proxy_overlay.get("aggregate_market_score")

    warnings = list(_strings(weekly_regime.get("warnings")))
    warnings.extend(_strings(market_proxy_overlay.get("warnings")))

    blocked_reasons = list(_strings(weekly_regime.get("blocked_reasons")))
    blocked_reasons.extend(_strings(market_proxy_overlay.get("blocked_reasons")))

    overlay_status = _clean(market_proxy_overlay.get("status"))
    weekly_status = _clean(weekly_regime.get("status"))
    market_confirmation = _clean(market_proxy_overlay.get("market_confirmation"))

    if weekly_status == "blocked" or overlay_status == "blocked":
        status = "blocked"
    elif market_confirmation == "market_contradicts_regime" or weekly_status == "needs_review" or overlay_status == "needs_review" or warnings:
        status = "needs_review"
    else:
        status = "ready"

    combined["status"] = status
    combined["is_ready"] = status == "ready"
    combined["requires_manual_approval"] = (
        bool(weekly_regime.get("requires_manual_approval"))
        or bool(market_proxy_overlay.get("requires_manual_approval"))
        or status != "ready"
    )
    combined["warnings"] = _dedupe_strings(warnings)
    combined["blocked_reasons"] = _dedupe_strings(blocked_reasons)
    combined["excluded"] = EXCLUDED_ACTIONS

    return combined


def _input_errors(
    *,
    market_price_history: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
    lookback_days: int,
    neutral_threshold: float,
    min_required_groups: int,
) -> list[str]:
    errors: list[str] = []

    if not isinstance(market_price_history, Mapping) and not _is_sequence(market_price_history):
        errors.append("market_price_history must be a mapping or sequence of mappings")

    if lookback_days <= 0:
        errors.append("lookback_days must be positive")

    if neutral_threshold < 0:
        errors.append("neutral_threshold cannot be negative")

    if min_required_groups <= 0:
        errors.append("min_required_groups must be positive")

    return errors


def _extract_price_rows(
    source: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
) -> list[Mapping[str, Any]]:
    if source is None:
        return []

    if _is_sequence(source):
        rows: list[Mapping[str, Any]] = []
        for item in source:  # type: ignore[union-attr]
            rows.extend(_extract_price_rows(item))
        return rows

    if not isinstance(source, Mapping):
        return []

    row_candidate = _row_from_mapping(source)
    if row_candidate is not None:
        return [row_candidate]

    rows = []
    for key in ROW_COLLECTION_KEYS:
        value = source.get(key)
        if value is not None:
            rows.extend(_extract_price_rows(value))

    payload = source.get("payload") or source.get("normalized_payload") or source.get("record")
    if isinstance(payload, Mapping):
        rows.extend(_extract_price_rows(payload))

    return rows


def _row_from_mapping(value: Mapping[str, Any]) -> Mapping[str, Any] | None:
    symbol = _symbol_from_row(value)
    date_value = _date_from_row(value)
    close = _close_from_row(value)

    if symbol and date_value is not None and close is not None:
        return value

    return None


def _build_series_by_symbol(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[tuple[date, float]]]:
    series: dict[str, dict[date, float]] = {}

    for row in rows:
        symbol = _symbol_from_row(row)
        date_value = _date_from_row(row)
        close = _close_from_row(row)

        if not symbol or date_value is None or close is None:
            continue

        series.setdefault(symbol, {})[date_value] = close

    return {
        symbol: sorted(points.items(), key=lambda item: item[0])
        for symbol, points in series.items()
        if len(points) >= 2
    }


def _build_proxy_group_detail(
    *,
    config: ProxyGroupConfig,
    series_by_symbol: Mapping[str, Sequence[tuple[date, float]]],
    as_of_date: date,
    lookback_days: int,
    neutral_threshold: float,
) -> dict[str, Any] | None:
    primary_returns = _returns_for_symbols(
        symbols=config.primary_symbols,
        series_by_symbol=series_by_symbol,
        as_of_date=as_of_date,
        lookback_days=lookback_days,
    )
    comparison_returns = _returns_for_symbols(
        symbols=config.comparison_symbols,
        series_by_symbol=series_by_symbol,
        as_of_date=as_of_date,
        lookback_days=lookback_days,
    )

    if not primary_returns:
        return None

    primary_score = _average(primary_returns.values())
    comparison_score = _average(comparison_returns.values()) if comparison_returns else 0.0
    raw_score = primary_score - comparison_score
    score = -raw_score if config.invert_for_score else raw_score

    classification = _classification_for_score(
        score=score,
        config=config,
        neutral_threshold=neutral_threshold,
    )

    return {
        "classification": classification,
        "score": round(score, 6),
        "raw_score": round(raw_score, 6),
        "primary_score": round(primary_score, 6),
        "comparison_score": round(comparison_score, 6),
        "primary_symbols_used": sorted(primary_returns),
        "comparison_symbols_used": sorted(comparison_returns),
        "primary_returns": {key: round(value, 6) for key, value in sorted(primary_returns.items())},
        "comparison_returns": {key: round(value, 6) for key, value in sorted(comparison_returns.items())},
        "lookback_days": lookback_days,
    }


def _returns_for_symbols(
    *,
    symbols: Sequence[str],
    series_by_symbol: Mapping[str, Sequence[tuple[date, float]]],
    as_of_date: date,
    lookback_days: int,
) -> dict[str, float]:
    output: dict[str, float] = {}

    for symbol in symbols:
        normalized = _normalize_symbol(symbol)
        points = series_by_symbol.get(normalized)
        if not points:
            continue

        computed = _lookback_return(points, as_of_date=as_of_date, lookback_days=lookback_days)
        if computed is not None:
            output[normalized] = computed

    return output


def _lookback_return(
    points: Sequence[tuple[date, float]],
    *,
    as_of_date: date,
    lookback_days: int,
) -> float | None:
    available = [(point_date, value) for point_date, value in points if point_date <= as_of_date]
    if len(available) < 2:
        return None

    end_date, end_value = available[-1]
    target = end_date - timedelta(days=lookback_days)

    start_candidates = [(point_date, value) for point_date, value in available if point_date <= target]
    if start_candidates:
        _, start_value = start_candidates[-1]
    else:
        _, start_value = available[0]

    if start_value == 0:
        return None

    return (end_value / start_value) - 1.0


def _aggregate_market_confirmation(
    proxy_details: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    weighted_scores: list[float] = []

    config_by_name = {config.name: config for config in PROXY_GROUPS}
    for name, detail in proxy_details.items():
        config = config_by_name.get(name)
        if config is None or config.risk_weight == 0:
            continue
        weighted_scores.append(_float(detail.get("score")) * config.risk_weight)

    if not weighted_scores:
        return {
            "aggregate_market_bias": "insufficient_market_confirmation",
            "aggregate_market_score": 0.0,
        }

    score = _average(weighted_scores)

    if score > 0.0025:
        bias = "risk_on_confirmation"
    elif score < -0.0025:
        bias = "risk_off_confirmation"
    else:
        bias = "mixed_market_confirmation"

    return {
        "aggregate_market_bias": bias,
        "aggregate_market_score": round(score, 6),
    }


def _market_confirmation(
    *,
    aggregate_bias: str,
    context_bias: str | None,
) -> str:
    if aggregate_bias == "insufficient_market_confirmation":
        return "insufficient_market_confirmation"

    if not context_bias or context_bias == "neutral":
        if aggregate_bias == "risk_on_confirmation":
            return "market_confirms_risk_on"
        if aggregate_bias == "risk_off_confirmation":
            return "market_confirms_risk_off"
        return "partial_market_confirmation"

    if context_bias == "risk_on" and aggregate_bias == "risk_on_confirmation":
        return "market_confirms_regime"

    if context_bias == "risk_off" and aggregate_bias == "risk_off_confirmation":
        return "market_confirms_regime"

    if context_bias == "risk_on" and aggregate_bias == "risk_off_confirmation":
        return "market_contradicts_regime"

    if context_bias == "risk_off" and aggregate_bias == "risk_on_confirmation":
        return "market_contradicts_regime"

    return "partial_market_confirmation"


def _classification_for_score(
    *,
    score: float,
    config: ProxyGroupConfig,
    neutral_threshold: float,
) -> str:
    if abs(score) <= neutral_threshold:
        return config.neutral_label

    if score > 0:
        return config.positive_label

    return config.negative_label


def _regime_context_summary(regime_context: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(regime_context, Mapping):
        return {}

    risk_environment = _clean(
        regime_context.get("risk_environment")
        or regime_context.get("weekly_risk_environment")
    )
    regime_label = _clean(
        regime_context.get("policy_regime_label")
        or regime_context.get("weekly_planning_label")
        or regime_context.get("macro_regime")
        or regime_context.get("regime_label")
        or regime_context.get("macro_regime_label")
    )

    context_risk_bias = _context_risk_bias(
        risk_environment=risk_environment,
        regime_label=regime_label,
    )

    return {
        "artifact_type": regime_context.get("artifact_type"),
        "status": regime_context.get("status"),
        "regime_label": regime_context.get("regime_label") or regime_context.get("macro_regime_label"),
        "macro_regime": regime_context.get("macro_regime"),
        "macro_regime_score": regime_context.get("macro_regime_score"),
        "macro_regime_confidence": regime_context.get("macro_regime_confidence"),
        "macro_regime_drivers": regime_context.get("macro_regime_drivers"),
        "selected_regime_context_label": regime_label,
        "weekly_planning_label": regime_context.get("weekly_planning_label"),
        "policy_regime_label": regime_context.get("policy_regime_label"),
        "risk_environment": regime_context.get("risk_environment") or regime_context.get("weekly_risk_environment"),
        "volatility_regime": regime_context.get("volatility_regime") or regime_context.get("weekly_volatility_regime"),
        "liquidity_regime": regime_context.get("liquidity_regime") or regime_context.get("weekly_liquidity_regime"),
        "context_risk_bias": context_risk_bias,
    }


def _context_risk_bias(*, risk_environment: str, regime_label: str) -> str:
    if risk_environment in {"risk_on", "strong_risk_on"}:
        return "risk_on"
    if risk_environment in {"risk_off", "strong_risk_off"}:
        return "risk_off"

    if regime_label in {"goldilocks", "reflation", "risk_on", "strong_risk_on"}:
        return "risk_on"
    if regime_label in {
        "stagflation",
        "disinflationary_slowdown",
        "deflationary_shock",
        "credit_stress",
        "liquidity_stress",
        "risk_off_transition",
        "risk_off",
        "strong_risk_off",
        "event_risk",
    }:
        return "risk_off"

    return "neutral"


def _overlay_status(
    *,
    available_group_count: int,
    min_required_groups: int,
    warnings: Sequence[str],
) -> str:
    if available_group_count <= 0:
        return "blocked"

    if available_group_count < min_required_groups:
        return "needs_review"

    if warnings:
        return "needs_review"

    return "ready"


def _blocked_overlay(
    *,
    as_of_date: str | None = None,
    warnings: Sequence[str] | None = None,
    blocked_reasons: Sequence[str] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "regime_market_proxy_overlay",
        "schema_version": "signalforge_regime_market_proxy_overlay.v1",
        "status": "blocked",
        "is_ready": False,
        "as_of_date": as_of_date,
        "lookback_days": None,
        "available_group_count": 0,
        "missing_groups": sorted(SUPPORTED_PROXY_GROUPS),
        "market_confirmation": "insufficient_market_confirmation",
        "aggregate_market_bias": "insufficient_market_confirmation",
        "aggregate_market_score": 0.0,
        "proxy_summary": {},
        "proxy_details": {},
        "source_symbol_count": 0,
        "source_symbols": [],
        "source_regime_context": {},
        "requires_manual_approval": True,
        "warnings": _dedupe_strings(warnings or []),
        "blocked_reasons": _dedupe_strings(blocked_reasons or []),
        "excluded": EXCLUDED_ACTIONS,
    }


def _resolve_as_of_date(
    series_by_symbol: Mapping[str, Sequence[tuple[date, float]]],
    as_of_date: str | date | datetime | None,
) -> date | None:
    if as_of_date is not None:
        return _parse_date(as_of_date)

    latest: date | None = None
    for points in series_by_symbol.values():
        if not points:
            continue
        point_date = points[-1][0]
        if latest is None or point_date > latest:
            latest = point_date

    return latest


def _symbol_from_row(row: Mapping[str, Any]) -> str | None:
    value = (
        row.get("symbol")
        or row.get("ticker")
        or row.get("asset")
        or row.get("instrument")
    )
    normalized = _normalize_symbol(value)
    return normalized or None


def _date_from_row(row: Mapping[str, Any]) -> date | None:
    value = (
        row.get("timestamp")
        or row.get("date")
        or row.get("time")
        or row.get("datetime")
    )
    return _parse_date(value)


def _close_from_row(row: Mapping[str, Any]) -> float | None:
    for key in ("adjusted_close", "adj_close", "close", "c", "value"):
        value = row.get(key)
        parsed = _maybe_float(value)
        if parsed is not None:
            return parsed

    return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None


def _normalize_symbol(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip().upper()


def _maybe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None

    return parsed


def _float(value: Any) -> float:
    parsed = _maybe_float(value)
    return parsed if parsed is not None else 0.0


def _average(values: Sequence[float]) -> float:
    clean_values = [float(value) for value in values]
    if not clean_values:
        return 0.0

    return sum(clean_values) / len(clean_values)


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _clean(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip().lower()


def _strings(value: Any) -> list[str]:
    if not _is_sequence(value):
        return []

    return [_clean(item) for item in value if _clean(item)]


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []

    for value in values:
        cleaned = _clean(value)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            output.append(cleaned)

    return output
