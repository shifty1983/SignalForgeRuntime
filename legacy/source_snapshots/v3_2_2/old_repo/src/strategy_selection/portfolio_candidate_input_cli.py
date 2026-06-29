from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.strategy_selection.portfolio_candidate_input import build_signalforge_portfolio_candidate_input
from src.strategy_selection.portfolio_candidate_input_file_writer import write_portfolio_candidate_input_result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge optimizer-ready portfolio candidate input from contract candidate scoring."
    )
    parser.add_argument(
        "--contract-candidate-scoring-source",
        required=True,
        help="Path to contract candidate scoring JSON artifact.",
    )
    parser.add_argument(
        "--portfolio-source",
        required=False,
        default=None,
        help="Optional current portfolio/open positions JSON source for portfolio constraint prechecks.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")
    parser.add_argument("--max-candidates-per-symbol", type=int, default=1)
    parser.add_argument("--max-portfolio-candidate-count", type=int, default=10)
    parser.add_argument("--max-existing-positions-per-symbol", type=int, default=1)
    parser.add_argument("--max-abs-delta-per-candidate", type=float, default=0.60)
    parser.add_argument("--max-abs-vega-per-candidate", type=float, default=1.00)

    args = parser.parse_args(argv)

    portfolio_source = _read_json(args.portfolio_source) if args.portfolio_source else None
    result = build_signalforge_portfolio_candidate_input(
        contract_candidate_scoring_source=_read_json(args.contract_candidate_scoring_source),
        portfolio_source=portfolio_source,
        max_candidates_per_symbol=args.max_candidates_per_symbol,
        max_portfolio_candidate_count=args.max_portfolio_candidate_count,
        max_existing_positions_per_symbol=args.max_existing_positions_per_symbol,
        max_abs_delta_per_candidate=args.max_abs_delta_per_candidate,
        max_abs_vega_per_candidate=args.max_abs_vega_per_candidate,
    )

    summary = write_portfolio_candidate_input_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
