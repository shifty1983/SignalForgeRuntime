from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


ASSET_BEHAVIOR_SELECTION_SCHEMA_VERSION = "signalforge_asset_behavior_selection.v1"

_SELECTION_BUCKETS = {"preferred", "allowed", "needs_review", "blocked"}
_DEFAULT_UNKNOWN_ASSET_CLASS = "unknown"


def build_signalforge_asset_behavior_selection(
    asset_behavior_source: Mapping[str, Any] | None,
    *,
    regime_source: Mapping[str, Any] | None = None,
    asset_class_by_symbol: Mapping[str, str] | None = None,
    symbols: Sequence[str] | None = None,
) -> dict[str, Any]:
    """
    Build a symbol-level asset behavior selection artifact.

    This reviews already-built asset behavior against optional regime and
    asset-class policy context. It does not call brokers, submit orders, route
    orders, model fills, perform live execution, model slippage, or make
    automatic strategy/parameter/pause changes.
    """

    if not isinstance(asset_behavior_source, Mapping):
        return _blocked_result("asset behavior source must be a mapping")

    asset_behaviors = asset_behavior_source.get("asset_behaviors")
    if not isinstance(asset_behaviors, Sequence) or isinstance(
        asset_behaviors, (str, bytes, bytearray)
    ):
        return _blocked_result("asset behavior source must contain asset_behaviors list")

    requested_symbols = _normalize_symbols(symbols)
    asset_class_lookup = _normalize_asset_class_lookup(asset_class_by_symbol)
    asset_class_policy = _extract_asset_class_policy(regime_source)

    candidates: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []
    warning_items: list[dict[str, Any]] = []
    blocker_items: list[dict[str, Any]] = []

    for index, item in enumerate(asset_behaviors):
        if not isinstance(item, Mapping):
            skipped_items.append(
                {
                    "reason": "asset behavior item must be a mapping",
                    "item_index": index,
                }
            )
            continue

        symbol = _clean_symbol(item.get("symbol"))
        if symbol is None:
            skipped_items.append(
                {
                    "reason": "asset behavior item missing symbol",
                    "item_index": index,
                }
            )
            continue

        if requested_symbols is not None and symbol not in requested_symbols:
            continue

        asset_class = asset_class_lookup.get(symbol, _infer_asset_class(symbol))
        policy = asset_class_policy.get(asset_class, _default_policy(asset_class))

        candidate = _build_candidate(
            behavior=item,
            symbol=symbol,
            asset_class=asset_class,
            policy=policy,
        )
        candidates.append(candidate)

    if requested_symbols is not None:
        observed = {candidate["symbol"] for candidate in candidates}
        for missing_symbol in sorted(requested_symbols - observed):
            warning_items.append(
                {
                    "reason": "requested symbol did not produce an asset behavior candidate",
                    "symbol": missing_symbol,
                }
            )

    if not candidates:
        blocker_items.append({"reason": "no asset behavior candidates were produced"})

    source_status = _clean_text(asset_behavior_source.get("status"))
    if source_status not in {None, "ready"}:
        warning_items.append(
            {
                "reason": "asset behavior source is not ready",
                "source_status": source_status,
            }
        )

    selection_summary = _selection_summary(candidates)

    if blocker_items:
        status = "blocked"
    elif warning_items:
        status = "needs_review"
    else:
        status = "ready"

    return {
        "artifact_type": "signalforge_asset_behavior_selection",
        "schema_version": ASSET_BEHAVIOR_SELECTION_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "asset_behavior_selection",
        "adapter_type": "asset_behavior_selection_builder",
        "source_artifact_type": asset_behavior_source.get("artifact_type"),
        "source_status": asset_behavior_source.get("status"),
        "source_kind": asset_behavior_source.get("source_kind"),
        "regime_artifact_type": regime_source.get("artifact_type") if isinstance(regime_source, Mapping) else None,
        "regime_status": regime_source.get("status") if isinstance(regime_source, Mapping) else None,
        "macro_regime_label": regime_source.get("macro_regime_label") if isinstance(regime_source, Mapping) else None,
        "policy_regime_label": regime_source.get("policy_regime_label") if isinstance(regime_source, Mapping) else None,
        "weekly_planning_label": regime_source.get("weekly_planning_label") if isinstance(regime_source, Mapping) else None,
        "market_confirmation": regime_source.get("market_confirmation") if isinstance(regime_source, Mapping) else None,
        "candidates": sorted(candidates, key=lambda item: (item["selection_rank"], item["symbol"])),
        "skipped_items": skipped_items,
        "selection_summary": selection_summary,
        "blocker_items": blocker_items,
        "warning_items": _dedupe_items(warning_items),
        "requested_symbols": sorted(requested_symbols) if requested_symbols is not None else None,
        "observed_symbol_count": len(candidates),
        "observed_symbols": sorted(candidate["symbol"] for candidate in candidates),
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_candidate(
    *,
    behavior: Mapping[str, Any],
    symbol: str,
    asset_class: str,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    behavior_state = _clean_text(behavior.get("behavior_state"))
    trend_behavior = _clean_text(behavior.get("trend_behavior"))
    return_behavior = _clean_text(behavior.get("return_behavior"))
    volatility_behavior = _clean_text(behavior.get("volatility_behavior"))
    drawdown_behavior = _clean_text(behavior.get("drawdown_behavior"))
    behavior_status = _clean_text(behavior.get("status"))

    policy_bucket = _clean_bucket(
        policy.get("policy_bucket")
        or policy.get("bucket")
        or policy.get("status")
        or policy.get("action")
    )

    selection_bucket, reasons = _selection_bucket_and_reasons(
        behavior_state=behavior_state,
        trend_behavior=trend_behavior,
        return_behavior=return_behavior,
        behavior_status=behavior_status,
        policy_bucket=policy_bucket,
    )

    return {
        "artifact_type": "asset_behavior_selection_candidate",
        "symbol": symbol,
        "asset_class": asset_class,
        "status": "ready" if selection_bucket != "blocked" else "blocked",
        "selection_bucket": selection_bucket,
        "selection_rank": _selection_rank(selection_bucket),
        "selection_reasons": reasons,
        "as_of_date": behavior.get("as_of_date"),
        "source_row_count": behavior.get("source_row_count"),
        "period_return": behavior.get("period_return"),
        "behavior_score": behavior.get("behavior_score"),
        "behavior_state": behavior_state,
        "trend_behavior": trend_behavior,
        "return_behavior": return_behavior,
        "volatility_behavior": volatility_behavior,
        "drawdown_behavior": drawdown_behavior,
        "asset_class_policy_bucket": policy_bucket,
        "asset_class_policy_reason": policy.get("reason") or policy.get("policy_reason"),
        "warnings": list(behavior.get("warnings") or []),
        "blocked_reasons": list(behavior.get("blocked_reasons") or []),
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _selection_bucket_and_reasons(
    *,
    behavior_state: str | None,
    trend_behavior: str | None,
    return_behavior: str | None,
    behavior_status: str | None,
    policy_bucket: str,
) -> tuple[str, list[str]]:
    reasons: list[str] = []

    if behavior_status not in {None, "ready"}:
        reasons.append(f"behavior_status_{behavior_status}")
        return "blocked", reasons

    if policy_bucket == "blocked":
        reasons.append("asset_class_policy_blocked")
        return "blocked", reasons

    if behavior_state == "defensive":
        reasons.append("defensive_behavior_state")
        return "needs_review", reasons

    if trend_behavior == "downtrend":
        reasons.append("downtrend_behavior")
        return "needs_review", reasons

    if return_behavior == "negative":
        reasons.append("negative_return_behavior")
        return "needs_review", reasons

    if policy_bucket == "needs_review":
        reasons.append("asset_class_policy_needs_review")
        return "needs_review", reasons

    if behavior_state == "constructive" and trend_behavior == "uptrend":
        if policy_bucket == "preferred":
            reasons.append("constructive_uptrend_preferred_asset_class")
            return "preferred", reasons

        reasons.append("constructive_uptrend_allowed")
        return "allowed", reasons

    if behavior_state == "neutral":
        reasons.append("neutral_behavior_state")
        return "allowed", reasons

    reasons.append("behavior_requires_review")
    return "needs_review", reasons


def _extract_asset_class_policy(
    regime_source: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    if not isinstance(regime_source, Mapping):
        return {}

    policy_source = (
        regime_source.get("latest_regime_asset_class_policy")
        or regime_source.get("asset_class_policy")
        or regime_source.get("asset_class_policies")
    )

    return _normalize_policy_source(policy_source)


def _normalize_policy_source(policy_source: Any) -> dict[str, dict[str, Any]]:
    if not policy_source:
        return {}

    if isinstance(policy_source, Mapping):
        if isinstance(policy_source.get("asset_class_policies"), Sequence):
            return _normalize_policy_source(policy_source.get("asset_class_policies"))

        normalized: dict[str, dict[str, Any]] = {}

        for key, value in policy_source.items():
            if isinstance(value, Mapping):
                asset_class = _clean_text(value.get("asset_class") or key)
                if asset_class:
                    normalized[asset_class] = _normalize_policy_item(asset_class, value)
            elif key not in {"artifact_type", "schema_version", "status"}:
                asset_class = _clean_text(key)
                if asset_class:
                    normalized[asset_class] = {
                        "asset_class": asset_class,
                        "policy_bucket": _clean_bucket(value),
                        "reason": None,
                    }

        return normalized

    if isinstance(policy_source, Sequence) and not isinstance(policy_source, (str, bytes, bytearray)):
        normalized = {}

        for item in policy_source:
            if not isinstance(item, Mapping):
                continue
            asset_class = _clean_text(item.get("asset_class"))
            if asset_class:
                normalized[asset_class] = _normalize_policy_item(asset_class, item)

        return normalized

    return {}


def _normalize_policy_item(asset_class: str, item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "asset_class": asset_class,
        "policy_bucket": _clean_bucket(
            item.get("policy_bucket")
            or item.get("bucket")
            or item.get("status")
            or item.get("action")
        ),
        "reason": item.get("reason") or item.get("policy_reason"),
    }


def _selection_summary(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    bucket_counts = Counter(str(item.get("selection_bucket")) for item in candidates)
    asset_class_counts = Counter(str(item.get("asset_class")) for item in candidates)
    behavior_state_counts = Counter(str(item.get("behavior_state")) for item in candidates)
    trend_counts = Counter(str(item.get("trend_behavior")) for item in candidates)

    return {
        "candidate_count": len(candidates),
        "preferred_count": bucket_counts.get("preferred", 0),
        "allowed_count": bucket_counts.get("allowed", 0),
        "needs_review_count": bucket_counts.get("needs_review", 0),
        "blocked_count": bucket_counts.get("blocked", 0),
        "selection_bucket_counts": dict(sorted(bucket_counts.items())),
        "asset_class_counts": dict(sorted(asset_class_counts.items())),
        "behavior_state_counts": dict(sorted(behavior_state_counts.items())),
        "trend_behavior_counts": dict(sorted(trend_counts.items())),
        "preferred_symbols": sorted(
            str(item.get("symbol")) for item in candidates if item.get("selection_bucket") == "preferred"
        ),
        "allowed_symbols": sorted(
            str(item.get("symbol")) for item in candidates if item.get("selection_bucket") == "allowed"
        ),
        "needs_review_symbols": sorted(
            str(item.get("symbol")) for item in candidates if item.get("selection_bucket") == "needs_review"
        ),
        "blocked_symbols": sorted(
            str(item.get("symbol")) for item in candidates if item.get("selection_bucket") == "blocked"
        ),
    }


def _normalize_symbols(symbols: Sequence[str] | None) -> set[str] | None:
    if symbols is None:
        return None
    cleaned = {_clean_symbol(symbol) for symbol in symbols}
    return {symbol for symbol in cleaned if symbol}


def _normalize_asset_class_lookup(source: Mapping[str, str] | None) -> dict[str, str]:
    if not isinstance(source, Mapping):
        return {}

    lookup: dict[str, str] = {}
    for symbol, asset_class in source.items():
        cleaned_symbol = _clean_symbol(symbol)
        cleaned_class = _clean_text(asset_class)
        if cleaned_symbol and cleaned_class:
            lookup[cleaned_symbol] = cleaned_class

    return lookup


def _infer_asset_class(symbol: str) -> str:
    equity_symbols = {
        "SPY", "QQQ", "IWM", "RSP", "DIA", "VTI", "ITOT", "VT", "VEA", "VWO",
        "EEM", "EFA", "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE",
        "XLU", "XLV", "XLY",
    }
    bond_symbols = {
        "AGG", "BND", "GOVT", "IEF", "IEI", "SHY", "SGOV", "TIP", "TLT",
        "TLH", "MUB", "HYD", "VCIT", "VCSH", "VGIT", "VGSH", "VGLT",
    }
    credit_symbols = {"HYG", "JNK", "LQD", "EMB", "SHYG", "SRLN", "BKLN"}
    commodity_symbols = {
        "DBC", "DBA", "GLD", "IAU", "SLV", "PALL", "PPLT", "USO", "UNG",
        "WEAT", "CORN", "SOYB", "CPER", "GDX", "GDXJ", "XME", "XOP",
    }
    currency_symbols = {"UUP", "UDN", "FXA", "FXB", "FXC", "FXE", "FXY", "CEW"}
    volatility_symbols = {"VIXY", "VIXM", "VXX", "UVXY", "SVXY"}

    if symbol in bond_symbols:
        return "bonds"
    if symbol in credit_symbols:
        return "credit"
    if symbol in commodity_symbols:
        return "commodities"
    if symbol in currency_symbols:
        return "currencies"
    if symbol in volatility_symbols:
        return "volatility"
    if symbol in equity_symbols or symbol.startswith("X"):
        return "equities"

    return _DEFAULT_UNKNOWN_ASSET_CLASS


def _default_policy(asset_class: str) -> dict[str, Any]:
    return {
        "asset_class": asset_class,
        "policy_bucket": "allowed",
        "reason": "no explicit asset class policy supplied",
    }


def _clean_bucket(value: Any) -> str:
    text = _clean_text(value)
    if text in _SELECTION_BUCKETS:
        return text
    return "allowed"


def _selection_rank(bucket: str) -> int:
    return {
        "preferred": 0,
        "allowed": 1,
        "needs_review": 2,
        "blocked": 3,
    }.get(bucket, 9)


def _clean_symbol(value: Any) -> str | None:
    text = _clean_text(value)
    return text.upper() if text else None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text.lower() if text else None


def _dedupe_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[tuple[str, str], ...]] = set()
    deduped: list[dict[str, Any]] = []

    for item in items:
        normalized = {str(key): str(value) for key, value in item.items()}
        key = tuple(sorted(normalized.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(dict(item))

    return deduped


def _blocked_result(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_asset_behavior_selection",
        "schema_version": ASSET_BEHAVIOR_SELECTION_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "asset_behavior_selection",
        "adapter_type": "asset_behavior_selection_builder",
        "candidates": [],
        "skipped_items": [],
        "selection_summary": {
            "candidate_count": 0,
            "preferred_count": 0,
            "allowed_count": 0,
            "needs_review_count": 0,
            "blocked_count": 0,
            "selection_bucket_counts": {},
            "asset_class_counts": {},
            "behavior_state_counts": {},
            "trend_behavior_counts": {},
            "preferred_symbols": [],
            "allowed_symbols": [],
            "needs_review_symbols": [],
            "blocked_symbols": [],
        },
        "blocker_items": [{"reason": reason}],
        "warning_items": [],
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }

