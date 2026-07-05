from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def symbol_from_row(row: dict[str, Any]) -> str | None:
    candidates = [
        "underlying_symbol",
        "symbol",
        "ticker",
        "asset_symbol",
        "selected_symbol",
        "market_symbol",
        "option_underlying",
    ]
    for field in candidates:
        value = row.get(field)
        if value:
            return str(value).upper()
    return None


def symbols_from_jsonl(path: Path) -> set[str]:
    symbols = set()
    for row in read_jsonl(path):
        symbol = symbol_from_row(row)
        if symbol:
            symbols.add(symbol)
    return symbols


def count_symbols(path: Path) -> Counter:
    counter = Counter()
    for row in read_jsonl(path):
        symbol = symbol_from_row(row)
        if symbol:
            counter[symbol] += 1
    return counter


paths = {
    "symbol_date_metrics": Path("artifacts/options_execution_symbol_date_metrics_v2full_20260703_234020/signalforge_options_execution_symbol_date_metrics.jsonl"),

    "historical_decision_rows": Path("artifacts/historical_decision_rows_20210601_20260531/signalforge_historical_decision_rows.jsonl"),

    "historical_strategy_selection_rows": Path("artifacts/historical_strategy_selection_rows_20210601_20260531/signalforge_historical_strategy_selection_rows.jsonl"),

    "selected_trade_sequence": Path("artifacts/portfolio_selected_trade_sequence_20210601_20260531/signalforge_portfolio_selected_trade_sequence.jsonl"),

    "position_sizing_replay": Path("artifacts/portfolio_position_sizing_replay_20210601_20260531/signalforge_portfolio_position_sizing_replay.jsonl"),
}

metric_symbols = symbols_from_jsonl(paths["symbol_date_metrics"])

summary = {
    "adapter_type": "options_execution_symbol_coverage_auditor",
    "artifact_type": "signalforge_options_execution_symbol_coverage_audit",
    "is_ready": True,
    "blocker_count": 0,
    "blockers": [],
    "metric_symbol_count": len(metric_symbols),
    "metric_symbols_sample": sorted(metric_symbols)[:25],
    "comparisons": {},
}

for name, path in paths.items():
    if name == "symbol_date_metrics":
        continue

    symbols = symbols_from_jsonl(path)
    counts = count_symbols(path)

    missing = sorted(symbols - metric_symbols)
    extra = sorted(metric_symbols - symbols)

    comparison = {
        "path": str(path),
        "exists": path.exists(),
        "source_symbol_count": len(symbols),
        "missing_from_execution_metrics_count": len(missing),
        "missing_from_execution_metrics": missing,
        "top_missing_by_source_row_count": [
            {"symbol": symbol, "source_row_count": counts[symbol]}
            for symbol in sorted(missing, key=lambda x: counts[x], reverse=True)[:50]
        ],
        "extra_in_execution_metrics_count": len(extra),
    }

    summary["comparisons"][name] = comparison

# Hard blocker only if selected/position-sized trade symbols are missing.
hard_sources = ["selected_trade_sequence", "position_sizing_replay"]

for source in hard_sources:
    comparison = summary["comparisons"].get(source, {})
    if comparison.get("exists") and comparison.get("missing_from_execution_metrics_count", 0) > 0:
        summary["is_ready"] = False
        summary["blockers"].append(f"{source}_symbols_missing_execution_metrics")

summary["blocker_count"] = len(summary["blockers"])

output_dir = Path("artifacts/options_execution_symbol_coverage_audit_v2full_20260703_234020")
output_dir.mkdir(parents=True, exist_ok=True)

summary_path = output_dir / "signalforge_options_execution_symbol_coverage_audit.json"
summary["paths"] = {"summary_path": str(summary_path)}

summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
print(json.dumps(summary, indent=2, sort_keys=True))
