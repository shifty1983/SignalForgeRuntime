from __future__ import annotations

from pathlib import Path

from signalforge.runtime.closed_outcomes_discovery import (
    SEARCH_ROOTS,
    build_closed_outcomes_discovery,
    write_discovery,
)


def test_closed_outcomes_discovery_not_ready_when_seed_bundle_missing():
    discovery = build_closed_outcomes_discovery(Path("does_not_exist"))

    assert not discovery.is_ready
    assert discovery.seed_bundle_root is None
    assert discovery.candidate_file_count == 0
    assert discovery.viable_candidate_count == 0


def test_closed_outcomes_discovery_finds_full_schema_jsonl(tmp_path: Path):
    seed_root = tmp_path / "seed"
    source_root = seed_root / SEARCH_ROOTS[0]
    source_root.mkdir(parents=True)

    candidate_file = source_root / "closed_outcomes.jsonl"
    candidate_file.write_text(
        '{"symbol":"SPY","regime_state":"overheating","entry_date":"2026-01-01",'
        '"close_date":"2026-01-05","pnl":123.45,"strategy":"long_call",'
        '"quantity":1,"capital_label":"30k"}\n',
        encoding="utf-8",
    )

    discovery = build_closed_outcomes_discovery(seed_root)

    assert discovery.is_ready
    assert discovery.viable_candidate_count == 1
    assert discovery.best_candidate is not None
    assert discovery.best_candidate.relative_path.endswith("closed_outcomes.jsonl")


def test_closed_outcomes_discovery_accepts_alias_fields(tmp_path: Path):
    seed_root = tmp_path / "seed"
    source_root = seed_root / SEARCH_ROOTS[1]
    source_root.mkdir(parents=True)

    candidate_file = source_root / "alias_outcomes.jsonl"
    candidate_file.write_text(
        '{"underlying":"SPY","regime":"overheating","open_date":"2026-01-01",'
        '"exit_date":"2026-01-05","net_pnl":123.45,"strategy_family":"long_call",'
        '"contracts":1,"account_label":"30k"}\n',
        encoding="utf-8",
    )

    discovery = build_closed_outcomes_discovery(seed_root)

    assert discovery.is_ready
    assert discovery.best_candidate is not None
    assert discovery.best_candidate.has_required_core_fields


def test_write_closed_outcomes_discovery(tmp_path: Path):
    seed_root = tmp_path / "seed"
    source_root = seed_root / SEARCH_ROOTS[0]
    source_root.mkdir(parents=True)

    candidate_file = source_root / "closed_outcomes.jsonl"
    candidate_file.write_text(
        '{"symbol":"SPY","regime_state":"overheating","entry_date":"2026-01-01",'
        '"close_date":"2026-01-05","pnl":123.45,"strategy":"long_call",'
        '"quantity":1,"capital_label":"30k"}\n',
        encoding="utf-8",
    )

    discovery = build_closed_outcomes_discovery(seed_root)
    output = write_discovery(discovery, tmp_path / "closed_outcomes_discovery.json")

    assert output.exists()
    assert output.read_text(encoding="utf-8")

