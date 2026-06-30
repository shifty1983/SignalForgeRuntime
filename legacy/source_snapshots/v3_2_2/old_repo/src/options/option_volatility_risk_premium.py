from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


OPTION_VOLATILITY_RISK_PREMIUM_SCHEMA_VERSION = (
    "signalforge_option_volatility_risk_premium.v1"
)

DEFAULT_RICH_RATIO_THRESHOLD = 1.10
DEFAULT_CHEAP_RATIO_THRESHOLD = 0.90
DEFAULT_WIDE_SPREAD_THRESHOLD = 0.05
DEFAULT_ANNUALIZATION_FACTOR = 252
DEFAULT_MIN_RETURN_OBSERVATIONS = 10


class _MissingType:
    pass


_MISSING = _MissingType()


def build_signalforge_option_volatility_risk_premium(
    iv_history_source: Mapping[str, Any] | Sequence[Any] | None,
    realized_volatility_source: Mapping[str, Any] | Sequence[Any] | None,
    *,
    rich_ratio_threshold: float = DEFAULT_RICH_RATIO_THRESHOLD,
    cheap_ratio_threshold: float = DEFAULT_CHEAP_RATIO_THRESHOLD,
    wide_spread_threshold: float = DEFAULT_WIDE_SPREAD_THRESHOLD,
    annualization_factor: int = DEFAULT_ANNUALIZATION_FACTOR,
    min_return_observations: int = DEFAULT_MIN_RETURN_OBSERVATIONS,
) -> dict[str, Any]:
    """Classify implied volatility richness versus realized volatility.

    This artifact is a strategy-selection bridge. It consumes compact IV
    history snapshots plus asset/price-derived realized volatility and emits
    one per-symbol volatility-risk-premium label. It does not export raw option
    chains or route orders.
    """

    threshold_error = _threshold_error(
        rich_ratio_threshold=rich_ratio_threshold,
        cheap_ratio_threshold=cheap_ratio_threshold,
        wide_spread_threshold=wide_spread_threshold,
        annualization_factor=annualization_factor,
        min_return_observations=min_return_observations,
    )
    if threshold_error:
        return _blocked_result(threshold_error)

    iv_items, malformed_iv_items = _extract_iv_items(iv_history_source)
    if not iv_items:
        return _blocked_result("IV history source contains no usable IV items")

    realized_items, malformed_realized_items = _extract_realized_volatility_items(
        realized_volatility_source,
        annualization_factor=annualization_factor,
        min_return_observations=min_return_observations,
    )
    if not realized_items:
        return _blocked_result(
            "realized volatility source contains no usable realized volatility items"
        )

    realized_by_symbol = {
        item["symbol"]: item for item in realized_items if item.get("symbol")
    }

    items = [
        _build_premium_item(
            iv_item=iv_item,
            realized_item=realized_by_symbol.get(iv_item["symbol"]),
            rich_ratio_threshold=rich_ratio_threshold,
            cheap_ratio_threshold=cheap_ratio_threshold,
            wide_spread_threshold=wide_spread_threshold,
        )
        for iv_item in iv_items
    ]

    ready_count = sum(1 for item in items if item["coverage_status"] == "ready")
    needs_review_count = len(items) - ready_count
    malformed_count = len(malformed_iv_items) + len(malformed_realized_items)
    status = "ready" if needs_review_count == 0 and malformed_count == 0 else "needs_review"
    summary = _summary(items, malformed_count)

    return {
        "artifact_type": "signalforge_option_volatility_risk_premium",
        "schema_version": OPTION_VOLATILITY_RISK_PREMIUM_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "option_volatility_risk_premium",
        "adapter_type": "option_volatility_risk_premium_builder",
        "review_scope": "iv_versus_realized_volatility_strategy_selection_bridge",
        "source_artifacts": {
            "iv_history_source": _source_artifact_type(iv_history_source),
            "realized_volatility_source": _source_artifact_type(realized_volatility_source),
        },
        "thresholds": {
            "rich_ratio_threshold": rich_ratio_threshold,
            "cheap_ratio_threshold": cheap_ratio_threshold,
            "wide_spread_threshold": wide_spread_threshold,
            "annualization_factor": annualization_factor,
            "min_return_observations": min_return_observations,
        },
        "covered_capabilities": ["volatility_risk_premium"],
        "depends_on_capabilities": ["iv_rank_percentile", "asset_realized_volatility"],
        "next_build_recommendations": [
            {
                "capability": "options_behavior_integration",
                "priority": "medium",
                "recommendation": "Merge IV, gamma, theta, volatility risk premium, skew, term structure, and liquidity into a unified Options Behavior decision artifact.",
            }
        ],
        "option_volatility_risk_premium_items": items,
        "option_volatility_risk_premium_summary": summary,
        "malformed_iv_items": malformed_iv_items[:100],
        "malformed_realized_volatility_items": malformed_realized_items[:100],
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_premium_item(
    *,
    iv_item: Mapping[str, Any],
    realized_item: Mapping[str, Any] | None,
    rich_ratio_threshold: float,
    cheap_ratio_threshold: float,
    wide_spread_threshold: float,
) -> dict[str, Any]:
    symbol = _clean_symbol(iv_item.get("symbol")) or "UNKNOWN"
    current_iv = _clean_float(
        _first_present(
            iv_item,
            (
                "current_implied_volatility",
                "implied_volatility",
                "current_iv",
                "atm_iv",
            ),
        )
    )

    realized_20d = None
    realized_60d = None
    selected_rv = None
    selected_window = None
    realized_source = None
    return_observation_count = None

    if realized_item is not None:
        realized_20d = _clean_float(realized_item.get("realized_volatility_20d"))
        realized_60d = _clean_float(realized_item.get("realized_volatility_60d"))
        selected_rv = _clean_float(realized_item.get("selected_realized_volatility"))
        if selected_rv is None:
            selected_rv = _clean_float(realized_item.get("realized_volatility"))
        if selected_rv is None:
            selected_rv = realized_20d if realized_20d is not None else realized_60d
        selected_window = _clean_text(realized_item.get("selected_realized_volatility_window"))
        if selected_window is None:
            if selected_rv is not None and realized_20d is not None and math.isclose(selected_rv, realized_20d):
                selected_window = "20d"
            elif selected_rv is not None and realized_60d is not None and math.isclose(selected_rv, realized_60d):
                selected_window = "60d"
            elif selected_rv is not None:
                selected_window = "source_realized_volatility"
        realized_source = _clean_text(realized_item.get("realized_volatility_source"))
        return_observation_count = realized_item.get("return_observation_count")

    state, reasons = _premium_state(
        current_iv=current_iv,
        selected_realized_volatility=selected_rv,
        rich_ratio_threshold=rich_ratio_threshold,
        cheap_ratio_threshold=cheap_ratio_threshold,
        wide_spread_threshold=wide_spread_threshold,
        realized_item_present=realized_item is not None,
    )
    coverage_status = "ready" if state != "needs_review" else "needs_review"

    iv_vs_rv_spread = None
    iv_vs_rv_ratio = None
    if current_iv is not None and selected_rv is not None and selected_rv > 0:
        iv_vs_rv_spread = current_iv - selected_rv
        iv_vs_rv_ratio = current_iv / selected_rv

    return {
        "artifact_type": "option_volatility_risk_premium_item",
        "symbol": symbol,
        "coverage_status": coverage_status,
        "volatility_risk_premium_state": state,
        "volatility_risk_premium_reasons": reasons,
        "current_implied_volatility": _round(current_iv),
        "realized_volatility_20d": _round(realized_20d),
        "realized_volatility_60d": _round(realized_60d),
        "selected_realized_volatility": _round(selected_rv),
        "selected_realized_volatility_window": selected_window,
        "realized_volatility_source": realized_source,
        "return_observation_count": return_observation_count,
        "iv_vs_rv_spread": _round(iv_vs_rv_spread),
        "iv_vs_rv_ratio": _round(iv_vs_rv_ratio),
        "premium_bias": _premium_bias(state),
        "strategy_family_bias": _strategy_family_bias(state),
        "iv_rank_state": iv_item.get("iv_rank_state"),
        "iv_percentile_state": iv_item.get("iv_percentile_state"),
        "current_quote_date": iv_item.get("current_quote_date"),
        "manual_review_required": coverage_status != "ready",
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _premium_state(
    *,
    current_iv: float | None,
    selected_realized_volatility: float | None,
    rich_ratio_threshold: float,
    cheap_ratio_threshold: float,
    wide_spread_threshold: float,
    realized_item_present: bool,
) -> tuple[str, list[str]]:
    if not realized_item_present:
        return "needs_review", ["missing_realized_volatility_match"]
    if current_iv is None or current_iv <= 0:
        return "needs_review", ["missing_current_implied_volatility"]
    if selected_realized_volatility is None or selected_realized_volatility <= 0:
        return "needs_review", ["missing_or_invalid_realized_volatility"]

    spread = current_iv - selected_realized_volatility
    ratio = current_iv / selected_realized_volatility

    if ratio <= cheap_ratio_threshold:
        return "iv_cheap_vs_realized", ["iv_to_realized_ratio_below_cheap_threshold"]
    if ratio >= rich_ratio_threshold or spread >= wide_spread_threshold:
        return "iv_rich_vs_realized", ["iv_to_realized_ratio_or_spread_above_rich_threshold"]
    if spread < 0:
        return "realized_vol_above_iv", ["realized_volatility_slightly_above_implied_volatility"]
    return "iv_fair_vs_realized", ["iv_close_to_realized_volatility"]


def _premium_bias(state: str) -> str:
    if state == "iv_rich_vs_realized":
        return "short_premium_bias"
    if state in {"iv_cheap_vs_realized", "realized_vol_above_iv"}:
        return "long_premium_bias"
    if state == "iv_fair_vs_realized":
        return "neutral_premium_bias"
    return "needs_review"


def _strategy_family_bias(state: str) -> str:
    if state == "iv_rich_vs_realized":
        return "credit_spread_or_short_premium_candidate"
    if state == "iv_cheap_vs_realized":
        return "debit_spread_or_long_gamma_candidate"
    if state == "realized_vol_above_iv":
        return "long_gamma_or_directional_convexity_candidate"
    if state == "iv_fair_vs_realized":
        return "structure_selection_depends_on_directional_edge"
    return "needs_review"


def _extract_iv_items(
    source: Mapping[str, Any] | Sequence[Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_items = _extract_items(
        source,
        (
            "option_iv_history_items",
            "iv_history_items",
            "option_volatility_items",
            "items",
            "data",
            "rows",
        ),
    )
    items: list[dict[str, Any]] = []
    malformed: list[dict[str, Any]] = []

    for index, item in enumerate(raw_items):
        if not isinstance(item, Mapping):
            malformed.append({"row_index": index, "reason": "IV item must be a mapping"})
            continue
        symbol = _clean_symbol(item.get("symbol"))
        current_iv = _clean_float(
            _first_present(
                item,
                (
                    "current_implied_volatility",
                    "implied_volatility",
                    "current_iv",
                    "atm_iv",
                ),
            )
        )
        if symbol is None:
            malformed.append({"row_index": index, "reason": "missing IV item symbol"})
            continue
        if current_iv is None or current_iv <= 0:
            malformed.append(
                {"row_index": index, "symbol": symbol, "reason": "missing current IV"}
            )
            continue
        clean_item = dict(item)
        clean_item["symbol"] = symbol
        clean_item["current_implied_volatility"] = current_iv
        items.append(clean_item)

    return sorted(items, key=lambda row: row["symbol"]), malformed


def _extract_realized_volatility_items(
    source: Mapping[str, Any] | Sequence[Any] | None,
    *,
    annualization_factor: int,
    min_return_observations: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if source is None:
        return [], []

    if isinstance(source, Mapping) and _looks_like_price_history_source(source):
        return _realized_volatility_from_price_history(
            _extract_items(source, ("normalized_payloads", "price_rows", "rows", "data")),
            annualization_factor=annualization_factor,
            min_return_observations=min_return_observations,
        )

    raw_items = _extract_items(
        source,
        (
            "realized_volatility_rows",
            "volatility_rows",
            "asset_behaviors",
            "asset_behavior_items",
            "items",
            "data",
            "rows",
        ),
    )
    if raw_items and any(_looks_like_price_row(item) for item in raw_items if isinstance(item, Mapping)):
        return _realized_volatility_from_price_history(
            raw_items,
            annualization_factor=annualization_factor,
            min_return_observations=min_return_observations,
        )

    items: list[dict[str, Any]] = []
    malformed: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, Mapping):
            malformed.append(
                {"row_index": index, "reason": "realized volatility item must be a mapping"}
            )
            continue
        symbol = _clean_symbol(
            _first_present(item, ("symbol", "underlying_symbol", "ticker", "underlying"))
        )
        if symbol is None:
            malformed.append({"row_index": index, "reason": "missing realized volatility symbol"})
            continue

        realized_20d = _clean_float(
            _first_present(
                item,
                (
                    "realized_volatility_20d",
                    "realized_vol_20d",
                    "historical_volatility_20d",
                    "hv_20d",
                ),
            )
        )
        realized_60d = _clean_float(
            _first_present(
                item,
                (
                    "realized_volatility_60d",
                    "realized_vol_60d",
                    "historical_volatility_60d",
                    "hv_60d",
                ),
            )
        )
        realized = _clean_float(
            _first_present(
                item,
                (
                    "selected_realized_volatility",
                    "realized_volatility",
                    "historical_volatility",
                    "annualized_volatility",
                ),
            )
        )
        selected = realized if realized is not None else realized_20d or realized_60d
        if selected is None or selected <= 0:
            malformed.append(
                {
                    "row_index": index,
                    "symbol": symbol,
                    "reason": "missing usable realized volatility",
                }
            )
            continue

        clean_item = dict(item)
        clean_item.update(
            {
                "symbol": symbol,
                "realized_volatility_20d": realized_20d,
                "realized_volatility_60d": realized_60d,
                "selected_realized_volatility": selected,
                "selected_realized_volatility_window": _selected_window(
                    selected=selected,
                    realized_20d=realized_20d,
                    realized_60d=realized_60d,
                    source_window=_clean_text(
                        item.get("selected_realized_volatility_window")
                    ),
                ),
                "realized_volatility_source": _clean_text(
                    item.get("realized_volatility_source")
                )
                or "source_realized_volatility_item",
            }
        )
        items.append(clean_item)

    return sorted(items, key=lambda row: row["symbol"]), malformed


def _realized_volatility_from_price_history(
    raw_rows: Sequence[Any],
    *,
    annualization_factor: int,
    min_return_observations: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    malformed: list[dict[str, Any]] = []

    for index, row in enumerate(raw_rows):
        if not isinstance(row, Mapping):
            malformed.append({"row_index": index, "reason": "price row must be a mapping"})
            continue
        symbol = _clean_symbol(row.get("symbol"))
        timestamp = _clean_text(_first_present(row, ("timestamp", "date", "quote_date")))
        close = _clean_float(_first_present(row, ("adjusted_close", "close", "Close")))
        if symbol is None or timestamp is None or close is None or close <= 0:
            malformed.append({"row_index": index, "reason": "missing symbol/timestamp/close"})
            continue
        rows_by_symbol[symbol].append(
            {"symbol": symbol, "timestamp": timestamp, "close": close}
        )

    items: list[dict[str, Any]] = []
    for symbol, rows in sorted(rows_by_symbol.items()):
        ordered_rows = sorted(rows, key=lambda row: str(row["timestamp"]))
        closes = [row["close"] for row in ordered_rows]
        returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
        realized_20d = _annualized_stdev(
            returns[-20:], annualization_factor, min_return_observations
        )
        realized_60d = _annualized_stdev(
            returns[-60:], annualization_factor, min_return_observations
        )
        selected = realized_20d if realized_20d is not None else realized_60d
        if selected is None:
            malformed.append(
                {
                    "symbol": symbol,
                    "reason": "insufficient_price_returns_for_realized_volatility",
                }
            )
            continue
        items.append(
            {
                "symbol": symbol,
                "realized_volatility_20d": realized_20d,
                "realized_volatility_60d": realized_60d,
                "selected_realized_volatility": selected,
                "selected_realized_volatility_window": "20d" if realized_20d is not None else "60d",
                "realized_volatility_source": "computed_from_market_price_history",
                "return_observation_count": len(returns),
                "start_timestamp": ordered_rows[0]["timestamp"],
                "end_timestamp": ordered_rows[-1]["timestamp"],
            }
        )

    return items, malformed


def _annualized_stdev(
    returns: Sequence[float], annualization_factor: int, min_return_observations: int
) -> float | None:
    values = [value for value in returns if value is not None]
    if len(values) < min_return_observations:
        return None
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / max(len(values) - 1, 1)
    return math.sqrt(variance) * math.sqrt(annualization_factor)


def _looks_like_price_history_source(source: Mapping[str, Any]) -> bool:
    if "normalized_payloads" in source:
        return True
    artifact_type = _clean_text(source.get("artifact_type")) or ""
    return artifact_type == "signalforge_market_price_history_import"


def _looks_like_price_row(item: Mapping[str, Any]) -> bool:
    return (
        _first_present(item, ("adjusted_close", "close", "Close")) is not None
        and _first_present(item, ("timestamp", "date", "quote_date")) is not None
    )


def _selected_window(
    *,
    selected: float,
    realized_20d: float | None,
    realized_60d: float | None,
    source_window: str | None,
) -> str:
    if source_window:
        return source_window
    if realized_20d is not None and math.isclose(selected, realized_20d):
        return "20d"
    if realized_60d is not None and math.isclose(selected, realized_60d):
        return "60d"
    return "source_realized_volatility"


def _summary(items: Sequence[Mapping[str, Any]], malformed_count: int) -> dict[str, Any]:
    coverage_counts = Counter(_clean_text(item.get("coverage_status")) for item in items)
    state_counts = Counter(
        _clean_text(item.get("volatility_risk_premium_state")) for item in items
    )
    premium_bias_counts = Counter(_clean_text(item.get("premium_bias")) for item in items)
    strategy_bias_counts = Counter(
        _clean_text(item.get("strategy_family_bias")) for item in items
    )

    return {
        "symbol_count": len(items),
        "ready_symbol_count": coverage_counts.get("ready", 0),
        "needs_review_symbol_count": coverage_counts.get("needs_review", 0),
        "malformed_item_count": malformed_count,
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "volatility_risk_premium_state_counts": dict(sorted(state_counts.items())),
        "premium_bias_counts": dict(sorted(premium_bias_counts.items())),
        "strategy_family_bias_counts": dict(sorted(strategy_bias_counts.items())),
        "covered_capabilities": ["volatility_risk_premium"],
    }


def _extract_items(source: Any, keys: Sequence[str]) -> list[Any]:
    if source is None:
        return []
    if isinstance(source, Mapping):
        for key in keys:
            value = source.get(key)
            if isinstance(value, Sequence) and not isinstance(
                value, (str, bytes, bytearray),
            ):
                return list(value)
        return []
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return list(source)
    return []


def _threshold_error(
    *,
    rich_ratio_threshold: float,
    cheap_ratio_threshold: float,
    wide_spread_threshold: float,
    annualization_factor: int,
    min_return_observations: int,
) -> str | None:
    if rich_ratio_threshold <= 1:
        return "rich_ratio_threshold must be greater than 1"
    if cheap_ratio_threshold <= 0 or cheap_ratio_threshold >= 1:
        return "cheap_ratio_threshold must be greater than 0 and less than 1"
    if cheap_ratio_threshold >= rich_ratio_threshold:
        return "cheap_ratio_threshold must be less than rich_ratio_threshold"
    if wide_spread_threshold < 0:
        return "wide_spread_threshold must be greater than or equal to 0"
    if annualization_factor <= 0:
        return "annualization_factor must be greater than 0"
    if min_return_observations < 2:
        return "min_return_observations must be at least 2"
    return None


def _blocked_result(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_option_volatility_risk_premium",
        "schema_version": OPTION_VOLATILITY_RISK_PREMIUM_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "option_volatility_risk_premium",
        "adapter_type": "option_volatility_risk_premium_builder",
        "review_scope": "iv_versus_realized_volatility_strategy_selection_bridge",
        "blocker_items": [{"reason": reason}],
        "covered_capabilities": ["volatility_risk_premium"],
        "option_volatility_risk_premium_items": [],
        "option_volatility_risk_premium_summary": {
            "symbol_count": 0,
            "ready_symbol_count": 0,
            "needs_review_symbol_count": 0,
            "malformed_item_count": 0,
        },
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _source_artifact_type(source: Mapping[str, Any] | Sequence[Any] | None) -> str | None:
    if isinstance(source, Mapping):
        artifact_type = _clean_text(source.get("artifact_type"))
        return artifact_type or "mapping"
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return "sequence"
    return None


def _first_present(row: Mapping[str, Any], names: Sequence[str]) -> Any:
    for name in names:
        value = row.get(name, _MISSING)
        if value is not _MISSING and value is not None:
            return value
    return None


def _clean_symbol(value: Any) -> str | None:
    text = _clean_text(value)
    if text is None:
        return None
    return text.split(" ")[0].upper()


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 6)
