from __future__ import annotations

import json
from pathlib import Path

from signalforge.bootstrap.option_quote_bootstrap import (
    QUOTE_AUDIT_SOURCE_RELATIVE_PATH,
    build_option_quote_bootstrap,
)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_option_quote_bootstrap_blocks_when_seed_missing(tmp_path: Path):
    summary = build_option_quote_bootstrap(
        seed_bundle=tmp_path / "missing",
        output_path=tmp_path / "option_quote_snapshot.jsonl",
    )

    assert not summary.is_ready
    assert "seed_bundle_missing" in summary.blockers


def test_option_quote_bootstrap_writes_flattened_quotes(tmp_path: Path):
    seed = tmp_path / "seed"
    source = seed / QUOTE_AUDIT_SOURCE_RELATIVE_PATH

    write_jsonl(
        source,
        [
            {
                "capital_label": "30k",
                "row_index": 1,
                "leg_index": 0,
                "entry_date": "2026-01-01",
                "entry_matched": True,
                "entry_target_key": ["contract", "SPY260116C00500000", "2026-01-01"],
                "entry_quote": {
                    "bid": 1.0,
                    "ask": 1.2,
                    "mid": 1.1,
                    "spread": 0.2,
                    "spread_pct": 0.1818,
                    "sanity": "ok",
                    "source_path": "source.jsonl",
                    "source_row_index": 10,
                    "key_used": ["contract", "SPY260116C00500000", "2026-01-01"],
                },
                "exit_date": "2026-01-02",
                "exit_matched": True,
                "exit_target_key": ["contract", "SPY260116C00500000", "2026-01-02"],
                "exit_quote": {
                    "bid": 1.4,
                    "ask": 1.6,
                    "mid": 1.5,
                    "spread": 0.2,
                    "spread_pct": 0.1333,
                    "sanity": "ok",
                    "source_path": "source.jsonl",
                    "source_row_index": 11,
                    "key_used": ["contract", "SPY260116C00500000", "2026-01-02"],
                },
                "identity": {
                    "contract_symbol": "SPY260116C00500000",
                    "expiration": "2026-01-16",
                    "right": "C",
                    "strike": "500",
                    "underlying": "SPY",
                },
            }
        ],
    )

    output = tmp_path / "option_quote_snapshot.jsonl"
    summary = build_option_quote_bootstrap(seed_bundle=seed, output_path=output)

    assert summary.is_ready
    assert summary.source_audit_row_count == 1
    assert summary.matched_entry_quote_count == 1
    assert summary.matched_exit_quote_count == 1
    assert summary.emitted_quote_count == 2
    assert summary.written_quote_count == 2
    assert summary.contract_symbol_count == 1
    assert summary.quote_date_count == 2

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

    assert rows[0]["contract"] == "option_quote_snapshot_row"
    assert rows[0]["contract_symbol"] == "SPY260116C00500000"
    assert {row["quote_role"] for row in rows} == {"entry", "exit"}


def test_option_quote_bootstrap_dedupes_same_quote_observation(tmp_path: Path):
    seed = tmp_path / "seed"
    source = seed / QUOTE_AUDIT_SOURCE_RELATIVE_PATH

    row = {
        "capital_label": "30k",
        "row_index": 1,
        "leg_index": 0,
        "entry_date": "2026-01-01",
        "entry_matched": True,
        "entry_target_key": ["contract", "SPY260116C00500000", "2026-01-01"],
        "entry_quote": {
            "bid": 1.0,
            "ask": 1.2,
            "mid": 1.1,
            "source_row_index": 10,
        },
        "exit_date": "2026-01-01",
        "exit_matched": False,
        "exit_quote": None,
        "identity": {
            "contract_symbol": "SPY260116C00500000",
        },
    }

    duplicate = dict(row)
    duplicate["capital_label"] = "40k"

    write_jsonl(source, [row, duplicate])

    output = tmp_path / "option_quote_snapshot.jsonl"
    summary = build_option_quote_bootstrap(seed_bundle=seed, output_path=output)

    assert summary.is_ready
    assert summary.emitted_quote_count == 2
    assert summary.written_quote_count == 1
    assert summary.duplicate_quote_count == 1




