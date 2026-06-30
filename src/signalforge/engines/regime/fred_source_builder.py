from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


FRED_REGIME_SOURCE_SCHEMA_VERSION = "signalforge_fred_regime_source.v1"


@dataclass(frozen=True)
class FredSeriesGroup:
    group: str
    series: tuple[str, ...]
    required: bool = True
    description: str = ""


DEFAULT_FRED_SERIES_GROUPS: tuple[FredSeriesGroup, ...] = (
    FredSeriesGroup(
        group="growth",
        series=("INDPRO", "PAYEMS", "W875RX1", "GDPC1"),
        description="Real activity / employment growth inputs.",
    ),
    FredSeriesGroup(
        group="inflation",
        series=("CPIAUCSL", "PCEPI", "CPILFESL", "PCEPILFE"),
        description="Price-index inputs used to measure inflation momentum.",
    ),
    FredSeriesGroup(
        group="rates",
        series=("FEDFUNDS", "DGS10", "DGS2", "T10Y2Y"),
        description="Policy rate, Treasury-rate, and yield-curve inputs.",
    ),
    FredSeriesGroup(
        group="liquidity",
        series=("M2SL", "WALCL", "RESBALNS", "NFCI", "ANFCI"),
        description="Money, balance-sheet, reserve, and financial-conditions inputs.",
    ),
    FredSeriesGroup(
        group="credit",
        series=("BAMLH0A0HYM2", "BAMLC0A0CM"),
        description="High-yield and investment-grade credit-spread inputs.",
    ),
    FredSeriesGroup(
        group="risk",
        series=("BAMLH0A0HYM2", "VIXCLS", "NFCI", "ANFCI", "USREC"),
        description="Credit-spread, volatility, financial-conditions, and recession inputs.",
    ),
    FredSeriesGroup(
        group="volatility",
        series=("VIXCLS",),
        required=False,
        description="Volatility-policy modifier for the regime options policy layer.",
    ),
)


SOURCE_ROW_KEYS = (
    "macro_rows",
    "fred_rows",
    "rows",
    "payload",
    "normalized_payloads",
)


