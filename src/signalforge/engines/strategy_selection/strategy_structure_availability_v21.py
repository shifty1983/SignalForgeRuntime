from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from itertools import groupby
from pathlib import Path
from typing import Any, Iterable


STRATEGY_NAMES = [
    "long_call",
    "long_put",
    "bull_call_debit_spread",
    "bear_put_debit_spread",
    "put_credit_spread",
    "call_credit_spread",
    "iron_condor",
    "iron_butterfly",
    "calendar_spread",
    "diagonal_spread",
]


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def to_float(value: Any) -> float | None:
    if value in (None, "", "NaN", "nan"):
        return None
    try:
        value = float(value)
    except Exception:
        return None
    if value != value:
        return None
    return value


def to_int(value: Any) -> int:
    if value in (None, "", "NaN", "nan"):
        return 0
    try:
        return int(float(value))
    except Exception:
        return 0


def liquid_enough(
    contract: dict[str, Any],
    max_spread_pct: float = 0.20,
    min_open_interest: int = 1,
) -> bool:
    spread_pct = contract.get("spread_pct")
    open_interest = contract.get("open_interest") or 0

    return (
        contract.get("quote_complete") == 1
        and contract.get("greeks_complete") == 1
        and spread_pct is not None
        and spread_pct <= max_spread_pct
        and open_interest >= min_open_interest
    )


