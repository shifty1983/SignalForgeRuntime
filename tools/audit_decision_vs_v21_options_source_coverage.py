from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if line:
                yield line_number, json.loads(line)


def first_present(row: dict[str, Any], fields: list[str]) -> Any:
    for field in fields:
        value = row.get(field)
        if value not in (None, ""):
            return value
    return None


def key_for_row(row: dict[str, Any]) -> tuple[str, str]:
    symbol = str(first_present(row, [
        "underlying_symbol",
        "requested_underlying_symbol",
        "option_underlying",
        "underlying",
        "root_symbol",
        "market_symbol",
        "asset_symbol",
        "ticker",
        "symbol",
    ]) or "").strip().upper()

    date = str(first_present(row, [
        "quote_date",
        "decision_date",
        "asof_quote_date",
        "trade_date",
        "as_of_date",
        "date",
    ]) or "").strip()[:10]

    return symbol, date


def load_decision_keys(path: Path):
    decision = {}
    duplicate_count = 0
    bad_count = 0
    data_state_counts = Counter()

    for _, row in read_jsonl(path):
        key = key_for_row(row)

        if not key[0] or not key[1]:
            bad_count += 1
            continue

        if key in decision:
            duplicate_count += 1

        data_state = str(row.get("data_state") or row.get("source_decision_data_state") or "unknown")
        data_state_counts[data_state] += 1

        decision[key] = {
            "symbol": key[0],
            "date": key[1],
            "data_state": data_state,
            "decision_row": row,
        }

    return decision, duplicate_count, bad_count, data_state_counts


def collect_key_counts(path: Path, decision_keys: set[tuple[str, str]], label: str):
    all_key_counts = Counter()
    relevant_key_counts = Counter()
    relevant_contract_rows = 0
    row_count = 0
    bad_count = 0

    symbol_counts = Counter()
    relevant_symbol_counts = Counter()

    for _, row in read_jsonl(path):
        row_count += 1
        key = key_for_row(row)

        if not key[0] or not key[1]:
            bad_count += 1
            continue

        all_key_counts[key] += 1
        symbol_counts[key[0]] += 1

        if key in decision_keys:
            relevant_key_counts[key] += 1
            relevant_symbol_counts[key[0]] += 1
            relevant_contract_rows += 1

    return {
        "label": label,
        "path": str(path),
        "row_count": row_count,
        "bad_key_count": bad_count,
        "all_key_count": len(all_key_counts),
        "relevant_key_count": len(relevant_key_counts),
        "relevant_row_count": relevant_contract_rows,
        "all_key_counts": all_key_counts,
        "relevant_key_counts": relevant_key_counts,
        "symbol_count": len(symbol_counts),
        "relevant_symbol_count": len(relevant_symbol_counts),
        "top_relevant_symbols": dict(relevant_symbol_counts.most_common(50)),
    }


