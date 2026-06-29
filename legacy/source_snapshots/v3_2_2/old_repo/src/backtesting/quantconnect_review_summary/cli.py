from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from src.backtesting.quantconnect_review_summary.file_writer import (
    write_quantconnect_review_summary_files,
)


CLI_SUMMARY_SCHEMA_VERSION = "quantconnect_review_summary_cli_summary.v1"


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        export_operation_result = _read_json(args.export_operation)
    except FileNotFoundError:
        print(f"export operation file not found: {args.export_operation}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as error:
        print(f"export operation file is not valid JSON: {error}", file=sys.stderr)
        return 2

    try:
        result_import_operation_result = _read_json(args.result_import_operation)
    except FileNotFoundError:
        print(
            f"result import operation file not found: {args.result_import_operation}",
            file=sys.stderr,
        )
        return 2
    except json.JSONDecodeError as error:
        print(
            f"result import operation file is not valid JSON: {error}",
            file=sys.stderr,
        )
        return 2

    result = write_quantconnect_review_summary_files(
        export_operation_result,
        result_import_operation_result,
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
            "Build QuantConnect review summary artifacts from a local export "
            "operation JSON and a local result-import operation JSON. This command "
            "writes local files only and does not call QuantConnect, brokers, "
            "market-data APIs, order-routing systems, live execution systems, "
            "fill engines, slippage engines, or external data warehouses."
        )
    )

    parser.add_argument(
        "--export-operation",
        required=True,
        help="Path to quantconnect_export_operation.json.",
    )
    parser.add_argument(
        "--result-import-operation",
        required=True,
        help="Path to quantconnect_result_import_operation.json.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where QuantConnect review summary artifacts should be written.",
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

    review_summary = operation_result.get("review_summary")
    review_summary = review_summary if isinstance(review_summary, dict) else {}

    alignment = review_summary.get("alignment")
    alignment = alignment if isinstance(alignment, dict) else {}

    return {
        "schema_version": CLI_SUMMARY_SCHEMA_VERSION,
        "status": result.get("status", "needs_review"),
        "output_dir": result.get("output_dir"),
        "files": result.get("files", {}),
        "file_summary": result.get("file_summary", {}),
        "operation_summary": operation_record.get("summary", {}),
        "health_status": health_report.get("status"),
        "health_recommendations": health_report.get("recommendations", []),
        "alignment": {
            "strategies_match": alignment.get("strategies_match"),
            "symbols_match": alignment.get("symbols_match"),
            "reported_count_matches_export": alignment.get(
                "reported_count_matches_export"
            ),
            "missing_decision_strategy_ids": alignment.get(
                "missing_decision_strategy_ids",
                [],
            ),
            "unexpected_decision_strategy_ids": alignment.get(
                "unexpected_decision_strategy_ids",
                [],
            ),
            "missing_symbols": alignment.get("missing_symbols", []),
            "unexpected_symbols": alignment.get("unexpected_symbols", []),
        },
        "explicit_exclusions": result.get("explicit_exclusions", []),
    }


if __name__ == "__main__":
    raise SystemExit(main())
