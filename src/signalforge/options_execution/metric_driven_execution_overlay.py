from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_STRATEGIES = [
    "long_call",
    "long_put",
    "bull_call_debit_spread",
    "bear_put_debit_spread",
    "put_credit_spread",
    "call_credit_spread",
    "iron_condor",
    "iron_butterfly",
    "calendar_spread",
    "diagonal_spread",
]

SIMPLE_LONG_PREMIUM = {"long_call", "long_put"}

VERTICAL_SPREADS = {
    "bull_call_debit_spread",
    "bear_put_debit_spread",
    "put_credit_spread",
    "call_credit_spread",
}

COMPLEX_MULTI_LEG = {
    "iron_condor",
    "iron_butterfly",
    "calendar_spread",
    "diagonal_spread",
}


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        value = float(value)
    except Exception:
        return None
    if value != value:
        return None
    return value


def ratio(numerator: Any, denominator: Any) -> float:
    n = to_float(numerator) or 0.0
    d = to_float(denominator) or 0.0
    return n / d if d > 0 else 0.0


def load_strategy_names(path: Path | None) -> list[str]:
    if path is None or not path.exists():
        return list(DEFAULT_STRATEGIES)

    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return list(DEFAULT_STRATEGIES)

    names = set()

    def walk(obj: Any):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in {"strategy_name", "strategy", "name"} and isinstance(value, str):
                    if value in DEFAULT_STRATEGIES:
                        names.add(value)
                walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)

    return sorted(names) if names else list(DEFAULT_STRATEGIES)


