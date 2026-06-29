from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from src.backtesting.quantconnect_review_pipeline.file_writer import (
    write_quantconnect_review_pipeline_files,
)


CLI_SUMMARY_SCHEMA_VERSION = "quantconnect_review_pipeline_cli_summary.v1"


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

    result = write_quantconnect_review_pipeline_files(
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
            "Run the local QuantConnect review pipeline from an export operation "
            "JSON and a result-import operation JSON. This command writes local "
            "files only and does not call QuantConnect, brokers, market-data APIs, "
            "order-routing systems, live execution systems, fill engines, slippage "
            "engines, or external data warehouses."
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
        help="Directory where QuantConnect review pipeline artifacts should be written.",
    )

    return parser


def _read_json(path: str) -> Any:
    source_path = Path(path)
    with source_path.open(encoding="utf-8") as file:
        return json.load(file)


def _build_cli_summary(result: dict[str, Any]) -> dict[str, Any]:
    pipeline_result = result.get("pipeline_result")
    pipeline_result = pipeline_result if isinstance(pipeline_result, dict) else {}

    pipeline_summary = pipeline_result.get("summary")
    pipeline_summary = pipeline_summary if isinstance(pipeline_summary, dict) else {}

    review_handoff_operation = pipeline_result.get("review_handoff_operation")
    review_handoff_operation = (
        review_handoff_operation
        if isinstance(review_handoff_operation, dict)
        else {}
    )

    handoff_bundle = review_handoff_operation.get("handoff_bundle")
    handoff_bundle = handoff_bundle if isinstance(handoff_bundle, dict) else {}

    return {
        "schema_version": CLI_SUMMARY_SCHEMA_VERSION,
        "status": result.get("status", "needs_review"),
        "output_dir": result.get("output_dir"),
        "files": result.get("files", {}),
        "file_summary": result.get("file_summary", {}),
        "pipeline_summary": pipeline_summary,
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
        "warnings": pipeline_result.get("warnings", []),
        "blocked_reasons": pipeline_result.get("blocked_reasons", []),
        "explicit_exclusions": result.get("explicit_exclusions", []),
    }


if __name__ == "__main__":
    raise SystemExit(main())
