from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from .lean_cli_plan import EXPLICIT_EXCLUSIONS

FILTERED_OPTION_CHAIN_ARTIFACT_TYPE = "signalforge_quantconnect_filtered_option_chain_export_plan"
FILTERED_OPTION_CHAIN_SCHEMA_VERSION = "signalforge_quantconnect_filtered_option_chain_export_plan.v1"
FILTERED_OPTION_CHAIN_SUMMARY_SCHEMA_VERSION = "signalforge_quantconnect_filtered_option_chain_export_cli_summary.v1"
DEFAULT_OBJECT_STORE_PREFIX = "signalforge/options/filtered_chain"
DEFAULT_FIELDS = [
    "underlying_symbol",
    "quote_date",
    "contract_symbol",
    "expiration",
    "dte",
    "strike",
    "right",
    "bid",
    "ask",
    "mid",
    "spread",
    "spread_pct",
    "last",
    "volume",
    "open_interest",
    "implied_volatility",
    "delta",
    "gamma",
    "theta",
    "vega",
    "rho",
    "underlying_price",
    "moneyness",
]


@dataclass(frozen=True)
class DateWindow:
    start: date
    end: date

    def as_row(self) -> dict[str, str]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
        }


@dataclass(frozen=True)
class SymbolBatch:
    batch_index: int
    symbols: tuple[str, ...]

    def as_row(self) -> dict[str, Any]:
        return {
            "batch_index": self.batch_index,
            "symbol_count": len(self.symbols),
            "symbols": list(self.symbols),
        }


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    with manifest_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("filtered option chain manifest must be a JSON object")
    return payload


def _clean_symbol(symbol: Any) -> str:
    text = str(symbol or "").strip().upper()
    if not text:
        raise ValueError("symbols must not contain blank values")
    return text


def _as_list(value: Any, *, default: Sequence[Any] | None = None) -> list[Any]:
    if value is None:
        return list(default or [])
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _as_int(value: Any, *, field: str, default: int, minimum: int | None = None) -> int:
    if value is None:
        parsed = default
    else:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} must be an integer") from exc
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{field} must be >= {minimum}")
    return parsed


def _as_float(value: Any, *, field: str, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    if value is None:
        parsed = default
    else:
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} must be numeric") from exc
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{field} must be >= {minimum}")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"{field} must be <= {maximum}")
    return parsed


def _parse_date(value: Any, *, field: str) -> date:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"{field} must be YYYY-MM-DD or YYYYMMDD")


def _symbols_from_manifest(manifest: Mapping[str, Any]) -> list[str]:
    return sorted({_clean_symbol(symbol) for symbol in _as_list(manifest.get("symbols"))})


