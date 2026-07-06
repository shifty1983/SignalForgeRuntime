from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


OLD_CANDIDATE_DIR = Path("artifacts/historical_strategy_candidate_rows_local_rebuild_20210601_20260531")
ELIGIBILITY_ROWS = Path("artifacts/historical_strategy_family_eligibility_enrichment_local_rebuild_20210601_20260531/signalforge_historical_strategy_family_eligibility_enriched_decision_rows.jsonl")
OUT_DIR = Path("artifacts/calendar_diagonal_candidate_source_audit_20210601_20260531")

OUT_DIR.mkdir(parents=True, exist_ok=True)

ROWS_OUT = OUT_DIR / "signalforge_calendar_diagonal_candidate_source_audit_rows.jsonl"
SUMMARY_OUT = OUT_DIR / "signalforge_calendar_diagonal_candidate_source_audit_summary.json"


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def first_present(row: dict[str, Any], fields: list[str]) -> Any:
    for field in fields:
        value = row.get(field)
        if value not in (None, ""):
            return value
    return None


def row_symbol(row: dict[str, Any]) -> str:
    return str(first_present(row, [
        "underlying_symbol",
        "requested_underlying_symbol",
        "symbol",
        "asset_symbol",
        "market_symbol",
        "ticker",
    ]) or "").strip().upper()


def row_date(row: dict[str, Any]) -> str:
    return str(first_present(row, [
        "decision_date",
        "quote_date",
        "asof_quote_date",
        "trade_date",
        "as_of_date",
        "date",
    ]) or "").strip()[:10]


def extract_status_map(row: dict[str, Any]) -> dict[str, str]:
    candidates = []

    if isinstance(row.get("strategy_family_statuses"), dict):
        candidates.append(row.get("strategy_family_statuses"))

    sfe = row.get("strategy_family_eligibility")
    if isinstance(sfe, dict) and isinstance(sfe.get("strategy_family_statuses"), dict):
        candidates.append(sfe.get("strategy_family_statuses"))

    rc = row.get("research_context")
    if isinstance(rc, dict):
        if isinstance(rc.get("strategy_family_statuses"), dict):
            candidates.append(rc.get("strategy_family_statuses"))

        rc_sfe = rc.get("strategy_family_eligibility")
        if isinstance(rc_sfe, dict) and isinstance(rc_sfe.get("strategy_family_statuses"), dict):
            candidates.append(rc_sfe.get("strategy_family_statuses"))

    for candidate in candidates:
        if candidate:
            return {str(k): str(v) for k, v in candidate.items()}

    return {}


def strategy_for_row(row: dict[str, Any]) -> str:
    return str(row.get("strategy") or row.get("strategy_name") or row.get("candidate_strategy") or "").strip()


def flatten_interesting(row: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "strategy",
        "strategy_name",
        "strategy_family",
        "strategy_family_status",
        "candidate_source",
        "candidate_source_family",
        "candidate_source_families",
        "candidate_source_family_statuses",
        "strategy_candidate_reason",
        "candidate_reason",
        "term_structure_state",
        "term_structure_shape",
        "term_structure_signal",
        "calendar_candidate",
        "diagonal_candidate",
        "premium_profile",
        "holding_period_days",
        "data_state",
    ]

    out = {}
    for key in keys:
        value = row.get(key)
        if value not in (None, "", [], {}):
            out[key] = value

    nested_names = [
        "option_behavior",
        "regime_asset_options_alignment",
        "strategy_family_eligibility",
        "research_context",
    ]

    for nested_name in nested_names:
        nested = row.get(nested_name)
        if isinstance(nested, dict):
            for key in [
                "term_structure_state",
                "term_structure_shape",
                "term_structure_signal",
                "iv_rank_state",
                "iv_percentile_state",
                "skew_state",
                "liquidity_state",
                "strategy_family_statuses",
            ]:
                value = nested.get(key)
                if value not in (None, "", [], {}):
                    out[f"{nested_name}.{key}"] = value

    return out


eligibility_by_key = {}

for row in read_jsonl(ELIGIBILITY_ROWS):
    key = (row_symbol(row), row_date(row))
    eligibility_by_key[key] = {
        "data_state": row.get("data_state") or row.get("source_decision_data_state"),
        "status_map": extract_status_map(row),
    }


