from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.backtesting.historical_research_evidence_promotion_handoff.file_writer import (
    write_historical_research_evidence_promotion_handoff_files,
)


CLI_SUMMARY_SCHEMA_VERSION = (
    "historical_research_evidence_promotion_handoff_cli_summary.v1"
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

    result = write_historical_research_evidence_promotion_handoff_files(
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
            "Build downstream-ready historical research evidence promotion "
            "handoff artifacts from a local promotion-gate result JSON. "
            "This command writes local files only and does not call "
            "QuantConnect, brokers, market-data APIs, order-routing systems, "
            "live execution systems, fill engines, slippage engines, or "
            "external data warehouses."
        )
    )

    parser.add_argument(
        "--source",
        required=True,
        help="Path to a historical research evidence promotion-gate result JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where promotion handoff artifacts should be written.",
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

    promotion_handoff = operation_result.get("promotion_handoff")
    promotion_handoff = (
        promotion_handoff
        if isinstance(promotion_handoff, dict)
        else {}
    )

    promoted_items = promotion_handoff.get("promoted_items")
    promoted_items = (
        promoted_items
        if isinstance(promoted_items, list)
        else []
    )

    strategy_ids = promotion_handoff.get("strategy_ids")
    strategy_ids = (
        strategy_ids
        if isinstance(strategy_ids, list)
        else []
    )

    symbols = promotion_handoff.get("symbols")
    symbols = symbols if isinstance(symbols, list) else []

    backtest_ids = promotion_handoff.get("backtest_ids")
    backtest_ids = (
        backtest_ids
        if isinstance(backtest_ids, list)
        else []
    )

    evidence_ids = promotion_handoff.get("evidence_ids")
    evidence_ids = (
        evidence_ids
        if isinstance(evidence_ids, list)
        else []
    )

    handoff_summary = _as_mapping(
        promotion_handoff.get("summary")
    )

    return {
        "schema_version": CLI_SUMMARY_SCHEMA_VERSION,
        "status": result.get("status", "needs_review"),
        "handoff_status": promotion_handoff.get("status"),
        "output_dir": result.get("output_dir"),
        "files": result.get("files", {}),
        "file_summary": result.get("file_summary", {}),
        "operation_summary": operation_record.get("summary", {}),
        "health_status": health_report.get("status"),
        "health_recommendations": health_report.get(
            "recommendations",
            [],
        ),
        "handoff_counts": {
            "promoted_items": len(promoted_items),
            "strategies": len(strategy_ids),
            "symbols": len(symbols),
            "backtests": len(backtest_ids),
            "evidence": len(evidence_ids),
        },
        "can_enter_downstream_historical_research": bool(
            handoff_summary.get(
                "can_enter_downstream_historical_research"
            )
        ),
        "strategy_ids": strategy_ids,
        "symbols": symbols,
        "backtest_ids": backtest_ids,
        "evidence_ids": evidence_ids,
        "warnings": promotion_handoff.get("warnings", []),
        "blocked_reasons": promotion_handoff.get(
            "blocked_reasons",
            [],
        ),
        "explicit_exclusions": result.get(
            "explicit_exclusions",
            [],
        ),
        
    }

def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)

    return {}


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)

    return {}

if __name__ == "__main__":
    raise SystemExit(main())
