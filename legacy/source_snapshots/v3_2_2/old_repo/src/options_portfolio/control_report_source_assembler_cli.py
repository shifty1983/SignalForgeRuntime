from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from src.options_portfolio.control_report_source_assembler_file_writer import (
    write_options_portfolio_control_report_source_assembler_operation_files,
)


CLI_SUMMARY_SCHEMA_VERSION = "options_portfolio_control_report_source_assembler_cli_summary.v1"
DEFAULT_CLI_SUMMARY_FILENAME = "options_portfolio_control_report_source_assembler_cli_summary.json"

WriterFunction = Callable[..., dict[str, Any]]


def main(
    argv: Sequence[str] | None = None,
    *,
    writer: WriterFunction = write_options_portfolio_control_report_source_assembler_operation_files,
) -> int:
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

    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    writer_result = writer(
        source,
        output_dir=output_path,
        base_dir=args.base_dir,
        report_date=args.report_date,
    )

    summary_path = output_path / DEFAULT_CLI_SUMMARY_FILENAME
    summary = _build_cli_summary(writer_result=writer_result, summary_path=summary_path)
    _write_json(summary_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))

    return 1 if summary["status"] == "blocked" else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Assemble the source JSON used by the top-level options portfolio "
            "control report from local artifact paths or direct artifacts. This "
            "command writes local files only and does not call brokers, route "
            "orders, submit orders, model fills, perform live execution, model "
            "slippage, create automatic close/roll/defense orders, change "
            "strategy logic automatically, update parameters automatically, or "
            "pause strategies automatically."
        )
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to source assembler manifest JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where source assembler artifacts should be written.",
    )
    parser.add_argument(
        "--base-dir",
        default=None,
        help="Optional base directory for relative artifact paths.",
    )
    parser.add_argument(
        "--report-date",
        default=None,
        help="Optional report date override. If omitted, source.report_date is used.",
    )
    return parser


def _build_cli_summary(
    *,
    writer_result: dict[str, Any],
    summary_path: Path,
) -> dict[str, Any]:
    operation_result = _as_mapping(writer_result.get("operation_result"))
    operation_record = _as_mapping(operation_result.get("operation_record"))

    return {
        "schema_version": CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "options_portfolio_control_report_source_assembler_cli",
        "status": writer_result.get("status", "needs_review"),
        "output_dir": writer_result.get("output_dir"),
        "base_dir": writer_result.get("base_dir"),
        "summary_path": str(summary_path),
        "files": writer_result.get("files", {}),
        "file_summary": writer_result.get("file_summary", {}),
        "operation_summary": operation_record.get("operation_summary", {}),
        "source_summary": writer_result.get("source_summary", {}),
        "explicit_exclusions": list(writer_result.get("explicit_exclusions", [])),
    }


def _read_json(path: str) -> Any:
    source_path = Path(path)
    with source_path.open(encoding="utf-8") as file:
        return json.load(file)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


if __name__ == "__main__":
    raise SystemExit(main())

