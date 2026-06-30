from __future__ import annotations

import json
from pathlib import Path

from signalforge.bootstrap.v3_2_2_pre_trade_decisions_bootstrap import (
    build_v3_2_2_pre_trade_decisions_bootstrap,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_v3_2_2_pre_trade_blocks_when_inputs_missing(tmp_path: Path):
    summary = build_v3_2_2_pre_trade_decisions_bootstrap(
        portfolio_construction_snapshot_path=tmp_path / "missing_portfolio.json",
        prior_state_path=tmp_path / "missing_prior.json",
        option_quote_snapshot_path=tmp_path / "missing_quotes.jsonl",
        output_path=tmp_path / "decisions.jsonl",
    )

    assert not summary.is_ready
    assert "portfolio_construction_snapshot_missing" in summary.blockers
    assert "prior_symbol_regime_state_missing" in summary.blockers
    assert "option_quote_snapshot_missing" in summary.blockers


def test_v3_2_2_pre_trade_writes_accept_and_skip_decisions(tmp_path: Path):
    portfolio_path = tmp_path / "portfolio.json"
    prior_path = tmp_path / "prior.json"
    quote_path = tmp_path / "quotes.jsonl"
    output_path = tmp_path / "decisions.jsonl"

    write_json(
        portfolio_path,
        {
            "contract": "portfolio_construction_latest_snapshot",
            "allocator_recommended_candidate": {
                "starting_capital": 30000,
                "allocation_profile": "top_heavy_42100",
            },
            "latest_rows": [
                {
                    "sequence_id": "seq_accept",
                    "trade_key": "2026-01-01|SPY|long_call",
                    "decision_date": "2026-01-01",
                    "symbol": "SPY",
                    "regime_state": "goldilocks",
                    "selected_strategy": "long_call",
                    "selection_state": "selected",
                    "sizing_state": "sized",
                    "spread_pct": 0.05,
                },
                {
                    "sequence_id": "seq_spread_skip",
                    "trade_key": "2026-01-01|QQQ|long_call",
                    "decision_date": "2026-01-01",
                    "symbol": "QQQ",
                    "regime_state": "goldilocks",
                    "selected_strategy": "long_call",
                    "selection_state": "selected",
                    "sizing_state": "sized",
                    "spread_pct": 0.20,
                },
                {
                    "sequence_id": "seq_prior_skip",
                    "trade_key": "2026-01-01|TLT|long_put",
                    "decision_date": "2026-01-01",
                    "symbol": "TLT",
                    "regime_state": "overheating",
                    "selected_strategy": "long_put",
                    "selection_state": "selected",
                    "sizing_state": "sized",
                    "spread_pct": 0.05,
                },
            ],
        },
    )

    write_json(
        prior_path,
        {
            "state_rows": [
                {
                    "capital_label": "30k",
                    "symbol": "SPY",
                    "regime_state": "goldilocks",
                    "prior_count": 10,
                    "prior_net_pnl": 1000.0,
                    "prior_profit_factor": 2.0,
                },
                {
                    "capital_label": "30k",
                    "symbol": "QQQ",
                    "regime_state": "goldilocks",
                    "prior_count": 10,
                    "prior_net_pnl": 1000.0,
                    "prior_profit_factor": 2.0,
                },
                {
                    "capital_label": "30k",
                    "symbol": "TLT",
                    "regime_state": "overheating",
                    "prior_count": 8,
                    "prior_net_pnl": -1.0,
                    "prior_profit_factor": 0.5,
                },
            ]
        },
    )

    write_jsonl(quote_path, [{"contract_symbol": "SPY260116C00500000"}])

    summary = build_v3_2_2_pre_trade_decisions_bootstrap(
        portfolio_construction_snapshot_path=portfolio_path,
        prior_state_path=prior_path,
        option_quote_snapshot_path=quote_path,
        output_path=output_path,
    )

    assert summary.is_ready
    assert summary.portfolio_candidate_count == 3
    assert summary.quote_snapshot_row_count == 1
    assert summary.prior_state_row_count == 3
    assert summary.decision_count == 3
    assert summary.accepted_count == 1
    assert summary.skipped_count == 2
    assert summary.spread_guardrail_skip_count == 1
    assert summary.prior_gate_skip_count == 1

    rows = read_jsonl(output_path)
    by_sequence = {row["sequence_id"]: row for row in rows}

    assert by_sequence["seq_accept"]["paper_candidate_action"] == "accept"
    assert by_sequence["seq_spread_skip"]["paper_candidate_action"] == "skip"
    assert "spread_gt_12_5pct" in by_sequence["seq_spread_skip"]["skip_reasons"]
    assert by_sequence["seq_prior_skip"]["paper_candidate_action"] == "skip"
    assert "prior_symbol_regime_weak" in by_sequence["seq_prior_skip"]["skip_reasons"]

