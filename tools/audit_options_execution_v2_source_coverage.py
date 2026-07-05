from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


SOURCE_PATH = Path("artifacts/qc_replay_5y_behavior_inputs/signalforge_qc_replay_option_behavior_input.jsonl")

METRICS_PATH = Path(
    "artifacts/options_execution_symbol_date_metrics_v2full_20260703_234020/"
    "signalforge_options_execution_symbol_date_metrics.jsonl"
)

OUTPUT_DIR = Path("artifacts/options_execution_v2_source_coverage_audit_v2full_20260703_234020")


SYMBOL_FIELDS = [
    "underlying_symbol",
    "requested_underlying_symbol",
    "option_underlying",
    "underlying",
    "root_symbol",
    "market_symbol",
    "asset_symbol",
    "ticker",
    "symbol",
]

DATE_FIELDS = [
    "quote_date",
    "date",
    "as_of_date",
    "decision_date",
    "trade_date",
]

CONTRACT_FIELDS = [
    "contract_key",
    "option_symbol",
    "contract_symbol",
    "canonical_symbol",
]


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception as exc:
                raise RuntimeError(f"Bad JSON at {path}:{line_number}: {exc}") from exc


def normalize_symbol(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None

    # Avoid treating full OCC-style option symbols as underlyings when there is another field.
    if " " in text and len(text) > 12:
        return None

    return text.replace("/", "-")


def normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:10]


def first_present(row: dict[str, Any], fields: list[str]) -> Any:
    for field in fields:
        if field in row and row.get(field) not in (None, ""):
            return row.get(field)
    return None


def row_symbol(row: dict[str, Any]) -> str | None:
    return normalize_symbol(first_present(row, SYMBOL_FIELDS))


def row_date(row: dict[str, Any]) -> str | None:
    return normalize_date(first_present(row, DATE_FIELDS))


def row_contract(row: dict[str, Any]) -> str | None:
    value = first_present(row, CONTRACT_FIELDS)
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def collect_source(path: Path):
    symbols = set()
    symbol_dates = set()
    contracts = set()

    symbol_counts = Counter()
    symbol_date_counts = Counter()

    row_count = 0
    missing_symbol_count = 0
    missing_date_count = 0

    for row in read_jsonl(path):
        row_count += 1

        symbol = row_symbol(row)
        quote_date = row_date(row)
        contract = row_contract(row)

        if symbol:
            symbols.add(symbol)
            symbol_counts[symbol] += 1
        else:
            missing_symbol_count += 1

        if symbol and quote_date:
            key = (symbol, quote_date)
            symbol_dates.add(key)
            symbol_date_counts[key] += 1
        elif symbol and not quote_date:
            missing_date_count += 1

        if contract:
            contracts.add(contract)

    return {
        "row_count": row_count,
        "symbols": symbols,
        "symbol_dates": symbol_dates,
        "contracts": contracts,
        "symbol_counts": symbol_counts,
        "symbol_date_counts": symbol_date_counts,
        "missing_symbol_count": missing_symbol_count,
        "missing_date_count": missing_date_count,
    }


