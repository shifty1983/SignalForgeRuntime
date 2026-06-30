from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from signalforge.data.seed_bundle import resolve_seed_bundle_root


POSITION_SIZING_SOURCE_RELATIVE_PATH = (
    "artifacts/strategy_eligibility_native_family_gate_position_sizing_replay_v1_20210601_20260531/"
    "signalforge_portfolio_position_sizing_replay_strategy_gate_v1.jsonl"
)

POSITION_SIZING_COMPATIBLE_SUMMARY_RELATIVE_PATH = (
    "artifacts/strategy_eligibility_native_family_gate_position_sizing_replay_v1_20210601_20260531/"
    "signalforge_portfolio_position_sizing_replay_strategy_gate_v1_compatible_summary.json"
)

LAYER_ENRICHED_SOURCE_RELATIVE_PATH = (
    "artifacts/layer_field_carry_forward_enrichment_v2_20210601_20260531/"
    "signalforge_layer_enriched_position_sizing_rows_v2.jsonl"
)

LAYER_ENRICHED_SUMMARY_RELATIVE_PATH = (
    "artifacts/layer_field_carry_forward_enrichment_v2_20210601_20260531/"
    "layer_field_carry_forward_enrichment_v2_summary.json"
)

ALLOCATOR_SUMMARY_RELATIVE_PATH = (
    "artifacts/portfolio_value_ranked_allocator_v2_20210601_20260531/"
    "portfolio_value_ranked_allocator_v2_summary.json"
)

ALLOCATOR_AGGREGATE_ROWS_RELATIVE_PATH = (
    "artifacts/portfolio_value_ranked_allocator_v2_20210601_20260531/"
    "portfolio_value_ranked_allocator_v2_aggregate_rows.jsonl"
)

DEFAULT_OUTPUT = "data/runtime/portfolio_construction/portfolio_construction_latest_snapshot.json"


@dataclass(frozen=True)
class PortfolioConstructionBootstrapSummary:
    seed_bundle_root: str | None
    output_path: str
    is_ready: bool
    position_sizing_source_row_count: int
    enriched_sized_row_count: int
    allocator_aggregate_row_count: int
    latest_decision_date: str | None
    latest_symbol_count: int
    sized_trade_count: int
    skipped_sequence_row_count: int
    selected_strategy_count: int
    allocator_summary_is_ready: bool | None
    layer_summary_is_ready: bool | None
    position_sizing_summary_is_ready: bool | None
    recommended_profile: str | None
    recommended_rank_method: str | None
    recommended_heat_cap: float | None
    blocker_count: int
    blockers: tuple[str, ...]


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()

            if not line:
                continue

            value = json.loads(line)

            if isinstance(value, dict):
                yield value


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))

    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")

    return value


def _counter(items: Iterable[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(item.get(key)) for item in items if item.get(key) is not None).items()))


def _latest_rows_by_symbol(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}

    for row in rows:
        symbol = row.get("symbol")
        decision_date = row.get("decision_date")

        if not symbol or not decision_date:
            continue

        current = latest.get(str(symbol))

        if current is None or str(decision_date) > str(current.get("decision_date") or ""):
            latest[str(symbol)] = row

    return sorted(latest.values(), key=lambda row: str(row.get("symbol") or ""))


