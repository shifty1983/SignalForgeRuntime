from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from signalforge.data.seed_bundle import resolve_seed_bundle_root
from signalforge.rulebooks.prior_symbol_regime_state import (
    PriorSymbolRegimeStats,
    passes_prior_symbol_regime_gate,
)


DEFAULT_CLOSED_OUTCOMES = "data/runtime/trade_outcomes/closed_trade_outcomes.jsonl"

SKIPPED_ROWS_RELATIVE_PATH = (
    "artifacts/v3_2_2_symbol_regime_walkforward_prune_stress_v1_20230101_20260531/"
    "signalforge_v3_2_2_symbol_regime_walkforward_prune_skipped_rows.jsonl"
)

EXPECTED_SKIP_COUNTS_BY_CAPITAL = {
    "30k": 85,
    "40k": 91,
}

NET_PNL_TOLERANCE = 0.0001
PF_TOLERANCE = 0.0001
WIN_RATE_TOLERANCE = 0.0001


@dataclass(frozen=True)
class PriorGateAsofMismatch:
    capital_label: str
    symbol: str
    regime_state: str
    entry_date: str
    mismatch_reasons: tuple[str, ...]
    expected_prior_count: int
    actual_prior_count: int
    expected_prior_net_pnl: float
    actual_prior_net_pnl: float
    expected_prior_pf: float | None
    actual_prior_pf: float | None
    expected_prior_win_rate: float
    actual_prior_win_rate: float
    clean_gate_blocks: bool


@dataclass(frozen=True)
class PriorGateAsofParitySummary:
    seed_bundle_root: str | None
    closed_outcomes_path: str
    skipped_rows_path: str | None
    is_ready: bool
    closed_outcome_row_count: int
    skipped_row_count: int
    matched_row_count: int
    mismatch_count: int
    clean_gate_block_count: int
    skip_count_by_capital: dict[str, int]
    expected_skip_count_by_capital: dict[str, int]
    expected_count_mismatch_by_capital: dict[str, dict[str, int]]
    blocker_count: int
    blockers: tuple[str, ...]
    mismatch_samples: tuple[PriorGateAsofMismatch, ...]


def _parse_date(value: str | None) -> date:
    if not value:
        raise ValueError("missing_date")
    return date.fromisoformat(str(value)[:10])


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue

            value = json.loads(line)
            if isinstance(value, dict):
                yield value


def _profit_factor(gross_profit: float, gross_loss_abs: float) -> float | None:
    if gross_loss_abs == 0:
        if gross_profit > 0:
            return None
        return 0.0
    return gross_profit / gross_loss_abs


def _win_rate(pnls: list[float]) -> float:
    if not pnls:
        return 0.0
    return sum(1 for pnl in pnls if pnl > 0) / len(pnls)


def _asof_stats(
    *,
    closed_rows: list[dict[str, Any]],
    capital_label: str,
    symbol: str,
    regime_state: str,
    entry_date: date,
) -> tuple[PriorSymbolRegimeStats, float]:
    pnls: list[float] = []

    for row in closed_rows:
        if str(row.get("capital_label")) != capital_label:
            continue
        if str(row.get("symbol")) != symbol:
            continue
        if str(row.get("regime_state")) != regime_state:
            continue

        close_date = _parse_date(row.get("close_date"))
        if close_date >= entry_date:
            continue

        pnls.append(float(row.get("pnl") or 0.0))

    gross_profit = sum(pnl for pnl in pnls if pnl > 0)
    gross_loss_abs = abs(sum(pnl for pnl in pnls if pnl < 0))
    prior_net_pnl = sum(pnls)
    prior_pf = _profit_factor(gross_profit, gross_loss_abs)

    return (
        PriorSymbolRegimeStats(
            prior_count=len(pnls),
            prior_net_pnl=prior_net_pnl,
            prior_profit_factor=prior_pf,
        ),
        _win_rate(pnls),
    )


def _float_close(left: float | None, right: float | None, tolerance: float) -> bool:
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    return abs(float(left) - float(right)) <= tolerance


