from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from signalforge.data.seed_bundle import resolve_seed_bundle_root


CANDIDATE_ID = "signalforge_v3_2_2_symbol_regime_walkforward_prune_20230101_20260531"

LEDGER_RELATIVE_PATHS: dict[str, str] = {
    "30k": (
        "artifacts/v3_2_2_symbol_regime_walkforward_prune_stress_v1_20230101_20260531/"
        "v3_2_2_30k/ledger.jsonl"
    ),
    "40k": (
        "artifacts/v3_2_2_symbol_regime_walkforward_prune_stress_v1_20230101_20260531/"
        "v3_2_2_40k/ledger.jsonl"
    ),
}

SKIPPED_ROWS_RELATIVE_PATH = (
    "artifacts/v3_2_2_symbol_regime_walkforward_prune_stress_v1_20230101_20260531/"
    "signalforge_v3_2_2_symbol_regime_walkforward_prune_skipped_rows.jsonl"
)


@dataclass(frozen=True)
class ClosedOutcomeRow:
    symbol: str
    regime_state: str
    strategy: str
    entry_date: str
    close_date: str
    pnl: float
    quantity: float
    capital_label: str
    source_candidate_id: str
    source_row_state: str | None
    source_sequence_id: str | None
    source_trade_key: str | None


@dataclass(frozen=True)
class ClosedOutcomesBootstrapSummary:
    seed_bundle_root: str | None
    output_path: str
    is_ready: bool
    source_ledger_count: int
    source_row_count: int
    written_row_count: int
    skipped_source_row_count: int
    missing_required_field_count: int
    total_pnl_by_capital: dict[str, float]
    written_count_by_capital: dict[str, int]
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


def _is_executed_closed_outcome(row: dict[str, Any]) -> bool:
    if row.get("row_state") == "skipped":
        return False

    if row.get("v3_2_1_action") == "skip_spread_gt_12_5pct":
        return False

    if row.get("skip_reason"):
        return False

    if row.get("selected_outcome_state") not in (None, "complete"):
        return False

    if not row.get("portfolio_realization_date") and not row.get("outcome_availability_date"):
        return False

    return True


