from __future__ import annotations

import argparse
import csv
import json
from bisect import bisect_right
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from src.signalforge.engines.alignment.regime_asset_options_alignment import (
    _build_alignment_item,
    _matrix_dimension_summary,
    _summary,
)
from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


SCHEMA_VERSION = "signalforge_historical_regime_asset_options_alignment.v2"
DEFAULT_REGIME_DATE_MAP = (
    "artifacts/qc_replay_5y_historical_regime_date_map/"
    "signalforge_historical_regime_date_map.json"
)
DEFAULT_ASSET_BEHAVIOR_ROWS = (
    "artifacts/historical_asset_behavior_from_market_price_history/"
    "signalforge_historical_asset_behavior_rows.jsonl"
)
DEFAULT_OPTION_BEHAVIOR_ROWS = (
    "artifacts/historical_option_behavior/"
    "signalforge_historical_option_behavior_rows.jsonl"
)
DEFAULT_OUTPUT_DIR = "artifacts/historical_regime_asset_options_alignment"
DEFAULT_SYMBOL_POLICY = "artifacts/qc_5y_data_inventory_symbol_policy.json"

CSV_FIELDS = [
    "quote_date",
    "symbol",
    "coverage_status",
    "regime_state",
    "macro_regime",
    "policy_regime_label",
    "weekly_planning_label",
    "weekly_risk_environment",
    "asset_behavior_state",
    "trend_behavior",
    "options_behavior_state",
    "premium_bias",
    "iv_expansion_state",
    "gamma_concentration_state",
    "theta_sensitivity_state",
    "option_liquidity_state",
    "spread_state",
    "regime_options_alignment",
    "asset_options_alignment",
    "strategy_environment_bias",
    "strategy_selection_handoff",
    "matrix_dimension_state",
]

REGIME_ALIASES = {
    "overheating": "late_cycle_overheating",
    "late_cycle": "late_cycle_overheating",
    "mixed": "neutral_mixed",
    "deflationary_slowdown": "disinflationary_slowdown",
    "disinflationary_slowdown_with_rates_review": "disinflationary_slowdown",
}

PREMIUM_BIAS_ALIASES = {
    "premium_buying_bias": "long_premium_bias",
    "premium_selling_bias": "short_premium_bias",
    "neutral_premium_bias": "neutral_premium_bias",
}

OPTIONS_BEHAVIOR_ALIASES = {
    "premium_buying_supported": "long_premium_candidate",
    "premium_selling_supported": "defined_risk_short_premium_candidate",
    "neutral_options_context": "neutral_options_context",
    "needs_review": "options_behavior_needs_review",
}

STRATEGY_FAMILY_BIAS_ALIASES = {
    "credit_defined_risk_or_income_bias": "credit_spread_bias",
    "debit_or_long_convexity_bias": "long_gamma_bias",
    "balanced_defined_risk_bias": "neutral_defined_risk_bias",
    "avoid_or_review_options": "review_required",
}

GAMMA_ALIASES = {
    "concentrated_gamma": "gamma_clustered",
    "distributed_gamma": "distributed_gamma",
    "low_gamma": "low_gamma",
}

