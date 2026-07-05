from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any


STALE_WARNINGS = {
    "delta_coverage_below_greek_selection_threshold",
    "open_interest_coverage_low",
    "volume_coverage_low",
}


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def key_symbol_date(row: dict[str, Any]) -> tuple[str, str]:
    return (
        str(row.get("underlying_symbol") or row.get("symbol") or "").strip().upper(),
        str(row.get("quote_date") or row.get("asof_quote_date") or "").strip()[:10],
    )


def pct(n: int, d: int) -> float:
    return n / d if d else 0.0


def build_contract_quality_by_symbol_date(contract_features_path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    agg = defaultdict(lambda: {
        "contract_count": 0,
        "quote_complete_count": 0,
        "greeks_complete_count": 0,
        "open_interest_available_count": 0,
        "volume_available_count": 0,
        "tier_counts": Counter(),
        "spread_pcts": [],
    })

    for row in read_jsonl(contract_features_path):
        key = key_symbol_date(row)
        item = agg[key]

        item["contract_count"] += 1

        if row.get("quote_complete"):
            item["quote_complete_count"] += 1

        if row.get("greeks_complete"):
            item["greeks_complete_count"] += 1

        if row.get("open_interest_available"):
            item["open_interest_available_count"] += 1

        if row.get("volume_available"):
            item["volume_available_count"] += 1

        tier = str(row.get("liquidity_tier") or "unknown")
        item["tier_counts"][tier] += 1

        spread_pct = row.get("spread_pct")
        if spread_pct is not None:
            try:
                item["spread_pcts"].append(float(spread_pct))
            except Exception:
                pass

    out = {}

    for key, item in agg.items():
        contract_count = item["contract_count"]
        spread_pcts = item["spread_pcts"]

        out[key] = {
            "v21_contract_count": contract_count,
            "v21_quote_complete_rate": pct(item["quote_complete_count"], contract_count),
            "v21_greeks_complete_rate": pct(item["greeks_complete_count"], contract_count),
            "v21_open_interest_available_rate": pct(item["open_interest_available_count"], contract_count),
            "v21_volume_available_rate": pct(item["volume_available_count"], contract_count),
            "v21_contract_liquidity_tier_counts": dict(sorted(item["tier_counts"].items())),
            "v21_median_contract_spread_pct": median(spread_pcts) if spread_pcts else None,
            "v21_max_contract_spread_pct": max(spread_pcts) if spread_pcts else None,
        }

    return out


def augment_overlay(
    metric_overlay_path: Path,
    contract_features_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    rows_path = output_dir / "signalforge_metric_driven_execution_overlay_v21.jsonl"
    summary_path = output_dir / "signalforge_metric_driven_execution_overlay_v21_summary.json"

    quality_by_key = build_contract_quality_by_symbol_date(contract_features_path)

    input_overlay_row_count = 0
    output_row_count = 0
    missing_contract_quality_count = 0

    stale_warning_removed_counts = Counter()
    warning_counts = Counter()
    state_counts = Counter()
    tier_counts = Counter()

    with rows_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in read_jsonl(metric_overlay_path):
            input_overlay_row_count += 1

            key = key_symbol_date(row)
            quality = quality_by_key.get(key)

            warnings = [
                warning
                for warning in row.get("warnings", [])
                if warning not in STALE_WARNINGS
            ]

            for warning in row.get("warnings", []):
                if warning in STALE_WARNINGS:
                    stale_warning_removed_counts[warning] += 1

            if quality is None:
                missing_contract_quality_count += 1
                warnings.append("missing_v21_contract_quality")
                quality = {
                    "v21_contract_count": 0,
                    "v21_quote_complete_rate": 0.0,
                    "v21_greeks_complete_rate": 0.0,
                    "v21_open_interest_available_rate": 0.0,
                    "v21_volume_available_rate": 0.0,
                    "v21_contract_liquidity_tier_counts": {},
                    "v21_median_contract_spread_pct": None,
                    "v21_max_contract_spread_pct": None,
                }
            else:
                if quality["v21_greeks_complete_rate"] < 0.80:
                    warnings.append("v21_greeks_coverage_below_threshold")
                if quality["v21_open_interest_available_rate"] < 0.50:
                    warnings.append("v21_open_interest_coverage_below_threshold")
                if quality["v21_volume_available_rate"] < 0.25:
                    warnings.append("v21_volume_coverage_below_threshold")

            warnings = sorted(set(warnings))

            row["adapter_type"] = "metric_driven_execution_overlay_v21_augmenter"
            row["artifact_type"] = "signalforge_metric_driven_execution_overlay_v21"
            row["contract"] = "metric_driven_execution_overlay_v21"
            row["v21_contract_quality_source"] = "option_contract_execution_features_v21"
            row.update(quality)
            row["greek_dependent_selection_allowed"] = quality["v21_greeks_complete_rate"] >= 0.80
            row["open_interest_filter_allowed"] = quality["v21_open_interest_available_rate"] >= 0.50
            row["volume_filter_allowed"] = quality["v21_volume_available_rate"] >= 0.25
            row["warning_count"] = len(warnings)
            row["warnings"] = warnings

            handle.write(json.dumps(row, sort_keys=True) + "\n")
            output_row_count += 1

            state_counts[str(row.get("new_entry_state") or "unknown")] += 1
            tier_counts[str(row.get("rolling_liquidity_tier") or "unknown")] += 1

            for warning in warnings:
                warning_counts[warning] += 1

    blockers = []
    if missing_contract_quality_count:
        blockers.append("missing_v21_contract_quality_rows")
    if output_row_count != input_overlay_row_count:
        blockers.append("output_row_count_mismatch")

    summary = {
        "adapter_type": "metric_driven_execution_overlay_v21_augmenter",
        "artifact_type": "signalforge_metric_driven_execution_overlay_v21",
        "contract": "metric_driven_execution_overlay_v21",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "metric_overlay_path": str(metric_overlay_path),
        "contract_features_path": str(contract_features_path),
        "input_overlay_row_count": input_overlay_row_count,
        "output_row_count": output_row_count,
        "contract_quality_key_count": len(quality_by_key),
        "missing_contract_quality_count": missing_contract_quality_count,
        "new_entry_state_counts": dict(sorted(state_counts.items())),
        "rolling_liquidity_tier_counts": dict(sorted(tier_counts.items())),
        "stale_warning_removed_counts": dict(sorted(stale_warning_removed_counts.items())),
        "overlay_warning_counts": dict(sorted(warning_counts.items())),
        "paths": {
            "rows_path": str(rows_path),
            "summary_path": str(summary_path),
        },
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metric-overlay", required=True)
    parser.add_argument("--contract-features", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    summary = augment_overlay(
        metric_overlay_path=Path(args.metric_overlay),
        contract_features_path=Path(args.contract_features),
        output_dir=Path(args.output_dir),
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
