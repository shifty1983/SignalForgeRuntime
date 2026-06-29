from __future__ import annotations

import json
from pathlib import Path

from signalforge.bootstrap.v3_2_2_runtime_readiness_audit import (
    build_v3_2_2_runtime_readiness_audit,
)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_runtime_readiness_blocks_when_pre_trade_missing(tmp_path: Path):
    summary = build_v3_2_2_runtime_readiness_audit(
        runtime_root=tmp_path,
        pre_trade_decisions_path="missing.jsonl",
    )

    assert not summary.is_ready
    assert "pre_trade_decisions_missing" in summary.blockers


def test_runtime_readiness_detects_rule_mismatches(tmp_path: Path):
    pre_trade = tmp_path / "decisions.jsonl"

    write_jsonl(
        pre_trade,
        [
            {
                "contract": "v3_2_2_pre_trade_decision",
                "rulebook": "signalforge_v3_2_2",
                "symbol": "SPY",
                "paper_candidate_action": "accept",
                "skip_reasons": [],
                "spread_pct": 0.20,
                "spread_guardrail_passed": False,
                "prior_symbol_regime_gate_passed": True,
                "prior_symbol_regime_stats": {
                    "prior_count": 10,
                    "prior_net_pnl": 100.0,
                    "prior_profit_factor": 2.0,
                },
            },
            {
                "contract": "v3_2_2_pre_trade_decision",
                "rulebook": "signalforge_v3_2_2",
                "symbol": "TLT",
                "paper_candidate_action": "accept",
                "skip_reasons": [],
                "spread_pct": 0.05,
                "spread_guardrail_passed": True,
                "prior_symbol_regime_gate_passed": False,
                "prior_symbol_regime_stats": {
                    "prior_count": 8,
                    "prior_net_pnl": -1.0,
                    "prior_profit_factor": 0.5,
                },
            },
        ],
    )

    summary = build_v3_2_2_runtime_readiness_audit(
        runtime_root=tmp_path,
        pre_trade_decisions_path="decisions.jsonl",
    )

    assert not summary.is_ready
    assert summary.spread_rule_mismatch_count == 1
    assert summary.prior_rule_mismatch_count == 1
    assert "spread_rule_mismatches" in summary.blockers
    assert "prior_rule_mismatches" in summary.blockers


def test_runtime_readiness_passes_with_consistent_decisions(tmp_path: Path):
    pre_trade = tmp_path / "decisions.jsonl"

    write_jsonl(
        pre_trade,
        [
            {
                "contract": "v3_2_2_pre_trade_decision",
                "rulebook": "signalforge_v3_2_2",
                "symbol": "SPY",
                "paper_candidate_action": "accept",
                "skip_reasons": [],
                "spread_pct": 0.05,
                "spread_guardrail_passed": True,
                "prior_symbol_regime_gate_passed": True,
                "prior_symbol_regime_stats": {
                    "prior_count": 10,
                    "prior_net_pnl": 100.0,
                    "prior_profit_factor": 2.0,
                },
            },
            {
                "contract": "v3_2_2_pre_trade_decision",
                "rulebook": "signalforge_v3_2_2",
                "symbol": "QQQ",
                "paper_candidate_action": "skip",
                "skip_reasons": ["spread_gt_12_5pct"],
                "spread_pct": 0.20,
                "spread_guardrail_passed": False,
                "prior_symbol_regime_gate_passed": True,
                "prior_symbol_regime_stats": {
                    "prior_count": 10,
                    "prior_net_pnl": 100.0,
                    "prior_profit_factor": 2.0,
                },
            },
            {
                "contract": "v3_2_2_pre_trade_decision",
                "rulebook": "signalforge_v3_2_2",
                "symbol": "TLT",
                "paper_candidate_action": "skip",
                "skip_reasons": ["prior_symbol_regime_weak"],
                "spread_pct": 0.05,
                "spread_guardrail_passed": True,
                "prior_symbol_regime_gate_passed": False,
                "prior_symbol_regime_stats": {
                    "prior_count": 8,
                    "prior_net_pnl": -1.0,
                    "prior_profit_factor": 0.5,
                },
            },
        ],
    )

    summary = build_v3_2_2_runtime_readiness_audit(
        runtime_root=tmp_path,
        pre_trade_decisions_path="decisions.jsonl",
    )

    # The isolated test root does not contain all runtime contracts, but rule consistency should pass.
    assert summary.pre_trade_decision_count == 3
    assert summary.accepted_count == 1
    assert summary.skipped_count == 2
    assert summary.spread_rule_mismatch_count == 0
    assert summary.prior_rule_mismatch_count == 0
