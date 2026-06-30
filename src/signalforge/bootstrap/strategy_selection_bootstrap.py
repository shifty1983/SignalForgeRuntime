from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from signalforge.data.seed_bundle import resolve_seed_bundle_root


STRATEGY_SELECTION_SOURCE_RELATIVE_PATH = (
    "artifacts/historical_strategy_selection_rows_20210601_20260531/"
    "signalforge_historical_strategy_selection_rows.jsonl"
)

STRATEGY_SELECTION_SUMMARY_RELATIVE_PATH = (
    "artifacts/historical_strategy_selection_rows_20210601_20260531/"
    "signalforge_historical_strategy_selection_rows_summary.json"
)

DECISION_ROWS_SOURCE_RELATIVE_PATH = (
    "artifacts/historical_decision_rows_20210601_20260531/"
    "signalforge_historical_decision_rows.jsonl"
)

DEFAULT_OUTPUT = "data/runtime/strategy_selection/strategy_selection_latest_snapshot.json"


@dataclass(frozen=True)
class StrategySelectionBootstrapSummary:
    seed_bundle_root: str | None
    strategy_selection_source_path: str | None
    strategy_selection_summary_path: str | None
    decision_rows_source_path: str | None
    output_path: str
    is_ready: bool
    source_is_ready: bool | None
    source_row_count: int
    decision_row_count: int
    joined_row_count: int
    latest_decision_date: str | None
    latest_row_count: int
    symbol_count: int
    selected_row_count: int
    no_trade_row_count: int
    selected_strategy_count: int
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


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))

    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")

    return value


def _counter(items: Iterable[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(item.get(key)) for item in items if item.get(key) is not None).items()))


def _nested_state(row: dict[str, Any], key: str) -> Any:
    value = row.get(key)

    if not isinstance(value, dict):
        return None

    return value.get("state")


def _nested_source_date(row: dict[str, Any], key: str) -> Any:
    value = row.get(key)

    if not isinstance(value, dict):
        return None

    return value.get("source_date")


def _nested_source_state(row: dict[str, Any], key: str) -> Any:
    value = row.get(key)

    if not isinstance(value, dict):
        return None

    return value.get("source_state")


def _normalize_row(selection_row: dict[str, Any], decision_row: dict[str, Any] | None) -> dict[str, Any]:
    decision_row = decision_row or {}
    eligibility = decision_row.get("eligibility") if isinstance(decision_row.get("eligibility"), dict) else {}

    return {
        "decision_row_id": selection_row.get("decision_row_id"),
        "decision_date": selection_row.get("decision_date") or selection_row.get("date"),
        "symbol": selection_row.get("symbol"),
        "selection_state": selection_row.get("selection_state"),
        "selection_reason": selection_row.get("selection_reason"),
        "candidate_count": selection_row.get("candidate_count"),
        "selectable_candidate_count": selection_row.get("selectable_candidate_count"),
        "rejected_candidate_count": selection_row.get("rejected_candidate_count"),
        "minimum_sample_count": selection_row.get("minimum_sample_count"),
        "selected_candidate_id": selection_row.get("selected_candidate_id"),
        "selected_strategy": selection_row.get("selected_strategy"),
        "selected_strategy_instance": selection_row.get("selected_strategy_instance"),
        "selected_expectancy_score": selection_row.get("selected_expectancy_score"),
        "selected_expectancy_average_return": selection_row.get("selected_expectancy_average_return"),
        "selected_expectancy_sample_count": selection_row.get("selected_expectancy_sample_count"),
        "selected_expectancy_state": selection_row.get("selected_expectancy_state"),
        "selected_outcome_state": selection_row.get("selected_outcome_state"),
        "blocked_reason_counts": selection_row.get("blocked_reason_counts") or {},
        "rejected_expectancy_state_counts": selection_row.get("rejected_expectancy_state_counts") or {},
        "rejected_strategy_counts": selection_row.get("rejected_strategy_counts") or {},
        "selection_uses_current_row_outcome": bool(selection_row.get("selection_uses_current_row_outcome")),
        "selection_uses_future_rows": bool(selection_row.get("selection_uses_future_rows")),
        "selection_uses_realized_outcome": bool(selection_row.get("selection_uses_realized_outcome")),
        "regime_state": _nested_state(decision_row, "regime"),
        "regime_source_date": _nested_source_date(decision_row, "regime"),
        "regime_source_state": _nested_source_state(decision_row, "regime"),
        "asset_behavior_state": _nested_state(decision_row, "asset_behavior"),
        "asset_behavior_source_date": _nested_source_date(decision_row, "asset_behavior"),
        "asset_behavior_source_state": _nested_source_state(decision_row, "asset_behavior"),
        "option_behavior_state": _nested_state(decision_row, "option_behavior"),
        "option_behavior_source_date": _nested_source_date(decision_row, "option_behavior"),
        "option_behavior_source_state": _nested_source_state(decision_row, "option_behavior"),
        "eligible_for_strategy_selection": eligibility.get("eligible_for_strategy_selection"),
        "eligible_for_option_strategy_selection": eligibility.get("eligible_for_option_strategy_selection"),
        "eligible_for_option_decision": eligibility.get("eligible_for_option_decision"),
        "is_tradable": eligibility.get("is_tradable"),
        "data_state": decision_row.get("data_state"),
        "decision_blocks": decision_row.get("blocks") or [],
        "source_selection_row": selection_row,
        "source_decision_row": decision_row,
    }


