from __future__ import annotations

import json
from pathlib import Path

from signalforge.bootstrap.prior_symbol_regime_state_builder import build_prior_symbol_regime_state


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_prior_state_blocks_when_input_missing(tmp_path: Path):
    summary = build_prior_symbol_regime_state(
        input_path=tmp_path / "missing.jsonl",
        output_path=tmp_path / "state.json",
    )

    assert not summary.is_ready
    assert summary.blocker_count == 1
    assert "closed_outcomes_input_missing" in summary.blockers


def test_prior_state_builds_grouped_symbol_regime_rows(tmp_path: Path):
    input_path = tmp_path / "closed_trade_outcomes.jsonl"
    output_path = tmp_path / "state.json"

    rows = [
        {
            "capital_label": "30k",
            "symbol": "SPY",
            "regime_state": "goldilocks",
            "strategy": "long_call",
            "entry_date": "2026-01-01",
            "close_date": "2026-01-02",
            "pnl": 100,
            "quantity": 1,
        },
        {
            "capital_label": "30k",
            "symbol": "SPY",
            "regime_state": "goldilocks",
            "strategy": "long_call",
            "entry_date": "2026-01-03",
            "close_date": "2026-01-04",
            "pnl": -50,
            "quantity": 1,
        },
        {
            "capital_label": "40k",
            "symbol": "SPY",
            "regime_state": "goldilocks",
            "strategy": "long_call",
            "entry_date": "2026-01-03",
            "close_date": "2026-01-04",
            "pnl": -25,
            "quantity": 1,
        },
    ]

    write_jsonl(input_path, rows)

    summary = build_prior_symbol_regime_state(input_path=input_path, output_path=output_path)

    assert summary.is_ready
    assert summary.input_row_count == 3
    assert summary.state_row_count == 2
    assert summary.capital_labels == ("30k", "40k")

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    state_rows = payload["state_rows"]

    row_30k = next(row for row in state_rows if row["capital_label"] == "30k")
    assert row_30k["prior_count"] == 2
    assert row_30k["prior_net_pnl"] == 50
    assert row_30k["prior_profit_factor"] == 2.0
    assert row_30k["v3_2_2_gate_blocks"] is False


def test_prior_state_marks_v3_2_2_blocking_group(tmp_path: Path):
    input_path = tmp_path / "closed_trade_outcomes.jsonl"
    output_path = tmp_path / "state.json"

    rows = []
    for index in range(8):
        rows.append(
            {
                "capital_label": "30k",
                "symbol": "XLF",
                "regime_state": "overheating",
                "strategy": "long_call",
                "entry_date": f"2026-01-{index + 1:02d}",
                "close_date": f"2026-01-{index + 2:02d}",
                "pnl": -100,
                "quantity": 1,
            }
        )

    write_jsonl(input_path, rows)

    summary = build_prior_symbol_regime_state(input_path=input_path, output_path=output_path)

    assert summary.is_ready
    assert summary.blocking_state_count == 1

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    state_row = payload["state_rows"][0]

    assert state_row["prior_count"] == 8
    assert state_row["prior_net_pnl"] == -800
    assert state_row["prior_profit_factor"] == 0.0
    assert state_row["v3_2_2_gate_blocks"] is True