def policy_for_row(row: dict[str, Any], strategy_names: list[str]) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "").strip().upper()
    asof_quote_date = str(row.get("asof_quote_date") or "").strip()[:10]
    window_name = str(row.get("window_name") or "").strip()

    tier = str(row.get("rolling_liquidity_tier") or "unknown")
    sample_state = str(row.get("sample_state") or "unknown")

    observation_count = int(row.get("window_observation_count") or 0)
    total_contract_row_count = int(row.get("total_contract_row_count") or 0)

    avg_daily_contract_row_count = to_float(row.get("avg_daily_contract_row_count"))
    median_relative_spread = to_float(row.get("median_daily_median_relative_spread"))
    weighted_relative_spread = to_float(row.get("weighted_avg_relative_spread"))

    quote_coverage_rate = min(
        ratio(row.get("bid_count"), total_contract_row_count),
        ratio(row.get("ask_count"), total_contract_row_count),
        ratio(row.get("mid_count"), total_contract_row_count),
    )

    spread_coverage_rate = ratio(row.get("spread_count"), total_contract_row_count)
    relative_spread_coverage_rate = ratio(row.get("relative_spread_count"), total_contract_row_count)
    delta_coverage_rate = ratio(row.get("delta_count"), total_contract_row_count)
    dte_coverage_rate = ratio(row.get("dte_count"), total_contract_row_count)
    open_interest_coverage_rate = ratio(row.get("open_interest_count"), total_contract_row_count)
    volume_coverage_rate = ratio(row.get("volume_count"), total_contract_row_count)

    blockers = []
    warnings = []

    if sample_state == "sample_limited" or observation_count < 5:
        blockers.append("rolling_sample_limited")

    if quote_coverage_rate < 0.95:
        blockers.append("quote_coverage_below_required_threshold")

    if spread_coverage_rate < 0.95 or relative_spread_coverage_rate < 0.95:
        blockers.append("spread_coverage_below_required_threshold")

    if dte_coverage_rate < 0.95:
        warnings.append("dte_coverage_below_preferred_threshold")

    if delta_coverage_rate < 0.80:
        warnings.append("delta_coverage_below_greek_selection_threshold")

    if open_interest_coverage_rate < 0.50:
        warnings.append("open_interest_coverage_low")

    if volume_coverage_rate < 0.25:
        warnings.append("volume_coverage_low")

    if tier == "A":
        new_entry_state = "allowed"
        fill_price_mode = "mid_limit_with_slippage_guard"
        max_allowed_relative_spread = 0.10
        allowed_strategy_names = list(strategy_names)
    elif tier == "B":
        new_entry_state = "allowed"
        fill_price_mode = "mid_limit_with_conservative_slippage_guard"
        max_allowed_relative_spread = 0.20
        allowed_strategy_names = list(strategy_names)
    elif tier == "C":
        new_entry_state = "conditional"
        fill_price_mode = "conservative_limit_only"
        max_allowed_relative_spread = 0.35
        allowed_strategy_names = [
            s for s in strategy_names
            if s in SIMPLE_LONG_PREMIUM or s in VERTICAL_SPREADS
        ]
        warnings.append("complex_multileg_and_time_spreads_restricted")
    elif tier == "D":
        new_entry_state = "manual_review"
        fill_price_mode = "conservative_bid_ask_or_skip"
        max_allowed_relative_spread = 0.50
        allowed_strategy_names = [
            s for s in strategy_names
            if s in SIMPLE_LONG_PREMIUM
        ]
        warnings.append("low_liquidity_manual_review")
    else:
        new_entry_state = "manual_review"
        fill_price_mode = "conservative_bid_ask_or_skip"
        max_allowed_relative_spread = 0.35
        allowed_strategy_names = [
            s for s in strategy_names
            if s in SIMPLE_LONG_PREMIUM
        ]
        warnings.append("unknown_liquidity_tier")

    if median_relative_spread is not None and median_relative_spread > max_allowed_relative_spread:
        blockers.append("median_relative_spread_above_overlay_limit")

    if blockers:
        if "rolling_sample_limited" in blockers:
            new_entry_state = "block"
            allowed_strategy_names = []
        elif new_entry_state == "allowed":
            new_entry_state = "conditional"

    blocked_strategy_names = sorted(set(strategy_names) - set(allowed_strategy_names))

    return {
        "adapter_type": "metric_driven_execution_overlay_builder",
        "artifact_type": "signalforge_metric_driven_execution_overlay",
        "contract": "metric_driven_execution_overlay",
        "asof_rule": "derived_only_from_rolling_symbol_execution_metrics_asof_quote_date",
        "symbol": symbol,
        "asof_quote_date": asof_quote_date,
        "window_name": window_name,
        "rolling_liquidity_tier": tier,
        "sample_state": sample_state,
        "window_observation_count": observation_count,
        "total_contract_row_count": total_contract_row_count,
        "avg_daily_contract_row_count": avg_daily_contract_row_count,
        "median_daily_median_relative_spread": median_relative_spread,
        "weighted_avg_relative_spread": weighted_relative_spread,
        "quote_coverage_rate": quote_coverage_rate,
        "spread_coverage_rate": spread_coverage_rate,
        "relative_spread_coverage_rate": relative_spread_coverage_rate,
        "delta_coverage_rate": delta_coverage_rate,
        "dte_coverage_rate": dte_coverage_rate,
        "open_interest_coverage_rate": open_interest_coverage_rate,
        "volume_coverage_rate": volume_coverage_rate,
        "new_entry_state": new_entry_state,
        "fill_price_mode": fill_price_mode,
        "max_allowed_relative_spread": max_allowed_relative_spread,
        "allowed_strategy_count": len(allowed_strategy_names),
        "allowed_strategy_names": allowed_strategy_names,
        "blocked_strategy_count": len(blocked_strategy_names),
        "blocked_strategy_names": blocked_strategy_names,
        "greek_dependent_selection_allowed": delta_coverage_rate >= 0.80,
        "open_interest_filter_allowed": open_interest_coverage_rate >= 0.50,
        "volume_filter_allowed": volume_coverage_rate >= 0.25,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
    }


