from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def key_overlay(row: dict[str, Any]) -> tuple[str, str]:
    return (
        str(row.get("symbol") or row.get("underlying_symbol") or "").strip().upper(),
        str(row.get("asof_quote_date") or row.get("quote_date") or "").strip()[:10],
    )


def key_availability(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("underlying_symbol") or row.get("symbol") or "").strip().upper(),
        str(row.get("quote_date") or row.get("asof_quote_date") or "").strip()[:10],
        str(row.get("strategy_name") or "").strip(),
    )


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def resolve_row(
    availability: dict[str, Any],
    overlay: dict[str, Any] | None,
) -> dict[str, Any]:
    symbol, quote_date, strategy_name = key_availability(availability)

    blockers = []
    warnings = []

    structure_available = bool(availability.get("is_available"))
    candidate_structure_count = int(availability.get("candidate_structure_count") or 0)

    if overlay is None:
        overlay_state = "missing"
        rolling_liquidity_tier = None
        fill_price_mode = None
        max_allowed_relative_spread = None
        allowed_strategy_names = []
        blocked_strategy_names = []
        blockers.append("missing_metric_driven_overlay")
    else:
        overlay_state = str(overlay.get("new_entry_state") or "unknown")
        rolling_liquidity_tier = overlay.get("rolling_liquidity_tier")
        fill_price_mode = overlay.get("fill_price_mode")
        max_allowed_relative_spread = overlay.get("max_allowed_relative_spread")
        allowed_strategy_names = as_list(overlay.get("allowed_strategy_names"))
        blocked_strategy_names = as_list(overlay.get("blocked_strategy_names"))

        blockers.extend(as_list(overlay.get("blockers")))
        warnings.extend(as_list(overlay.get("warnings")))

    if not structure_available:
        blockers.append("strategy_structure_unavailable")

    if overlay_state == "block":
        blockers.append("metric_overlay_blocked")

    if overlay is not None:
        if strategy_name in blocked_strategy_names:
            blockers.append("strategy_blocked_by_metric_overlay")

        if allowed_strategy_names and strategy_name not in allowed_strategy_names:
            blockers.append("strategy_not_in_metric_overlay_allowed_set")

    blockers = sorted(set(str(x) for x in blockers if x))
    warnings = sorted(set(str(x) for x in warnings if x))

    if blockers:
        final_execution_state = "block"
    elif overlay_state == "manual_review":
        final_execution_state = "manual_review"
    elif overlay_state == "conditional":
        final_execution_state = "conditional"
    elif overlay_state == "allowed":
        final_execution_state = "allowed"
    else:
        final_execution_state = "manual_review"
        warnings.append("unknown_overlay_state_manual_review")

    can_backtest_new_entry = final_execution_state in {"allowed", "conditional"}
    requires_manual_review = final_execution_state == "manual_review"

    return {
        "adapter_type": "resolved_strategy_execution_rules_v21_builder",
        "artifact_type": "signalforge_resolved_strategy_execution_rules_v21",
        "contract": "resolved_strategy_execution_rules_v21",
        "asof_rule": "metric_overlay_and_strategy_structure_availability_are_asof_quote_date",
        "underlying_symbol": symbol,
        "quote_date": quote_date,
        "strategy_name": strategy_name,
        "final_execution_state": final_execution_state,
        "can_backtest_new_entry": can_backtest_new_entry,
        "requires_manual_review": requires_manual_review,
        "structure_available": structure_available,
        "candidate_contract_count": availability.get("candidate_contract_count"),
        "candidate_pair_count": availability.get("candidate_pair_count"),
        "candidate_structure_count": candidate_structure_count,
        "expiration_count_with_structures": availability.get("expiration_count_with_structures"),
        "overlay_state": overlay_state,
        "rolling_liquidity_tier": rolling_liquidity_tier,
        "fill_price_mode": fill_price_mode,
        "max_allowed_relative_spread": max_allowed_relative_spread,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
    }


