from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from src.backtesting.quantconnect_export.algorithm_template import (
    write_quantconnect_algorithm_template,
)


CLI_SUMMARY_SCHEMA_VERSION = "quantconnect_algorithm_template_cli_summary.v1"


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

    result = write_quantconnect_algorithm_template(
        source,
        output_path=args.output_path,
    )

    summary = _build_cli_summary(result)
    print(json.dumps(summary, indent=2, sort_keys=True))

    if result.get("status") == "blocked":
        return 1

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Write a paste-ready QuantConnect main.py file from a SignalForge JSON "
            "source artifact. This command writes a local file only and does not call "
            "QuantConnect, brokers, market-data APIs, order-routing systems, live "
            "execution systems, fill engines, or slippage engines."
        )
    )

    parser.add_argument(
        "--source",
        required=True,
        help="Path to the SignalForge source JSON artifact.",
    )
    parser.add_argument(
        "--output-path",
        required=True,
        help="Path where the generated QuantConnect main.py should be written.",
    )

    return parser


def _read_json(path: str) -> Any:
    source_path = Path(path)
    with source_path.open(encoding="utf-8") as file:
        return json.load(file)


def _build_cli_summary(result: dict[str, Any]) -> dict[str, Any]:
    template_result = result.get("template_result")
    template_result = template_result if isinstance(template_result, dict) else {}

    return {
        "schema_version": CLI_SUMMARY_SCHEMA_VERSION,
        "status": result.get("status", "needs_review"),
        "output_path": result.get("output_path"),
        "file_summary": result.get("file_summary", {}),
        "template_summary": template_result.get("summary", {}),
        "explicit_exclusions": result.get("explicit_exclusions", []),
    }


if __name__ == "__main__":
    raise SystemExit(main())
