from __future__ import annotations

import json
import shutil
from pathlib import Path

from signalforge.bootstrap.portfolio_construction_bootstrap import (
    ALLOCATOR_AGGREGATE_ROWS_RELATIVE_PATH,
    ALLOCATOR_SUMMARY_RELATIVE_PATH,
    LAYER_ENRICHED_SOURCE_RELATIVE_PATH,
    LAYER_ENRICHED_SUMMARY_RELATIVE_PATH,
    POSITION_SIZING_COMPATIBLE_SUMMARY_RELATIVE_PATH,
    POSITION_SIZING_SOURCE_RELATIVE_PATH,
    build_portfolio_construction_bootstrap,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")



def short_seed(tmp_path: Path) -> Path:
    short_name = "s" + str(abs(hash(str(tmp_path))) % 100000)
    root = Path.cwd() / ".t" / short_name

    if root.exists():
        shutil.rmtree(root)

    return root / "s"

def test_portfolio_construction_bootstrap_blocks_when_seed_missing(tmp_path: Path):
    summary = build_portfolio_construction_bootstrap(
        seed_bundle=tmp_path / "missing",
        output_path=tmp_path / "portfolio_construction_latest_snapshot.json",
    )

    assert not summary.is_ready
    assert "seed_bundle_missing" in summary.blockers


def test_portfolio_construction_bootstrap_writes_snapshot(tmp_path: Path):
    seed = short_seed(tmp_path)

    write_jsonl(
        seed / POSITION_SIZING_SOURCE_RELATIVE_PATH,
        [
            {
                "sequence_id": "portfolio_selected_trade_000001",
                "decision_date": "2026-01-01",
                "symbol": "SPY",
                "sizing_state": "sized",
            },
            {
                "sequence_id": "portfolio_selected_trade_000002",
                "decision_date": "2026-01-01",
                "symbol": "TLT",
                "sizing_state": "skipped",
            },
        ],
    )

    write_json(
        seed / POSITION_SIZING_COMPATIBLE_SUMMARY_RELATIVE_PATH,
        {
            "is_ready": True,
            "sized_trade_count": 1,
            "skipped_sequence_row_count": 1,
        },
    )

    write_jsonl(
        seed / LAYER_ENRICHED_SOURCE_RELATIVE_PATH,
        [
            {
                "sequence_id": "portfolio_selected_trade_000001",
                "sequence_index": 1,
                "trade_key": "2026-01-01|SPY|long_call",
                "decision_date": "2026-01-01",
                "portfolio_realization_date": "2026-01-02",
                "symbol": "SPY",
                "selected_strategy": "long_call",
                "selection_state": "selected",
                "sizing_state": "sized",
                "contract_quantity": 2,
                "position_risk_dollars": 2000.0,
                "risk_budget_dollars": 2000.0,
                "risk_per_trade_pct": 0.01,
                "selected_expectancy_score": 0.25,
                "selected_expectancy_sample_count": 30,
                "selected_expectancy_state": "positive_expectancy_candidate",
                "regime_state": "risk_on",
                "asset_behavior_state": "constructive",
                "option_behavior_state": "iv_low_liquid",
                "selected_entry_legs": [{"option_symbol": "SPY260116C00500000"}],
                "selected_exit_legs": [],
                "portfolio_value_ranked_allocator_v2": {
                    "allocation_profile": "top_heavy_42100",
                    "rank_method": "strategy_prior_profit_factor",
                    "portfolio_heat_cap": 0.5,
                },
            }
        ],
    )

    write_json(seed / LAYER_ENRICHED_SUMMARY_RELATIVE_PATH, {"is_ready": True})

    write_json(
        seed / ALLOCATOR_SUMMARY_RELATIVE_PATH,
        {
            "is_ready": True,
            "policy": {"portfolio_heat_cap": 0.5},
            "recommended_by_capital": {},
            "top_heavy_candidates_top50": [
                {
                    "allocation_profile": "top_heavy_42100",
                    "rank_method": "strategy_prior_profit_factor",
                    "portfolio_heat_cap": 0.5,
                    "starting_capital": 30000,
                }
            ],
        },
    )

    write_jsonl(
        seed / ALLOCATOR_AGGREGATE_ROWS_RELATIVE_PATH,
        [
            {
                "allocation_profile": "top_heavy_42100",
                "rank_method": "strategy_prior_profit_factor",
                "portfolio_heat_cap": 0.5,
                "starting_capital": 30000,
            }
        ],
    )

    output = tmp_path / "portfolio_construction_latest_snapshot.json"

    summary = build_portfolio_construction_bootstrap(seed_bundle=seed, output_path=output)

    assert summary.is_ready
    assert summary.position_sizing_source_row_count == 2
    assert summary.enriched_sized_row_count == 1
    assert summary.allocator_aggregate_row_count == 1
    assert summary.latest_decision_date == "2026-01-01"
    assert summary.latest_symbol_count == 1
    assert summary.sized_trade_count == 1
    assert summary.skipped_sequence_row_count == 1
    assert summary.recommended_profile == "top_heavy_42100"
    assert summary.recommended_rank_method == "strategy_prior_profit_factor"
    assert summary.recommended_heat_cap == 0.5

    snapshot = json.loads(output.read_text(encoding="utf-8"))

    assert snapshot["contract"] == "portfolio_construction_latest_snapshot"
    assert snapshot["latest_rows_by_symbol"]["SPY"]["selected_strategy"] == "long_call"
    assert snapshot["latest_rows_by_symbol"]["SPY"]["regime_state"] == "risk_on"


def test_portfolio_construction_bootstrap_blocks_when_summaries_not_ready(tmp_path: Path):
    seed = short_seed(tmp_path)

    write_jsonl(seed / POSITION_SIZING_SOURCE_RELATIVE_PATH, [{"symbol": "SPY"}])
    write_json(seed / POSITION_SIZING_COMPATIBLE_SUMMARY_RELATIVE_PATH, {"is_ready": False})
    write_jsonl(seed / LAYER_ENRICHED_SOURCE_RELATIVE_PATH, [{"symbol": "SPY", "decision_date": "2026-01-01"}])
    write_json(seed / LAYER_ENRICHED_SUMMARY_RELATIVE_PATH, {"is_ready": False})
    write_json(seed / ALLOCATOR_SUMMARY_RELATIVE_PATH, {"is_ready": False, "top_heavy_candidates_top50": []})
    write_jsonl(seed / ALLOCATOR_AGGREGATE_ROWS_RELATIVE_PATH, [{"allocation_profile": "x"}])

    summary = build_portfolio_construction_bootstrap(
        seed_bundle=seed,
        output_path=tmp_path / "portfolio_construction_latest_snapshot.json",
    )

    assert not summary.is_ready
    assert "position_sizing_summary_not_ready" in summary.blockers
    assert "layer_enriched_summary_not_ready" in summary.blockers
    assert "allocator_summary_not_ready" in summary.blockers