def _require_str(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if value is None or value == "":
        raise KeyError(key)
    return str(value)


def _quantity(row: dict[str, Any]) -> float:
    for key in ("contract_quantity", "canonical_locked_quantity", "quantity", "contract_count"):
        value = row.get(key)
        if value is not None:
            return float(value)
    raise KeyError("quantity")


def normalize_ledger_row(row: dict[str, Any], *, capital_label: str) -> ClosedOutcomeRow:
    return ClosedOutcomeRow(
        symbol=_require_str(row, "symbol"),
        regime_state=_require_str(row, "regime_state"),
        strategy=_require_str(row, "selected_strategy"),
        entry_date=_require_str(row, "decision_date"),
        close_date=str(
            row.get("portfolio_realization_date")
            or row.get("outcome_availability_date")
            or row.get("close_date")
        ),
        pnl=float(row.get("realized_pnl_dollars") or 0.0),
        quantity=_quantity(row),
        capital_label=capital_label,
        source_candidate_id=CANDIDATE_ID,
        source_row_state=row.get("row_state"),
        source_sequence_id=row.get("sequence_id"),
        source_trade_key=row.get("trade_key"),
    )


def build_closed_outcomes_bootstrap(
    *,
    seed_bundle: str | Path | None = None,
    output_path: str | Path = "data/runtime/trade_outcomes/closed_trade_outcomes.jsonl",
) -> ClosedOutcomesBootstrapSummary:
    seed_root = resolve_seed_bundle_root(seed_bundle)
    output = Path(output_path)

    blockers: list[str] = []

    if seed_root is None:
        return ClosedOutcomesBootstrapSummary(
            seed_bundle_root=None,
            output_path=str(output),
            is_ready=False,
            source_ledger_count=0,
            source_row_count=0,
            written_row_count=0,
            skipped_source_row_count=0,
            missing_required_field_count=0,
            total_pnl_by_capital={},
            written_count_by_capital={},
            blocker_count=1,
            blockers=("seed_bundle_missing",),
        )

    source_paths: dict[str, Path] = {
        capital_label: seed_root / relative_path
        for capital_label, relative_path in LEDGER_RELATIVE_PATHS.items()
    }

    for capital_label, path in source_paths.items():
        if not path.is_file():
            blockers.append(f"missing_ledger:{capital_label}:{path}")

    if blockers:
        return ClosedOutcomesBootstrapSummary(
            seed_bundle_root=str(seed_root),
            output_path=str(output),
            is_ready=False,
            source_ledger_count=len(source_paths),
            source_row_count=0,
            written_row_count=0,
            skipped_source_row_count=0,
            missing_required_field_count=0,
            total_pnl_by_capital={},
            written_count_by_capital={},
            blocker_count=len(blockers),
            blockers=tuple(blockers),
        )

    normalized_rows: list[ClosedOutcomeRow] = []
    source_row_count = 0
    skipped_source_row_count = 0
    missing_required_field_count = 0

    for capital_label, path in source_paths.items():
        for row in _read_jsonl(path):
            source_row_count += 1

            if not _is_executed_closed_outcome(row):
                skipped_source_row_count += 1
                continue

            try:
                normalized_rows.append(normalize_ledger_row(row, capital_label=capital_label))
            except KeyError:
                missing_required_field_count += 1

    total_pnl_by_capital: dict[str, float] = {}
    written_count_by_capital: dict[str, int] = {}

    for row in normalized_rows:
        total_pnl_by_capital[row.capital_label] = total_pnl_by_capital.get(row.capital_label, 0.0) + row.pnl
        written_count_by_capital[row.capital_label] = written_count_by_capital.get(row.capital_label, 0) + 1

    if not normalized_rows:
        blockers.append("no_executed_closed_outcomes_written")

    if missing_required_field_count:
        blockers.append("one_or_more_rows_missing_required_fields")

    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", encoding="utf-8") as handle:
        for row in normalized_rows:
            handle.write(json.dumps(asdict(row), sort_keys=True) + "\n")

    return ClosedOutcomesBootstrapSummary(
        seed_bundle_root=str(seed_root),
        output_path=str(output),
        is_ready=not blockers,
        source_ledger_count=len(source_paths),
        source_row_count=source_row_count,
        written_row_count=len(normalized_rows),
        skipped_source_row_count=skipped_source_row_count,
        missing_required_field_count=missing_required_field_count,
        total_pnl_by_capital={
            key: round(value, 6)
            for key, value in sorted(total_pnl_by_capital.items())
        },
        written_count_by_capital=dict(sorted(written_count_by_capital.items())),
        blocker_count=len(blockers),
        blockers=tuple(blockers),
    )


def summary_to_dict(summary: ClosedOutcomesBootstrapSummary) -> dict[str, Any]:
    return asdict(summary)


def write_summary(summary: ClosedOutcomesBootstrapSummary, summary_path: str | Path) -> Path:
    path = Path(summary_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True), encoding="utf-8")
    return path


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap normalized closed outcomes from V3.2.2 seed ledgers.")
    parser.add_argument("--seed-bundle", default=None)
    parser.add_argument("--output", default="data/runtime/trade_outcomes/closed_trade_outcomes.jsonl")
    parser.add_argument("--summary-output", default="artifacts/closed_outcomes_bootstrap_summary.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = build_closed_outcomes_bootstrap(
        seed_bundle=args.seed_bundle,
        output_path=args.output,
    )
    write_summary(summary, args.summary_output)

    if args.json:
        print(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True))
    else:
        print(f"is_ready: {summary.is_ready}")
        print(f"source_row_count: {summary.source_row_count}")
        print(f"written_row_count: {summary.written_row_count}")
        print(f"skipped_source_row_count: {summary.skipped_source_row_count}")
        print(f"blocker_count: {summary.blocker_count}")
        print(f"output_path: {summary.output_path}")

    return 0 if summary.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
