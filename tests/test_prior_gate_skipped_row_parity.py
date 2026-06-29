from __future__ import annotations

import json
from pathlib import Path

from signalforge.runtime.prior_gate_skipped_row_parity import (
    EXPECTED_SKIP_COUNTS_BY_CAPITAL,
    SKIPPED_ROWS_RELATIVE_PATH,
    build_prior_gate_skipped_row_parity,
)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def skipped_row(capital_label: str, pnl: float = -1.0) -> dict:
    return {
        "capital_label": capital_label,
        "close_date": "2026-01-02",
        "entry_date": "2026-01-01",
        "pnl": pnl,
        "prior_count": 8,
        "prior_net_pnl": -100.0,
        "prior_pf": 0.5,
        "prior_win_rate": 0.25,
        "quantity": 1,
        "regime": "goldilocks",
        "row_index": 1,
        "strategy": "long_call",
        "symbol": "SPY",
    }


def test_prior_gate_parity_blocks_without_seed_bundle(tmp_path: Path):
    summary = build_prior_gate_skipped_row_parity(seed_bundle=tmp_path / "missing")

    assert not summary.is_ready
    assert summary.blocker_count == 1
    assert "seed_bundle_missing" in summary.blockers


def test_prior_gate_parity_passes_for_expected_locked_counts(tmp_path: Path):
    seed = tmp_path / "seed"
    path = seed / SKIPPED_ROWS_RELATIVE_PATH

    rows = []
    for capital_label, count in EXPECTED_SKIP_COUNTS_BY_CAPITAL.items():
        rows.extend(skipped_row(capital_label=capital_label) for _ in range(count))

    write_jsonl(path, rows)

    summary = build_prior_gate_skipped_row_parity(seed_bundle=seed)

    assert summary.is_ready
    assert summary.skipped_row_count == 176
    assert summary.blocked_by_clean_gate_count == 176
    assert summary.mismatch_count == 0
    assert summary.skip_count_by_capital == EXPECTED_SKIP_COUNTS_BY_CAPITAL


def test_prior_gate_parity_detects_gate_mismatch(tmp_path: Path):
    seed = tmp_path / "seed"
    path = seed / SKIPPED_ROWS_RELATIVE_PATH

    rows = []
    for capital_label, count in EXPECTED_SKIP_COUNTS_BY_CAPITAL.items():
        rows.extend(skipped_row(capital_label=capital_label) for _ in range(count))

    rows[0]["prior_net_pnl"] = 100.0

    write_jsonl(path, rows)

    summary = build_prior_gate_skipped_row_parity(seed_bundle=seed)

    assert not summary.is_ready
    assert summary.mismatch_count == 1
    assert "clean_prior_gate_did_not_block_all_locked_skipped_rows" in summary.blockers


def test_prior_gate_parity_detects_count_mismatch(tmp_path: Path):
    seed = tmp_path / "seed"
    path = seed / SKIPPED_ROWS_RELATIVE_PATH

    rows = [skipped_row(capital_label="30k") for _ in range(84)]
    rows.extend(skipped_row(capital_label="40k") for _ in range(91))

    write_jsonl(path, rows)

    summary = build_prior_gate_skipped_row_parity(seed_bundle=seed)

    assert not summary.is_ready
    assert "skip_count_by_capital_mismatch" in summary.blockers
    assert summary.expected_count_mismatch_by_capital["30k"]["expected"] == 85
    assert summary.expected_count_mismatch_by_capital["30k"]["actual"] == 84
