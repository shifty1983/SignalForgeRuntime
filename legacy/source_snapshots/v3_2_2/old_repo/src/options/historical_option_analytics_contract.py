# src/options/historical_option_analytics_contract.py

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


CONTRACT_TYPE = "historical_option_analytics_input_contract"

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
]

REQUIRED_CANONICAL_FIELDS = {
    "symbol",
    "as_of_date",
    "implied_volatility",
    "volume",
    "open_interest",
    "spread_pct",
}

PREFERRED_CANONICAL_FIELDS = {
    "liquidity_regime",
    "iv_rv_ratio",
    "vol_premium_regime",
    "skew_regime",
    "term_structure_regime",
    "delta",
    "gamma",
    "theta",
    "vega",
    "days_to_expiration",
    "moneyness",
    "expiration",
    "strike",
    "option_type",
}

NUMERIC_FIELDS = {
    "implied_volatility",
    "volume",
    "open_interest",
    "spread_pct",
    "iv_rv_ratio",
    "delta",
    "gamma",
    "theta",
    "vega",
    "days_to_expiration",
    "moneyness",
    "strike",
}

DEFAULT_FIELD_ALIASES = {
    "symbol": ("symbol", "ticker", "underlying", "underlying_symbol"),
    "as_of_date": ("as_of_date", "date", "quote_date", "trade_date"),
    "implied_volatility": (
        "implied_volatility",
        "iv",
        "mid_iv",
        "mark_iv",
        "option_iv",
    ),
    "volume": ("volume", "option_volume", "contract_volume"),
    "open_interest": ("open_interest", "oi", "option_open_interest"),
    "spread_pct": (
        "spread_pct",
        "bid_ask_spread_pct",
        "avg_bid_ask_spread_pct",
        "spread_percent",
    ),
    "liquidity_regime": ("liquidity_regime", "liquidity_profile"),
    "iv_rv_ratio": ("iv_rv_ratio", "implied_realized_ratio"),
    "vol_premium_regime": ("vol_premium_regime", "vol_premium_profile"),
    "skew_regime": ("skew_regime", "skew_profile"),
    "term_structure_regime": (
        "term_structure_regime",
        "term_structure_profile",
    ),
    "delta": ("delta",),
    "gamma": ("gamma",),
    "theta": ("theta",),
    "vega": ("vega",),
    "days_to_expiration": ("days_to_expiration", "dte"),
    "moneyness": ("moneyness",),
    "expiration": ("expiration", "expiration_date", "expiry"),
    "strike": ("strike", "strike_price"),
    "option_type": ("option_type", "right", "put_call"),
}


