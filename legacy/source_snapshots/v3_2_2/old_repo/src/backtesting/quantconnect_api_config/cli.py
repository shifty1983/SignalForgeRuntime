from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.backtesting.quantconnect_api_config.file_writer import (
    write_quantconnect_api_config_files,
)


CLI_SUMMARY_SCHEMA_VERSION = "quantconnect_api_config_cli_summary.v1"


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

    result = write_quantconnect_api_config_files(
        source,
        output_dir=args.output_dir,
        environment=dict(os.environ),
    )

    summary = _build_cli_summary(result)
    print(json.dumps(summary, indent=2, sort_keys=True))

    if result.get("status") == "blocked":
        return 1

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build safe QuantConnect API config artifacts from a local JSON config "
            "file and environment variables. This command writes local files only "
            "and does not call QuantConnect, brokers, market-data APIs, order-routing "
            "systems, live execution systems, fill engines, slippage engines, or "
            "external data warehouses. API token values are never written to artifacts."
        )
    )

    parser.add_argument(
        "--source",
        required=True,
        help="Path to QuantConnect API config JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where QuantConnect API config artifacts should be written.",
    )

    return parser


def _read_json(path: str) -> Any:
    source_path = Path(path)
    with source_path.open(encoding="utf-8") as file:
        return json.load(file)


def _build_cli_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    operation_result = result.get("operation_result")
    operation_result = operation_result if isinstance(operation_result, dict) else {}

    operation_record = operation_result.get("operation_record")
    operation_record = operation_record if isinstance(operation_record, dict) else {}

    health_report = operation_result.get("health_report")
    health_report = health_report if isinstance(health_report, dict) else {}

    api_config = operation_result.get("api_config")
    api_config = api_config if isinstance(api_config, dict) else {}

    credentials = api_config.get("credentials")
    credentials = credentials if isinstance(credentials, dict) else {}

    backtest_context = api_config.get("backtest_context")
    backtest_context = backtest_context if isinstance(backtest_context, dict) else {}

    return {
        "schema_version": CLI_SUMMARY_SCHEMA_VERSION,
        "status": result.get("status", "needs_review"),
        "output_dir": result.get("output_dir"),
        "files": result.get("files", {}),
        "file_summary": result.get("file_summary", {}),
        "operation_summary": operation_record.get("summary", {}),
        "health_status": health_report.get("status"),
        "health_recommendations": health_report.get("recommendations", []),
        "credential_summary": {
            "user_id_present": bool(credentials.get("user_id_present")),
            "user_id_source": credentials.get("user_id_source"),
            "user_id_env": credentials.get("user_id_env"),
            "api_token_present": bool(credentials.get("api_token_present")),
            "api_token_source": credentials.get("api_token_source"),
            "api_token_env": credentials.get("api_token_env"),
            "api_token_value_persisted": bool(
                credentials.get("api_token_value_persisted")
            ),
        },
        "backtest_context": {
            "project_id_present": bool(backtest_context.get("project_id_present")),
            "backtest_id_present": bool(backtest_context.get("backtest_id_present")),
        },
        "warnings": api_config.get("warnings", []),
        "blocked_reasons": api_config.get("blocked_reasons", []),
        "explicit_exclusions": result.get("explicit_exclusions", []),
    }


if __name__ == "__main__":
    raise SystemExit(main())
