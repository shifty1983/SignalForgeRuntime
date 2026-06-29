from __future__ import annotations

import json
from pathlib import Path

from signalforge.bootstrap.prior_gate_evaluation_outcomes_bootstrap import (
    build_prior_gate_evaluation_outcomes_bootstrap,
)
from signalforge.bootstrap.prior_gate_skipped_row_parity import SKIPPED_ROWS_RELATIVE_PATH


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_prior_gate_evaluation_bootstrap_blocks_when_inputs_missing(tmp_path: Path):
    summary = build_prior_gate_evaluation_outcomes_bootstrap(
        seed_bundle=tmp_path / "missing_seed",
        closed_outcomes_path=tmp_path / "missing_closed.jsonl",
        output_path=tmp_path / "evaluation.jsonl",
    )

    assert not summary.is_ready
    assert "seed_bundle_missing" in summary.blockers
    assert "closed_outcomes_missing" in summary.blockers


def test_prior_gate_evaluation_bootstrap_combines_executed_and_shadow_rows(tmp_path: Path):
    seed = tmp_path / "seed"
    closed_path = tmp_path / "closed_trade_outcomes.jsonl"
    skipped_path = seed / SKIPPED_ROWS_RELATIVE_PATH
    output_path = tmp_path / "evaluation.jsonl"

    write_jsonl(
        closed_path,
        [
            {
                "capital_label": "30k",
                "symbol": "SPY",
                "regime_state": "goldilocks",
                "strategy": "long_call",
                "entry_date": "2026-01-01",
                "close_date": "2026-01-02",
                "pnl": 100,
                "quantity": 1,
            }
        ],
    )

    write_jsonl(
        skipped_path,
        [
            {
                "capital_label": "30k",
                "symbol": "SPY",
                "regime": "goldilocks",
                "strategy": "long_call",
                "entry_date": "2026-01-03",
                "close_date": "2026-01-04",
                "pnl": -50,
                "quantity": 1,
                "prior_count": 8,
                "prior_net_pnl": -100,
                "prior_pf": 0.5,
                "prior_win_rate": 0.25,
                "row_index": 1,
            }
        ],
    )

    summary = build_prior_gate_evaluation_outcomes_bootstrap(
        seed_bundle=seed,
        closed_outcomes_path=closed_path,
        output_path=output_path,
    )

    assert summary.is_ready
    assert summary.executed_outcome_count == 1
    assert summary.shadow_skipped_outcome_count == 1
    assert summary.evaluation_outcome_count == 2

    rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert {row["outcome_role"] for row in rows} == {
        "executed_closed_trade",
        "v3_2_2_prior_gate_shadow_skipped",
    }
