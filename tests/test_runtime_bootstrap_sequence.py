from __future__ import annotations

from pathlib import Path

from signalforge.bootstrap.bootstrap_sequence import (
    RuntimeBootstrapSequenceSummary,
    build_runtime_bootstrap_sequence,
    write_summary,
)


def test_bootstrap_sequence_blocks_when_seed_bundle_missing(tmp_path: Path):
    summary = build_runtime_bootstrap_sequence(seed_bundle=tmp_path / "missing_seed")

    assert not summary.is_ready
    assert summary.step_count == 1
    assert summary.failed_step_count == 1
    assert summary.blocker_count >= 1
    assert any(blocker.startswith("market_regime_bootstrap:") for blocker in summary.blockers)


def test_write_bootstrap_sequence_summary(tmp_path: Path):
    summary = RuntimeBootstrapSequenceSummary(
        is_ready=False,
        step_count=0,
        ready_step_count=0,
        failed_step_count=0,
        blocker_count=0,
        blockers=tuple(),
        steps=tuple(),
    )

    output = write_summary(summary, tmp_path / "runtime_bootstrap_sequence_summary.json")

    assert output.exists()
    assert output.read_text(encoding="utf-8")

