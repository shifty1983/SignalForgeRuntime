from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from src.options_portfolio.control_report_pipeline_file_writer import (
    write_options_portfolio_control_report_pipeline_files,
)


WriterFunction = Callable[..., dict[str, Any]]


def main(
    argv: Sequence[str] | None = None,
    *,
    writer: WriterFunction = write_options_portfolio_control_report_pipeline_files,
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

    result = writer(
        source,
        output_dir=args.output_dir,
        base_dir=args.base_dir,
        report_date=args.report_date,
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result.get("status") == "blocked" else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the file-driven options portfolio control report pipeline. "
            "This command assembles local artifact files into a control-report "
            "source and then builds the top-level portfolio control report. It "
            "does not call brokers, route orders, submit orders, model fills, "
            "perform live execution, model slippage, create automatic close/roll/"
            "defense orders, change strategy logic automatically, update "
            "parameters automatically, or pause strategies automatically."
        )
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to artifact-path manifest JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where pipeline artifacts should be written.",
    )
    parser.add_argument(
        "--base-dir",
        default=None,
        help="Optional base directory for relative artifact paths.",
    )
    parser.add_argument(
        "--report-date",
        default=None,
        help="Optional report date override.",
    )
    return parser


def _read_json(path: str) -> Any:
    with Path(path).open(encoding="utf-8") as file:
        return json.load(file)


if __name__ == "__main__":
    raise SystemExit(main())

