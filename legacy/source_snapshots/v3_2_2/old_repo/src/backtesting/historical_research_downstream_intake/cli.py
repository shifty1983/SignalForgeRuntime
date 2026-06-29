from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.backtesting.historical_research_downstream_intake.file_writer import (
    write_historical_research_downstream_intake_files,
)


CLI_SUMMARY_SCHEMA_VERSION = (
    "historical_research_downstream_intake_cli_summary.v1"
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        source = _read_json(args.source)
    except FileNotFoundError:
        print(f"source file not found: {args.source}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as error:
        print(f"source file is not valid JSON: {error}", file=sys.stderr)
        return 2

    result = write_historical_research_downstream_intake_files(
        source,
        output_dir=args.output_dir,
    )

    summary = _build_cli_summary(result)
    print(json.dumps(summary, indent=2, sort_keys=True))

    if result.get("status") == "blocked":
        return 1

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build downstream historical research intake artifacts from a "
            "local promotion handoff or pipeline operation JSON. This command "
            "writes local files only and does not call QuantConnect, brokers, "
            "market-data APIs, order-routing systems, live execution systems, "
            "fill engines, slippage engines, or external data warehouses."
        )
    )

    parser.add_argument(
        "--source",
        required=True,
        help=(
            "Path to promotion handoff, promotion handoff operation, "
            "or manual pipeline operation JSON."
        ),
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where downstream intake artifacts should be written.",
    )

    return parser


def _read_json(path: str) -> Any:
    source_path = Path(path)

    with source_path.open(encoding="utf-8") as file:
        return json.load(file)


def _build_cli_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    operation_result = result.get("operation_result")
    operation_result = (
        operation_result
        if isinstance(operation_result, dict)
        else {}
    )

    operation_record = operation_result.get("operation_record")
    operation_record = (
        operation_record
        if isinstance(operation_record, dict)
        else {}
    )

    health_report = operation_result.get("health_report")
    health_report = (
        health_report
        if isinstance(health_report, dict)
        else {}
    )

    downstream_intake = operation_result.get("downstream_intake")
    downstream_intake = (
        downstream_intake
        if isinstance(downstream_intake, dict)
        else {}
    )

    intake_summary = _as_mapping(
        downstream_intake.get("summary")
    )

    intake_items = downstream_intake.get("intake_items")
    intake_items = intake_items if isinstance(intake_items, list) else []

    strategy_ids = downstream_intake.get("strategy_ids")
    strategy_ids = strategy_ids if isinstance(strategy_ids, list) else []

    symbols = downstream_intake.get("symbols")
    symbols = symbols if isinstance(symbols, list) else []

    backtest_ids = downstream_intake.get("backtest_ids")
    backtest_ids = backtest_ids if isinstance(backtest_ids, list) else []

    evidence_ids = downstream_intake.get("evidence_ids")
    evidence_ids = evidence_ids if isinstance(evidence_ids, list) else []

    return {
        "schema_version": CLI_SUMMARY_SCHEMA_VERSION,
        "status": result.get("status", "needs_review"),
        "output_dir": result.get("output_dir"),
        "files": result.get("files", {}),
        "file_summary": result.get("file_summary", {}),
        "operation_summary": operation_record.get("summary", {}),
        "health_status": health_report.get("status"),
        "health_recommendations": health_report.get(
            "recommendations",
            [],
        ),
        "intake_status": downstream_intake.get("status"),
        "intake_counts": {
            "items": len(intake_items),
            "strategies": len(strategy_ids),
            "symbols": len(symbols),
            "backtests": len(backtest_ids),
            "evidence": len(evidence_ids),
        },
        "can_enter_expected_value_research": bool(
            intake_summary.get("can_enter_expected_value_research")
        ),
        "can_enter_strategy_selection": bool(
            intake_summary.get("can_enter_strategy_selection")
        ),
        "strategy_ids": strategy_ids,
        "symbols": symbols,
        "backtest_ids": backtest_ids,
        "evidence_ids": evidence_ids,
        "warnings": downstream_intake.get("warnings", []),
        "blocked_reasons": downstream_intake.get("blocked_reasons", []),
        "explicit_exclusions": result.get("explicit_exclusions", []),
    }


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)

    return {}


if __name__ == "__main__":
    raise SystemExit(main())