def audit(
    decision_rows_path: Path,
    contract_features_path: Path,
    symbol_date_metrics_path: Path | None,
    option_behavior_source_path: Path | None,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    rows_path = output_dir / "signalforge_decision_vs_v21_options_source_coverage_rows.jsonl"
    summary_path = output_dir / "signalforge_decision_vs_v21_options_source_coverage_audit.json"

    decision, duplicate_decision_key_count, bad_decision_key_count, decision_data_state_counts = load_decision_keys(decision_rows_path)
    decision_keys = set(decision)

    contract = collect_key_counts(contract_features_path, decision_keys, "contract_features")

    metrics = None
    if symbol_date_metrics_path is not None:
        metrics = collect_key_counts(symbol_date_metrics_path, decision_keys, "symbol_date_metrics")

    source = None
    if option_behavior_source_path is not None:
        source = collect_key_counts(option_behavior_source_path, decision_keys, "option_behavior_source")

    classification_counts = Counter()
    classification_data_state_counts = Counter()
    missing_contract_data_state_counts = Counter()

    missing_contract_samples = []
    partial_missing_samples = []
    mismatch_samples = []

    with rows_path.open("w", encoding="utf-8", newline="\n") as handle:
        for key in sorted(decision_keys):
            symbol, date = key
            data_state = decision[key]["data_state"]

            contract_count = contract["relevant_key_counts"].get(key, 0)

            metrics_count = 0
            if metrics is not None:
                metrics_count = metrics["relevant_key_counts"].get(key, 0)

            source_count = 0
            if source is not None:
                source_count = source["relevant_key_counts"].get(key, 0)

            has_contract = contract_count > 0
            has_metrics = metrics_count > 0
            has_source = source_count > 0

            if has_contract:
                classification = "decision_key_has_v21_contract_features"
            elif has_source:
                classification = "decision_key_missing_contract_features_but_present_in_option_behavior_source"
            elif has_metrics:
                classification = "decision_key_missing_contract_features_but_present_in_symbol_date_metrics"
            else:
                classification = "decision_key_missing_from_all_v21_option_sources"

            classification_counts[classification] += 1
            classification_data_state_counts[f"{classification}:{data_state}"] += 1

            if not has_contract:
                missing_contract_data_state_counts[data_state] += 1

                sample = {
                    "symbol": symbol,
                    "date": date,
                    "data_state": data_state,
                    "classification": classification,
                    "v21_contract_feature_count": contract_count,
                    "v21_symbol_date_metric_count": metrics_count,
                    "v21_option_behavior_source_count": source_count,
                }

                if len(missing_contract_samples) < 100:
                    missing_contract_samples.append(sample)

                if data_state == "partial_option_missing" and len(partial_missing_samples) < 100:
                    partial_missing_samples.append(sample)

            if (has_source or has_metrics) and not has_contract and len(mismatch_samples) < 100:
                mismatch_samples.append({
                    "symbol": symbol,
                    "date": date,
                    "data_state": data_state,
                    "classification": classification,
                    "v21_symbol_date_metric_count": metrics_count,
                    "v21_option_behavior_source_count": source_count,
                    "v21_contract_feature_count": contract_count,
                })

            handle.write(json.dumps({
                "symbol": symbol,
                "date": date,
                "data_state": data_state,
                "classification": classification,
                "v21_contract_feature_count": contract_count,
                "v21_symbol_date_metric_count": metrics_count,
                "v21_option_behavior_source_count": source_count,
            }, sort_keys=True) + "\n")

    blockers = []

    if duplicate_decision_key_count:
        blockers.append("duplicate_decision_keys")

    if bad_decision_key_count:
        blockers.append("bad_decision_keys")

    if classification_counts["decision_key_missing_contract_features_but_present_in_option_behavior_source"]:
        blockers.append("contract_features_missing_keys_present_in_option_behavior_source")

    if classification_counts["decision_key_missing_contract_features_but_present_in_symbol_date_metrics"]:
        blockers.append("contract_features_missing_keys_present_in_symbol_date_metrics")

    summary = {
        "adapter_type": "decision_vs_v21_options_source_coverage_auditor",
        "artifact_type": "signalforge_decision_vs_v21_options_source_coverage_audit",
        "contract": "decision_vs_v21_options_source_coverage_audit",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "decision_rows_path": str(decision_rows_path),
        "contract_features_path": str(contract_features_path),
        "symbol_date_metrics_path": str(symbol_date_metrics_path) if symbol_date_metrics_path else None,
        "option_behavior_source_path": str(option_behavior_source_path) if option_behavior_source_path else None,
        "decision_key_count": len(decision_keys),
        "duplicate_decision_key_count": duplicate_decision_key_count,
        "bad_decision_key_count": bad_decision_key_count,
        "decision_data_state_counts": dict(sorted(decision_data_state_counts.items())),
        "classification_counts": dict(sorted(classification_counts.items())),
        "classification_data_state_counts": dict(sorted(classification_data_state_counts.items())),
        "missing_contract_data_state_counts": dict(sorted(missing_contract_data_state_counts.items())),
        "contract_features": {
            "row_count": contract["row_count"],
            "bad_key_count": contract["bad_key_count"],
            "all_key_count": contract["all_key_count"],
            "relevant_key_count": contract["relevant_key_count"],
            "relevant_row_count": contract["relevant_row_count"],
            "symbol_count": contract["symbol_count"],
            "relevant_symbol_count": contract["relevant_symbol_count"],
            "top_relevant_symbols": contract["top_relevant_symbols"],
        },
        "symbol_date_metrics": None if metrics is None else {
            "row_count": metrics["row_count"],
            "bad_key_count": metrics["bad_key_count"],
            "all_key_count": metrics["all_key_count"],
            "relevant_key_count": metrics["relevant_key_count"],
            "relevant_row_count": metrics["relevant_row_count"],
            "symbol_count": metrics["symbol_count"],
            "relevant_symbol_count": metrics["relevant_symbol_count"],
            "top_relevant_symbols": metrics["top_relevant_symbols"],
        },
        "option_behavior_source": None if source is None else {
            "row_count": source["row_count"],
            "bad_key_count": source["bad_key_count"],
            "all_key_count": source["all_key_count"],
            "relevant_key_count": source["relevant_key_count"],
            "relevant_row_count": source["relevant_row_count"],
            "symbol_count": source["symbol_count"],
            "relevant_symbol_count": source["relevant_symbol_count"],
            "top_relevant_symbols": source["top_relevant_symbols"],
        },
        "missing_contract_samples": missing_contract_samples,
        "partial_option_missing_samples": partial_missing_samples,
        "mismatch_samples": mismatch_samples,
        "paths": {
            "rows_path": str(rows_path),
            "summary_path": str(summary_path),
        },
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decision-rows", required=True)
    parser.add_argument("--contract-features", required=True)
    parser.add_argument("--symbol-date-metrics", default=None)
    parser.add_argument("--option-behavior-source", default=None)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    summary = audit(
        decision_rows_path=Path(args.decision_rows),
        contract_features_path=Path(args.contract_features),
        symbol_date_metrics_path=Path(args.symbol_date_metrics) if args.symbol_date_metrics else None,
        option_behavior_source_path=Path(args.option_behavior_source) if args.option_behavior_source else None,
        output_dir=Path(args.output_dir),
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
