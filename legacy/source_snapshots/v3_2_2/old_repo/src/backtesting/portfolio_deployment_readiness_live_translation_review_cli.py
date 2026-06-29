"""CLI for portfolio deployment readiness / live translation review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from .portfolio_deployment_readiness_live_translation_review import (
    BuildConfig,
    InputPathSet,
    build_portfolio_deployment_readiness_live_translation_review,
)


def _optional_path(value: Optional[str]) -> Optional[Path]:
    if value is None or value == "":
        return None
    return Path(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build portfolio deployment readiness / live translation review artifacts."
    )
    parser.add_argument("--decision-rows", required=True)
    parser.add_argument("--decision-summary", required=True)
    parser.add_argument("--strategy-selection-rows", required=True)
    parser.add_argument("--strategy-selection-summary", required=True)
    parser.add_argument("--selected-trade-sequence-summary", required=True)
    parser.add_argument("--position-sizing-summary", required=True)
    parser.add_argument("--equity-reconstruction-summary", required=True)
    parser.add_argument("--metrics-report", required=True)
    parser.add_argument("--stress-validation-summary", required=True)
    parser.add_argument("--stress-validation-scenarios", required=False)
    parser.add_argument(
        "--execution-rulebook-readiness-bridge",
        required=False,
        help="Optional readiness bridge emitted by portfolio_execution_translation_rulebook; resolves mapped execution gaps for paper-trading readiness.",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--max-timing-audit-rows",
        type=int,
        default=25000,
        help="Maximum decision/selection rows to include in detailed timing audit.",
    )
    parser.add_argument(
        "--decision-timestamp-assumption",
        default="after_market_close",
        choices=("before_market_open", "during_market_hours", "after_market_close"),
        help="Timestamp assumption used for the live-translation timing audit.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    inputs = InputPathSet(
        decision_rows=_optional_path(args.decision_rows),
        decision_summary=_optional_path(args.decision_summary),
        strategy_selection_rows=_optional_path(args.strategy_selection_rows),
        strategy_selection_summary=_optional_path(args.strategy_selection_summary),
        selected_trade_sequence_summary=_optional_path(args.selected_trade_sequence_summary),
        position_sizing_summary=_optional_path(args.position_sizing_summary),
        equity_reconstruction_summary=_optional_path(args.equity_reconstruction_summary),
        metrics_report=_optional_path(args.metrics_report),
        stress_validation_summary=_optional_path(args.stress_validation_summary),
        stress_validation_scenarios=_optional_path(args.stress_validation_scenarios),
        execution_rulebook_readiness_bridge=_optional_path(args.execution_rulebook_readiness_bridge),
    )
    config = BuildConfig(
        max_timing_audit_rows=args.max_timing_audit_rows,
        decision_timestamp_assumption=args.decision_timestamp_assumption,
    )
    result = build_portfolio_deployment_readiness_live_translation_review(
        inputs=inputs,
        output_dir=Path(args.output_dir),
        config=config,
    )
    print(json.dumps(result.summary, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