candidate_paths = sorted(OLD_CANDIDATE_DIR.glob("*.jsonl"))

if not candidate_paths:
    raise SystemExit(f"No candidate files found under {OLD_CANDIDATE_DIR}")

strategy_counts = Counter()
strategy_family_counts = Counter()
strategy_status_counts = Counter()
strategy_source_family_counts = Counter()
strategy_source_status_counts = Counter()
calendar_diagonal_key_counts = Counter()
calendar_diagonal_status_map_counts = Counter()
calendar_diagonal_positive_family_counts = Counter()

samples = []
row_count = 0
calendar_diagonal_row_count = 0

with ROWS_OUT.open("w", encoding="utf-8", newline="\n") as out_handle:
    for path in candidate_paths:
        for row in read_jsonl(path):
            row_count += 1

            strategy = strategy_for_row(row)
            strategy_counts[strategy] += 1

            if strategy not in {"calendar_spread", "diagonal_spread"}:
                continue

            calendar_diagonal_row_count += 1

            symbol = row_symbol(row)
            date = row_date(row)
            key = (symbol, date)

            family = str(row.get("strategy_family") or "")
            status = str(row.get("strategy_family_status") or "")

            strategy_family_counts[f"{strategy}:{family}"] += 1
            strategy_status_counts[f"{strategy}:{status}"] += 1
            calendar_diagonal_key_counts[f"{symbol}:{date}:{strategy}"] += 1

            source_families = row.get("candidate_source_families")
            if isinstance(source_families, list):
                for source_family in source_families:
                    strategy_source_family_counts[f"{strategy}:{source_family}"] += 1

            source_statuses = row.get("candidate_source_family_statuses")
            if isinstance(source_statuses, dict):
                for source_family, source_status in source_statuses.items():
                    strategy_source_status_counts[f"{strategy}:{source_family}:{source_status}"] += 1

            eligibility = eligibility_by_key.get(key, {})
            status_map = eligibility.get("status_map") or {}

            for family_name, family_status in status_map.items():
                calendar_diagonal_status_map_counts[f"{strategy}:{family_name}:{family_status}"] += 1

                if family_status in {
                    "allowed",
                    "allowed_constrained",
                    "favored",
                    "favored_constrained",
                }:
                    calendar_diagonal_positive_family_counts[f"{strategy}:{family_name}:{family_status}"] += 1

            audit_row = {
                "symbol": symbol,
                "date": date,
                "strategy": strategy,
                "old_candidate_strategy_family": family,
                "old_candidate_strategy_family_status": status,
                "old_candidate_source_families": source_families,
                "old_candidate_source_family_statuses": source_statuses,
                "eligibility_data_state": eligibility.get("data_state"),
                "eligibility_status_map": status_map,
                "interesting_fields": flatten_interesting(row),
            }

            out_handle.write(json.dumps(audit_row, sort_keys=True) + "\n")

            if len(samples) < 50:
                samples.append(audit_row)


summary = {
    "adapter_type": "calendar_diagonal_candidate_source_auditor",
    "artifact_type": "signalforge_calendar_diagonal_candidate_source_audit",
    "is_ready": True,
    "candidate_paths": [str(path) for path in candidate_paths],
    "eligibility_rows_path": str(ELIGIBILITY_ROWS),
    "input_candidate_row_count": row_count,
    "calendar_diagonal_row_count": calendar_diagonal_row_count,
    "old_strategy_counts": dict(sorted(strategy_counts.items())),
    "calendar_diagonal_strategy_family_counts": dict(sorted(strategy_family_counts.items())),
    "calendar_diagonal_strategy_status_counts": dict(sorted(strategy_status_counts.items())),
    "calendar_diagonal_source_family_counts": dict(sorted(strategy_source_family_counts.items())),
    "calendar_diagonal_source_family_status_counts": dict(sorted(strategy_source_status_counts.items())),
    "calendar_diagonal_positive_family_counts": dict(sorted(calendar_diagonal_positive_family_counts.items())),
    "calendar_diagonal_status_map_counts": dict(sorted(calendar_diagonal_status_map_counts.items())),
    "samples": samples,
    "paths": {
        "rows_path": str(ROWS_OUT),
        "summary_path": str(SUMMARY_OUT),
    },
}

SUMMARY_OUT.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
print(json.dumps(summary, indent=2, sort_keys=True))