def build_metric_driven_execution_overlay(
    rolling_metrics_path: Path,
    output_dir: Path,
    base_strategy_map_path: Path | None,
    selected_window: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    rows_path = output_dir / "signalforge_metric_driven_execution_overlay.jsonl"
    summary_path = output_dir / "signalforge_metric_driven_execution_overlay_summary.json"

    strategy_names = load_strategy_names(base_strategy_map_path)

    input_row_count = 0
    selected_input_row_count = 0
    bad_row_count = 0
    output_rows = []

    state_counts = Counter()
    tier_counts = Counter()
    blocker_counts = Counter()
    warning_counts = Counter()
    allowed_strategy_counter = Counter()

    duplicate_keys = []
    seen_keys = set()

    for row in read_jsonl(rolling_metrics_path):
        input_row_count += 1

        if str(row.get("window_name") or "") != selected_window:
            continue

        selected_input_row_count += 1

        symbol = str(row.get("symbol") or "").strip().upper()
        asof_quote_date = str(row.get("asof_quote_date") or "").strip()[:10]

        if not symbol or not asof_quote_date:
            bad_row_count += 1
            continue

        key = (symbol, asof_quote_date, selected_window)
        if key in seen_keys:
            duplicate_keys.append(key)
        seen_keys.add(key)

        overlay = policy_for_row(row, strategy_names)
        output_rows.append(overlay)

        state_counts[overlay["new_entry_state"]] += 1
        tier_counts[overlay["rolling_liquidity_tier"]] += 1

        for blocker in overlay["blockers"]:
            blocker_counts[blocker] += 1

        for warning in overlay["warnings"]:
            warning_counts[warning] += 1

        for strategy_name in overlay["allowed_strategy_names"]:
            allowed_strategy_counter[strategy_name] += 1

    with rows_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in output_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    blockers = []
    if bad_row_count:
        blockers.append("bad_selected_rolling_metric_rows")
    if duplicate_keys:
        blockers.append("duplicate_symbol_date_window_overlay_keys")
    if not output_rows:
        blockers.append("no_overlay_rows")

    summary = {
        "adapter_type": "metric_driven_execution_overlay_builder",
        "artifact_type": "signalforge_metric_driven_execution_overlay",
        "contract": "metric_driven_execution_overlay",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "rolling_metrics_path": str(rolling_metrics_path),
        "base_strategy_map_path": str(base_strategy_map_path) if base_strategy_map_path else None,
        "selected_window": selected_window,
        "strategy_names": strategy_names,
        "strategy_count": len(strategy_names),
        "input_row_count": input_row_count,
        "selected_input_row_count": selected_input_row_count,
        "bad_row_count": bad_row_count,
        "duplicate_key_count": len(duplicate_keys),
        "duplicate_keys_sample": [
            {"symbol": k[0], "asof_quote_date": k[1], "window_name": k[2]}
            for k in duplicate_keys[:50]
        ],
        "output_row_count": len(output_rows),
        "symbol_count": len(set(r["symbol"] for r in output_rows)),
        "new_entry_state_counts": dict(sorted(state_counts.items())),
        "rolling_liquidity_tier_counts": dict(sorted(tier_counts.items())),
        "overlay_blocker_counts": dict(sorted(blocker_counts.items())),
        "overlay_warning_counts": dict(sorted(warning_counts.items())),
        "allowed_strategy_observation_counts": dict(sorted(allowed_strategy_counter.items())),
        "paths": {
            "rows_path": str(rows_path),
            "summary_path": str(summary_path),
        },
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rolling-metrics", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--base-strategy-map", default=None)
    parser.add_argument("--window", default="rolling_60d")

    args = parser.parse_args()

    summary = build_metric_driven_execution_overlay(
        rolling_metrics_path=Path(args.rolling_metrics),
        output_dir=Path(args.output_dir),
        base_strategy_map_path=Path(args.base_strategy_map) if args.base_strategy_map else None,
        selected_window=args.window,
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
