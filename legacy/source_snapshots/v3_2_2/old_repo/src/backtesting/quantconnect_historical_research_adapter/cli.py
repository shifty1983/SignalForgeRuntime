from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from src.backtesting.quantconnect_historical_research_adapter.file_writer import (
    write_quantconnect_historical_research_adapter_files,
)


CLI_SUMMARY_SCHEMA_VERSION = "quantconnect_historical_research_adapter_cli_summary.v1"


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        final_summary_operation_result = _read_json(args.final_summary_operation)
    except FileNotFoundError:
        print(
            f"final summary operation file not found: {args.final_summary_operation}",
            file=sys.stderr,
        )
        return 2
    except json.JSONDecodeError as error:
        print(
            f"final summary operation file is not valid JSON: {error}",
            file=sys.stderr,
        )
        return 2

    result = write_quantconnect_historical_research_adapter_files(
        final_summary_operation_result,
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
            "Build historical research input artifacts from a local QuantConnect "
            "review final summary operation JSON. This command writes local files "
            "only and does not call QuantConnect, brokers, market-data APIs, "
            "order-routing systems, live execution systems, fill engines, slippage "
            "engines, or external data warehouses."
        )
    )

    parser.add_argument(
        "--final-summary-operation",
        required=True,
        help="Path to quantconnect_review_final_summary_operation.json.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where historical research adapter artifacts should be written.",
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

    research_input = operation_result.get("research_input")
    research_input = research_input if isinstance(research_input, dict) else {}

    return {
        "schema_version": CLI_SUMMARY_SCHEMA_VERSION,
        "status": result.get("status", "needs_review"),
        "output_dir": result.get("output_dir"),
        "files": result.get("files", {}),
        "file_summary": result.get("file_summary", {}),
        "operation_summary": operation_record.get("summary", {}),
        "health_status": health_report.get("status"),
        "health_recommendations": health_report.get("recommendations", []),
        "historical_research_payload_counts": {
            "ready": len(research_input.get("ready_payloads", []))
            if isinstance(research_input.get("ready_payloads"), list)
            else 0,
            "needs_review": len(research_input.get("needs_review_payloads", []))
            if isinstance(research_input.get("needs_review_payloads"), list)
            else 0,
            "blocked": len(research_input.get("blocked_payloads", []))
            if isinstance(research_input.get("blocked_payloads"), list)
            else 0,
        },
        "warnings": research_input.get("warnings", []),
        "blocked_reasons": research_input.get("blocked_reasons", []),
        "explicit_exclusions": result.get("explicit_exclusions", []),
    }


if __name__ == "__main__":
    raise SystemExit(main())
