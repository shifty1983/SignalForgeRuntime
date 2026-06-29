# src/backtesting/historical_option_behavior_dry_run_cli.py

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from src.backtesting.historical_option_behavior_dry_run import (
    run_historical_option_behavior_dry_run,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a historical option behavior dry run from local sample files."
    )

    parser.add_argument(
        "--option-rows",
        required=True,
        help="Path to option rows file. Supports .json, .jsonl, or .csv.",
    )
    parser.add_argument(
        "--asset-behavior",
        required=True,
        help="Path to asset behavior JSON file.",
    )
    parser.add_argument(
        "--historical-evaluation",
        required=False,
        help="Optional historical evaluation report JSON file.",
    )
    parser.add_argument(
        "--final-review-export",
        required=False,
        help="Optional final review export JSON file.",
    )
    parser.add_argument(
        "--output",
        required=False,
        help="Optional output JSON path. If omitted, prints JSON to stdout.",
    )
    parser.add_argument(
        "--dry-run-name",
        default="historical_option_behavior_sample_dry_run",
        help="Name to attach to the dry run artifact.",
    )

    args = parser.parse_args(argv)

    raw_option_rows = _load_rows(Path(args.option_rows))
    asset_behavior_result = _load_mapping(Path(args.asset_behavior))

    historical_evaluation_report = (
        _load_mapping(Path(args.historical_evaluation))
        if args.historical_evaluation
        else None
    )

    final_review_export = (
        _load_mapping(Path(args.final_review_export))
        if args.final_review_export
        else None
    )

    result = run_historical_option_behavior_dry_run(
        raw_option_rows=raw_option_rows,
        asset_behavior_result=asset_behavior_result,
        historical_evaluation_report=historical_evaluation_report,
        final_review_export=final_review_export,
        dry_run_name=args.dry_run_name,
        metadata={
            "source": "historical_option_behavior_dry_run_cli",
            "option_rows_path": str(Path(args.option_rows)),
            "asset_behavior_path": str(Path(args.asset_behavior)),
            "historical_evaluation_path": args.historical_evaluation,
            "final_review_export_path": args.final_review_export,
        },
    )

    serialized = json.dumps(
        result,
        indent=2,
        sort_keys=True,
        default=str,
    )

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)

    return 0


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"option rows file does not exist: {path}")

    suffix = path.suffix.lower()

    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8-sig"))

        if isinstance(payload, list):
            return _validate_row_list(payload, path)

        if isinstance(payload, dict):
            for key in ("rows", "option_rows", "raw_option_rows", "data"):
                value = payload.get(key)

                if isinstance(value, list):
                    return _validate_row_list(value, path)

        raise ValueError(
            "JSON option rows file must contain a list or an object with "
            "rows, option_rows, raw_option_rows, or data"
        )

    if suffix == ".jsonl":
        rows: list[dict[str, Any]] = []

        for line_number, line in enumerate(
            path.read_text(encoding="utf-8-sig").splitlines(),
            start=1,
        ):
            stripped = line.strip()

            if not stripped:
                continue

            value = json.loads(stripped)

            if not isinstance(value, dict):
                raise ValueError(
                    f"JSONL row {line_number} in {path} must be an object"
                )

            rows.append(value)

        return rows

    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as file:
            return [dict(row) for row in csv.DictReader(file)]

    raise ValueError(f"unsupported option rows file type: {suffix}")


def _load_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON file does not exist: {path}")

    payload = json.loads(path.read_text(encoding="utf-8-sig"))

    if not isinstance(payload, dict):
        raise ValueError(f"JSON file must contain an object: {path}")

    return payload


def _validate_row_list(
    rows: list[Any],
    path: Path,
) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"row {index} in {path} must be an object")

        normalized_rows.append(row)

    return normalized_rows


if __name__ == "__main__":
    raise SystemExit(main())