def build_historical_option_analytics_input_contract(
    raw_rows: Sequence[Mapping[str, Any]] | None,
    *,
    field_aliases: Mapping[str, Sequence[str]] | None = None,
    contract_name: str = CONTRACT_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Normalize raw historical option analytics rows into the canonical shape used
    by option behavior and readiness review.

    This does not calculate option analytics. It only validates and maps fields.
    """

    metadata_dict = dict(metadata or {})

    if raw_rows is None:
        return _blocked_contract(
            contract_name=contract_name,
            metadata=metadata_dict,
            blocked_reasons=["raw historical option analytics rows were not provided"],
        )

    if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes)):
        return _blocked_contract(
            contract_name=contract_name,
            metadata=metadata_dict,
            blocked_reasons=[
                "raw historical option analytics rows must be a sequence of mappings"
            ],
        )

    if not raw_rows:
        return _blocked_contract(
            contract_name=contract_name,
            metadata=metadata_dict,
            blocked_reasons=["raw historical option analytics rows are empty"],
        )

    aliases = _merged_aliases(field_aliases)

    normalized_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    blocked_reasons: list[str] = []

    for index, row in enumerate(raw_rows):
        if not isinstance(row, Mapping):
            blocked_reasons.append(f"row {index} must be a mapping")
            continue

        normalized_row, row_warnings, row_blocked_reasons = _normalize_row(
            row=row,
            index=index,
            aliases=aliases,
        )

        warnings.extend(row_warnings)
        blocked_reasons.extend(row_blocked_reasons)

        if not row_blocked_reasons:
            normalized_rows.append(normalized_row)

    if blocked_reasons:
        return _blocked_contract(
            contract_name=contract_name,
            metadata=metadata_dict,
            blocked_reasons=_unique_ordered(blocked_reasons),
            warnings=_unique_ordered(warnings),
            normalized_rows=normalized_rows,
        )

    preferred_missing = _preferred_missing_across_rows(normalized_rows)

    if preferred_missing:
        warnings.append(
            "historical option analytics rows are missing preferred fields: "
            f"{sorted(preferred_missing)}"
        )

    contract_status = "needs_review" if warnings else "ready"

    return {
        "contract_type": CONTRACT_TYPE,
        "contract_name": contract_name,
        "contract_status": contract_status,
        "is_ready": contract_status == "ready",
        "is_blocked": False,
        "row_count": len(raw_rows),
        "normalized_row_count": len(normalized_rows),
        "required_fields": sorted(REQUIRED_CANONICAL_FIELDS),
        "preferred_fields": sorted(PREFERRED_CANONICAL_FIELDS),
        "field_coverage": _field_coverage(normalized_rows),
        "normalized_rows": normalized_rows,
        "warnings": _unique_ordered(warnings),
        "blocked_reasons": [],
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "metadata": metadata_dict,
    }


def _normalize_row(
    *,
    row: Mapping[str, Any],
    index: int,
    aliases: Mapping[str, Sequence[str]],
) -> tuple[dict[str, Any], list[str], list[str]]:
    warnings: list[str] = []
    blocked_reasons: list[str] = []
    normalized: dict[str, Any] = {}

    for canonical_field, alias_names in aliases.items():
        value = _first_present(row, alias_names)

        if value is None:
            continue

        normalized_value = _normalize_value(canonical_field, value)

        if normalized_value is None:
            if canonical_field in REQUIRED_CANONICAL_FIELDS:
                blocked_reasons.append(
                    f"row {index} has invalid required field: {canonical_field}"
                )
            else:
                warnings.append(
                    f"row {index} has invalid optional field: {canonical_field}"
                )
            continue

        normalized[canonical_field] = normalized_value

    missing_required = sorted(REQUIRED_CANONICAL_FIELDS - set(normalized.keys()))

    if missing_required:
        blocked_reasons.append(
            f"row {index} missing required fields: {missing_required}"
        )

    return normalized, warnings, blocked_reasons


def _normalize_value(
    canonical_field: str,
    value: Any,
) -> Any:
    if value is None:
        return None

    if canonical_field in NUMERIC_FIELDS:
        return _float_or_none(value)

    if canonical_field == "option_type":
        return _normalize_option_type(value)

    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None

    return value


def _normalize_option_type(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip().lower()

    if normalized in {"call", "c"}:
        return "call"

    if normalized in {"put", "p"}:
        return "put"

    return normalized or None


def _first_present(
    row: Mapping[str, Any],
    aliases: Sequence[str],
) -> Any:
    for alias in aliases:
        if alias in row:
            return row[alias]

    return None


def _merged_aliases(
    field_aliases: Mapping[str, Sequence[str]] | None,
) -> dict[str, Sequence[str]]:
    merged = {
        key: tuple(value)
        for key, value in DEFAULT_FIELD_ALIASES.items()
    }

    if field_aliases is None:
        return merged

    for canonical_field, aliases in field_aliases.items():
        merged[canonical_field] = tuple(aliases)

    return merged


def _preferred_missing_across_rows(
    normalized_rows: list[dict[str, Any]],
) -> set[str]:
    if not normalized_rows:
        return set(PREFERRED_CANONICAL_FIELDS)

    present_fields = set()

    for row in normalized_rows:
        present_fields.update(row.keys())

    return PREFERRED_CANONICAL_FIELDS - present_fields


def _field_coverage(
    normalized_rows: list[dict[str, Any]],
) -> dict[str, int]:
    coverage: dict[str, int] = {}

    for row in normalized_rows:
        for field_name in row:
            coverage[field_name] = coverage.get(field_name, 0) + 1

    return {
        field_name: coverage[field_name]
        for field_name in sorted(coverage)
    }


def _blocked_contract(
    *,
    contract_name: str,
    metadata: dict[str, Any],
    blocked_reasons: list[str],
    warnings: list[str] | None = None,
    normalized_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "contract_type": CONTRACT_TYPE,
        "contract_name": contract_name,
        "contract_status": "blocked",
        "is_ready": False,
        "is_blocked": True,
        "row_count": 0,
        "normalized_row_count": len(normalized_rows or []),
        "required_fields": sorted(REQUIRED_CANONICAL_FIELDS),
        "preferred_fields": sorted(PREFERRED_CANONICAL_FIELDS),
        "field_coverage": _field_coverage(normalized_rows or []),
        "normalized_rows": normalized_rows or [],
        "warnings": _unique_ordered(warnings or []),
        "blocked_reasons": _unique_ordered(blocked_reasons),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "metadata": metadata,
    }


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None

    if numeric_value != numeric_value:
        return None

    return numeric_value


def _unique_ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)

    return result
