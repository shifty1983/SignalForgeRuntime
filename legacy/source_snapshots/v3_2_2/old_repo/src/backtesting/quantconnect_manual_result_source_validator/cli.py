from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.backtesting.quantconnect_manual_result_source_validator.file_writer import (
    write_quantconnect_manual_result_source_validation_files,
)


CLI_SUMMARY_SCHEMA_VERSION = (
    "quantconnect_manual_result_source_validation_cli_summary.v1"
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

    result = write_quantconnect_manual_result_source_validation_files(
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
            "Validate a local manual QuantConnect result source JSON before "
            "running the manual backtest evidence pipeline. This command "
            "writes local validation artifacts only and does not call "
            "QuantConnect, brokers, market-data APIs, order-routing systems, "
            "live execution systems, fill engines, slippage engines, or "
            "external data warehouses."
        )
    )

    parser.add_argument(
        "--source",
        required=True,
        help="Path to filled manual QuantConnect result source JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where validation artifacts should be written.",
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

    validation = operation_result.get("validation")
    validation = (
        validation
        if isinstance(validation, dict)
        else {}
    )

    validation_summary = _as_mapping(validation.get("summary"))

    placeholders = validation.get("placeholders")
    placeholders = (
        placeholders
        if isinstance(placeholders, list)
        else []
    )

    sensitive_fields = validation.get("sensitive_fields")
    sensitive_fields = (
        sensitive_fields
        if isinstance(sensitive_fields, list)
        else []
    )

    checks = validation.get("checks")
    checks = checks if isinstance(checks, list) else []

    failed_checks = [
        check
        for check in checks
        if isinstance(check, dict) and check.get("status") == "failed"
    ]
    warning_checks = [
        check
        for check in checks
        if isinstance(check, dict) and check.get("status") == "warning"
    ]

    return {
        "schema_version": CLI_SUMMARY_SCHEMA_VERSION,
        "status": result.get("status", "needs_review"),
        "validation_status": validation.get("status"),
        "output_dir": result.get("output_dir"),
        "files": result.get("files", {}),
        "file_summary": result.get("file_summary", {}),
        "operation_summary": operation_record.get("summary", {}),
        "health_status": health_report.get("status"),
        "health_recommendations": health_report.get(
            "recommendations",
            [],
        ),
        "backtest_id": validation_summary.get("backtest_id"),
        "project_name": validation_summary.get("project_name"),
        "backtest_name": validation_summary.get("backtest_name"),
        "strategy_count": validation_summary.get("strategy_count", 0),
        "symbol_count": validation_summary.get("symbol_count", 0),
        "placeholder_count": len(placeholders),
        "sensitive_field_count": len(sensitive_fields),
        "check_counts": {
            "checks": len(checks),
            "failed": len(failed_checks),
            "warnings": len(warning_checks),
            "passed": sum(
                1
                for check in checks
                if isinstance(check, dict)
                and check.get("status") == "passed"
            ),
        },
        "can_enter_manual_backtest_pipeline": bool(
            validation_summary.get("can_enter_manual_backtest_pipeline")
        ),
        "warnings": validation.get("warnings", []),
        "blocked_reasons": validation.get("blocked_reasons", []),
        "placeholders": placeholders,
        "sensitive_fields": sensitive_fields,
        "explicit_exclusions": result.get("explicit_exclusions", []),
    }


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)

    return {}


if __name__ == "__main__":
    raise SystemExit(main())