def collect_metrics(path: Path):
    symbols = set()
    symbol_dates = set()

    row_count = 0
    total_contract_rows = 0
    symbol_counts = Counter()
    symbol_date_contract_rows = Counter()

    for row in read_jsonl(path):
        row_count += 1

        symbol = row_symbol(row)
        quote_date = row_date(row)
        contract_row_count = int(float(row.get("row_count") or 0))

        if symbol:
            symbols.add(symbol)
            symbol_counts[symbol] += 1

        if symbol and quote_date:
            key = (symbol, quote_date)
            symbol_dates.add(key)
            symbol_date_contract_rows[key] += contract_row_count

        total_contract_rows += contract_row_count

    return {
        "row_count": row_count,
        "total_contract_rows": total_contract_rows,
        "symbols": symbols,
        "symbol_dates": symbol_dates,
        "symbol_counts": symbol_counts,
        "symbol_date_contract_rows": symbol_date_contract_rows,
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not SOURCE_PATH.exists():
        raise SystemExit(f"Missing source path: {SOURCE_PATH}")

    if not METRICS_PATH.exists():
        raise SystemExit(f"Missing metrics path: {METRICS_PATH}")

    source = collect_source(SOURCE_PATH)
    metrics = collect_metrics(METRICS_PATH)

    missing_symbols = sorted(source["symbols"] - metrics["symbols"])
    extra_symbols = sorted(metrics["symbols"] - source["symbols"])

    missing_symbol_dates = sorted(source["symbol_dates"] - metrics["symbol_dates"])
    extra_symbol_dates = sorted(metrics["symbol_dates"] - source["symbol_dates"])

    common_symbol_dates = source["symbol_dates"] & metrics["symbol_dates"]

    # Check whether the aggregated row_count in metrics matches source rows by symbol/date.
    mismatched_symbol_dates = []
    for key in sorted(common_symbol_dates):
        source_count = source["symbol_date_counts"][key]
        metric_count = metrics["symbol_date_contract_rows"][key]
        if source_count != metric_count:
            mismatched_symbol_dates.append({
                "underlying_symbol": key[0],
                "quote_date": key[1],
                "source_row_count": source_count,
                "metric_contract_row_count": metric_count,
                "difference": metric_count - source_count,
            })

    summary = {
        "adapter_type": "options_execution_v2_source_coverage_auditor",
        "artifact_type": "signalforge_options_execution_v2_source_coverage_audit",
        "contract": "options_execution_v2_source_coverage_audit",
        "source_path": str(SOURCE_PATH),
        "metrics_path": str(METRICS_PATH),

        "source_row_count": source["row_count"],
        "source_symbol_count": len(source["symbols"]),
        "source_symbol_date_count": len(source["symbol_dates"]),
        "source_contract_count": len(source["contracts"]),
        "source_missing_symbol_count": source["missing_symbol_count"],
        "source_missing_date_count": source["missing_date_count"],

        "metrics_row_count": metrics["row_count"],
        "metrics_total_contract_rows": metrics["total_contract_rows"],
        "metrics_symbol_count": len(metrics["symbols"]),
        "metrics_symbol_date_count": len(metrics["symbol_dates"]),

        "missing_symbol_count": len(missing_symbols),
        "missing_symbols": missing_symbols,
        "extra_symbol_count": len(extra_symbols),
        "extra_symbols": extra_symbols[:100],

        "missing_symbol_date_count": len(missing_symbol_dates),
        "missing_symbol_dates_sample": [
            {"underlying_symbol": s, "quote_date": d}
            for s, d in missing_symbol_dates[:100]
        ],

        "extra_symbol_date_count": len(extra_symbol_dates),
        "extra_symbol_dates_sample": [
            {"underlying_symbol": s, "quote_date": d}
            for s, d in extra_symbol_dates[:100]
        ],

        "mismatched_symbol_date_count": len(mismatched_symbol_dates),
        "mismatched_symbol_dates_sample": mismatched_symbol_dates[:100],

        "top_missing_symbols_by_source_row_count": [
            {
                "underlying_symbol": symbol,
                "source_row_count": source["symbol_counts"][symbol],
            }
            for symbol in sorted(missing_symbols, key=lambda x: source["symbol_counts"][x], reverse=True)[:100]
        ],
    }

    blockers = []

    if missing_symbols:
        blockers.append("source_symbols_missing_from_execution_metrics")

    if missing_symbol_dates:
        blockers.append("source_symbol_dates_missing_from_execution_metrics")

    if mismatched_symbol_dates:
        blockers.append("source_metric_symbol_date_row_count_mismatch")

    summary["blockers"] = blockers
    summary["blocker_count"] = len(blockers)
    summary["is_ready"] = len(blockers) == 0

    summary_path = OUTPUT_DIR / "signalforge_options_execution_v2_source_coverage_audit.json"
    summary["paths"] = {
        "summary_path": str(summary_path),
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))

    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