IV_EXPANSION_ALIASES = {
    "iv_expansion": "iv_expanding",
    "iv_spike": "iv_spike",
    "iv_contraction": "iv_contraction",
    "iv_stable": "iv_stable",
    "insufficient_prior_iv": "insufficient_prior_iv",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    result = build_historical_regime_asset_options_alignment(
        regime_date_map_path=Path(args.regime_date_map),
        asset_behavior_rows_path=Path(args.asset_behavior_rows),
        option_behavior_rows_path=Path(args.option_behavior_rows),
        output_dir=Path(args.output_dir),
        date_mode=args.date_mode,
        start_date=_parse_date(args.start_date),
        end_date=_parse_date(args.end_date),
        max_dates=args.max_dates,
        symbols=_parse_symbols(args.symbols),
        include_needs_review=args.include_needs_review,
        symbol_policy_path=Path(args.symbol_policy) if args.symbol_policy else None,
        universe_mode=args.universe_mode,
    )

    print(json.dumps(result["summary"], indent=2, sort_keys=True, default=str))
    return 0 if result["summary"].get("status") != "blocked" else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build historical SignalForge regime + asset + options alignment rows. "
            "This performs a point-in-time join and does not route orders, model fills, "
            "or make automatic strategy changes."
        )
    )
    parser.add_argument("--regime-date-map", default=DEFAULT_REGIME_DATE_MAP)
    parser.add_argument("--asset-behavior-rows", default=DEFAULT_ASSET_BEHAVIOR_ROWS)
    parser.add_argument("--option-behavior-rows", default=DEFAULT_OPTION_BEHAVIOR_ROWS)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--date-mode",
        choices=("regime_map_dates", "asset_option_intersection", "option_dates"),
        default="regime_map_dates",
        help=(
            "regime_map_dates aligns only dates present in the regime date map, which is "
            "best for contract-outcome replay. asset_option_intersection builds daily rows "
            "where both asset and option behavior exist. option_dates uses option dates and "
            "requires asset rows for each emitted symbol/date."
        ),
    )
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--max-dates", type=int, default=None)
    parser.add_argument("--symbols", default=None, help="Optional comma-separated symbol list. Overrides --symbol-policy universe selection when provided.")
    parser.add_argument(
        "--symbol-policy",
        default=DEFAULT_SYMBOL_POLICY,
        help=(
            "Optional symbol policy artifact with tradable_option_symbols, context_only_symbols, "
            "and accepted_missing_contract_outcome_symbols. Defaults to the stable QC 5Y policy path."
        ),
    )
    parser.add_argument(
        "--universe-mode",
        choices=("tradable_option_symbols", "option_underlyings", "asset_option_intersection"),
        default="tradable_option_symbols",
        help=(
            "Symbol universe used for emitted alignment rows. tradable_option_symbols uses the "
            "policy's outcome-backed option universe; option_underlyings uses option behavior symbols "
            "minus context-only symbols; asset_option_intersection uses the raw asset/options intersection."
        ),
    )
    parser.add_argument(
        "--include-needs-review",
        action="store_true",
        help="Emit rows even when asset/options/regime context needs review. Default is to emit them too, but keep status fields. This flag is retained for compatibility.",
    )
    return parser


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_historical_regime_asset_options_alignment(
    *,
    regime_date_map_path: Path,
    asset_behavior_rows_path: Path,
    option_behavior_rows_path: Path,
    output_dir: Path,
    date_mode: str = "regime_map_dates",
    start_date: date | None = None,
    end_date: date | None = None,
    max_dates: int | None = None,
    symbols: set[str] | None = None,
    include_needs_review: bool = False,
    symbol_policy_path: Path | None = None,
    universe_mode: str = "tradable_option_symbols",
) -> dict[str, Any]:
    _require_file(regime_date_map_path)
    _require_file(asset_behavior_rows_path)
    _require_file(option_behavior_rows_path)
    symbol_policy = _load_symbol_policy(symbol_policy_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "signalforge_historical_regime_asset_options_alignment.json"
    summary_path = output_dir / "signalforge_historical_regime_asset_options_alignment_summary.json"
    rows_path = output_dir / "signalforge_historical_regime_asset_options_alignment_rows.jsonl"
    csv_path = output_dir / "signalforge_historical_regime_asset_options_alignment_rows.csv"

    regime_map = _read_json(regime_date_map_path)
    regime_exact, regime_asof = _build_regime_indexes(regime_map)
    asset_index, asset_dates, asset_symbols, asset_count = _load_asset_rows(asset_behavior_rows_path, symbols)
    option_index, option_dates, option_symbols, option_count = _load_option_rows(option_behavior_rows_path, symbols)

    target_dates = _target_dates(
        date_mode=date_mode,
        regime_dates=set(regime_exact),
        asset_dates=asset_dates,
        option_dates=option_dates,
        start_date=start_date,
        end_date=end_date,
        max_dates=max_dates,
    )

    row_count = 0
    ready_count = 0
    missing_regime_count = 0
    missing_asset_count = 0
    missing_option_count = 0
    emitted_dates: set[str] = set()
    emitted_symbols: set[str] = set()
    coverage_counts: Counter[str] = Counter()
    date_counts: Counter[str] = Counter()
    allowed_family_counts: Counter[str] = Counter()
    blocked_family_counts: Counter[str] = Counter()
    option_state_counts: Counter[str] = Counter()
    asset_state_counts: Counter[str] = Counter()
    regime_state_counts: Counter[str] = Counter()
    sample_items: list[dict[str, Any]] = []
    all_items_for_summary: list[dict[str, Any]] = []

    universe = _resolve_candidate_symbols(
        explicit_symbols=symbols,
        asset_symbols=asset_symbols,
        option_symbols=option_symbols,
        symbol_policy=symbol_policy,
        universe_mode=universe_mode,
    )
    candidate_symbols = sorted(universe["candidate_symbols"])
    context_only_symbols = set(universe["context_only_symbols"])
    accepted_missing_contract_symbols = set(universe["accepted_missing_contract_outcome_symbols"])
    accepted_missing_option_symbols = set(universe["accepted_missing_option_behavior_symbols"])
    excluded_policy_symbols = set(universe["excluded_policy_symbols"])

    missing_option_examples: list[dict[str, Any]] = []
    missing_option_by_symbol: Counter[str] = Counter()
    missing_option_by_date: Counter[str] = Counter()

    with rows_path.open("w", encoding="utf-8") as jsonl_handle, csv_path.open("w", newline="", encoding="utf-8") as csv_handle:
        writer = csv.DictWriter(csv_handle, fieldnames=CSV_FIELDS)
        writer.writeheader()

        for current_date in target_dates:
            date_text = current_date.isoformat()
            regime_item = regime_exact.get(date_text) or regime_asof(date_text)
            if regime_item is None:
                missing_regime_count += len(candidate_symbols)
                continue
            regime_context = _regime_context_from_map_item(regime_item, date_text)

            for symbol in candidate_symbols:
                asset_item = asset_index.get((symbol, date_text))
                options_item = option_index.get((symbol, date_text))
                if asset_item is None:
                    missing_asset_count += 1
                    continue
                if options_item is None:
                    missing_option_count += 1
                    missing_option_by_symbol[symbol] += 1
                    missing_option_by_date[date_text] += 1
                    if len(missing_option_examples) < 100:
                        missing_option_examples.append(
                            {
                                "quote_date": date_text,
                                "symbol": symbol,
                                "symbol_policy_role": _symbol_policy_role(symbol, symbol_policy),
                                "reason": "missing_option_behavior_for_candidate_symbol_date",
                            }
                        )
                    continue

                normalized_options = _normalize_options_item(options_item)
                alignment = _build_alignment_item(
                    symbol=symbol,
                    regime_context=regime_context,
                    asset_item=asset_item,
                    options_item=normalized_options,
                )
                alignment["artifact_type"] = "historical_regime_asset_options_alignment_item"
                alignment["schema_version"] = "signalforge_historical_regime_asset_options_alignment_item.v1"
                alignment["quote_date"] = date_text
                alignment["as_of_date"] = date_text
                alignment["historical_replay_mode"] = True
                alignment["symbol_policy_role"] = _symbol_policy_role(symbol, symbol_policy)
                alignment["is_tradable_option_symbol"] = symbol in set(universe.get("tradable_option_symbols", []))
                alignment["regime_date"] = regime_item.get("regime_date")
                alignment["regime_match_state"] = regime_item.get("regime_match_state")
                alignment["macro_regime_source_date"] = regime_item.get("macro_regime_source_date") or regime_item.get("regime_date")
                alignment["source_refs"] = {
                    "regime_date_map": str(regime_date_map_path),
                    "asset_behavior_rows": str(asset_behavior_rows_path),
                    "option_behavior_rows": str(option_behavior_rows_path),
                }

                jsonl_handle.write(json.dumps(alignment, sort_keys=True, default=str) + "\n")
                writer.writerow({field: _csv_value(alignment.get(field)) for field in CSV_FIELDS})

                row_count += 1
                emitted_dates.add(date_text)
                emitted_symbols.add(symbol)
                date_counts[date_text] += 1
                coverage = str(alignment.get("coverage_status") or "unknown")
                coverage_counts[coverage] += 1
                ready_count += 1 if coverage == "ready" else 0
                option_state_counts[str(alignment.get("options_behavior_state") or "unknown")] += 1
                asset_state_counts[str(alignment.get("asset_behavior_state") or "unknown")] += 1
                regime_state_counts[str(alignment.get("regime_state") or "unknown")] += 1
                allowed_family_counts.update(alignment.get("allowed_strategy_families") or [])
                blocked_family_counts.update(alignment.get("blocked_strategy_families") or [])
                if len(sample_items) < 25:
                    sample_items.append(alignment)
                if len(all_items_for_summary) < 50000:
                    all_items_for_summary.append(alignment)

    if row_count == 0:
        status = "blocked"
        is_ready = False
        blocked_reasons = ["no historical alignment rows were emitted"]
    else:
        status = "ready"
        is_ready = True
        blocked_reasons = []

    matrix_summary = _matrix_dimension_summary(all_items_for_summary) if all_items_for_summary else {}
    alignment_summary = _summary(all_items_for_summary) if all_items_for_summary else {}
    alignment_summary.update(
        {
            "historical_alignment_row_count": row_count,
            "ready_alignment_row_count": ready_count,
            "needs_review_alignment_row_count": row_count - ready_count,
            "coverage_status_counts": dict(sorted(coverage_counts.items())),
            "asset_behavior_state_counts": dict(sorted(asset_state_counts.items())),
            "options_behavior_state_counts": dict(sorted(option_state_counts.items())),
            "regime_state_counts": dict(sorted(regime_state_counts.items())),
            "allowed_strategy_family_counts": dict(sorted(allowed_family_counts.items())),
            "blocked_strategy_family_counts": dict(sorted(blocked_family_counts.items())),
        }
    )

    result = {
        "artifact_type": "signalforge_historical_regime_asset_options_alignment",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "is_ready": is_ready,
        "requires_manual_approval": True,
        "contract": "historical_regime_asset_options_alignment",
        "adapter_type": "historical_regime_asset_options_alignment_builder",
        "review_scope": "historical_policy_alignment_before_strategy_family_eligibility_not_trade_selection",
        "source_artifacts": {
            "regime_date_map": regime_map.get("artifact_type"),
            "asset_behavior_rows": "signalforge_historical_asset_behavior_rows.jsonl",
            "option_behavior_rows": "signalforge_historical_option_behavior_rows.jsonl",
        },
        "source_paths": {
            "regime_date_map": str(regime_date_map_path),
            "asset_behavior_rows": str(asset_behavior_rows_path),
            "option_behavior_rows": str(option_behavior_rows_path),
            "symbol_policy": str(symbol_policy_path) if symbol_policy_path else None,
        },
        "symbol_policy_artifact_type": symbol_policy.get("artifact_type") if symbol_policy else None,
        "universe_mode": universe_mode,
        "candidate_symbol_count": len(candidate_symbols),
        "tradable_option_symbol_count": len(universe.get("tradable_option_symbols", [])),
        "context_only_symbol_count": len(context_only_symbols),
        "accepted_missing_contract_outcome_symbol_count": len(accepted_missing_contract_symbols),
        "accepted_missing_option_behavior_symbol_count": len(accepted_missing_option_symbols),
        "excluded_policy_symbol_count": len(excluded_policy_symbols),
        "context_only_symbols": sorted(context_only_symbols),
        "accepted_missing_contract_outcome_symbols": sorted(accepted_missing_contract_symbols),
        "accepted_missing_option_behavior_symbols": sorted(accepted_missing_option_symbols),
        "excluded_policy_symbols": sorted(excluded_policy_symbols),
        "missing_option_candidate_examples": missing_option_examples,
        "missing_option_candidate_by_symbol_top": _counter_top(missing_option_by_symbol),
        "missing_option_candidate_by_date_top": _counter_top(missing_option_by_date),
        "date_mode": date_mode,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "target_date_count": len(target_dates),
        "emitted_date_count": len(emitted_dates),
        "emitted_symbol_count": len(emitted_symbols),
        "historical_alignment_row_count": row_count,
        "ready_alignment_row_count": ready_count,
        "needs_review_alignment_row_count": row_count - ready_count,
        "missing_regime_candidate_count": missing_regime_count,
        "missing_asset_candidate_count": missing_asset_count,
        "missing_option_candidate_count": missing_option_count,
        "missing_option_candidate_by_symbol_top": _counter_top(missing_option_by_symbol),
        "missing_option_candidate_by_date_top": _counter_top(missing_option_by_date),
        "input_asset_row_count": asset_count,
        "input_option_row_count": option_count,
        "input_asset_symbol_count": len(asset_symbols),
        "input_option_symbol_count": len(option_symbols),
        "input_asset_date_count": len(asset_dates),
        "input_option_date_count": len(option_dates),
        "regime_date_map_item_count": len(regime_exact),
        "alignment_summary": alignment_summary,
        "matrix_dimension_provider": "historical_regime_asset_options_alignment",
        "matrix_dimension_fields": ["symbol", "regime_state", "asset_behavior_state", "option_behavior_state"],
        "matrix_dimension_summary": matrix_summary,
        "sample_alignment_items": sample_items,
        "paths": {
            "result": str(result_path),
            "summary": str(summary_path),
            "rows_jsonl": str(rows_path),
            "rows_csv": str(csv_path),
        },
        "next_step": "historical_strategy_family_eligibility",
        "blocked_reasons": blocked_reasons,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }

    summary = {
        "schema_version": "signalforge_historical_regime_asset_options_alignment_cli_summary.v1",
        "operation_type": "signalforge_historical_regime_asset_options_alignment_cli",
        "artifact_type": result["artifact_type"],
        "status": status,
        "is_ready": is_ready,
        "date_mode": date_mode,
        "universe_mode": universe_mode,
        "symbol_policy_artifact_type": symbol_policy.get("artifact_type") if symbol_policy else None,
        "candidate_symbol_count": len(candidate_symbols),
        "tradable_option_symbol_count": len(universe.get("tradable_option_symbols", [])),
        "context_only_symbol_count": len(context_only_symbols),
        "accepted_missing_contract_outcome_symbol_count": len(accepted_missing_contract_symbols),
        "accepted_missing_option_behavior_symbol_count": len(accepted_missing_option_symbols),
        "excluded_policy_symbol_count": len(excluded_policy_symbols),
        "target_date_count": len(target_dates),
        "emitted_date_count": len(emitted_dates),
        "emitted_symbol_count": len(emitted_symbols),
        "historical_alignment_row_count": row_count,
        "ready_alignment_row_count": ready_count,
        "needs_review_alignment_row_count": row_count - ready_count,
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "regime_state_counts": dict(sorted(regime_state_counts.items())),
        "asset_behavior_state_counts": dict(sorted(asset_state_counts.items())),
        "options_behavior_state_counts": dict(sorted(option_state_counts.items())),
        "allowed_strategy_family_counts": dict(sorted(allowed_family_counts.items())),
        "blocked_strategy_family_counts": dict(sorted(blocked_family_counts.items())),
        "missing_regime_candidate_count": missing_regime_count,
        "missing_asset_candidate_count": missing_asset_count,
        "missing_option_candidate_count": missing_option_count,
        "missing_option_candidate_by_symbol_top": _counter_top(missing_option_by_symbol),
        "missing_option_candidate_by_date_top": _counter_top(missing_option_by_date),
        "input_asset_row_count": asset_count,
        "input_option_row_count": option_count,
        "input_asset_symbol_count": len(asset_symbols),
        "input_option_symbol_count": len(option_symbols),
        "input_asset_date_count": len(asset_dates),
        "input_option_date_count": len(option_dates),
        "regime_date_map_item_count": len(regime_exact),
        "next_step": result["next_step"],
        "blocked_reasons": blocked_reasons,
        "paths": result["paths"],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }

    result_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

    return {"result": result, "summary": summary}


# ---------------------------------------------------------------------------
# Loading/indexing
# ---------------------------------------------------------------------------


def _load_symbol_policy(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.exists():
        return {
            "artifact_type": "missing_symbol_policy",
            "policy_missing": True,
            "policy_path": str(path),
        }
    value = _read_json(path)
    if not isinstance(value, dict):
        return {}
    return value


def _policy_set(policy: Mapping[str, Any], key: str) -> set[str]:
    values = policy.get(key) or []
    output: set[str] = set()
    if isinstance(values, Sequence) and not isinstance(values, (str, bytes, bytearray)):
        for value in values:
            symbol = _clean_symbol(value)
            if symbol:
                output.add(symbol)
    return output


def _resolve_candidate_symbols(
    *,
    explicit_symbols: set[str] | None,
    asset_symbols: set[str],
    option_symbols: set[str],
    symbol_policy: Mapping[str, Any],
    universe_mode: str,
) -> dict[str, Any]:
    context_only = _policy_set(symbol_policy, "context_only_symbols")
    accepted_missing_contract = _policy_set(symbol_policy, "accepted_missing_contract_outcome_symbols")
    accepted_missing_option = _policy_set(symbol_policy, "accepted_missing_option_behavior_symbols")
    tradable = _policy_set(symbol_policy, "tradable_option_symbols")

    raw_intersection = asset_symbols & option_symbols
    if explicit_symbols is not None:
        candidates = set(explicit_symbols)
    elif universe_mode == "tradable_option_symbols" and tradable:
        candidates = raw_intersection & tradable
    elif universe_mode == "option_underlyings":
        candidates = raw_intersection - context_only - accepted_missing_contract - accepted_missing_option
    else:
        candidates = raw_intersection

    excluded_policy_symbols = ((context_only | accepted_missing_contract | accepted_missing_option) & raw_intersection) - candidates

    return {
        "candidate_symbols": candidates,
        "tradable_option_symbols": tradable,
        "context_only_symbols": context_only,
        "accepted_missing_contract_outcome_symbols": accepted_missing_contract,
        "accepted_missing_option_behavior_symbols": accepted_missing_option,
        "excluded_policy_symbols": excluded_policy_symbols,
    }


def _symbol_policy_role(symbol: str, policy: Mapping[str, Any]) -> str:
    if not policy:
        return "policy_not_provided"
    if symbol in _policy_set(policy, "tradable_option_symbols"):
        return "tradable_option_symbol"
    if symbol in _policy_set(policy, "context_only_symbols"):
        return "context_only_symbol"
    if symbol in _policy_set(policy, "accepted_missing_contract_outcome_symbols"):
        return "accepted_missing_contract_outcome_symbol"
    if symbol in _policy_set(policy, "accepted_missing_option_behavior_symbols"):
        return "accepted_missing_option_behavior_symbol"
    return "unclassified_symbol"


def _counter_top(counter: Counter[str], limit: int = 25) -> list[dict[str, Any]]:
    return [
        {"value": value, "count": count}
        for value, count in counter.most_common(limit)
    ]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise SystemExit(f"input JSON must be an object: {path}")
    return value


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError as error:
                raise SystemExit(f"invalid JSONL at {path}:{line_number}: {error}") from error
            if isinstance(value, dict):
                yield value


def _load_asset_rows(path: Path, symbols: set[str] | None) -> tuple[dict[tuple[str, str], dict[str, Any]], set[str], set[str], int]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    dates: set[str] = set()
    symbol_set: set[str] = set()
    count = 0
    for row in _iter_jsonl(path):
        symbol = _clean_symbol(row.get("symbol"))
        as_of_date = _date_text(row.get("as_of_date") or row.get("quote_date") or row.get("date"))
        if symbol is None or as_of_date is None:
            continue
        if symbols is not None and symbol not in symbols:
            continue
        normalized = dict(row)
        normalized["symbol"] = symbol
        normalized["as_of_date"] = as_of_date
        index[(symbol, as_of_date)] = normalized
        dates.add(as_of_date)
        symbol_set.add(symbol)
        count += 1
    return index, dates, symbol_set, count


def _load_option_rows(path: Path, symbols: set[str] | None) -> tuple[dict[tuple[str, str], dict[str, Any]], set[str], set[str], int]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    dates: set[str] = set()
    symbol_set: set[str] = set()
    count = 0
    for row in _iter_jsonl(path):
        symbol = _clean_symbol(row.get("symbol") or row.get("underlying_symbol"))
        quote_date = _date_text(row.get("quote_date") or row.get("as_of_date") or row.get("date"))
        if symbol is None or quote_date is None:
            continue
        if symbols is not None and symbol not in symbols:
            continue
        normalized = dict(row)
        normalized["symbol"] = symbol
        normalized["quote_date"] = quote_date
        index[(symbol, quote_date)] = normalized
        dates.add(quote_date)
        symbol_set.add(symbol)
        count += 1
    return index, dates, symbol_set, count


def _build_regime_indexes(regime_map: Mapping[str, Any]) -> tuple[dict[str, dict[str, Any]], Any]:
    raw_items = regime_map.get("date_map_items") or regime_map.get("items") or regime_map.get("rows") or []
    exact: dict[str, dict[str, Any]] = {}
    asof_rows: dict[str, dict[str, Any]] = {}

    for raw in raw_items:
        if not isinstance(raw, Mapping):
            continue
        item = dict(raw)
        quote_date = _date_text(item.get("quote_date") or item.get("as_of_date") or item.get("date"))
        regime_date = _date_text(item.get("regime_date") or item.get("macro_regime_source_date"))
        if quote_date is not None:
            exact[quote_date] = item
        if regime_date is not None:
            asof_rows[regime_date] = item

    sorted_regime_dates = sorted(asof_rows)

    def asof_lookup(date_text: str) -> dict[str, Any] | None:
        idx = bisect_right(sorted_regime_dates, date_text) - 1
        if idx < 0:
            return None
        matched = dict(asof_rows[sorted_regime_dates[idx]])
        matched["quote_date"] = date_text
        matched["regime_match_state"] = "prior_date_match" if matched.get("regime_date") != date_text else "exact_date_match"
        return matched

    return exact, asof_lookup


def _target_dates(
    *,
    date_mode: str,
    regime_dates: set[str],
    asset_dates: set[str],
    option_dates: set[str],
    start_date: date | None,
    end_date: date | None,
    max_dates: int | None,
) -> list[date]:
    if date_mode == "regime_map_dates":
        date_texts = regime_dates
    elif date_mode == "asset_option_intersection":
        date_texts = asset_dates & option_dates
    elif date_mode == "option_dates":
        date_texts = option_dates
    else:
        raise ValueError(f"unknown date_mode: {date_mode}")

    dates = [_parse_date(text) for text in date_texts]
    output = sorted(value for value in dates if value is not None)
    if start_date is not None:
        output = [value for value in output if value >= start_date]
    if end_date is not None:
        output = [value for value in output if value <= end_date]
    if max_dates is not None:
        output = output[:max_dates]
    return output


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def _regime_context_from_map_item(item: Mapping[str, Any], quote_date: str) -> dict[str, Any]:
    macro = _first_clean_text(
        item,
        (
            "policy_regime_label",
            "macro_regime_label",
            "macro_regime",
            "regime_state",
            "source_macro_regime_label",
        ),
    )
    macro = _normalize_regime(macro)
    policy = _normalize_regime(_first_clean_text(item, ("policy_regime_label", "macro_regime_label", "regime_state"))) or macro
    weekly_status = _first_clean_text(item, ("weekly_context_status", "status"))
    match_state = _first_clean_text(item, ("regime_match_state",))
    coverage_status = "ready"
    if not macro or macro in {"unknown", "not_provided"}:
        coverage_status = "needs_review"
    if weekly_status in {"blocked", "missing", "needs_review"}:
        coverage_status = "needs_review"
    if match_state in {"missing_prior_regime_row", "missing_date_map"}:
        coverage_status = "needs_review"

    return {
        "coverage_status": coverage_status,
        "artifact_type": item.get("artifact_type") or "historical_regime_date_map_item",
        "macro_regime": macro or "not_provided",
        "policy_regime_label": policy or macro or "not_provided",
        "weekly_planning_label": _first_clean_text(item, ("weekly_planning_label",)),
        "weekly_risk_environment": _first_clean_text(item, ("weekly_risk_environment", "risk_environment")),
        "weekly_volatility_regime": _first_clean_text(item, ("weekly_volatility_regime", "volatility_regime")),
        "weekly_liquidity_regime": _first_clean_text(item, ("weekly_liquidity_regime", "liquidity_regime")),
        "weekly_rates_regime": _first_clean_text(item, ("weekly_rates_regime", "rates_regime")),
        "weekly_event_risk": bool(item.get("weekly_event_risk") or item.get("event_risk") or False),
        "as_of_date": quote_date,
    }


def _normalize_options_item(item: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    premium_bias = _clean_text(normalized.get("premium_bias"))
    if premium_bias in PREMIUM_BIAS_ALIASES:
        normalized["source_premium_bias"] = premium_bias
        normalized["premium_bias"] = PREMIUM_BIAS_ALIASES[premium_bias]

    behavior_state = _clean_text(normalized.get("options_behavior_state"))
    if behavior_state in OPTIONS_BEHAVIOR_ALIASES:
        normalized["source_options_behavior_state"] = behavior_state
        normalized["options_behavior_state"] = OPTIONS_BEHAVIOR_ALIASES[behavior_state]

    strategy_bias = _clean_text(normalized.get("strategy_family_bias"))
    if strategy_bias in STRATEGY_FAMILY_BIAS_ALIASES:
        normalized["source_strategy_family_bias"] = strategy_bias
        normalized["strategy_family_bias"] = STRATEGY_FAMILY_BIAS_ALIASES[strategy_bias]

    gamma_state = _clean_text(normalized.get("gamma_concentration_state"))
    if gamma_state in GAMMA_ALIASES:
        normalized["source_gamma_concentration_state"] = gamma_state
        normalized["gamma_concentration_state"] = GAMMA_ALIASES[gamma_state]

    iv_expansion = _clean_text(normalized.get("iv_expansion_state"))
    if iv_expansion in IV_EXPANSION_ALIASES:
        normalized["source_iv_expansion_state"] = iv_expansion
        normalized["iv_expansion_state"] = IV_EXPANSION_ALIASES[iv_expansion]

    return normalized


def _normalize_regime(value: Any) -> str | None:
    text = _clean_text(value)
    if text is None:
        return None
    return REGIME_ALIASES.get(text, text)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_file(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    if not path.is_file():
        raise SystemExit(f"input path is not a file: {path}")


def _parse_symbols(value: str | None) -> set[str] | None:
    if not value:
        return None
    symbols = {_clean_symbol(part) for part in value.split(",")}
    return {symbol for symbol in symbols if symbol}


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _date_text(value: Any) -> str | None:
    parsed = _parse_date(value)
    return parsed.isoformat() if parsed else None


def _clean_symbol(value: Any) -> str | None:
    text = _clean_text(value)
    return text.upper() if text else None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_clean_text(item: Mapping[str, Any] | None, keys: Sequence[str]) -> str | None:
    if item is None:
        return None
    for key in keys:
        if key in item:
            text = _clean_text(item.get(key))
            if text:
                return text
    return None


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return ";".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, default=str)
    return value


if __name__ == "__main__":
    raise SystemExit(main())
