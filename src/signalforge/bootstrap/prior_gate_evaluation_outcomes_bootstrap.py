from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from signalforge.data.seed_bundle import resolve_seed_bundle_root
from signalforge.bootstrap.prior_gate_skipped_row_parity import SKIPPED_ROWS_RELATIVE_PATH


DEFAULT_CLOSED_OUTCOMES = "data/runtime/trade_outcomes/closed_trade_outcomes.jsonl"
DEFAULT_OUTPUT = "data/runtime/rule_state/v3_2_2_prior_gate_evaluation_outcomes.jsonl"


@dataclass(frozen=True)
class PriorGateEvaluationOutcomesBootstrapSummary:
    seed_bundle_root: str | None
    closed_outcomes_path: str
    skipped_rows_path: str | None
    output_path: str
    is_ready: bool
    executed_outcome_count: int
    shadow_skipped_outcome_count: int
    evaluation_outcome_count: int
    evaluation_count_by_capital: dict[str, int]
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


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _normalize_executed_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "capital_label": str(row["capital_label"]),
        "symbol": str(row["symbol"]),
        "regime_state": str(row["regime_state"]),
        "strategy": str(row["strategy"]),
        "entry_date": str(row["entry_date"]),
        "close_date": str(row["close_date"]),
        "pnl": float(row.get("pnl") or 0.0),
        "quantity": float(row.get("quantity") or 0.0),
        "outcome_role": "executed_closed_trade",
        "source_candidate_id": row.get("source_candidate_id"),
        "source_sequence_id": row.get("source_sequence_id"),
        "source_trade_key": row.get("source_trade_key"),
    }


def _normalize_shadow_skipped_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "capital_label": str(row["capital_label"]),
        "symbol": str(row["symbol"]),
        "regime_state": str(row["regime"]),
        "strategy": str(row["strategy"]),
        "entry_date": str(row["entry_date"]),
        "close_date": str(row["close_date"]),
        "pnl": float(row.get("pnl") or 0.0),
        "quantity": float(row.get("quantity") or 0.0),
        "outcome_role": "v3_2_2_prior_gate_shadow_skipped",
        "source_row_index": row.get("row_index"),
        "source_prior_count": row.get("prior_count"),
        "source_prior_net_pnl": row.get("prior_net_pnl"),
        "source_prior_pf": row.get("prior_pf"),
        "source_prior_win_rate": row.get("prior_win_rate"),
    }


def build_prior_gate_evaluation_outcomes_bootstrap(
    *,
    seed_bundle: str | Path | None = None,
    closed_outcomes_path: str | Path = DEFAULT_CLOSED_OUTCOMES,
    output_path: str | Path = DEFAULT_OUTPUT,
) -> PriorGateEvaluationOutcomesBootstrapSummary:
    seed_root = resolve_seed_bundle_root(seed_bundle)
    closed_path = Path(closed_outcomes_path)
    output = Path(output_path)

    blockers: list[str] = []

    if seed_root is None:
        blockers.append("seed_bundle_missing")

    if not closed_path.is_file():
        blockers.append("closed_outcomes_missing")

    skipped_path: Path | None = None

    if seed_root is not None:
        skipped_path = seed_root / SKIPPED_ROWS_RELATIVE_PATH
        if not skipped_path.is_file():
            blockers.append("skipped_rows_missing")

    if blockers:
        return PriorGateEvaluationOutcomesBootstrapSummary(
            seed_bundle_root=str(seed_root) if seed_root else None,
            closed_outcomes_path=str(closed_path),
            skipped_rows_path=str(skipped_path) if skipped_path else None,
            output_path=str(output),
            is_ready=False,
            executed_outcome_count=0,
            shadow_skipped_outcome_count=0,
            evaluation_outcome_count=0,
            evaluation_count_by_capital={},
            blocker_count=len(blockers),
            blockers=tuple(blockers),
        )

    executed_rows = [_normalize_executed_row(row) for row in _read_jsonl(closed_path)]
    shadow_rows = [_normalize_shadow_skipped_row(row) for row in _read_jsonl(skipped_path)]

    evaluation_rows = executed_rows + shadow_rows
    evaluation_rows.sort(
        key=lambda row: (
            row["capital_label"],
            row["close_date"],
            row["entry_date"],
            row["symbol"],
            row["regime_state"],
            row["strategy"],
            row["outcome_role"],
        )
    )

    count_by_capital: dict[str, int] = {}

    for row in evaluation_rows:
        capital_label = row["capital_label"]
        count_by_capital[capital_label] = count_by_capital.get(capital_label, 0) + 1

    if not evaluation_rows:
        blockers.append("no_evaluation_outcomes_written")

    _write_jsonl(output, evaluation_rows)

    return PriorGateEvaluationOutcomesBootstrapSummary(
        seed_bundle_root=str(seed_root),
        closed_outcomes_path=str(closed_path),
        skipped_rows_path=str(skipped_path),
        output_path=str(output),
        is_ready=not blockers,
        executed_outcome_count=len(executed_rows),
        shadow_skipped_outcome_count=len(shadow_rows),
        evaluation_outcome_count=len(evaluation_rows),
        evaluation_count_by_capital=dict(sorted(count_by_capital.items())),
        blocker_count=len(blockers),
        blockers=tuple(blockers),
    )


def summary_to_dict(summary: PriorGateEvaluationOutcomesBootstrapSummary) -> dict[str, Any]:
    return asdict(summary)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap V3.2.2 prior-gate evaluation outcomes.")
    parser.add_argument("--seed-bundle", default=None)
    parser.add_argument("--closed-outcomes", default=DEFAULT_CLOSED_OUTCOMES)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-output", default="artifacts/prior_gate_evaluation_outcomes_bootstrap_summary.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = build_prior_gate_evaluation_outcomes_bootstrap(
        seed_bundle=args.seed_bundle,
        closed_outcomes_path=args.closed_outcomes,
        output_path=args.output,
    )

    summary_path = Path(args.summary_output)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True), encoding="utf-8")

    if args.json:
        print(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True))
    else:
        print(f"is_ready: {summary.is_ready}")
        print(f"executed_outcome_count: {summary.executed_outcome_count}")
        print(f"shadow_skipped_outcome_count: {summary.shadow_skipped_outcome_count}")
        print(f"evaluation_outcome_count: {summary.evaluation_outcome_count}")
        print(f"blocker_count: {summary.blocker_count}")

    return 0 if summary.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())

