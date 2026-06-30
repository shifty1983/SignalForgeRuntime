from __future__ import annotations

from pathlib import Path

from signalforge.runtime.market_regime_source_discovery import (
    SEARCH_ROOTS_BY_LAYER,
    build_market_regime_source_discovery,
    write_discovery,
)


def test_market_regime_discovery_blocks_when_seed_bundle_missing():
    discovery = build_market_regime_source_discovery(Path("does_not_exist"))

    assert not discovery.is_ready
    assert discovery.blocker_count == 1
    assert "seed_bundle_missing" in discovery.blockers


def test_market_regime_discovery_finds_market_and_regime_sources(tmp_path: Path):
    seed = tmp_path / "seed"

    market_root = seed / SEARCH_ROOTS_BY_LAYER["market"][0]
    market_root.mkdir(parents=True)

    regime_root = seed / SEARCH_ROOTS_BY_LAYER["regime"][0]
    regime_root.mkdir(parents=True)

    (market_root / "market.jsonl").write_text(
        '{"symbol":"SPY","date":"2026-01-01","open":100,"high":101,"low":99,"close":100.5,"volume":1000}\n',
        encoding="utf-8",
    )

    (regime_root / "regime.jsonl").write_text(
        '{"date":"2026-01-01","regime_state":"goldilocks"}\n',
        encoding="utf-8",
    )

    discovery = build_market_regime_source_discovery(seed)

    assert discovery.is_ready
    assert discovery.viable_market_candidate_count == 1
    assert discovery.viable_regime_candidate_count == 1
    assert discovery.best_market_candidate is not None
    assert discovery.best_regime_candidate is not None


def test_market_regime_discovery_detects_missing_regime_source(tmp_path: Path):
    seed = tmp_path / "seed"

    market_root = seed / SEARCH_ROOTS_BY_LAYER["market"][0]
    market_root.mkdir(parents=True)

    (market_root / "market.jsonl").write_text(
        '{"symbol":"SPY","date":"2026-01-01","close":100.5}\n',
        encoding="utf-8",
    )

    discovery = build_market_regime_source_discovery(seed)

    assert not discovery.is_ready
    assert "no_viable_regime_source_found" in discovery.blockers


def test_write_market_regime_discovery(tmp_path: Path):
    seed = tmp_path / "seed"

    market_root = seed / SEARCH_ROOTS_BY_LAYER["market"][0]
    market_root.mkdir(parents=True)

    regime_root = seed / SEARCH_ROOTS_BY_LAYER["regime"][0]
    regime_root.mkdir(parents=True)

    (market_root / "market.jsonl").write_text(
        '{"symbol":"SPY","date":"2026-01-01","close":100.5}\n',
        encoding="utf-8",
    )

    (regime_root / "regime.jsonl").write_text(
        '{"date":"2026-01-01","regime_state":"goldilocks"}\n',
        encoding="utf-8",
    )

    discovery = build_market_regime_source_discovery(seed)
    output = write_discovery(discovery, tmp_path / "market_regime_source_discovery.json")

    assert output.exists()
    assert output.read_text(encoding="utf-8")