def by_expiration(contracts: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in contracts:
        grouped[str(c["expiration"])].append(c)
    return grouped


def count_long_candidates(
    contracts: list[dict[str, Any]],
    right: str,
) -> dict[str, Any]:
    candidates = [
        c for c in contracts
        if c["right"] == right
        and liquid_enough(c, max_spread_pct=0.20, min_open_interest=1)
        and c["dte"] is not None
        and 20 <= c["dte"] <= 90
        and c["abs_delta"] is not None
        and 0.30 <= c["abs_delta"] <= 0.75
    ]

    return {
        "candidate_contract_count": len(candidates),
        "candidate_pair_count": 0,
        "candidate_structure_count": len(candidates),
        "representative_dte_min": min((c["dte"] for c in candidates), default=None),
        "representative_dte_max": max((c["dte"] for c in candidates), default=None),
    }


def count_vertical_pairs(
    contracts: list[dict[str, Any]],
    strategy_name: str,
) -> dict[str, Any]:
    pair_count = 0
    expirations_with_pairs = 0

    for expiration, exp_rows in by_expiration(contracts).items():
        if strategy_name in {"bull_call_debit_spread", "call_credit_spread"}:
            rows = sorted(
                [
                    c for c in exp_rows
                    if c["right"] == "call"
                    and liquid_enough(c, max_spread_pct=0.20, min_open_interest=1)
                    and c["dte"] is not None
                    and 20 <= c["dte"] <= 90
                    and c["abs_delta"] is not None
                ],
                key=lambda c: c["strike"],
            )

            if strategy_name == "bull_call_debit_spread":
                longs = [c for c in rows if 0.40 <= c["abs_delta"] <= 0.80]
                shorts = [c for c in rows if 0.15 <= c["abs_delta"] <= 0.55]

                local_pairs = sum(
                    1
                    for long_leg in longs
                    for short_leg in shorts
                    if short_leg["strike"] > long_leg["strike"]
                )

            else:
                shorts = [c for c in rows if 0.10 <= c["abs_delta"] <= 0.35]
                longs = [c for c in rows if 0.02 <= c["abs_delta"] <= 0.25]

                local_pairs = sum(
                    1
                    for short_leg in shorts
                    for long_leg in longs
                    if long_leg["strike"] > short_leg["strike"]
                )

        elif strategy_name in {"bear_put_debit_spread", "put_credit_spread"}:
            rows = sorted(
                [
                    c for c in exp_rows
                    if c["right"] == "put"
                    and liquid_enough(c, max_spread_pct=0.20, min_open_interest=1)
                    and c["dte"] is not None
                    and 20 <= c["dte"] <= 90
                    and c["abs_delta"] is not None
                ],
                key=lambda c: c["strike"],
            )

            if strategy_name == "bear_put_debit_spread":
                longs = [c for c in rows if 0.40 <= c["abs_delta"] <= 0.80]
                shorts = [c for c in rows if 0.15 <= c["abs_delta"] <= 0.55]

                local_pairs = sum(
                    1
                    for long_leg in longs
                    for short_leg in shorts
                    if short_leg["strike"] < long_leg["strike"]
                )

            else:
                shorts = [c for c in rows if 0.10 <= c["abs_delta"] <= 0.35]
                longs = [c for c in rows if 0.02 <= c["abs_delta"] <= 0.25]

                local_pairs = sum(
                    1
                    for short_leg in shorts
                    for long_leg in longs
                    if long_leg["strike"] < short_leg["strike"]
                )

        else:
            local_pairs = 0

        if local_pairs > 0:
            expirations_with_pairs += 1

        pair_count += local_pairs

    return {
        "candidate_contract_count": 0,
        "candidate_pair_count": pair_count,
        "candidate_structure_count": pair_count,
        "expiration_count_with_structures": expirations_with_pairs,
    }


def count_iron_condors(contracts: list[dict[str, Any]]) -> dict[str, Any]:
    structure_count = 0
    expirations_with_structures = 0

    for expiration, exp_rows in by_expiration(contracts).items():
        puts = sorted(
            [
                c for c in exp_rows
                if c["right"] == "put"
                and liquid_enough(c, max_spread_pct=0.20, min_open_interest=1)
                and c["dte"] is not None
                and 20 <= c["dte"] <= 90
                and c["abs_delta"] is not None
            ],
            key=lambda c: c["strike"],
        )

        calls = sorted(
            [
                c for c in exp_rows
                if c["right"] == "call"
                and liquid_enough(c, max_spread_pct=0.20, min_open_interest=1)
                and c["dte"] is not None
                and 20 <= c["dte"] <= 90
                and c["abs_delta"] is not None
            ],
            key=lambda c: c["strike"],
        )

        short_puts = [c for c in puts if 0.10 <= c["abs_delta"] <= 0.35]
        long_puts = [c for c in puts if 0.02 <= c["abs_delta"] <= 0.25]

        short_calls = [c for c in calls if 0.10 <= c["abs_delta"] <= 0.35]
        long_calls = [c for c in calls if 0.02 <= c["abs_delta"] <= 0.25]

        put_spreads = sum(
            1
            for short_put in short_puts
            for long_put in long_puts
            if long_put["strike"] < short_put["strike"]
        )

        call_spreads = sum(
            1
            for short_call in short_calls
            for long_call in long_calls
            if long_call["strike"] > short_call["strike"]
        )

        local_structures = put_spreads * call_spreads

        if local_structures > 0:
            expirations_with_structures += 1

        structure_count += local_structures

    return {
        "candidate_contract_count": 0,
        "candidate_pair_count": 0,
        "candidate_structure_count": structure_count,
        "expiration_count_with_structures": expirations_with_structures,
    }


def count_iron_butterflies(contracts: list[dict[str, Any]]) -> dict[str, Any]:
    structure_count = 0
    expirations_with_structures = 0

    for expiration, exp_rows in by_expiration(contracts).items():
        calls = [
            c for c in exp_rows
            if c["right"] == "call"
            and liquid_enough(c, max_spread_pct=0.20, min_open_interest=1)
            and c["dte"] is not None
            and 20 <= c["dte"] <= 90
            and c["abs_delta"] is not None
        ]

        puts = [
            c for c in exp_rows
            if c["right"] == "put"
            and liquid_enough(c, max_spread_pct=0.20, min_open_interest=1)
            and c["dte"] is not None
            and 20 <= c["dte"] <= 90
            and c["abs_delta"] is not None
        ]

        call_by_strike = defaultdict(list)
        put_by_strike = defaultdict(list)

        for c in calls:
            call_by_strike[c["strike"]].append(c)
        for p in puts:
            put_by_strike[p["strike"]].append(p)

        local_structures = 0

        for center_strike in sorted(set(call_by_strike) & set(put_by_strike)):
            center_calls = [
                c for c in call_by_strike[center_strike]
                if 0.35 <= c["abs_delta"] <= 0.65
            ]
            center_puts = [
                p for p in put_by_strike[center_strike]
                if 0.35 <= p["abs_delta"] <= 0.65
            ]

            if not center_calls or not center_puts:
                continue

            put_wings = [
                p for p in puts
                if p["strike"] < center_strike
                and 0.02 <= p["abs_delta"] <= 0.35
            ]

            call_wings = [
                c for c in calls
                if c["strike"] > center_strike
                and 0.02 <= c["abs_delta"] <= 0.35
            ]

            local_structures += (
                len(center_calls)
                * len(center_puts)
                * len(put_wings)
                * len(call_wings)
            )

        if local_structures > 0:
            expirations_with_structures += 1

        structure_count += local_structures

    return {
        "candidate_contract_count": 0,
        "candidate_pair_count": 0,
        "candidate_structure_count": structure_count,
        "expiration_count_with_structures": expirations_with_structures,
    }


def count_calendar_or_diagonal(
    contracts: list[dict[str, Any]],
    strategy_name: str,
) -> dict[str, Any]:
    pair_count = 0

    rows = [
        c for c in contracts
        if liquid_enough(c, max_spread_pct=0.20, min_open_interest=1)
        and c["dte"] is not None
        and c["abs_delta"] is not None
        and 0.20 <= c["abs_delta"] <= 0.75
    ]

    by_right_strike = defaultdict(list)
    by_right = defaultdict(list)

    for c in rows:
        by_right_strike[(c["right"], c["strike"])].append(c)
        by_right[c["right"]].append(c)

    if strategy_name == "calendar_spread":
        for key, key_rows in by_right_strike.items():
            near_rows = [c for c in key_rows if 15 <= c["dte"] <= 60]
            far_rows = [c for c in key_rows if 45 <= c["dte"] <= 180]

            pair_count += sum(
                1
                for near in near_rows
                for far in far_rows
                if far["dte"] >= near["dte"] + 14
            )

    else:
        for right, right_rows in by_right.items():
            near_rows = [c for c in right_rows if 15 <= c["dte"] <= 60]
            far_rows = [c for c in right_rows if 45 <= c["dte"] <= 180]

            pair_count += sum(
                1
                for near in near_rows
                for far in far_rows
                if far["dte"] >= near["dte"] + 14
                and far["strike"] != near["strike"]
            )

    return {
        "candidate_contract_count": 0,
        "candidate_pair_count": pair_count,
        "candidate_structure_count": pair_count,
        "expiration_count_with_structures": None,
    }


def availability_for_strategy(
    symbol: str,
    quote_date: str,
    strategy_name: str,
    contracts: list[dict[str, Any]],
) -> dict[str, Any]:
    if strategy_name == "long_call":
        counts = count_long_candidates(contracts, "call")
    elif strategy_name == "long_put":
        counts = count_long_candidates(contracts, "put")
    elif strategy_name in {
        "bull_call_debit_spread",
        "bear_put_debit_spread",
        "put_credit_spread",
        "call_credit_spread",
    }:
        counts = count_vertical_pairs(contracts, strategy_name)
    elif strategy_name == "iron_condor":
        counts = count_iron_condors(contracts)
    elif strategy_name == "iron_butterfly":
        counts = count_iron_butterflies(contracts)
    elif strategy_name in {"calendar_spread", "diagonal_spread"}:
        counts = count_calendar_or_diagonal(contracts, strategy_name)
    else:
        counts = {
            "candidate_contract_count": 0,
            "candidate_pair_count": 0,
            "candidate_structure_count": 0,
        }

    structure_count = int(counts.get("candidate_structure_count") or 0)

    if structure_count > 0:
        availability_state = "available"
    else:
        availability_state = "unavailable"

    return {
        "adapter_type": "strategy_structure_availability_v21_builder",
        "artifact_type": "signalforge_strategy_structure_availability_v21",
        "contract": "strategy_structure_availability_v21",
        "underlying_symbol": symbol,
        "quote_date": quote_date,
        "strategy_name": strategy_name,
        "availability_state": availability_state,
        "is_available": availability_state == "available",
        **counts,
    }


def create_sqlite(contract_features_path: Path, sqlite_path: Path) -> dict[str, Any]:
    if sqlite_path.exists():
        sqlite_path.unlink()

    conn = sqlite3.connect(str(sqlite_path))
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE contracts (
            underlying_symbol TEXT NOT NULL,
            quote_date TEXT NOT NULL,
            option_symbol TEXT NOT NULL,
            right TEXT NOT NULL,
            strike REAL NOT NULL,
            expiration TEXT NOT NULL,
            dte INTEGER NOT NULL,
            abs_delta REAL,
            spread_pct REAL,
            open_interest INTEGER,
            volume INTEGER,
            quote_complete INTEGER,
            greeks_complete INTEGER,
            liquidity_tier TEXT
        )
    """)

    insert_sql = """
        INSERT INTO contracts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    row_count = 0
    batch = []

    for row in read_jsonl(contract_features_path):
        batch.append((
            row["underlying_symbol"],
            row["quote_date"],
            row["option_symbol"],
            row["right"],
            row["strike"],
            row["expiration"],
            row["dte"],
            row.get("abs_delta"),
            row.get("spread_pct"),
            row.get("open_interest"),
            row.get("volume"),
            1 if row.get("quote_complete") else 0,
            1 if row.get("greeks_complete") else 0,
            row.get("liquidity_tier"),
        ))

        row_count += 1

        if len(batch) >= 50000:
            cur.executemany(insert_sql, batch)
            conn.commit()
            batch.clear()

    if batch:
        cur.executemany(insert_sql, batch)
        conn.commit()

    cur.execute("CREATE INDEX idx_contracts_symbol_date ON contracts (underlying_symbol, quote_date)")
    conn.commit()
    conn.close()

    return {
        "sqlite_path": str(sqlite_path),
        "loaded_contract_row_count": row_count,
    }


def rows_from_sqlite(sqlite_path: Path) -> Iterable[dict[str, Any]]:
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("""
        SELECT
            underlying_symbol,
            quote_date,
            option_symbol,
            right,
            strike,
            expiration,
            dte,
            abs_delta,
            spread_pct,
            open_interest,
            volume,
            quote_complete,
            greeks_complete,
            liquidity_tier
        FROM contracts
        ORDER BY underlying_symbol, quote_date, expiration, right, strike, option_symbol
    """)

    for row in cursor:
        yield dict(row)

    conn.close()


def key_for_contract(row: dict[str, Any]) -> tuple[str, str]:
    return row["underlying_symbol"], row["quote_date"]


def build_strategy_structure_availability(
    contract_features_path: Path,
    output_dir: Path,
    keep_sqlite: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    rows_path = output_dir / "signalforge_strategy_structure_availability_v21.jsonl"
    summary_path = output_dir / "signalforge_strategy_structure_availability_v21_summary.json"
    sqlite_path = output_dir / "strategy_structure_availability_v21_source.sqlite"

    load_summary = create_sqlite(contract_features_path, sqlite_path)

    output_row_count = 0
    symbol_dates = set()
    symbols = set()

    strategy_available_counts = Counter()
    strategy_unavailable_counts = Counter()

    with rows_path.open("w", encoding="utf-8", newline="\n") as handle:
        for (symbol, quote_date), group_iter in groupby(rows_from_sqlite(sqlite_path), key_for_contract):
            contracts = list(group_iter)

            symbols.add(symbol)
            symbol_dates.add((symbol, quote_date))

            for strategy_name in STRATEGY_NAMES:
                out = availability_for_strategy(
                    symbol=symbol,
                    quote_date=quote_date,
                    strategy_name=strategy_name,
                    contracts=contracts,
                )

                handle.write(json.dumps(out, sort_keys=True) + "\n")
                output_row_count += 1

                if out["is_available"]:
                    strategy_available_counts[strategy_name] += 1
                else:
                    strategy_unavailable_counts[strategy_name] += 1

    if not keep_sqlite and sqlite_path.exists():
        sqlite_path.unlink()

    expected_output_row_count = len(symbol_dates) * len(STRATEGY_NAMES)

    blockers = []
    if output_row_count != expected_output_row_count:
        blockers.append("output_row_count_mismatch")

    summary = {
        "adapter_type": "strategy_structure_availability_v21_builder",
        "artifact_type": "signalforge_strategy_structure_availability_v21",
        "contract": "strategy_structure_availability_v21",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "contract_features_path": str(contract_features_path),
        "loaded_contract_row_count": load_summary["loaded_contract_row_count"],
        "symbol_count": len(symbols),
        "symbol_date_count": len(symbol_dates),
        "strategy_count": len(STRATEGY_NAMES),
        "output_row_count": output_row_count,
        "expected_output_row_count": expected_output_row_count,
        "strategy_available_counts": dict(sorted(strategy_available_counts.items())),
        "strategy_unavailable_counts": dict(sorted(strategy_unavailable_counts.items())),
        "sqlite_was_kept": keep_sqlite,
        "paths": {
            "rows_path": str(rows_path),
            "summary_path": str(summary_path),
            "sqlite_path": str(sqlite_path) if keep_sqlite else None,
        },
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract-features", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--keep-sqlite", action="store_true")
    args = parser.parse_args()

    summary = build_strategy_structure_availability(
        contract_features_path=Path(args.contract_features),
        output_dir=Path(args.output_dir),
        keep_sqlite=args.keep_sqlite,
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
