from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from signalforge.data.seed_bundle import resolve_seed_bundle_root
from signalforge.rulebooks.prior_symbol_regime_state import (
    PriorSymbolRegimeStats,
    passes_prior_symbol_regime_gate,
)


SKIPPED_ROWS_RELATIVE_PATH = (
    "artifacts/v3_2_2_symbol_regime_walkforward_prune_stress_v1_20230101_20260531/"
    "signalforge_v3_2_2_symbol_regime_walkforward_prune_skipped_rows.jsonl"
)

EXPECTED_SKIP_COUNTS_BY_CAPITAL = {
    "30k": 85,
    "40k": 91,
}


@dataclass(frozen=True)
class PriorGateSkippedRowParitySummary:
    seed_bundle_root: str | None
    skipped_rows_path: str | None
    is_ready: bool
    skipped_row_count: int
    blocked_by_clean_gate_count: int
    mismatch_count: int
    skip_count_by_capital: dict[str, int]
    expected_skip_count_by_capital: dict[str, int]
    expected_count_mismatch_by_capital: dict[str, dict[str, int]]
    skipped_pnl_by_capital: dict[str, float]
    blocker_count: int
    blockers: tuple[str, ...]


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue

            value = json.loads(line)
            if isinstance(value, dict):
                yield value


def _stats_from_skipped_row(row: dict[str, Any]) -> PriorSymbolRegimeStats:
    return PriorSymbolRegimeStats(
        prior_count=int(row["prior_count"]),
        prior_net_pnl=float(row["prior_net_pnl"]),
        prior_profit_factor=float(row["prior_pf"]) if row.get("prior_pf") is not None else None,
    )


def build_prior_gate_skipped_row_parity(
    *,
    seed_bundle: str | Path | None = None,
) -> PriorGateSkippedRowParitySummary:
    seed_root = resolve_seed_bundle_root(seed_bundle)
    blockers: list[str] = []

    if seed_root is None:
        return PriorGateSkippedRowParitySummary(
            seed_bundle_root=None,
            skipped_rows_path=None,
            is_ready=False,
            skipped_row_count=0,
            blocked_by_clean_gate_count=0,
            mismatch_count=0,
            skip_count_by_capital={},
            expected_skip_count_by_capital=dict(EXPECTED_SKIP_COUNTS_BY_CAPITAL),
            expected_count_mismatch_by_capital={},
            skipped_pnl_by_capital={},
            blocker_count=1,
            blockers=("seed_bundle_missing",),
        )

    skipped_path = seed_root / SKIPPED_ROWS_RELATIVE_PATH

    if not skipped_path.is_file():
        return PriorGateSkippedRowParitySummary(
            seed_bundle_root=str(seed_root),
            skipped_rows_path=str(skipped_path),
            is_ready=False,
            skipped_row_count=0,
            blocked_by_clean_gate_count=0,
            mismatch_count=0,
            skip_count_by_capital={},
            expected_skip_count_by_capital=dict(EXPECTED_SKIP_COUNTS_BY_CAPITAL),
            expected_count_mismatch_by_capital={},
            skipped_pnl_by_capital={},
            blocker_count=1,
            blockers=("skipped_rows_file_missing",),
        )

    skipped_row_count = 0
    blocked_by_clean_gate_count = 0
    mismatch_count = 0
    skip_count_by_capital: dict[str, int] = {}
    skipped_pnl_by_capital: dict[str, float] = {}

    for row in _read_jsonl(skipped_path):
        skipped_row_count += 1

        capital_label = str(row["capital_label"])
        skip_count_by_capital[capital_label] = skip_count_by_capital.get(capital_label, 0) + 1
        skipped_pnl_by_capital[capital_label] = skipped_pnl_by_capital.get(capital_label, 0.0) + float(row.get("pnl") or 0.0)

        stats = _stats_from_skipped_row(row)
        passes_gate = passes_prior_symbol_regime_gate(stats)

        if not passes_gate:
            blocked_by_clean_gate_count += 1
        else:
            mismatch_count += 1

    expected_count_mismatch_by_capital: dict[str, dict[str, int]] = {}

    for capital_label, expected_count in EXPECTED_SKIP_COUNTS_BY_CAPITAL.items():
        actual_count = skip_count_by_capital.get(capital_label, 0)
        if actual_count != expected_count:
            expected_count_mismatch_by_capital[capital_label] = {
                "expected": expected_count,
                "actual": actual_count,
            }

    if skipped_row_count == 0:
        blockers.append("no_skipped_rows_found")

    if mismatch_count:
        blockers.append("clean_prior_gate_did_not_block_all_locked_skipped_rows")

    if expected_count_mismatch_by_capital:
        blockers.append("skip_count_by_capital_mismatch")

    rounded_pnl = {
        key: round(value, 6)
        for key, value in sorted(skipped_pnl_by_capital.items())
    }

    return PriorGateSkippedRowParitySummary(
        seed_bundle_root=str(seed_root),
        skipped_rows_path=str(skipped_path),
        is_ready=not blockers,
        skipped_row_count=skipped_row_count,
        blocked_by_clean_gate_count=blocked_by_clean_gate_count,
        mismatch_count=mismatch_count,
        skip_count_by_capital=dict(sorted(skip_count_by_capital.items())),
        expected_skip_count_by_capital=dict(EXPECTED_SKIP_COUNTS_BY_CAPITAL),
        expected_count_mismatch_by_capital=expected_count_mismatch_by_capital,
        skipped_pnl_by_capital=rounded_pnl,
        blocker_count=len(blockers),
        blockers=tuple(blockers),
    )


def summary_to_dict(summary: PriorGateSkippedRowParitySummary) -> dict[str, Any]:
    return asdict(summary)


def write_summary(summary: PriorGateSkippedRowParitySummary, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True), encoding="utf-8")
    return path


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate clean prior gate against locked V3.2.2 skipped rows.")
    parser.add_argument("--seed-bundle", default=None)
    parser.add_argument("--output", default="artifacts/prior_gate_skipped_row_parity_summary.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = build_prior_gate_skipped_row_parity(seed_bundle=args.seed_bundle)
    write_summary(summary, args.output)

    if args.json:
        print(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True))
    else:
        print(f"is_ready: {summary.is_ready}")
        print(f"skipped_row_count: {summary.skipped_row_count}")
        print(f"blocked_by_clean_gate_count: {summary.blocked_by_clean_gate_count}")
        print(f"mismatch_count: {summary.mismatch_count}")
        print(f"blocker_count: {summary.blocker_count}")

    return 0 if summary.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())


