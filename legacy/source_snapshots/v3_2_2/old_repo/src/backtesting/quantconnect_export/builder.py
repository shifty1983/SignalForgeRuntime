from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


SCHEMA_VERSION = "quantconnect_export.v1"
PLATFORM = "quantconnect"
ENGINE = "lean"
MANUAL_EXECUTION_MODE = "manual_cloud_backtest"

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
]

READY_ITEM_KEYS = (
    "ready_items",
    "ready_final_review_items",
    "ready_review_items",
    "ready_candidates",
    "ready_payloads",
)

NEEDS_REVIEW_ITEM_KEYS = (
    "needs_review_items",
    "needs_review_final_review_items",
    "needs_review_candidates",
    "needs_review_payloads",
)

BLOCKED_ITEM_KEYS = (
    "blocked_items",
    "blocked_final_review_items",
    "blocked_candidates",
    "blocked_payloads",
)

GENERAL_ITEM_KEYS = (
    "items",
    "final_review_items",
    "review_items",
    "candidates",
    "payloads",
)

WARNING_KEYS = ("warnings", "warning_messages")
BLOCKED_REASON_KEYS = ("blocked_reasons", "blocked_reason_messages")


def build_quantconnect_export(source: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic QuantConnect/LEAN export package.

    This builder does not call QuantConnect, brokers, market-data services,
    order-routing systems, or live-trading APIs. It only converts an existing
    SignalForge review/research artifact into a portable JSON-safe payload.
    """

    if not isinstance(source, Mapping):
        return _blocked_invalid_shape("source must be a mapping/dict")

    source_copy = deepcopy(dict(source))
    source_status = _extract_status(source_copy)

    warnings = _collect_text_values(source_copy, WARNING_KEYS)
    blocked_reasons = _collect_text_values(source_copy, BLOCKED_REASON_KEYS)

    ready_items = _extract_bucketed_items(source_copy, READY_ITEM_KEYS)
    needs_review_items = _extract_bucketed_items(source_copy, NEEDS_REVIEW_ITEM_KEYS)
    blocked_items = _extract_bucketed_items(source_copy, BLOCKED_ITEM_KEYS)

    general_items = _extract_bucketed_items(source_copy, GENERAL_ITEM_KEYS)
    split_general = _split_general_items(general_items)
    ready_items.extend(split_general["ready"])
    needs_review_items.extend(split_general["needs_review"])
    blocked_items.extend(split_general["blocked"])

    ready_items = _dedupe_items(ready_items)
    needs_review_items = _dedupe_items(needs_review_items)
    blocked_items = _dedupe_items(blocked_items)

    exportable_candidates: list[dict[str, Any]] = []
    invalid_ready_count = 0

    for index, item in enumerate(ready_items):
        normalized = _normalize_ready_candidate(item, index=index)
        if normalized is None:
            invalid_ready_count += 1
            continue
        exportable_candidates.append(normalized)

    if invalid_ready_count:
        warnings.append(
            f"{invalid_ready_count} ready item(s) could not be exported because required fields were missing"
        )

    exportable_candidates = sorted(
        exportable_candidates,
        key=lambda candidate: (
            candidate["strategy_id"],
            candidate["symbol"],
            candidate["asset_class"],
        ),
    )

    strategy_configs = [
        _build_strategy_config(candidate, source_copy)
        for candidate in exportable_candidates
    ]
    universe = _build_universe(exportable_candidates)
    decision_rules = [
        _build_decision_rule(candidate)
        for candidate in exportable_candidates
    ]
    backtest_manifest = _build_backtest_manifest(
        source_copy,
        source_status,
        strategy_configs,
    )

    status = _classify_export_status(
        source_status=source_status,
        exportable_count=len(exportable_candidates),
        needs_review_count=len(needs_review_items),
        blocked_count=len(blocked_items),
        warnings=warnings,
    )

    if not exportable_candidates and status == "needs_review":
        warnings.append("no QuantConnect-exportable ready items found")

    if status == "blocked" and not blocked_reasons:
        blocked_reasons.append("no QuantConnect-exportable ready items found")

    return {
        "schema_version": SCHEMA_VERSION,
        "platform": PLATFORM,
        "engine": ENGINE,
        "execution_mode": MANUAL_EXECUTION_MODE,
        "status": status,
        "summary": {
            "source_status": source_status,
            "ready_item_count": len(ready_items),
            "needs_review_item_count": len(needs_review_items),
            "blocked_item_count": len(blocked_items),
            "exportable_strategy_count": len(strategy_configs),
            "warning_count": len(warnings),
            "blocked_reason_count": len(blocked_reasons),
        },
        "warnings": _sorted_unique_text(warnings),
        "blocked_reasons": _sorted_unique_text(blocked_reasons),
        "generated_payloads": {
            "strategy_configs": strategy_configs,
            "universe": universe,
            "decision_rules": decision_rules,
            "backtest_manifest": backtest_manifest,
        },
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _blocked_invalid_shape(reason: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "platform": PLATFORM,
        "engine": ENGINE,
        "execution_mode": MANUAL_EXECUTION_MODE,
        "status": "blocked",
        "summary": {
            "source_status": "invalid_shape",
            "ready_item_count": 0,
            "needs_review_item_count": 0,
            "blocked_item_count": 0,
            "exportable_strategy_count": 0,
            "warning_count": 0,
            "blocked_reason_count": 1,
        },
        "warnings": [],
        "blocked_reasons": [reason],
        "generated_payloads": {
            "strategy_configs": [],
            "universe": [],
            "decision_rules": [],
            "backtest_manifest": {
                "manifest_id": "quantconnect_export_manifest",
                "platform": PLATFORM,
                "engine": ENGINE,
                "execution_mode": MANUAL_EXECUTION_MODE,
                "strategy_count": 0,
                "source_status": "invalid_shape",
            },
        },
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _extract_status(source: Mapping[str, Any]) -> str:
    for key in ("status", "operation_status", "final_status", "review_status"):
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return _normalize_status(value)

    summary = source.get("summary")
    if isinstance(summary, Mapping):
        for key in ("status", "operation_status", "final_status", "review_status"):
            value = summary.get(key)
            if isinstance(value, str) and value.strip():
                return _normalize_status(value)

    return "needs_review"


def _normalize_status(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"ready", "needs_review", "blocked"}:
        return normalized
    if normalized in {"pass", "passed", "ok", "valid"}:
        return "ready"
    if normalized in {"review", "warning", "warn"}:
        return "needs_review"
    if normalized in {"fail", "failed", "invalid", "error"}:
        return "blocked"
    return normalized


def _collect_text_values(source: Mapping[str, Any], keys: tuple[str, ...]) -> list[str]:
    values: list[str] = []

    for key in keys:
        values.extend(_as_text_list(source.get(key)))

    summary = source.get("summary")
    if isinstance(summary, Mapping):
        for key in keys:
            values.extend(_as_text_list(summary.get(key)))

    return _sorted_unique_text(values)


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _extract_bucketed_items(
    source: Mapping[str, Any],
    keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for key in keys:
        items.extend(_as_mapping_list(source.get(key)))

    summary = source.get("summary")
    if isinstance(summary, Mapping):
        for key in keys:
            items.extend(_as_mapping_list(summary.get(key)))

    return items


def _as_mapping_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [dict(value)]
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    if isinstance(value, tuple):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def _split_general_items(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    split = {"ready": [], "needs_review": [], "blocked": []}

    for item in items:
        item_status = _normalize_status(
            str(item.get("status", item.get("review_status", "needs_review")))
        )
        if item_status == "ready":
            split["ready"].append(item)
        elif item_status == "blocked":
            split["blocked"].append(item)
        else:
            split["needs_review"].append(item)

    return split


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}

    for index, item in enumerate(items):
        key = _stable_item_key(item, index)
        if key not in deduped:
            deduped[key] = item

    return [deduped[key] for key in sorted(deduped)]


def _stable_item_key(item: Mapping[str, Any], index: int) -> str:
    for key in ("id", "candidate_id", "strategy_id", "name"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    symbol = _extract_symbol(item)
    strategy = item.get("strategy") or item.get("strategy_type") or "strategy"
    return f"{symbol or 'missing_symbol'}::{strategy}::{index}"


def _normalize_ready_candidate(
    item: Mapping[str, Any],
    index: int,
) -> dict[str, Any] | None:
    symbol = _extract_symbol(item)
    if not symbol:
        return None

    strategy_id = _extract_strategy_id(item, symbol, index)
    asset_class = (
        str(item.get("asset_class", item.get("security_type", "equity")))
        .strip()
        .lower()
        or "equity"
    )
    strategy_type = str(
        item.get("strategy_type", item.get("strategy", "signalforge_candidate"))
    ).strip()

    rules = item.get("rules")
    if not isinstance(rules, Mapping):
        rules = {}

    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "asset_class": asset_class,
        "strategy_type": strategy_type,
        "resolution": _normalize_resolution(
            str(item.get("resolution", item.get("bar_size", "daily")))
        ),
        "start_date": _optional_text(item.get("start_date")),
        "end_date": _optional_text(item.get("end_date")),
        "cash": _optional_number(item.get("cash")),
        "regime": _optional_text(item.get("regime")),
        "asset_behavior": _optional_text(item.get("asset_behavior")),
        "expected_value": _optional_number(item.get("expected_value", item.get("ev"))),
        "confidence": _optional_number(item.get("confidence")),
        "entry_rule": _optional_text(item.get("entry_rule", rules.get("entry"))),
        "exit_rule": _optional_text(item.get("exit_rule", rules.get("exit"))),
        "risk_rule": _optional_text(item.get("risk_rule", rules.get("risk"))),
        "position_sizing": _optional_text(
            item.get("position_sizing", rules.get("position_sizing"))
        ),
        "source_item": _json_safe_mapping(item),
    }


def _extract_symbol(item: Mapping[str, Any]) -> str | None:
    for key in ("symbol", "ticker", "underlying_symbol", "underlying"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    return None


def _extract_strategy_id(item: Mapping[str, Any], symbol: str, index: int) -> str:
    for key in ("strategy_id", "candidate_id", "id", "name"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return _slug(value)

    strategy_type = item.get("strategy_type", item.get("strategy", "strategy"))
    return _slug(f"{symbol}_{strategy_type}_{index + 1}")


def _normalize_resolution(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "_")
    if normalized in {"minute", "hour", "daily", "tick", "second"}:
        return normalized
    if normalized in {"1m", "min"}:
        return "minute"
    if normalized in {"1d", "day"}:
        return "daily"
    return "daily"


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _optional_number(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value

    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None

    if number.is_integer():
        return int(number)
    return number


def _build_strategy_config(
    candidate: Mapping[str, Any],
    source: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "strategy_id": candidate["strategy_id"],
        "name": candidate["strategy_id"],
        "platform": PLATFORM,
        "engine": ENGINE,
        "asset_class": candidate["asset_class"],
        "strategy_type": candidate["strategy_type"],
        "symbol": candidate["symbol"],
        "resolution": candidate["resolution"],
        "start_date": candidate["start_date"] or _optional_text(source.get("start_date")),
        "end_date": candidate["end_date"] or _optional_text(source.get("end_date")),
        "cash": candidate["cash"] or _optional_number(source.get("cash")) or 100000,
        "regime": candidate["regime"],
        "asset_behavior": candidate["asset_behavior"],
        "expected_value": candidate["expected_value"],
        "confidence": candidate["confidence"],
        "execution_mode": MANUAL_EXECUTION_MODE,
    }


def _build_universe(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    universe_by_key: dict[tuple[str, str], dict[str, Any]] = {}

    for candidate in candidates:
        key = (candidate["symbol"], candidate["asset_class"])
        universe_by_key[key] = {
            "symbol": candidate["symbol"],
            "asset_class": candidate["asset_class"],
            "resolution": candidate["resolution"],
        }

    return [universe_by_key[key] for key in sorted(universe_by_key)]


def _build_decision_rule(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "strategy_id": candidate["strategy_id"],
        "symbol": candidate["symbol"],
        "strategy_type": candidate["strategy_type"],
        "entry_rule": candidate["entry_rule"] or "external_signal_required",
        "exit_rule": candidate["exit_rule"] or "external_signal_required",
        "risk_rule": candidate["risk_rule"] or "not_specified",
        "position_sizing": candidate["position_sizing"] or "not_specified",
        "source_item": candidate["source_item"],
    }


def _build_backtest_manifest(
    source: Mapping[str, Any],
    source_status: str,
    strategy_configs: list[dict[str, Any]],
) -> dict[str, Any]:
    strategy_ids = [config["strategy_id"] for config in strategy_configs]

    return {
        "manifest_id": _slug(
            str(source.get("id", source.get("manifest_id", "quantconnect_export_manifest")))
        ),
        "platform": PLATFORM,
        "engine": ENGINE,
        "execution_mode": MANUAL_EXECUTION_MODE,
        "source_status": source_status,
        "strategy_count": len(strategy_configs),
        "strategy_ids": sorted(strategy_ids),
        "default_start_date": _optional_text(source.get("start_date")),
        "default_end_date": _optional_text(source.get("end_date")),
        "default_cash": _optional_number(source.get("cash")) or 100000,
    }


def _classify_export_status(
    *,
    source_status: str,
    exportable_count: int,
    needs_review_count: int,
    blocked_count: int,
    warnings: list[str],
) -> str:
    if exportable_count > 0:
        return "needs_review" if warnings else "ready"

    if source_status == "blocked":
        return "blocked"

    if needs_review_count > 0:
        return "needs_review"

    if blocked_count > 0:
        return "blocked"

    return "needs_review"


def _json_safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}

    for key, item in value.items():
        if isinstance(item, Mapping):
            safe[str(key)] = _json_safe_mapping(item)
        elif isinstance(item, list):
            safe[str(key)] = [_json_safe_value(child) for child in item]
        elif isinstance(item, tuple):
            safe[str(key)] = [_json_safe_value(child) for child in item]
        elif isinstance(item, (str, int, float, bool)) or item is None:
            safe[str(key)] = item
        else:
            safe[str(key)] = str(item)

    return safe


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _json_safe_mapping(value)
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _sorted_unique_text(values: list[str]) -> list[str]:
    return sorted({value.strip() for value in values if value and value.strip()})


def _slug(value: str) -> str:
    lowered = value.strip().lower()
    chars = []
    previous_was_separator = False

    for char in lowered:
        if char.isalnum():
            chars.append(char)
            previous_was_separator = False
        elif not previous_was_separator:
            chars.append("_")
            previous_was_separator = True

    slug = "".join(chars).strip("_")
    return slug or "strategy"
