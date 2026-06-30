from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.engines.strategy_selection.portfolio_construction_optimizer import build_signalforge_portfolio_construction_optimizer
from src.signalforge.engines.strategy_selection.portfolio_construction_optimizer_file_writer import write_portfolio_construction_optimizer_result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge review-only portfolio construction optimizer recommendation."
    )
    parser.add_argument(
        "--portfolio-candidate-input-source",
        required=True,
        help="Path to portfolio candidate input JSON artifact.",
    )
    parser.add_argument(
        "--portfolio-source",
        required=False,
        default=None,
        help="Optional current portfolio/open positions JSON source for exposure prechecks.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")
    parser.add_argument("--max-optimizer-candidate-count", type=int, default=5)
    parser.add_argument("--max-net-abs-delta", type=float, default=1.00)
    parser.add_argument("--max-gross-abs-delta", type=float, default=2.00)
    parser.add_argument("--max-gross-abs-gamma", type=float, default=0.25)
    parser.add_argument("--max-gross-abs-vega", type=float, default=2.00)
    parser.add_argument("--max-strategy-family-count", type=int, default=3)
    parser.add_argument("--min-portfolio-construction-score", type=float, default=0.40)

    args = parser.parse_args(argv)

    portfolio_source = _read_json(args.portfolio_source) if args.portfolio_source else None
    result = build_signalforge_portfolio_construction_optimizer(
        portfolio_candidate_input_source=_read_json(args.portfolio_candidate_input_source),
        portfolio_source=portfolio_source,
        max_optimizer_candidate_count=args.max_optimizer_candidate_count,
        max_net_abs_delta=args.max_net_abs_delta,
        max_gross_abs_delta=args.max_gross_abs_delta,
        max_gross_abs_gamma=args.max_gross_abs_gamma,
        max_gross_abs_vega=args.max_gross_abs_vega,
        max_strategy_family_count=args.max_strategy_family_count,
        min_portfolio_construction_score=args.min_portfolio_construction_score,
    )

    summary = write_portfolio_construction_optimizer_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
