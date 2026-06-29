from __future__ import annotations

import base64
import io
import json
import math
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

EXPLICIT_EXCLUSIONS = [
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

QUOTE_AWARE_ARTIFACT_TYPE = "signalforge_quantconnect_quote_aware_option_chain_snapshot"
QUOTE_AWARE_SCHEMA_VERSION = "signalforge_quantconnect_quote_aware_option_chain_snapshot.v1"
BASE64_MARKER = "SIGNALFORGE_QUOTE_AWARE_OPTION_CHAIN_ZIP_BASE64_PART"


@dataclass(frozen=True)
class OptionChainBatch:
    batch_number: int
    batch_count: int
    symbols: tuple[str, ...]
    quote_dates: tuple[str, ...]


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def number_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def clean_symbol(value: Any) -> str:
    text = str(value).strip().upper()
    if not text:
        raise ValueError("symbol must not be blank")
    return text


def parse_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def date_text(value: str | date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value).split(" ")[0]


def weekday_date_range(start: str | date, end: str | date) -> list[str]:
    start_date = parse_date(start)
    end_date = parse_date(end)
    if end_date < start_date:
        raise ValueError("end date must be greater than or equal to start date")

    dates: list[str] = []
    cursor = start_date
    while cursor <= end_date:
        if cursor.weekday() < 5:
            dates.append(cursor.strftime("%Y-%m-%d"))
        cursor += timedelta(days=1)
    return dates


def parse_quote_dates(
    *,
    quote_dates: Sequence[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[str]:
    if quote_dates:
        return sorted({parse_date(item).strftime("%Y-%m-%d") for item in quote_dates})
    if start_date and end_date:
        return weekday_date_range(start_date, end_date)
    raise ValueError("provide quote dates or start/end date")


def chunked(items: Sequence[Any], size: int) -> list[tuple[Any, ...]]:
    if size <= 0:
        raise ValueError("chunk size must be positive")
    return [tuple(items[index : index + size]) for index in range(0, len(items), size)]


def build_batches(
    *,
    symbols: Sequence[str],
    quote_dates: Sequence[str],
    symbol_batch_size: int,
    date_batch_size: int,
) -> list[OptionChainBatch]:
    clean_symbols = tuple(clean_symbol(symbol) for symbol in symbols)
    clean_dates = tuple(parse_date(item).strftime("%Y-%m-%d") for item in quote_dates)
    symbol_batches = chunked(clean_symbols, symbol_batch_size)
    date_batches = chunked(clean_dates, date_batch_size)

    combinations: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    for date_group in date_batches:
        for symbol_group in symbol_batches:
            combinations.append((symbol_group, date_group))

    batch_count = len(combinations)
    return [
        OptionChainBatch(
            batch_number=index + 1,
            batch_count=batch_count,
            symbols=symbol_group,
            quote_dates=date_group,
        )
        for index, (symbol_group, date_group) in enumerate(combinations)
    ]


def extract_requested_symbols(payload: Mapping[str, Any]) -> list[str]:
    for key in ("requested_symbols", "symbols", "universe", "underlyings"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            return [clean_symbol(item) for item in value]

    rows = payload.get("rows")
    if isinstance(rows, list):
        values = [row.get("symbol") or row.get("underlying_symbol") for row in rows if isinstance(row, Mapping)]
        symbols = [clean_symbol(value) for value in values if value]
        if symbols:
            return sorted(set(symbols))

    raise ValueError("could not find requested symbols in request payload")


def build_snapshot_payload(
    *,
    batch_number: int,
    batch_count: int,
    requested_symbols: Sequence[str],
    quote_dates: Sequence[str],
    option_rows: Sequence[Mapping[str, Any]],
    diagnostics: Sequence[Mapping[str, Any]],
    filters: Mapping[str, Any],
    source: str = "quantconnect_research_notebook_option_chain_dataframe",
) -> dict[str, Any]:
    observed_symbols = sorted(
        {
            clean_symbol(row["underlying_symbol"])
            for row in option_rows
            if row.get("underlying_symbol")
        }
    )
    observed_quote_dates = sorted(
        {str(row["quote_date"]) for row in option_rows if row.get("quote_date")}
    )
    bid_ask_rows = [
        row
        for row in option_rows
        if number_or_none(row.get("bid")) is not None and number_or_none(row.get("ask")) is not None
    ]
    positive_bid_ask_rows = [
        row
        for row in bid_ask_rows
        if (number_or_none(row.get("bid")) or 0) > 0 and (number_or_none(row.get("ask")) or 0) > 0
    ]

    return {
        "artifact_type": QUOTE_AWARE_ARTIFACT_TYPE,
        "schema_version": QUOTE_AWARE_SCHEMA_VERSION,
        "status": "ready",
        "source": source,
        "batch_number": batch_number,
        "batch_count": batch_count,
        "requested_symbols": [clean_symbol(symbol) for symbol in requested_symbols],
        "requested_symbol_count": len(requested_symbols),
        "quote_dates": list(quote_dates),
        "quote_date_count": len(quote_dates),
        "observed_symbols": observed_symbols,
        "observed_symbol_count": len(observed_symbols),
        "observed_quote_dates": observed_quote_dates,
        "observed_quote_date_count": len(observed_quote_dates),
        "option_row_count": len(option_rows),
        "bid_ask_row_count": len(bid_ask_rows),
        "positive_bid_ask_row_count": len(positive_bid_ask_rows),
        "diagnostics": list(diagnostics),
        "filters": dict(filters),
        "option_rows": [dict(row) for row in option_rows],
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def encode_payload_zip_base64(
    payload: Mapping[str, Any],
    *,
    json_filename: str,
    zip_filename: str | None = None,
) -> tuple[str, bytes, bytes]:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(json_filename, raw)
    zip_bytes = zip_buffer.getvalue()
    encoded = base64.b64encode(zip_bytes).decode("ascii")
    return encoded, raw, zip_bytes


def split_base64_chunks(encoded: str, chunk_size: int = 4000) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk size must be positive")
    return [encoded[index : index + chunk_size] for index in range(0, len(encoded), chunk_size)]


def decode_base64_parts(parts: Sequence[str]) -> bytes:
    text = "".join(part.strip() for part in parts if part and part.strip())
    if not text:
        raise ValueError("no base64 parts were provided")
    return base64.b64decode(text)


def extract_base64_parts_from_text(text: str, marker: str = BASE64_MARKER) -> list[str]:
    parts: list[tuple[int, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith(marker):
            continue
        tokens = line.split(maxsplit=2)
        if len(tokens) != 3:
            continue
        ordinal_text, chunk = tokens[1], tokens[2]
        ordinal = int(ordinal_text.split("/")[0])
        parts.append((ordinal, chunk.strip()))
    return [chunk for _, chunk in sorted(parts, key=lambda item: item[0])]


def read_payloads_from_zip_bytes(zip_bytes: bytes) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        for name in sorted(zf.namelist()):
            if not name.endswith(".json"):
                continue
            payloads.append(json.loads(zf.read(name).decode("utf-8-sig")))
    return payloads


def decode_output_text(text: str) -> tuple[bytes, list[dict[str, Any]]]:
    parts = extract_base64_parts_from_text(text)
    zip_bytes = decode_base64_parts(parts)
    payloads = read_payloads_from_zip_bytes(zip_bytes)
    return zip_bytes, payloads


def merge_quote_aware_snapshots(payloads: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not payloads:
        raise ValueError("at least one payload is required")

    requested_symbols: set[str] = set()
    quote_dates: set[str] = set()
    rows: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    filters: dict[str, Any] = {}

    for payload in payloads:
        if payload.get("artifact_type") != QUOTE_AWARE_ARTIFACT_TYPE:
            raise ValueError(f"unexpected artifact type: {payload.get('artifact_type')}")
        requested_symbols.update(clean_symbol(item) for item in payload.get("requested_symbols", []))
        quote_dates.update(str(item) for item in payload.get("quote_dates", []))
        filters.update(payload.get("filters", {}) or {})
        rows.extend(dict(row) for row in payload.get("option_rows", []) or [])
        diagnostics.extend(dict(item) for item in payload.get("diagnostics", []) or [])

    # Deduplicate exact contract-date rows while preserving deterministic order.
    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        key = (
            row.get("underlying_symbol"),
            row.get("quote_date"),
            row.get("contract_symbol"),
            row.get("expiration"),
            row.get("strike"),
            row.get("right"),
        )
        deduped[key] = row

    merged_rows = [
        deduped[key]
        for key in sorted(
            deduped,
            key=lambda item: (
                str(item[1] or ""),
                str(item[0] or ""),
                str(item[3] or ""),
                float(item[4] or 0),
                str(item[5] or ""),
                str(item[2] or ""),
            ),
        )
    ]

    return build_snapshot_payload(
        batch_number=1,
        batch_count=1,
        requested_symbols=sorted(requested_symbols),
        quote_dates=sorted(quote_dates),
        option_rows=merged_rows,
        diagnostics=diagnostics,
        filters=filters,
        source="quantconnect_research_notebook_option_chain_dataframe_merged",
    )