def build_signalforge_fred_regime_source(
    source: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    *,
    periods: int = 3,
    inflation_yoy_periods: int = 12,
) -> dict[str, Any]:
    """Build regime-ready macro rows from normalized FRED rows.

    Input rows should contain at least date, series_id, and value. The builder is
    intentionally local-artifact only: it does not call FRED, brokers, market-data
    vendors, route orders, submit orders, model fills, perform live execution, or
    create automatic strategy/parameter/maintenance actions.
    """

    if periods <= 0:
        return _blocked_result("periods must be positive")

    if inflation_yoy_periods <= 0:
        return _blocked_result("inflation_yoy_periods must be positive")

    raw_rows = _raw_rows(source)
    if raw_rows is None:
        return _blocked_result("macro rows are required")

    if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes, bytearray)):
        return _blocked_result("macro rows must be a sequence of mappings")

    normalized_rows: list[dict[str, Any]] = []
    blocker_items: list[dict[str, Any]] = []
    warning_items: list[dict[str, Any]] = []

    for index, raw_row in enumerate(raw_rows):
        row, errors = _normalize_macro_row(raw_row)
        if errors:
            for error in errors:
                blocker_items.append({"row_index": index, "reason": error})
            continue
        normalized_rows.append(row)

    if not normalized_rows and not blocker_items:
        blocker_items.append({"reason": "macro rows are empty"})

    available_series = sorted({row["series_id"] for row in normalized_rows})
    group_summary = _group_summary(available_series)

    for group in DEFAULT_FRED_SERIES_GROUPS:
        if group.required and not any(series in available_series for series in group.series):
            blocker_items.append(
                {
                    "reason": f"missing required FRED group: {group.group}",
                    "expected_any_of": list(group.series),
                }
            )
        elif not any(series in available_series for series in group.series):
            warning_items.append(
                {
                    "reason": f"missing optional FRED group: {group.group}",
                    "expected_any_of": list(group.series),
                }
            )

    if blocker_items:
        return {
            "artifact_type": "signalforge_fred_regime_source",
            "schema_version": FRED_REGIME_SOURCE_SCHEMA_VERSION,
            "status": "blocked",
            "is_ready": False,
            "requires_manual_approval": True,
            "normalized_macro_rows": normalized_rows,
            "available_series": available_series,
            "series_group_summary": group_summary,
            "regime_rows": [],
            "regime_row_count": 0,
            "blocker_items": blocker_items,
            "warning_items": warning_items,
            "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        }

    wide_rows = _wide_forward_filled_rows(normalized_rows)
    regime_rows = _build_regime_rows(
        wide_rows,
        periods=periods,
        inflation_yoy_periods=inflation_yoy_periods,
        event_risk=bool(_mapping(source).get("event_risk", False)),
        use_recession_as_event_risk=bool(
            _mapping(source).get("use_recession_as_event_risk", False)
        ),
    )

    if not any(_has_core_metrics(row) for row in regime_rows):
        warning_items.append(
            {
                "reason": "no complete regime signal rows after lookback calculations",
                "periods": periods,
                "inflation_yoy_periods": inflation_yoy_periods,
            }
        )

    status = "needs_review" if warning_items else "ready"

    return {
        "artifact_type": "signalforge_fred_regime_source",
        "schema_version": FRED_REGIME_SOURCE_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "source_kind": "fred_macro_rows",
        "periods": periods,
        "inflation_yoy_periods": inflation_yoy_periods,
        "normalized_macro_rows": normalized_rows,
        "normalized_macro_row_count": len(normalized_rows),
        "available_series": available_series,
        "series_group_summary": group_summary,
        "regime_rows": regime_rows,
        "regime_row_count": len(regime_rows),
        "latest_date": regime_rows[-1]["date"] if regime_rows else None,
        "blocker_items": [],
        "warning_items": warning_items,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def default_fred_series_ids() -> list[str]:
    output: list[str] = []
    for group in DEFAULT_FRED_SERIES_GROUPS:
        output.extend(group.series)
    return sorted(set(output))


def _raw_rows(source: Any) -> Any | None:
    if source is None:
        return None

    if isinstance(source, Mapping):
        for key in SOURCE_ROW_KEYS:
            if key in source:
                value = source.get(key)
                if isinstance(value, Mapping):
                    return [value]
                return value
        if {"date", "series_id", "value"}.issubset(source.keys()) or {"date", "series", "value"}.issubset(source.keys()):
            return [source]
        return None

    return source


def _normalize_macro_row(raw_row: Any) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if not isinstance(raw_row, Mapping):
        return {}, ["macro row must be a mapping"]

    date_value = _first_present(raw_row, ("date", "timestamp", "observation_date"))
    series_value = _first_present(raw_row, ("series_id", "series", "symbol"))
    value = _first_present(raw_row, ("value", "close", "level"))

    parsed_date = _date_string(date_value)
    if parsed_date is None:
        errors.append("date is required")

    series_id = _string(series_value).upper()
    if not series_id:
        errors.append("series_id is required")

    parsed_value = _float_or_none(value)
    if parsed_value is None:
        errors.append("value is required and must be numeric")

    if errors:
        return {}, errors

    row = {
        "date": parsed_date,
        "series_id": series_id,
        "value": parsed_value,
    }

    source = _first_present(raw_row, ("source", "provider"))
    if source is not None:
        row["source"] = _string(source) or "fred"
    else:
        row["source"] = "fred"

    return row, []


def _wide_forward_filled_rows(normalized_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_date: dict[str, dict[str, float]] = {}
    for row in sorted(normalized_rows, key=lambda item: (str(item["date"]), str(item["series_id"]))):
        date_key = str(row["date"])
        by_date.setdefault(date_key, {})[str(row["series_id"])] = float(row["value"])

    latest: dict[str, float] = {}
    monthly_snapshots: dict[str, dict[str, Any]] = {}

    for date_key in sorted(by_date):
        latest.update(by_date[date_key])

        snapshot = {"date": date_key}
        snapshot.update(latest)

        month_key = date_key[:7]
        monthly_snapshots[month_key] = snapshot

    return [monthly_snapshots[key] for key in sorted(monthly_snapshots)]


def _build_regime_rows(
    wide_rows: Sequence[Mapping[str, Any]],
    *,
    periods: int,
    inflation_yoy_periods: int,
    event_risk: bool,
    use_recession_as_event_risk: bool,
) -> list[dict[str, Any]]:
    series_values = _series_values(wide_rows)
    inflation_yoy = {
        series: _pct_change_series(values, inflation_yoy_periods)
        for series, values in series_values.items()
        if series in {"CPIAUCSL", "PCEPI", "CPILFESL", "PCEPILFE"}
    }

    output: list[dict[str, Any]] = []
    for index, source_row in enumerate(wide_rows):
        row: dict[str, Any] = {"date": source_row["date"]}

        row["growth_metric"] = _mean_optional(
            _pct_change(series_values.get(series), index, periods)
            for series in ("INDPRO", "PAYEMS", "W875RX1", "GDPC1")
        )

        row["inflation_metric"] = _mean_optional(
            _diff(inflation_yoy.get(series), index, periods)
            for series in ("CPIAUCSL", "PCEPI", "CPILFESL", "PCEPILFE")
        )

        row["rates_metric"] = _mean_optional(
            _diff(series_values.get(series), index, periods)
            for series in ("FEDFUNDS", "DGS10")
        )

        row["yield_curve_spread"] = _yield_curve_spread(source_row)

        row["liquidity_metric"] = _mean_optional(
            [
                _pct_change(series_values.get("M2SL"), index, periods),
                _pct_change(series_values.get("WALCL"), index, periods),
                _pct_change(series_values.get("RESBALNS"), index, periods),
                _negative(_diff(series_values.get("NFCI"), index, periods)),
                _negative(_diff(series_values.get("ANFCI"), index, periods)),
            ]
        )

        row["credit_metric"] = _mean_optional(
            _diff(series_values.get(series), index, periods)
            for series in ("BAMLH0A0HYM2", "BAMLC0A0CM")
        )
        row["credit_spread_level"] = _mean_optional(
            source_row.get(series)
            for series in ("BAMLH0A0HYM2", "BAMLC0A0CM")
        )

        row["risk_metric"] = _mean_optional(
            [
                _negative(_diff(series_values.get("BAMLH0A0HYM2"), index, periods)),
                _negative(_diff(series_values.get("VIXCLS"), index, periods)),
                _negative(_diff(series_values.get("NFCI"), index, periods)),
                _negative(_diff(series_values.get("ANFCI"), index, periods)),
            ]
        )

        row["volatility_metric"] = _diff(series_values.get("VIXCLS"), index, periods)
        row["volatility_regime"] = _classify_volatility(row["volatility_metric"])
        row["recession_indicator"] = _float_or_none(source_row.get("USREC"))
        row["event_risk"] = bool(event_risk or (use_recession_as_event_risk and row["recession_indicator"] == 1.0))
        row["source_series_values"] = {
            key: source_row[key]
            for key in sorted(source_row)
            if key != "date" and _float_or_none(source_row.get(key)) is not None
        }
        output.append(row)

    return output


def _series_values(wide_rows: Sequence[Mapping[str, Any]]) -> dict[str, list[float | None]]:
    series_ids = sorted({key for row in wide_rows for key in row if key != "date"})
    return {
        series: [_float_or_none(row.get(series)) for row in wide_rows]
        for series in series_ids
    }


def _pct_change_series(values: Sequence[float | None], periods: int) -> list[float | None]:
    return [_pct_change(values, index, periods) for index in range(len(values))]


def _pct_change(values: Sequence[float | None] | None, index: int, periods: int) -> float | None:
    if values is None or index - periods < 0:
        return None
    current = values[index]
    prior = values[index - periods]
    if current is None or prior in (None, 0):
        return None
    return (current - prior) / prior


def _diff(values: Sequence[float | None] | None, index: int, periods: int) -> float | None:
    if values is None or index - periods < 0:
        return None
    current = values[index]
    prior = values[index - periods]
    if current is None or prior is None:
        return None
    return current - prior


def _negative(value: float | None) -> float | None:
    return -value if value is not None else None


def _mean_optional(values: Any) -> float | None:
    parsed = [value for value in values if value is not None]
    if not parsed:
        return None
    return sum(parsed) / len(parsed)


def _yield_curve_spread(row: Mapping[str, Any]) -> float | None:
    explicit = _float_or_none(row.get("T10Y2Y"))
    if explicit is not None:
        return explicit

    ten_year = _float_or_none(row.get("DGS10"))
    two_year = _float_or_none(row.get("DGS2"))
    if ten_year is None or two_year is None:
        return None
    return ten_year - two_year


def _classify_volatility(value: float | None) -> str | None:
    if value is None:
        return None
    if value > 0:
        return "volatility_expansion"
    if value < 0:
        return "volatility_compression"
    return "volatility_stable"


def _has_core_metrics(row: Mapping[str, Any]) -> bool:
    return all(
        row.get(column) is not None
        for column in (
            "growth_metric",
            "inflation_metric",
            "rates_metric",
            "liquidity_metric",
            "risk_metric",
            "credit_metric",
            "yield_curve_spread",
        )
    )


def _group_summary(available_series: Sequence[str]) -> list[dict[str, Any]]:
    available = set(available_series)
    output = []
    for group in DEFAULT_FRED_SERIES_GROUPS:
        present = [series for series in group.series if series in available]
        missing = [series for series in group.series if series not in available]
        output.append(
            {
                "group": group.group,
                "required": group.required,
                "present_series": present,
                "missing_series": missing,
                "present_count": len(present),
                "description": group.description,
            }
        )
    return output


def _blocked_result(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_fred_regime_source",
        "schema_version": FRED_REGIME_SOURCE_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "normalized_macro_rows": [],
        "available_series": [],
        "series_group_summary": _group_summary([]),
        "regime_rows": [],
        "regime_row_count": 0,
        "blocker_items": [{"reason": reason}],
        "warning_items": [],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_present(payload: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    for alias in aliases:
        if alias in payload and payload.get(alias) is not None:
            return payload.get(alias)
    return None


def _date_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    return text[:10]


def _string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None