def build_prior_gate_asof_parity(
    *,
    seed_bundle: str | Path | None = None,
    closed_outcomes_path: str | Path = DEFAULT_CLOSED_OUTCOMES,
    mismatch_sample_limit: int = 25,
) -> PriorGateAsofParitySummary:
    seed_root = resolve_seed_bundle_root(seed_bundle)
    closed_path = Path(closed_outcomes_path)
    blockers: list[str] = []

    if seed_root is None:
        blockers.append("seed_bundle_missing")

    if not closed_path.is_file():
        blockers.append("closed_outcomes_missing")

    if blockers:
        return PriorGateAsofParitySummary(
            seed_bundle_root=str(seed_root) if seed_root else None,
            closed_outcomes_path=str(closed_path),
            skipped_rows_path=None,
            is_ready=False,
            closed_outcome_row_count=0,
            skipped_row_count=0,
            matched_row_count=0,
            mismatch_count=0,
            clean_gate_block_count=0,
            skip_count_by_capital={},
            expected_skip_count_by_capital=dict(EXPECTED_SKIP_COUNTS_BY_CAPITAL),
            expected_count_mismatch_by_capital={},
            blocker_count=len(blockers),
            blockers=tuple(blockers),
            mismatch_samples=tuple(),
        )

    skipped_path = seed_root / SKIPPED_ROWS_RELATIVE_PATH

    if not skipped_path.is_file():
        return PriorGateAsofParitySummary(
            seed_bundle_root=str(seed_root),
            closed_outcomes_path=str(closed_path),
            skipped_rows_path=str(skipped_path),
            is_ready=False,
            closed_outcome_row_count=0,
            skipped_row_count=0,
            matched_row_count=0,
            mismatch_count=0,
            clean_gate_block_count=0,
            skip_count_by_capital={},
            expected_skip_count_by_capital=dict(EXPECTED_SKIP_COUNTS_BY_CAPITAL),
            expected_count_mismatch_by_capital={},
            blocker_count=1,
            blockers=("skipped_rows_missing",),
            mismatch_samples=tuple(),
        )

    closed_rows = list(_read_jsonl(closed_path))
    skipped_rows = list(_read_jsonl(skipped_path))

    skip_count_by_capital: dict[str, int] = {}
    mismatch_samples: list[PriorGateAsofMismatch] = []
    mismatch_count = 0
    matched_row_count = 0
    clean_gate_block_count = 0

    for skipped_row in skipped_rows:
        capital_label = str(skipped_row["capital_label"])
        symbol = str(skipped_row["symbol"])
        regime_state = str(skipped_row["regime"])
        entry_date_raw = str(skipped_row["entry_date"])
        entry_date = _parse_date(entry_date_raw)

        skip_count_by_capital[capital_label] = skip_count_by_capital.get(capital_label, 0) + 1

        actual_stats, actual_win_rate = _asof_stats(
            closed_rows=closed_rows,
            capital_label=capital_label,
            symbol=symbol,
            regime_state=regime_state,
            entry_date=entry_date,
        )

        expected_count = int(skipped_row["prior_count"])
        expected_net_pnl = float(skipped_row["prior_net_pnl"])
        expected_pf = float(skipped_row["prior_pf"]) if skipped_row.get("prior_pf") is not None else None
        expected_win_rate = float(skipped_row.get("prior_win_rate") or 0.0)

        clean_gate_blocks = not passes_prior_symbol_regime_gate(actual_stats)
        if clean_gate_blocks:
            clean_gate_block_count += 1

        reasons: list[str] = []

        if actual_stats.prior_count != expected_count:
            reasons.append("prior_count_mismatch")

        if not _float_close(actual_stats.prior_net_pnl, expected_net_pnl, NET_PNL_TOLERANCE):
            reasons.append("prior_net_pnl_mismatch")

        if not _float_close(actual_stats.prior_profit_factor, expected_pf, PF_TOLERANCE):
            reasons.append("prior_pf_mismatch")

        if not _float_close(actual_win_rate, expected_win_rate, WIN_RATE_TOLERANCE):
            reasons.append("prior_win_rate_mismatch")

        if not clean_gate_blocks:
            reasons.append("clean_gate_did_not_block")

        if reasons:
            mismatch_count += 1

            if len(mismatch_samples) < mismatch_sample_limit:
                mismatch_samples.append(
                    PriorGateAsofMismatch(
                        capital_label=capital_label,
                        symbol=symbol,
                        regime_state=regime_state,
                        entry_date=entry_date_raw,
                        mismatch_reasons=tuple(reasons),
                        expected_prior_count=expected_count,
                        actual_prior_count=actual_stats.prior_count,
                        expected_prior_net_pnl=round(expected_net_pnl, 6),
                        actual_prior_net_pnl=round(actual_stats.prior_net_pnl, 6),
                        expected_prior_pf=None if expected_pf is None else round(expected_pf, 6),
                        actual_prior_pf=None
                        if actual_stats.prior_profit_factor is None
                        else round(actual_stats.prior_profit_factor, 6),
                        expected_prior_win_rate=round(expected_win_rate, 6),
                        actual_prior_win_rate=round(actual_win_rate, 6),
                        clean_gate_blocks=clean_gate_blocks,
                    )
                )
        else:
            matched_row_count += 1

    expected_count_mismatch_by_capital: dict[str, dict[str, int]] = {}

    for capital_label, expected_count in EXPECTED_SKIP_COUNTS_BY_CAPITAL.items():
        actual_count = skip_count_by_capital.get(capital_label, 0)
        if actual_count != expected_count:
            expected_count_mismatch_by_capital[capital_label] = {
                "expected": expected_count,
                "actual": actual_count,
            }

    if not closed_rows:
        blockers.append("closed_outcomes_empty")

    if not skipped_rows:
        blockers.append("skipped_rows_empty")

    if mismatch_count:
        blockers.append("asof_prior_stats_mismatch")

    if expected_count_mismatch_by_capital:
        blockers.append("skip_count_by_capital_mismatch")

    return PriorGateAsofParitySummary(
        seed_bundle_root=str(seed_root),
        closed_outcomes_path=str(closed_path),
        skipped_rows_path=str(skipped_path),
        is_ready=not blockers,
        closed_outcome_row_count=len(closed_rows),
        skipped_row_count=len(skipped_rows),
        matched_row_count=matched_row_count,
        mismatch_count=mismatch_count,
        clean_gate_block_count=clean_gate_block_count,
        skip_count_by_capital=dict(sorted(skip_count_by_capital.items())),
        expected_skip_count_by_capital=dict(EXPECTED_SKIP_COUNTS_BY_CAPITAL),
        expected_count_mismatch_by_capital=expected_count_mismatch_by_capital,
        blocker_count=len(blockers),
        blockers=tuple(blockers),
        mismatch_samples=tuple(mismatch_samples),
    )


def summary_to_dict(summary: PriorGateAsofParitySummary) -> dict[str, Any]:
    return asdict(summary)


def write_summary(summary: PriorGateAsofParitySummary, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True), encoding="utf-8")
    return path


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate as-of V3.2.2 prior symbol/regime stats.")
    parser.add_argument("--seed-bundle", default=None)
    parser.add_argument("--closed-outcomes", default=DEFAULT_CLOSED_OUTCOMES)
    parser.add_argument("--output", default="artifacts/prior_gate_asof_parity_summary.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = build_prior_gate_asof_parity(
        seed_bundle=args.seed_bundle,
        closed_outcomes_path=args.closed_outcomes,
    )
    write_summary(summary, args.output)

    if args.json:
        print(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True))
    else:
        print(f"is_ready: {summary.is_ready}")
        print(f"closed_outcome_row_count: {summary.closed_outcome_row_count}")
        print(f"skipped_row_count: {summary.skipped_row_count}")
        print(f"matched_row_count: {summary.matched_row_count}")
        print(f"mismatch_count: {summary.mismatch_count}")
        print(f"clean_gate_block_count: {summary.clean_gate_block_count}")
        print(f"blocker_count: {summary.blocker_count}")

    return 0 if summary.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
