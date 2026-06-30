from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.engines.strategy_selection.position_sizing_recommendation import build_signalforge_position_sizing_recommendation
from src.signalforge.engines.strategy_selection.position_sizing_recommendation_file_writer import write_position_sizing_recommendation_result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge review-only position sizing recommendations."
    )
    parser.add_argument(
        "--portfolio-construction-optimizer-source",
        required=True,
        help="Path to portfolio construction optimizer JSON artifact.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")
    parser.add_argument("--portfolio-equity", type=float, default=100000.0)
    parser.add_argument("--base-risk-per-trade-pct", type=float, default=0.01)
    parser.add_argument("--constrained-risk-multiplier", type=float, default=0.50)
    parser.add_argument("--max-risk-per-trade-pct", type=float, default=0.015)
    parser.add_argument("--max-total-new-risk-pct", type=float, default=0.03)
    parser.add_argument("--min-position-sizing-score", type=float, default=0.40)

    args = parser.parse_args(argv)

    result = build_signalforge_position_sizing_recommendation(
        portfolio_construction_optimizer_source=_read_json(args.portfolio_construction_optimizer_source),
        portfolio_equity=args.portfolio_equity,
        base_risk_per_trade_pct=args.base_risk_per_trade_pct,
        constrained_risk_multiplier=args.constrained_risk_multiplier,
        max_risk_per_trade_pct=args.max_risk_per_trade_pct,
        max_total_new_risk_pct=args.max_total_new_risk_pct,
        min_position_sizing_score=args.min_position_sizing_score,
    )

    summary = write_position_sizing_recommendation_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