def _option_config(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    options = manifest.get("options") or {}
    if not isinstance(options, Mapping):
        raise ValueError("options must be a JSON object when provided")
    return options


def split_symbols(symbols: Sequence[str], batch_size: int) -> list[SymbolBatch]:
    if batch_size <= 0:
        raise ValueError("symbol_batch_size must be positive")
    batches: list[SymbolBatch] = []
    for index, start in enumerate(range(0, len(symbols), batch_size), start=1):
        batches.append(SymbolBatch(batch_index=index, symbols=tuple(symbols[start : start + batch_size])))
    return batches


def split_date_range(start: date, end: date, chunk_days: int) -> list[DateWindow]:
    if chunk_days <= 0:
        raise ValueError("date_chunk_days must be positive")
    if end < start:
        raise ValueError("end must be on or after start")
    windows: list[DateWindow] = []
    cursor = start
    while cursor <= end:
        window_end = min(end, cursor + timedelta(days=chunk_days - 1))
        windows.append(DateWindow(start=cursor, end=window_end))
        cursor = window_end + timedelta(days=1)
    return windows


def normalize_filtered_option_chain_config(manifest: Mapping[str, Any]) -> dict[str, Any]:
    options = _option_config(manifest)
    start = _parse_date(manifest.get("start"), field="start")
    end = _parse_date(manifest.get("end"), field="end")
    if end < start:
        raise ValueError("end must be on or after start")

    min_dte = _as_int(options.get("min_dte"), field="options.min_dte", default=7, minimum=0)
    max_dte = _as_int(options.get("max_dte"), field="options.max_dte", default=90, minimum=0)
    if max_dte < min_dte:
        raise ValueError("options.max_dte must be >= options.min_dte")

    strike_window_percent = _as_float(
        options.get("strike_window_percent"),
        field="options.strike_window_percent",
        default=0.2,
        minimum=0.0,
        maximum=1.0,
    )
    symbol_batch_size = _as_int(options.get("symbol_batch_size"), field="options.symbol_batch_size", default=10, minimum=1)
    date_chunk_days = _as_int(options.get("date_chunk_days"), field="options.date_chunk_days", default=5, minimum=1)
    object_store_prefix = str(options.get("object_store_prefix") or DEFAULT_OBJECT_STORE_PREFIX).strip().strip("/")
    if not object_store_prefix:
        raise ValueError("options.object_store_prefix must not be blank")

    return {
        "enabled": _as_bool(options.get("enabled"), True),
        "mode": str(options.get("mode") or "filtered_chain_export"),
        "resolution": str(options.get("resolution") or "Daily"),
        "start": start,
        "end": end,
        "start_iso": start.isoformat(),
        "end_iso": end.isoformat(),
        "min_dte": min_dte,
        "max_dte": max_dte,
        "strike_window_percent": strike_window_percent,
        "symbol_batch_size": symbol_batch_size,
        "date_chunk_days": date_chunk_days,
        "object_store_prefix": object_store_prefix,
        "include_weeklys": _as_bool(options.get("include_weeklys"), True),
        "fields": [str(field) for field in _as_list(options.get("fields"), default=DEFAULT_FIELDS)],
    }


def build_filtered_option_chain_export_plan(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic ETF-only filtered option-chain export plan.

    The option date range intentionally comes from the same top-level manifest
    ``start`` and ``end`` fields used by market-price pulls. This keeps the
    option pull aligned to the market-price artifact while limiting option rows
    to the ETF universe, DTE window, and moneyness window.
    """

    symbols = _symbols_from_manifest(manifest)
    config = normalize_filtered_option_chain_config(manifest)
    warnings: list[str] = []
    blockers: list[str] = []

    if not symbols:
        blockers.append("symbols_missing")
    if not config["enabled"]:
        blockers.append("filtered_option_chain_export_disabled")
    if str(config["mode"]).lower() != "filtered_chain_export":
        blockers.append("options_mode_must_be_filtered_chain_export")

    symbol_batches = split_symbols(symbols, config["symbol_batch_size"]) if symbols else []
    date_windows = split_date_range(config["start"], config["end"], config["date_chunk_days"])

    export_jobs: list[dict[str, Any]] = []
    job_index = 1
    for window in date_windows:
        for batch in symbol_batches:
            key = (
                f"{config['object_store_prefix']}/"
                f"{window.start.strftime('%Y%m%d')}_{window.end.strftime('%Y%m%d')}/"
                f"symbols_{batch.batch_index:04d}.json.gz"
            )
            export_jobs.append(
                {
                    "job_index": job_index,
                    "start": window.start.isoformat(),
                    "end": window.end.isoformat(),
                    "batch_index": batch.batch_index,
                    "symbol_count": len(batch.symbols),
                    "symbols": list(batch.symbols),
                    "object_store_key": key,
                }
            )
            job_index += 1

    if len(export_jobs) > 500:
        warnings.append(
            "filtered option chain export has more than 500 jobs; increase options.date_chunk_days or options.symbol_batch_size if Object Store overhead is too high."
        )

    status = "ready" if not blockers and export_jobs else "blocked"
    if not export_jobs:
        blockers.append("no_export_jobs_built")

    return {
        "artifact_type": FILTERED_OPTION_CHAIN_ARTIFACT_TYPE,
        "schema_version": FILTERED_OPTION_CHAIN_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "source_kind": "quantconnect_research_filtered_option_chain_export",
        "contract": "historical_filtered_option_chain_data_pull",
        "operation_type": "quantconnect_filtered_option_chain_export_plan",
        "start": config["start_iso"],
        "end": config["end_iso"],
        "date_alignment": "uses_same_top_level_start_end_as_market_price_pull",
        "symbol_count": len(symbols),
        "symbols": symbols,
        "symbol_batch_size": config["symbol_batch_size"],
        "symbol_batch_count": len(symbol_batches),
        "symbol_batches": [batch.as_row() for batch in symbol_batches],
        "date_chunk_days": config["date_chunk_days"],
        "date_window_count": len(date_windows),
        "date_windows": [window.as_row() for window in date_windows],
        "min_dte": config["min_dte"],
        "max_dte": config["max_dte"],
        "strike_window_percent": config["strike_window_percent"],
        "moneyness_lower_bound": round(1.0 - config["strike_window_percent"], 10),
        "moneyness_upper_bound": round(1.0 + config["strike_window_percent"], 10),
        "include_weeklys": config["include_weeklys"],
        "resolution": config["resolution"],
        "object_store_prefix": config["object_store_prefix"],
        "fields": config["fields"],
        "export_job_count": len(export_jobs),
        "export_jobs": export_jobs,
        "warning_count": len(warnings),
        "warnings": warnings,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "requires_manual_approval": True,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "broker_order_id": None,
        "order_intent": None,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_quantconnect_research_export_script(plan: Mapping[str, Any]) -> str:
    """Render a QuantConnect Research script with the plan embedded as JSON.

    The script keeps the moneyness filter explicit: strikes are retained only
    when ``strike / underlying_price`` is between ``1 - strike_window_percent``
    and ``1 + strike_window_percent``. This avoids relying on LEAN's strike-count
    filter, which is not the same thing as a percentage moneyness window.
    """

    plan_json = json.dumps(plan, indent=2, sort_keys=True)
    return f'''# SignalForge QuantConnect filtered option chain export
# Generated from {FILTERED_OPTION_CHAIN_ARTIFACT_TYPE}.
# Scope: ETF universe only, same date range as market price, DTE {plan.get('min_dte')}..{plan.get('max_dte')}, moneyness +/- {plan.get('strike_window_percent')}.
#
# Run inside a QuantConnect Research notebook / research project that has access
# to the requested equity and option data. The script writes compressed JSON rows
# into Object Store keys listed in SIGNALFORGE_FILTERED_OPTION_CHAIN_PLAN.

from AlgorithmImports import *

import gzip
import json
from datetime import datetime

try:
    import pandas as pd
except Exception:  # pragma: no cover - QuantConnect Research normally includes pandas
    pd = None

SIGNALFORGE_FILTERED_OPTION_CHAIN_PLAN = {plan_json}


def _parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d")


def _safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _contract_row(underlying_symbol, quote_date, contract, underlying_price):
    strike = _safe_float(getattr(contract.ID, "StrikePrice", None) or getattr(contract, "Strike", None))
    expiration = getattr(contract.ID, "Date", None) or getattr(contract, "Expiry", None)
    if expiration is None or strike is None or not underlying_price:
        return None

    dte = (expiration.date() - quote_date.date()).days
    moneyness = strike / float(underlying_price)
    if dte < SIGNALFORGE_FILTERED_OPTION_CHAIN_PLAN["min_dte"]:
        return None
    if dte > SIGNALFORGE_FILTERED_OPTION_CHAIN_PLAN["max_dte"]:
        return None
    if moneyness < SIGNALFORGE_FILTERED_OPTION_CHAIN_PLAN["moneyness_lower_bound"]:
        return None
    if moneyness > SIGNALFORGE_FILTERED_OPTION_CHAIN_PLAN["moneyness_upper_bound"]:
        return None

    bid = _safe_float(getattr(contract, "BidPrice", None))
    ask = _safe_float(getattr(contract, "AskPrice", None))
    mid = None
    spread = None
    spread_pct = None
    if bid is not None and ask is not None and ask >= bid:
        mid = (bid + ask) / 2.0
        spread = ask - bid
        spread_pct = spread / mid if mid else None

    greeks = getattr(contract, "Greeks", None)
    return {{
        "underlying_symbol": str(underlying_symbol),
        "quote_date": quote_date.date().isoformat(),
        "contract_symbol": str(getattr(contract, "Symbol", "")),
        "expiration": expiration.date().isoformat(),
        "dte": dte,
        "strike": strike,
        "right": str(getattr(contract.ID, "OptionRight", getattr(contract, "Right", ""))),
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread": spread,
        "spread_pct": spread_pct,
        "last": _safe_float(getattr(contract, "LastPrice", None)),
        "volume": _safe_float(getattr(contract, "Volume", None)),
        "open_interest": _safe_float(getattr(contract, "OpenInterest", None)),
        "implied_volatility": _safe_float(getattr(contract, "ImpliedVolatility", None)),
        "delta": _safe_float(getattr(greeks, "Delta", None)) if greeks is not None else None,
        "gamma": _safe_float(getattr(greeks, "Gamma", None)) if greeks is not None else None,
        "theta": _safe_float(getattr(greeks, "Theta", None)) if greeks is not None else None,
        "vega": _safe_float(getattr(greeks, "Vega", None)) if greeks is not None else None,
        "rho": _safe_float(getattr(greeks, "Rho", None)) if greeks is not None else None,
        "underlying_price": _safe_float(underlying_price),
        "moneyness": moneyness,
    }}


def _write_object_store_json_gz(qb, key, rows, metadata):
    payload = {{
        "artifact_type": "signalforge_quantconnect_filtered_option_chain_export_part",
        "schema_version": "signalforge_quantconnect_filtered_option_chain_export_part.v1",
        "metadata": metadata,
        "row_count": len(rows),
        "rows": rows,
    }}
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    compressed = gzip.compress(raw)
    # QuantConnect Object Store supports saving byte payloads in Research/Algorithm contexts.
    qb.ObjectStore.SaveBytes(key, compressed)


def run_signalforge_filtered_option_chain_export():
    qb = QuantBook()
    plan = SIGNALFORGE_FILTERED_OPTION_CHAIN_PLAN
    summary = {{
        "artifact_type": "signalforge_quantconnect_filtered_option_chain_export_summary",
        "schema_version": "signalforge_quantconnect_filtered_option_chain_export_summary.v1",
        "start": plan["start"],
        "end": plan["end"],
        "symbol_count": plan["symbol_count"],
        "export_job_count": plan["export_job_count"],
        "written_object_count": 0,
        "written_row_count": 0,
        "object_store_keys": [],
        "warnings": [],
    }}

    for symbol in plan["symbols"]:
        qb.AddEquity(symbol, Resolution.Daily)
        option = qb.AddOption(symbol, Resolution.Daily)
        if plan.get("include_weeklys", True):
            option.SetFilter(lambda universe: universe.IncludeWeeklys().Expiration(plan["min_dte"], plan["max_dte"]))
        else:
            option.SetFilter(lambda universe: universe.Expiration(plan["min_dte"], plan["max_dte"]))

    # NOTE: The exact option-chain history API available can vary between Research and LEAN versions.
    # Keep this script as the generated export driver and adjust the small history retrieval block below
    # if your QuantConnect environment exposes a different chain-history shape.
    for job in plan["export_jobs"]:
        rows = []
        start = _parse_date(job["start"])
        end = _parse_date(job["end"])
        for symbol in job["symbols"]:
            equity_symbol = qb.Symbol(symbol)
            underlying_history = qb.History(equity_symbol, start, end, Resolution.Daily)
            if underlying_history is None or len(underlying_history) == 0:
                summary["warnings"].append(f"missing underlying history: {{symbol}} {{job['start']}}..{{job['end']}}")
                continue

            option_symbol = qb.Securities[equity_symbol].Symbol if False else None
            # Prefer OptionHistory when available in Research; otherwise, use this block as the one
            # environment-specific adapter point.
            option_history = qb.OptionHistory(symbol, start, end, Resolution.Daily)
            for slice_time, chain in option_history:
                underlying_price = None
                try:
                    underlying_price = float(underlying_history.loc[slice_time]["close"])
                except Exception:
                    pass
                if underlying_price is None:
                    continue
                for contract in chain:
                    row = _contract_row(symbol, slice_time, contract, underlying_price)
                    if row is not None:
                        rows.append(row)

        metadata = {{
            "job_index": job["job_index"],
            "start": job["start"],
            "end": job["end"],
            "symbols": job["symbols"],
            "min_dte": plan["min_dte"],
            "max_dte": plan["max_dte"],
            "strike_window_percent": plan["strike_window_percent"],
            "moneyness_lower_bound": plan["moneyness_lower_bound"],
            "moneyness_upper_bound": plan["moneyness_upper_bound"],
        }}
        _write_object_store_json_gz(qb, job["object_store_key"], rows, metadata)
        summary["written_object_count"] += 1
        summary["written_row_count"] += len(rows)
        summary["object_store_keys"].append(job["object_store_key"])

    qb.ObjectStore.Save("{plan.get('object_store_prefix')}/summary.json", json.dumps(summary, indent=2, sort_keys=True))
    return summary


summary = run_signalforge_filtered_option_chain_export()
print(json.dumps(summary, indent=2, sort_keys=True))
'''
