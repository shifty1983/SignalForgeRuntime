from __future__ import annotations

import json
from pathlib import Path

from signalforge.bootstrap.asset_behavior_bootstrap import (
    ASSET_BEHAVIOR_SOURCE_RELATIVE_PATH,
    build_asset_behavior_bootstrap,
)


def test_asset_behavior_bootstrap_blocks_when_seed_missing(tmp_path: Path):
    summary = build_asset_behavior_bootstrap(
        seed_bundle=tmp_path / "missing",
        output_path=tmp_path / "asset_behavior_latest_snapshot.json",
    )

    assert not summary.is_ready
    assert "seed_bundle_missing" in summary.blockers


def test_asset_behavior_bootstrap_writes_snapshot(tmp_path: Path):
    seed = tmp_path / "seed"
    source = seed / ASSET_BEHAVIOR_SOURCE_RELATIVE_PATH
    source.parent.mkdir(parents=True)

    source.write_text(
        json.dumps(
            {
                "artifact_type": "signalforge_asset_behavior_decision_export",
                "schema_version": "test",
                "is_ready": True,
                "status": "ready",
                "macro_regime_label": "late_cycle_overheating",
                "policy_regime_label": "late_cycle_overheating",
                "weekly_planning_label": "late_cycle_overheating_with_rates_review",
                "asset_behavior_decision_items": [
                    {
                        "symbol": "SPY",
                        "asset_class": "equities",
                        "directional_stance": "long_bias",
                        "final_decision": "eligible_long",
                        "final_gate": "allowed",
                        "manual_review_required": False,
                        "option_behavior_handoff": "ready",
                        "tradability_gate": "allowed",
                        "tradability_state": "tradable",
                        "stance_gate": "allowed",
                        "direction_fit_score": 90.0,
                        "final_decision_score": 1.0,
                        "relative_strength_score": 80.0,
                        "relative_weakness_score": 20.0,
                        "tradability_score": 95.0,
                        "decision_reasons": ["final_decision:eligible_long"],
                    },
                    {
                        "symbol": "TLT",
                        "asset_class": "bonds",
                        "directional_stance": "short_bias",
                        "final_decision": "eligible_short",
                        "final_gate": "review_required",
                        "manual_review_required": True,
                        "option_behavior_handoff": "review_required",
                        "tradability_gate": "allowed",
                        "tradability_state": "manual_review",
                        "stance_gate": "allowed",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    output = tmp_path / "asset_behavior_latest_snapshot.json"

    summary = build_asset_behavior_bootstrap(seed_bundle=seed, output_path=output)

    assert summary.is_ready
    assert summary.item_count == 2
    assert summary.symbol_count == 2
    assert summary.eligible_long_count == 1
    assert summary.eligible_short_count == 1
    assert summary.review_required_count == 1

    snapshot = json.loads(output.read_text(encoding="utf-8"))

    assert snapshot["contract"] == "asset_behavior_latest_snapshot"
    assert snapshot["items_by_symbol"]["SPY"]["final_decision"] == "eligible_long"
    assert snapshot["final_decision_counts"] == {"eligible_long": 1, "eligible_short": 1}


def test_asset_behavior_bootstrap_blocks_when_source_not_ready(tmp_path: Path):
    seed = tmp_path / "seed"
    source = seed / ASSET_BEHAVIOR_SOURCE_RELATIVE_PATH
    source.parent.mkdir(parents=True)

    source.write_text(
        json.dumps(
            {
                "is_ready": False,
                "status": "blocked",
                "asset_behavior_decision_items": [
                    {
                        "symbol": "SPY",
                        "final_decision": "eligible_long",
                        "final_gate": "allowed",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = build_asset_behavior_bootstrap(
        seed_bundle=seed,
        output_path=tmp_path / "asset_behavior_latest_snapshot.json",
    )

    assert not summary.is_ready
    assert "source_not_ready" in summary.blockers
    assert "source_status_not_ready" in summary.blockers