def build_resolved_rules(
    metric_overlay_path: Path,
    strategy_structure_availability_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    rows_path = output_dir / "signalforge_resolved_strategy_execution_rules_v21.jsonl"
    summary_path = output_dir / "signalforge_resolved_strategy_execution_rules_v21_summary.json"

    overlay_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    duplicate_overlay_keys = []

    for row in read_jsonl(metric_overlay_path):
        key = key_overlay(row)

        if key in overlay_by_key:
            duplicate_overlay_keys.append(key)

        overlay_by_key[key] = row

    availability_input_row_count = 0
    output_row_count = 0

    seen_resolved_keys = set()
    duplicate_resolved_keys = []

    symbols = set()
    symbol_dates = set()
    strategies = set()

    final_state_counts = Counter()
    overlay_state_counts = Counter()
    blocker_counts = Counter()
    warning_counts = Counter()

    strategy_final_state_counts: dict[str, Counter] = defaultdict(Counter)
    strategy_available_counts = Counter()
    strategy_backtest_allowed_counts = Counter()

    missing_overlay_count = 0

    with rows_path.open("w", encoding="utf-8", newline="\n") as handle:
        for availability in read_jsonl(strategy_structure_availability_path):
            availability_input_row_count += 1

            symbol, quote_date, strategy_name = key_availability(availability)
            overlay = overlay_by_key.get((symbol, quote_date))

            if overlay is None:
                missing_overlay_count += 1

            out = resolve_row(availability, overlay)

            resolved_key = (symbol, quote_date, strategy_name)
            if resolved_key in seen_resolved_keys:
                duplicate_resolved_keys.append(resolved_key)
            seen_resolved_keys.add(resolved_key)

            handle.write(json.dumps(out, sort_keys=True) + "\n")
            output_row_count += 1

            symbols.add(symbol)
            symbol_dates.add((symbol, quote_date))
            strategies.add(strategy_name)

            final_state_counts[out["final_execution_state"]] += 1
            overlay_state_counts[out["overlay_state"]] += 1
            strategy_final_state_counts[strategy_name][out["final_execution_state"]] += 1

            if out["structure_available"]:
                strategy_available_counts[strategy_name] += 1

            if out["can_backtest_new_entry"]:
                strategy_backtest_allowed_counts[strategy_name] += 1

            for blocker in out["blockers"]:
                blocker_counts[blocker] += 1

            for warning in out["warnings"]:
                warning_counts[warning] += 1

    expected_output_row_count = len(symbol_dates) * len(strategies)

    blockers = []

    if duplicate_overlay_keys:
        blockers.append("duplicate_metric_overlay_keys")

    if duplicate_resolved_keys:
        blockers.append("duplicate_resolved_strategy_execution_keys")

    if missing_overlay_count:
        blockers.append("missing_metric_overlay_rows")

    if output_row_count != expected_output_row_count:
        blockers.append("output_row_count_mismatch")

    summary = {
        "adapter_type": "resolved_strategy_execution_rules_v21_builder",
        "artifact_type": "signalforge_resolved_strategy_execution_rules_v21",
        "contract": "resolved_strategy_execution_rules_v21",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "metric_overlay_path": str(metric_overlay_path),
        "strategy_structure_availability_path": str(strategy_structure_availability_path),
        "metric_overlay_row_count": len(overlay_by_key),
        "availability_input_row_count": availability_input_row_count,
        "output_row_count": output_row_count,
        "expected_output_row_count": expected_output_row_count,
        "symbol_count": len(symbols),
        "symbol_date_count": len(symbol_dates),
        "strategy_count": len(strategies),
        "missing_overlay_count": missing_overlay_count,
        "duplicate_overlay_key_count": len(duplicate_overlay_keys),
        "duplicate_resolved_key_count": len(duplicate_resolved_keys),
        "final_execution_state_counts": dict(sorted(final_state_counts.items())),
        "overlay_state_counts": dict(sorted(overlay_state_counts.items())),
        "resolved_blocker_counts": dict(sorted(blocker_counts.items())),
        "resolved_warning_counts": dict(sorted(warning_counts.items())),
        "strategy_available_counts": dict(sorted(strategy_available_counts.items())),
        "strategy_backtest_allowed_counts": dict(sorted(strategy_backtest_allowed_counts.items())),
        "strategy_final_state_counts": {
            strategy_name: dict(sorted(counter.items()))
            for strategy_name, counter in sorted(strategy_final_state_counts.items())
        },
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
    parser.add_argument("--strategy-structure-availability", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    summary = build_resolved_rules(
        metric_overlay_path=Path(args.metric_overlay),
        strategy_structure_availability_path=Path(args.strategy_structure_availability),
        output_dir=Path(args.output_dir),
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