def _normalize_enriched_row(row: dict[str, Any]) -> dict[str, Any]:
    allocator_payload = row.get("portfolio_value_ranked_allocator_v2")
    gate_payload = row.get("strategy_eligibility_gate_v1")

    return {
        "sequence_id": row.get("sequence_id"),
        "sequence_index": row.get("sequence_index"),
        "trade_key": row.get("trade_key"),
        "decision_date": row.get("decision_date"),
        "portfolio_realization_date": row.get("portfolio_realization_date"),
        "symbol": row.get("symbol"),
        "selected_strategy": row.get("selected_strategy"),
        "selection_state": row.get("selection_state"),
        "sizing_state": row.get("sizing_state"),
        "contract_quantity": row.get("contract_quantity"),
        "contract_count": row.get("contract_count"),
        "position_risk_dollars": row.get("position_risk_dollars"),
        "risk_budget_dollars": row.get("risk_budget_dollars"),
        "risk_per_trade_pct": row.get("risk_per_trade_pct"),
        "max_trade_risk_dollars": row.get("max_trade_risk_dollars"),
        "equity_before_trade": row.get("equity_before_trade"),
        "equity_after_trade": row.get("equity_after_trade"),
        "selected_expectancy_score": row.get("selected_expectancy_score"),
        "selected_expectancy_sample_count": row.get("selected_expectancy_sample_count"),
        "selected_expectancy_state": row.get("selected_expectancy_state"),
        "selected_outcome_state": row.get("selected_outcome_state"),
        "regime_state": row.get("regime_state"),
        "regime_source_date": row.get("regime_source_date"),
        "asset_behavior_state": row.get("asset_behavior_state"),
        "asset_behavior_source_date": row.get("asset_behavior_source_date"),
        "option_behavior_state": row.get("option_behavior_state"),
        "option_behavior_source_date": row.get("option_behavior_source_date"),
        "option_iv_level": row.get("option_iv_level"),
        "option_liquidity_state": row.get("option_liquidity_state"),
        "entry_mid": row.get("entry_mid"),
        "entry_spread_pct": row.get("entry_spread_pct"),
        "spread_pct": row.get("spread_pct"),
        "bid_price": row.get("bid_price"),
        "ask_price": row.get("ask_price"),
        "open_interest": row.get("open_interest"),
        "volume": row.get("volume"),
        "selected_construction_quality": row.get("selected_construction_quality"),
        "selected_construction_quality_reason": row.get("selected_construction_quality_reason"),
        "selected_entry_legs": row.get("selected_entry_legs") or [],
        "selected_exit_legs": row.get("selected_exit_legs") or [],
        "allocator_payload": allocator_payload if isinstance(allocator_payload, dict) else {},
        "strategy_eligibility_gate_v1": gate_payload if isinstance(gate_payload, dict) else {},
        "source_row": row,
    }


def _count_jsonl_rows(path: Path) -> int:
    with path.open("rb") as handle:
        return sum(1 for _ in handle)


def _choose_recommended_candidate(allocator_summary: dict[str, Any]) -> dict[str, Any] | None:
    candidates = allocator_summary.get("top_heavy_candidates_top50") or []

    if not isinstance(candidates, list) or not candidates:
        return None

    preferred = [
        candidate
        for candidate in candidates
        if isinstance(candidate, dict)
        and candidate.get("allocation_profile") == "top_heavy_42100"
        and candidate.get("rank_method") == "strategy_prior_profit_factor"
        and float(candidate.get("portfolio_heat_cap") or 0.0) == 0.5
    ]

    if preferred:
        return preferred[0]

    first = candidates[0]
    return first if isinstance(first, dict) else None


