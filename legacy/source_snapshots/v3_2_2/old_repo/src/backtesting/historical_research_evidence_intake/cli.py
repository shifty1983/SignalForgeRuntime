from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from src.backtesting.historical_research_evidence_intake.file_writer import (
    write_historical_research_evidence_intake_files,
)


CLI_SUMMARY_SCHEMA_VERSION = "historical_research_evidence_intake_cli_summary.v1"


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

    result = write_historical_research_evidence_intake_files(
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
            "Build normalized historical research evidence intake artifacts from a "
            "local historical research adapter operation JSON. This command writes "
            "local files only and does not call QuantConnect, brokers, market-data "
            "APIs, order-routing systems, live execution systems, fill engines, "
            "slippage engines, or external data warehouses."
        )
    )

    parser.add_argument(
        "--source",
        required=True,
        help="Path to historical research adapter operation JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where evidence intake artifacts should be written.",
    )

    return parser


def _read_json(path: str) -> Any:
    source_path = Path(path)
    with source_path.open(encoding="utf-8") as file:
        return json.load(file)


def _build_cli_summary(result: dict[str, Any]) -> dict[str, Any]:
    operation_result = result.get("operation_result")
    operation_result = operation_result if isinstance(operation_result, dict) else {}

    operation_record = operation_result.get("operation_record")
    operation_record = operation_record if isinstance(operation_record, dict) else {}

    health_report = operation_result.get("health_report")
    health_report = health_report if isinstance(health_report, dict) else {}

    intake_bundle = operation_result.get("intake_bundle")
    intake_bundle = intake_bundle if isinstance(intake_bundle, dict) else {}

    return {
        "schema_version": CLI_SUMMARY_SCHEMA_VERSION,
        "status": result.get("status", "needs_review"),
        "output_dir": result.get("output_dir"),
        "files": result.get("files", {}),
        "file_summary": result.get("file_summary", {}),
        "operation_summary": operation_record.get("summary", {}),
        "health_status": health_report.get("status"),
        "health_recommendations": health_report.get("recommendations", []),
        "evidence_counts": {
            "ready": len(intake_bundle.get("ready_evidence", []))
            if isinstance(intake_bundle.get("ready_evidence"), list)
            else 0,
            "needs_review": len(intake_bundle.get("needs_review_evidence", []))
            if isinstance(intake_bundle.get("needs_review_evidence"), list)
            else 0,
            "blocked": len(intake_bundle.get("blocked_evidence", []))
            if isinstance(intake_bundle.get("blocked_evidence"), list)
            else 0,
        },
        "warnings": intake_bundle.get("warnings", []),
        "blocked_reasons": intake_bundle.get("blocked_reasons", []),
        "explicit_exclusions": result.get("explicit_exclusions", []),
    }


if __name__ == "__main__":
    raise SystemExit(main())
