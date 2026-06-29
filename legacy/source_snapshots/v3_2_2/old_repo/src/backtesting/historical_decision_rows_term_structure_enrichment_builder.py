from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Tuple


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc

            if not isinstance(payload, dict):
                raise ValueError(f"Expected object at line {line_number}")

            rows.append(payload)

    return rows


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _key(symbol: Any, date: Any) -> tuple[str, str]:
    return (str(symbol).upper(), str(date)[:10])


def _option_behavior(row: Mapping[str, Any]) -> dict[str, Any]:
    value = row.get("option_behavior")
    if isinstance(value, Mapping):
        return dict(value)
    return {
        "source_state": "missing",
        "state": "missing",
    }


def build_historical_decision_rows_term_structure_enrichment(
    *,
    decision_rows: list[Mapping[str, Any]],
    term_structure_rows: list[Mapping[str, Any]],
) -> Tuple[list[dict[str, Any]], dict[str, Any]]:
    term_by_symbol_date: dict[tuple[str, str], Mapping[str, Any]] = {}

    duplicate_term_keys = 0
    for term_row in term_structure_rows:
        symbol = term_row.get("symbol")
        date = term_row.get("date")

        if not symbol or not date:
            continue

        key = _key(symbol, date)

        if key in term_by_symbol_date:
            duplicate_term_keys += 1
            continue

        term_by_symbol_date[key] = term_row

    output_rows: list[dict[str, Any]] = []

    data_state_counts: Counter[str] = Counter()
    option_behavior_state_counts: Counter[str] = Counter()
    term_structure_state_counts: Counter[str] = Counter()
    term_structure_shape_counts: Counter[str] = Counter()

    enriched_row_count = 0
    complete_rows_enriched_count = 0
    missing_term_structure_count = 0

    for source_row in decision_rows:
        row = dict(source_row)

        symbol = row.get("symbol")
        date = row.get("date") or row.get("decision_date")
        data_state = str(row.get("data_state") or "missing")

        data_state_counts[data_state] += 1

        option_behavior = _option_behavior(row)
        option_behavior_state_counts[str(option_behavior.get("state") or "missing")] += 1

        term_row = term_by_symbol_date.get(_key(symbol, date)) if symbol and date else None

        if term_row:
            option_behavior["term_structure_state"] = "available"
            option_behavior["term_structure_source_date"] = term_row.get("date")
            option_behavior["term_structure_shape"] = term_row.get("term_structure_shape")
            option_behavior["front_expiration"] = term_row.get("front_expiration")
            option_behavior["back_expiration"] = term_row.get("back_expiration")
            option_behavior["front_dte"] = term_row.get("front_dte")
            option_behavior["back_dte"] = term_row.get("back_dte")
            option_behavior["front_iv"] = term_row.get("front_iv")
            option_behavior["back_iv"] = term_row.get("back_iv")
            option_behavior["front_back_iv_spread"] = term_row.get("front_back_iv_spread")
            option_behavior["front_back_iv_spread_pct"] = term_row.get("front_back_iv_spread_pct")
            option_behavior["term_structure_front_contract_count"] = term_row.get("front_contract_count")
            option_behavior["term_structure_back_contract_count"] = term_row.get("back_contract_count")
            option_behavior["term_structure_expiration_count"] = term_row.get("expiration_count")

            enriched_row_count += 1
            if data_state == "complete":
                complete_rows_enriched_count += 1

            term_structure_state_counts["available"] += 1
            term_structure_shape_counts[str(term_row.get("term_structure_shape") or "missing")] += 1
        else:
            option_behavior["term_structure_state"] = "unavailable"
            option_behavior["term_structure_source_date"] = None

            missing_term_structure_count += 1
            term_structure_state_counts["unavailable"] += 1

        row["option_behavior"] = option_behavior
        row["term_structure_enrichment"] = {
            "adapter_type": "historical_decision_rows_term_structure_enrichment_builder",
            "source_state": "available" if term_row else "missing",
            "source_key": f"{symbol}_{str(date)[:10]}" if symbol and date else None,
        }

        output_rows.append(row)

    blockers: list[str] = []

    if not output_rows:
        blockers.append("no_decision_rows_written")

    if enriched_row_count == 0:
        blockers.append("no_decision_rows_enriched_with_term_structure")

    if duplicate_term_keys:
        blockers.append("duplicate_term_structure_symbol_date_keys")

    summary: dict[str, Any] = {
        "adapter_type": "historical_decision_rows_term_structure_enrichment_builder",
        "artifact_type": "signalforge_historical_decision_rows_term_structure_enrichment",
        "contract": "historical_decision_rows_term_structure_enrichment",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "input_decision_row_count": len(decision_rows),
        "input_term_structure_row_count": len(term_structure_rows),
        "output_decision_row_count": len(output_rows),
        "enriched_decision_row_count": enriched_row_count,
        "complete_rows_enriched_count": complete_rows_enriched_count,
        "missing_term_structure_count": missing_term_structure_count,
        "duplicate_term_structure_symbol_date_keys": duplicate_term_keys,
        "data_state_counts": dict(sorted(data_state_counts.items())),
        "option_behavior_state_counts": dict(sorted(option_behavior_state_counts.items())),
        "term_structure_state_counts": dict(sorted(term_structure_state_counts.items())),
        "term_structure_shape_counts": dict(sorted(term_structure_shape_counts.items())),
        "paths": {},
    }

    return output_rows, summary


def build_historical_decision_rows_term_structure_enrichment_artifact(
    *,
    decision_rows_path: str | Path,
    term_structure_rows_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)

    rows_path = output_path / "signalforge_historical_decision_rows_enriched.jsonl"
    summary_path = output_path / "signalforge_historical_decision_rows_term_structure_enrichment_summary.json"

    decision_rows = read_jsonl(decision_rows_path)
    term_structure_rows = read_jsonl(term_structure_rows_path)

    rows, summary = build_historical_decision_rows_term_structure_enrichment(
        decision_rows=decision_rows,
        term_structure_rows=term_structure_rows,
    )

    summary["paths"] = {
        "decision_rows_path": str(decision_rows_path),
        "term_structure_rows_path": str(term_structure_rows_path),
        "rows_path": str(rows_path),
        "summary_path": str(summary_path),
    }

    write_jsonl(rows_path, rows)
    write_json(summary_path, summary)

    return summary
