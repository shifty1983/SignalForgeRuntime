from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from src.backtesting.quantconnect_review_handoff.file_writer import (
    write_quantconnect_review_handoff_files,
)


CLI_SUMMARY_SCHEMA_VERSION = "quantconnect_review_handoff_cli_summary.v1"


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        review_summary_operation_result = _read_json(args.review_summary_operation)
    except FileNotFoundError:
        print(
            f"review summary operation file not found: {args.review_summary_operation}",
            file=sys.stderr,
        )
        return 2
    except json.JSONDecodeError as error:
        print(
            f"review summary operation file is not valid JSON: {error}",
            file=sys.stderr,
        )
        return 2

    result = write_quantconnect_review_handoff_files(
        review_summary_operation_result,
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
            "Build QuantConnect review handoff artifacts from a local review summary "
            "operation JSON. This command writes local files only and does not call "
            "QuantConnect, brokers, market-data APIs, order-routing systems, live "
            "execution systems, fill engines, slippage engines, or external data "
            "warehouses."
        )
    )

    parser.add_argument(
        "--review-summary-operation",
        required=True,
        help="Path to quantconnect_review_summary_operation.json.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where QuantConnect review handoff artifacts should be written.",
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

    handoff_bundle = operation_result.get("handoff_bundle")
    handoff_bundle = handoff_bundle if isinstance(handoff_bundle, dict) else {}

    return {
        "schema_version": CLI_SUMMARY_SCHEMA_VERSION,
        "status": result.get("status", "needs_review"),
        "output_dir": result.get("output_dir"),
        "files": result.get("files", {}),
        "file_summary": result.get("file_summary", {}),
        "operation_summary": operation_record.get("summary", {}),
        "health_status": health_report.get("status"),
        "health_recommendations": health_report.get("recommendations", []),
        "handoff_payload_counts": {
            "ready": len(handoff_bundle.get("ready_payloads", []))
            if isinstance(handoff_bundle.get("ready_payloads"), list)
            else 0,
            "needs_review": len(handoff_bundle.get("needs_review_payloads", []))
            if isinstance(handoff_bundle.get("needs_review_payloads"), list)
            else 0,
            "blocked": len(handoff_bundle.get("blocked_payloads", []))
            if isinstance(handoff_bundle.get("blocked_payloads"), list)
            else 0,
        },
        "explicit_exclusions": result.get("explicit_exclusions", []),
    }


if __name__ == "__main__":
    raise SystemExit(main())