def _latest_rows_by_symbol(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}

    for row in rows:
        symbol = row.get("symbol")
        decision_date = row.get("decision_date")

        if not symbol or not decision_date:
            continue

        current = latest.get(str(symbol))

        if current is None or str(decision_date) > str(current.get("decision_date") or ""):
            latest[str(symbol)] = row

    return sorted(latest.values(), key=lambda row: str(row.get("symbol") or ""))


def build_strategy_selection_bootstrap(
    *,
    seed_bundle: str | Path | None = None,
    output_path: str | Path = DEFAULT_OUTPUT,
) -> StrategySelectionBootstrapSummary:
    seed_root = resolve_seed_bundle_root(seed_bundle)
    output = Path(output_path)

    if seed_root is None:
        return StrategySelectionBootstrapSummary(
            seed_bundle_root=None,
            strategy_selection_source_path=None,
            strategy_selection_summary_path=None,
            decision_rows_source_path=None,
            output_path=str(output),
            is_ready=False,
            source_is_ready=None,
            source_row_count=0,
            decision_row_count=0,
            joined_row_count=0,
            latest_decision_date=None,
            latest_row_count=0,
            symbol_count=0,
            selected_row_count=0,
            no_trade_row_count=0,
            selected_strategy_count=0,
            blocker_count=1,
            blockers=("seed_bundle_missing",),
        )

    strategy_source = seed_root / STRATEGY_SELECTION_SOURCE_RELATIVE_PATH
    strategy_summary_source = seed_root / STRATEGY_SELECTION_SUMMARY_RELATIVE_PATH
    decision_source = seed_root / DECISION_ROWS_SOURCE_RELATIVE_PATH

    blockers: list[str] = []

    if not strategy_source.is_file():
        blockers.append("strategy_selection_source_missing")

    if not strategy_summary_source.is_file():
        blockers.append("strategy_selection_summary_missing")

    if not decision_source.is_file():
        blockers.append("decision_rows_source_missing")

    if blockers:
        return StrategySelectionBootstrapSummary(
            seed_bundle_root=str(seed_root),
            strategy_selection_source_path=str(strategy_source),
            strategy_selection_summary_path=str(strategy_summary_source),
            decision_rows_source_path=str(decision_source),
            output_path=str(output),
            is_ready=False,
            source_is_ready=None,
            source_row_count=0,
            decision_row_count=0,
            joined_row_count=0,
            latest_decision_date=None,
            latest_row_count=0,
            symbol_count=0,
            selected_row_count=0,
            no_trade_row_count=0,
            selected_strategy_count=0,
            blocker_count=len(blockers),
            blockers=tuple(blockers),
        )

    source_summary = _load_json(strategy_summary_source)

    if not source_summary.get("is_ready"):
        blockers.append("strategy_selection_summary_not_ready")

    decision_rows_by_id: dict[str, dict[str, Any]] = {}
    decision_row_count = 0

    for decision_row in _read_jsonl(decision_source):
        decision_row_count += 1
        decision_row_id = decision_row.get("decision_row_id")

        if decision_row_id:
            decision_rows_by_id[str(decision_row_id)] = decision_row

    normalized_rows: list[dict[str, Any]] = []
    source_row_count = 0
    joined_row_count = 0

    for selection_row in _read_jsonl(strategy_source):
        source_row_count += 1
        decision_row_id = selection_row.get("decision_row_id")
        decision_row = decision_rows_by_id.get(str(decision_row_id)) if decision_row_id else None

        if decision_row is not None:
            joined_row_count += 1

        normalized_rows.append(_normalize_row(selection_row, decision_row))

    if not normalized_rows:
        blockers.append("no_strategy_selection_rows")

    if joined_row_count != len(normalized_rows):
        blockers.append("one_or_more_strategy_rows_missing_decision_join")

    latest_rows = _latest_rows_by_symbol(normalized_rows)
    latest_decision_date = max((str(row.get("decision_date")) for row in latest_rows if row.get("decision_date")), default=None)

    selected_rows = [row for row in normalized_rows if row.get("selection_state") == "selected"]
    no_trade_rows = [row for row in normalized_rows if row.get("selection_state") == "no_trade"]

    snapshot = {
        "contract": "strategy_selection_latest_snapshot",
        "strategy_selection_source": STRATEGY_SELECTION_SOURCE_RELATIVE_PATH,
        "strategy_selection_summary_source": STRATEGY_SELECTION_SUMMARY_RELATIVE_PATH,
        "decision_rows_source": DECISION_ROWS_SOURCE_RELATIVE_PATH,
        "source_artifact_type": source_summary.get("artifact_type"),
        "source_is_ready": source_summary.get("is_ready"),
        "source_row_count": source_row_count,
        "decision_row_count": decision_row_count,
        "joined_row_count": joined_row_count,
        "latest_decision_date": latest_decision_date,
        "latest_row_count": len(latest_rows),
        "symbol_count": len({str(row.get("symbol")) for row in normalized_rows if row.get("symbol")}),
        "selected_row_count": len(selected_rows),
        "no_trade_row_count": len(no_trade_rows),
        "selected_strategy_count": len({str(row.get("selected_strategy")) for row in selected_rows if row.get("selected_strategy")}),
        "selection_state_counts": _counter(normalized_rows, "selection_state"),
        "selected_strategy_counts": _counter(selected_rows, "selected_strategy"),
        "selected_expectancy_state_counts": _counter(selected_rows, "selected_expectancy_state"),
        "regime_state_counts": _counter(normalized_rows, "regime_state"),
        "asset_behavior_state_counts": _counter(normalized_rows, "asset_behavior_state"),
        "option_behavior_state_counts": _counter(normalized_rows, "option_behavior_state"),
        "latest_rows": latest_rows,
        "latest_rows_by_symbol": {
            str(row["symbol"]): row
            for row in latest_rows
            if row.get("symbol")
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")

    return StrategySelectionBootstrapSummary(
        seed_bundle_root=str(seed_root),
        strategy_selection_source_path=str(strategy_source),
        strategy_selection_summary_path=str(strategy_summary_source),
        decision_rows_source_path=str(decision_source),
        output_path=str(output),
        is_ready=not blockers,
        source_is_ready=bool(source_summary.get("is_ready")),
        source_row_count=source_row_count,
        decision_row_count=decision_row_count,
        joined_row_count=joined_row_count,
        latest_decision_date=latest_decision_date,
        latest_row_count=len(latest_rows),
        symbol_count=snapshot["symbol_count"],
        selected_row_count=len(selected_rows),
        no_trade_row_count=len(no_trade_rows),
        selected_strategy_count=snapshot["selected_strategy_count"],
        blocker_count=len(blockers),
        blockers=tuple(blockers),
    )


def summary_to_dict(summary: StrategySelectionBootstrapSummary) -> dict[str, Any]:
    return asdict(summary)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap runtime strategy selection snapshot.")
    parser.add_argument("--seed-bundle", default=None)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-output", default="artifacts/strategy_selection_bootstrap_summary.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = build_strategy_selection_bootstrap(seed_bundle=args.seed_bundle, output_path=args.output)

    summary_path = Path(args.summary_output)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True), encoding="utf-8")

    if args.json:
        print(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True))
    else:
        print(f"is_ready: {summary.is_ready}")
        print(f"source_row_count: {summary.source_row_count}")
        print(f"decision_row_count: {summary.decision_row_count}")
        print(f"joined_row_count: {summary.joined_row_count}")
        print(f"latest_decision_date: {summary.latest_decision_date}")
        print(f"latest_row_count: {summary.latest_row_count}")
        print(f"symbol_count: {summary.symbol_count}")
        print(f"selected_row_count: {summary.selected_row_count}")
        print(f"no_trade_row_count: {summary.no_trade_row_count}")
        print(f"selected_strategy_count: {summary.selected_strategy_count}")
        print(f"blocker_count: {summary.blocker_count}")

    return 0 if summary.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())




