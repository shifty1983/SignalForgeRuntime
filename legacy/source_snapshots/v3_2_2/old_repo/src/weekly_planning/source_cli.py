from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from src.weekly_planning.source_file_writer import (
    write_weekly_option_trade_plan_source_file,
)


CLI_SUMMARY_SCHEMA_VERSION = "weekly_option_trade_plan_source_cli_summary.v1"
DEFAULT_CLI_SUMMARY_FILENAME = "weekly_option_trade_plan_source_cli_summary.json"

WriterFunction = Callable[..., dict[str, Any]]


def main(
    argv: Sequence[str] | None = None,
    *,
    writer: WriterFunction = write_weekly_option_trade_plan_source_file,
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
        plan_date=args.plan_date,
        market_regime=args.market_regime,
        setup_family=args.setup_family,
        has_underlying_positions=args.has_underlying_position,
        max_new_trades=args.max_new_trades,
        max_candidates_per_symbol=args.max_candidates_per_symbol,
        minimum_score=args.minimum_score,
    )

    summary_path = output_path / DEFAULT_CLI_SUMMARY_FILENAME
    summary = _build_cli_summary(
        writer_result=writer_result,
        summary_path=summary_path,
    )
    _write_json(summary_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))

    return 1 if summary["status"] == "blocked" else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a weekly option trade plan source artifact from option "
            "behavior strategy handoffs. This command writes local files only "
            "and does not call brokers, route orders, submit orders, model "
            "fills, perform live execution, model slippage, or create "
            "maintenance/defense actions."
        )
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to option behavior strategy handoff JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where weekly source artifacts should be written.",
    )
    parser.add_argument(
        "--plan-date",
        default=None,
        help="Optional plan date override. If omitted, source.plan_date is used.",
    )
    parser.add_argument(
        "--market-regime",
        default=None,
        help="Market regime used for candidate matching.",
    )
    parser.add_argument(
        "--setup-family",
        default=None,
        help="Optional setup family, such as momentum or mean_reversion.",
    )
    parser.add_argument(
        "--has-underlying-position",
        action="append",
        default=None,
        help="Symbol with an existing underlying position. Repeat as needed.",
    )
    parser.add_argument(
        "--max-new-trades",
        type=int,
        default=None,
        help="Optional cap for selected new trade actions.",
    )
    parser.add_argument(
        "--max-candidates-per-symbol",
        type=int,
        default=3,
        help="Optional cap for candidate strategies retained per symbol.",
    )
    parser.add_argument(
        "--minimum-score",
        type=float,
        default=2.0,
        help="Minimum setup score required for ready candidates.",
    )
    return parser


def _build_cli_summary(
    *,
    writer_result: dict[str, Any],
    summary_path: Path,
) -> dict[str, Any]:
    weekly_source = _as_mapping(
        writer_result.get("weekly_option_trade_plan_source")
    )

    return {
        "schema_version": CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "weekly_option_trade_plan_source_cli",
        "status": writer_result.get("status", "needs_review"),
        "output_dir": writer_result.get("output_dir"),
        "summary_path": str(summary_path),
        "files": writer_result.get("files", {}),
        "file_summary": writer_result.get("file_summary", {}),
        "source_summary": writer_result.get("source_summary", {}),
        "weekly_source_summary": {
            "artifact_type": weekly_source.get("artifact_type"),
            "plan_date": weekly_source.get("plan_date"),
            "candidate_result_count": weekly_source.get("candidate_result_count"),
            "ready_candidate_result_count": weekly_source.get(
                "ready_candidate_result_count"
            ),
            "needs_review_candidate_result_count": weekly_source.get(
                "needs_review_candidate_result_count"
            ),
            "blocked_candidate_result_count": weekly_source.get(
                "blocked_candidate_result_count"
            ),
            "warning_count": len(_as_list(weekly_source.get("warnings"))),
            "blocked_reason_count": len(
                _as_list(weekly_source.get("blocked_reasons"))
            ),
        },
        "explicit_exclusions": list(writer_result.get("explicit_exclusions", [])),
    }


def _read_json(path: str) -> Any:
    source_path = Path(path)
    with source_path.open(encoding="utf-8") as file:
        return json.load(file)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


if __name__ == "__main__":
    raise SystemExit(main())

