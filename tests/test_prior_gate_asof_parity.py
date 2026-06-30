from __future__ import annotations

import json
from pathlib import Path

from signalforge.bootstrap.prior_gate_asof_parity import (
    EXPECTED_SKIP_COUNTS_BY_CAPITAL,
    SKIPPED_ROWS_RELATIVE_PATH,
    build_prior_gate_asof_parity,
)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def closed_outcome(capital_label: str, close_date: str, pnl: float) -> dict:
    return {
        "capital_label": capital_label,
        "symbol": "SPY",
        "regime_state": "goldilocks",
        "strategy": "long_call",
        "entry_date": "2025-12-01",
        "close_date": close_date,
        "pnl": pnl,
        "quantity": 1,
    }


def skipped_row(capital_label: str) -> dict:
    return {
        "capital_label": capital_label,
        "close_date": "2026-01-02",
        "entry_date": "2026-01-01",
        "pnl": 25.0,
        "prior_count": 8,
        "prior_net_pnl": -800.0,
        "prior_pf": 0.0,
        "prior_win_rate": 0.0,
        "quantity": 1,
        "regime": "goldilocks",
        "row_index": 1,
        "strategy": "long_call",
        "symbol": "SPY",
    }


def test_prior_gate_asof_parity_blocks_when_inputs_missing(tmp_path: Path):
    summary = build_prior_gate_asof_parity(
        seed_bundle=tmp_path / "missing_seed",
        closed_outcomes_path=tmp_path / "missing_closed.jsonl",
    )

    assert not summary.is_ready
    assert "seed_bundle_missing" in summary.blockers
    assert "closed_outcomes_missing" in summary.blockers


def test_prior_gate_asof_parity_passes_expected_counts(tmp_path: Path):
    seed = tmp_path / "seed"
    skipped_path = seed / SKIPPED_ROWS_RELATIVE_PATH
    closed_path = tmp_path / "closed_trade_outcomes.jsonl"

    closed_rows = []
    skipped_rows = []

    for capital_label, skip_count in EXPECTED_SKIP_COUNTS_BY_CAPITAL.items():
        for index in range(8):
            closed_rows.append(
                closed_outcome(
                    capital_label=capital_label,
                    close_date=f"2025-12-{index + 1:02d}",
                    pnl=-100.0,
                )
            )

        skipped_rows.extend(skipped_row(capital_label) for _ in range(skip_count))

    write_jsonl(closed_path, closed_rows)
    write_jsonl(skipped_path, skipped_rows)

    summary = build_prior_gate_asof_parity(
        seed_bundle=seed,
        closed_outcomes_path=closed_path,
    )

    assert summary.is_ready
    assert summary.closed_outcome_row_count == 16
    assert summary.skipped_row_count == 176
    assert summary.matched_row_count == 176
    assert summary.mismatch_count == 0
    assert summary.clean_gate_block_count == 176
    assert summary.skip_count_by_capital == EXPECTED_SKIP_COUNTS_BY_CAPITAL


def test_prior_gate_asof_parity_detects_prior_stat_mismatch(tmp_path: Path):
    seed = tmp_path / "seed"
    skipped_path = seed / SKIPPED_ROWS_RELATIVE_PATH
    closed_path = tmp_path / "closed_trade_outcomes.jsonl"

    closed_rows = [closed_outcome("30k", f"2025-12-{index + 1:02d}", -100.0) for index in range(8)]
    closed_rows.extend(closed_outcome("40k", f"2025-12-{index + 1:02d}", -100.0) for index in range(8))

    skipped_rows = []
    skipped_rows.extend(skipped_row("30k") for _ in range(85))
    skipped_rows.extend(skipped_row("40k") for _ in range(91))
    skipped_rows[0]["prior_count"] = 9

    write_jsonl(closed_path, closed_rows)
    write_jsonl(skipped_path, skipped_rows)

    summary = build_prior_gate_asof_parity(
        seed_bundle=seed,
        closed_outcomes_path=closed_path,
    )

    assert not summary.is_ready
    assert summary.mismatch_count == 1
    assert "asof_prior_stats_mismatch" in summary.blockers
    assert summary.mismatch_samples[0].mismatch_reasons == ("prior_count_mismatch",)

