from __future__ import annotations

import json
from pathlib import Path

from signalforge.bootstrap.market_regime_bootstrap import (
    MARKET_SOURCE_RELATIVE_PATH,
    REGIME_SOURCE_RELATIVE_PATH,
    build_market_regime_bootstrap,
)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_market_regime_bootstrap_blocks_when_seed_missing(tmp_path: Path):
    summary = build_market_regime_bootstrap(
        seed_bundle=tmp_path / "missing",
        market_output_path=tmp_path / "market.jsonl",
        regime_output_path=tmp_path / "regime.json",
    )

    assert not summary.is_ready
    assert "seed_bundle_missing" in summary.blockers


def test_market_regime_bootstrap_writes_market_and_regime_outputs(tmp_path: Path):
    seed = tmp_path / "seed"
    market_source = seed / MARKET_SOURCE_RELATIVE_PATH
    regime_source = seed / REGIME_SOURCE_RELATIVE_PATH

    write_jsonl(
        market_source,
        [
            {
                "underlying_symbol": "SPY",
                "quote_date": "2026-01-01",
                "underlying_price": 500.0,
                "volume": 10,
            },
            {
                "underlying_symbol": "SPY",
                "quote_date": "2026-01-01",
                "underlying_price": 500.0,
                "volume": 5,
            },
            {
                "underlying_symbol": "QQQ",
                "quote_date": "2026-01-02",
                "underlying_price": 400.0,
                "volume": 7,
            },
        ],
    )

    regime_source.parent.mkdir(parents=True, exist_ok=True)
    regime_source.write_text(
        json.dumps(
            {
                "artifact_type": "signalforge_historical_regime_date_map",
                "schema_version": "test",
                "quote_date_count": 2,
                "mapped_quote_date_count": 2,
                "date_map_items": [
                    {
                        "quote_date": "2026-01-01",
                        "regime_date": "2025-12-31",
                        "regime_state": "risk_on",
                        "risk_environment": "risk_on",
                    },
                    {
                        "quote_date": "2026-01-02",
                        "regime_date": "2026-01-02",
                        "regime_state": "late_cycle_overheating",
                        "risk_environment": "risk_on",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    market_output = tmp_path / "underlying_daily.jsonl"
    regime_output = tmp_path / "regime_latest_snapshot.json"

    summary = build_market_regime_bootstrap(
        seed_bundle=seed,
        market_output_path=market_output,
        regime_output_path=regime_output,
    )

    assert summary.is_ready
    assert summary.source_option_row_count == 3
    assert summary.market_row_count == 2
    assert summary.market_symbol_count == 2
    assert summary.market_date_count == 2
    assert summary.latest_regime_quote_date == "2026-01-02"
    assert summary.latest_regime_state == "late_cycle_overheating"

    market_rows = [json.loads(line) for line in market_output.read_text(encoding="utf-8").splitlines()]
    spy_row = next(row for row in market_rows if row["symbol"] == "SPY")

    assert spy_row["close"] == 500.0
    assert spy_row["source_option_contract_row_count"] == 2
    assert spy_row["option_contract_volume"] == 15.0

    regime_snapshot = json.loads(regime_output.read_text(encoding="utf-8"))

    assert regime_snapshot["contract"] == "regime_latest_snapshot"
    assert regime_snapshot["latest_regime_state"] == "late_cycle_overheating"


def test_market_regime_bootstrap_counts_price_conflicts(tmp_path: Path):
    seed = tmp_path / "seed"
    market_source = seed / MARKET_SOURCE_RELATIVE_PATH
    regime_source = seed / REGIME_SOURCE_RELATIVE_PATH

    write_jsonl(
        market_source,
        [
            {
                "underlying_symbol": "SPY",
                "quote_date": "2026-01-01",
                "underlying_price": 500.0,
                "volume": 10,
            },
            {
                "underlying_symbol": "SPY",
                "quote_date": "2026-01-01",
                "underlying_price": 501.0,
                "volume": 5,
            },
        ],
    )

    regime_source.parent.mkdir(parents=True, exist_ok=True)
    regime_source.write_text(
        json.dumps(
            {
                "date_map_items": [
                    {
                        "quote_date": "2026-01-01",
                        "regime_date": "2026-01-01",
                        "regime_state": "risk_on",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    summary = build_market_regime_bootstrap(
        seed_bundle=seed,
        market_output_path=tmp_path / "market.jsonl",
        regime_output_path=tmp_path / "regime.json",
    )

    assert summary.is_ready
    assert summary.price_conflict_group_count == 1

