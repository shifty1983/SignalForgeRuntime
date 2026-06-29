from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.strategy_selection.position_maintenance_policy import build_signalforge_position_maintenance_policy
from src.strategy_selection.position_maintenance_policy_file_writer import write_position_maintenance_policy_result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge review-only position maintenance policies."
    )
    parser.add_argument(
        "--position-sizing-recommendation-source",
        required=True,
        help="Path to position sizing recommendation JSON artifact.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")
    parser.add_argument("--take-profit-capture-pct", type=float, default=0.50)
    parser.add_argument("--risk-cut-pct-of-budget", type=float, default=0.50)
    parser.add_argument("--delta-drift-threshold", type=float, default=0.20)
    parser.add_argument("--gamma-review-threshold", type=float, default=0.05)
    parser.add_argument("--vega-review-threshold", type=float, default=0.40)
    parser.add_argument("--theta-review-threshold", type=float, default=0.05)
    parser.add_argument("--dte-review-threshold", type=int, default=21)
    parser.add_argument("--min-position-maintenance-score", type=float, default=0.35)

    args = parser.parse_args(argv)

    result = build_signalforge_position_maintenance_policy(
        position_sizing_recommendation_source=_read_json(args.position_sizing_recommendation_source),
        take_profit_capture_pct=args.take_profit_capture_pct,
        risk_cut_pct_of_budget=args.risk_cut_pct_of_budget,
        delta_drift_threshold=args.delta_drift_threshold,
        gamma_review_threshold=args.gamma_review_threshold,
        vega_review_threshold=args.vega_review_threshold,
        theta_review_threshold=args.theta_review_threshold,
        dte_review_threshold=args.dte_review_threshold,
        min_position_maintenance_score=args.min_position_maintenance_score,
    )

    summary = write_position_maintenance_policy_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
