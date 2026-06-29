"""CLI for portfolio execution translation rulebook."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from .portfolio_execution_translation_rulebook import (
    InputPathSet,
    build_portfolio_execution_translation_rulebook,
)


def _optional_path(value: Optional[str]) -> Optional[Path]:
    if value is None or value == "":
        return None
    return Path(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build portfolio execution translation rulebook artifacts."
    )
    parser.add_argument(
        "--strategy-selection-rows",
        required=False,
        help="Historical strategy-selection rows used to discover selected strategy names.",
    )
    parser.add_argument(
        "--selected-trade-sequence-summary",
        required=False,
        help="Selected trade sequence summary used as an additional strategy source.",
    )
    parser.add_argument(
        "--readiness-execution-gap-audit",
        required=False,
        help="Deployment readiness execution-gap audit used to discover strategies with gaps.",
    )
    parser.add_argument(
        "--readiness-summary",
        required=False,
        help="Deployment readiness summary used as context for the rulebook.",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--include-default-supported-strategies",
        action="store_true",
        help="Include the built-in supported strategy templates even if they are not observed in the inputs.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    inputs = InputPathSet(
        strategy_selection_rows=_optional_path(args.strategy_selection_rows),
        selected_trade_sequence_summary=_optional_path(args.selected_trade_sequence_summary),
        readiness_execution_gap_audit=_optional_path(args.readiness_execution_gap_audit),
        readiness_summary=_optional_path(args.readiness_summary),
    )
    result = build_portfolio_execution_translation_rulebook(
        inputs=inputs,
        output_dir=Path(args.output_dir),
        include_default_supported_strategies=args.include_default_supported_strategies,
    )
    print(json.dumps(result.summary, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