def build_portfolio_construction_bootstrap(
    *,
    seed_bundle: str | Path | None = None,
    output_path: str | Path = DEFAULT_OUTPUT,
) -> PortfolioConstructionBootstrapSummary:
    seed_root = resolve_seed_bundle_root(seed_bundle)
    output = Path(output_path)

    if seed_root is None:
        return PortfolioConstructionBootstrapSummary(
            seed_bundle_root=None,
            output_path=str(output),
            is_ready=False,
            position_sizing_source_row_count=0,
            enriched_sized_row_count=0,
            allocator_aggregate_row_count=0,
            latest_decision_date=None,
            latest_symbol_count=0,
            sized_trade_count=0,
            skipped_sequence_row_count=0,
            selected_strategy_count=0,
            allocator_summary_is_ready=None,
            layer_summary_is_ready=None,
            position_sizing_summary_is_ready=None,
            recommended_profile=None,
            recommended_rank_method=None,
            recommended_heat_cap=None,
            blocker_count=1,
            blockers=("seed_bundle_missing",),
        )

    paths = {
        "position_sizing_source": seed_root / POSITION_SIZING_SOURCE_RELATIVE_PATH,
        "position_sizing_compatible_summary": seed_root / POSITION_SIZING_COMPATIBLE_SUMMARY_RELATIVE_PATH,
        "layer_enriched_source": seed_root / LAYER_ENRICHED_SOURCE_RELATIVE_PATH,
        "layer_enriched_summary": seed_root / LAYER_ENRICHED_SUMMARY_RELATIVE_PATH,
        "allocator_summary": seed_root / ALLOCATOR_SUMMARY_RELATIVE_PATH,
        "allocator_aggregate_rows": seed_root / ALLOCATOR_AGGREGATE_ROWS_RELATIVE_PATH,
    }

    blockers: list[str] = []

    for name, path in paths.items():
        if not path.is_file():
            blockers.append(f"{name}_missing")

    if blockers:
        return PortfolioConstructionBootstrapSummary(
            seed_bundle_root=str(seed_root),
            output_path=str(output),
            is_ready=False,
            position_sizing_source_row_count=0,
            enriched_sized_row_count=0,
            allocator_aggregate_row_count=0,
            latest_decision_date=None,
            latest_symbol_count=0,
            sized_trade_count=0,
            skipped_sequence_row_count=0,
            selected_strategy_count=0,
            allocator_summary_is_ready=None,
            layer_summary_is_ready=None,
            position_sizing_summary_is_ready=None,
            recommended_profile=None,
            recommended_rank_method=None,
            recommended_heat_cap=None,
            blocker_count=len(blockers),
            blockers=tuple(blockers),
        )

    position_summary = _load_json(paths["position_sizing_compatible_summary"])
    layer_summary = _load_json(paths["layer_enriched_summary"])
    allocator_summary = _load_json(paths["allocator_summary"])

    if not position_summary.get("is_ready"):
        blockers.append("position_sizing_summary_not_ready")

    if not layer_summary.get("is_ready"):
        blockers.append("layer_enriched_summary_not_ready")

    if not allocator_summary.get("is_ready"):
        blockers.append("allocator_summary_not_ready")

    position_sizing_source_row_count = _count_jsonl_rows(paths["position_sizing_source"])

    enriched_rows = [_normalize_enriched_row(row) for row in _read_jsonl(paths["layer_enriched_source"])]
    allocator_aggregate_rows = list(_read_jsonl(paths["allocator_aggregate_rows"]))

    if not enriched_rows:
        blockers.append("no_enriched_sized_rows")

    if not allocator_aggregate_rows:
        blockers.append("no_allocator_aggregate_rows")

    latest_rows = _latest_rows_by_symbol(enriched_rows)
    latest_decision_date = max((str(row.get("decision_date")) for row in latest_rows if row.get("decision_date")), default=None)

    recommended_candidate = _choose_recommended_candidate(allocator_summary)

    sized_trade_count = int(position_summary.get("sized_trade_count") or len(enriched_rows))
    skipped_sequence_row_count = int(position_summary.get("skipped_sequence_row_count") or 0)

    snapshot = {
        "contract": "portfolio_construction_latest_snapshot",
        "position_sizing_source": POSITION_SIZING_SOURCE_RELATIVE_PATH,
        "position_sizing_compatible_summary_source": POSITION_SIZING_COMPATIBLE_SUMMARY_RELATIVE_PATH,
        "layer_enriched_source": LAYER_ENRICHED_SOURCE_RELATIVE_PATH,
        "layer_enriched_summary_source": LAYER_ENRICHED_SUMMARY_RELATIVE_PATH,
        "allocator_summary_source": ALLOCATOR_SUMMARY_RELATIVE_PATH,
        "allocator_aggregate_rows_source": ALLOCATOR_AGGREGATE_ROWS_RELATIVE_PATH,
        "position_sizing_summary_is_ready": position_summary.get("is_ready"),
        "layer_summary_is_ready": layer_summary.get("is_ready"),
        "allocator_summary_is_ready": allocator_summary.get("is_ready"),
        "position_sizing_source_row_count": position_sizing_source_row_count,
        "enriched_sized_row_count": len(enriched_rows),
        "allocator_aggregate_row_count": len(allocator_aggregate_rows),
        "sized_trade_count": sized_trade_count,
        "skipped_sequence_row_count": skipped_sequence_row_count,
        "latest_decision_date": latest_decision_date,
        "latest_symbol_count": len(latest_rows),
        "selected_strategy_count": len({str(row.get("selected_strategy")) for row in enriched_rows if row.get("selected_strategy")}),
        "selected_strategy_counts": _counter(enriched_rows, "selected_strategy"),
        "sizing_state_counts": _counter(enriched_rows, "sizing_state"),
        "regime_state_counts": _counter(enriched_rows, "regime_state"),
        "asset_behavior_state_counts": _counter(enriched_rows, "asset_behavior_state"),
        "option_behavior_state_counts": _counter(enriched_rows, "option_behavior_state"),
        "allocator_policy": allocator_summary.get("policy") or {},
        "allocator_recommended_by_capital": allocator_summary.get("recommended_by_capital") or {},
        "allocator_recommended_candidate": recommended_candidate or {},
        "allocator_top_heavy_candidates_top50": allocator_summary.get("top_heavy_candidates_top50") or [],
        "allocator_aggregate_rows": allocator_aggregate_rows,
        "latest_rows": latest_rows,
        "latest_rows_by_symbol": {
            str(row["symbol"]): row
            for row in latest_rows
            if row.get("symbol")
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")

    return PortfolioConstructionBootstrapSummary(
        seed_bundle_root=str(seed_root),
        output_path=str(output),
        is_ready=not blockers,
        position_sizing_source_row_count=position_sizing_source_row_count,
        enriched_sized_row_count=len(enriched_rows),
        allocator_aggregate_row_count=len(allocator_aggregate_rows),
        latest_decision_date=latest_decision_date,
        latest_symbol_count=len(latest_rows),
        sized_trade_count=sized_trade_count,
        skipped_sequence_row_count=skipped_sequence_row_count,
        selected_strategy_count=snapshot["selected_strategy_count"],
        allocator_summary_is_ready=bool(allocator_summary.get("is_ready")),
        layer_summary_is_ready=bool(layer_summary.get("is_ready")),
        position_sizing_summary_is_ready=bool(position_summary.get("is_ready")),
        recommended_profile=(recommended_candidate or {}).get("allocation_profile"),
        recommended_rank_method=(recommended_candidate or {}).get("rank_method"),
        recommended_heat_cap=(recommended_candidate or {}).get("portfolio_heat_cap"),
        blocker_count=len(blockers),
        blockers=tuple(blockers),
    )


def summary_to_dict(summary: PortfolioConstructionBootstrapSummary) -> dict[str, Any]:
    return asdict(summary)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap runtime portfolio construction snapshot.")
    parser.add_argument("--seed-bundle", default=None)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-output", default="artifacts/portfolio_construction_bootstrap_summary.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = build_portfolio_construction_bootstrap(seed_bundle=args.seed_bundle, output_path=args.output)

    summary_path = Path(args.summary_output)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True), encoding="utf-8")

    if args.json:
        print(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True))
    else:
        print(f"is_ready: {summary.is_ready}")
        print(f"position_sizing_source_row_count: {summary.position_sizing_source_row_count}")
        print(f"enriched_sized_row_count: {summary.enriched_sized_row_count}")
        print(f"allocator_aggregate_row_count: {summary.allocator_aggregate_row_count}")
        print(f"latest_decision_date: {summary.latest_decision_date}")
        print(f"latest_symbol_count: {summary.latest_symbol_count}")
        print(f"sized_trade_count: {summary.sized_trade_count}")
        print(f"skipped_sequence_row_count: {summary.skipped_sequence_row_count}")
        print(f"recommended_profile: {summary.recommended_profile}")
        print(f"recommended_rank_method: {summary.recommended_rank_method}")
        print(f"recommended_heat_cap: {summary.recommended_heat_cap}")
        print(f"blocker_count: {summary.blocker_count}")

    return 0 if summary.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())

