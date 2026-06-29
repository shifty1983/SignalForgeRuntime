from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.strategy_selection.contract_candidate_scoring import build_signalforge_contract_candidate_scoring
from src.strategy_selection.contract_candidate_scoring_file_writer import write_contract_candidate_scoring_result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge contract candidate scoring from contract selection readiness."
    )
    parser.add_argument(
        "--contract-readiness-source",
        required=True,
        help="Path to contract selection readiness JSON artifact.",
    )
    parser.add_argument(
        "--option-source",
        required=False,
        default=None,
        help="Optional path to full contract-level option rows JSON artifact. When omitted, readiness candidate row previews are used.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")
    parser.add_argument("--max-spread-pct", type=float, default=0.15)
    parser.add_argument("--min-open-interest", type=int, default=100)
    parser.add_argument("--min-volume", type=int, default=1)
    parser.add_argument("--min-contract-score", type=float, default=0.50)
    parser.add_argument("--max-candidates-per-symbol", type=int, default=5)

    args = parser.parse_args(argv)

    option_source = _read_json(args.option_source) if args.option_source else None

    result = build_signalforge_contract_candidate_scoring(
        contract_readiness_source=_read_json(args.contract_readiness_source),
        option_source=option_source,
        max_spread_pct=args.max_spread_pct,
        min_open_interest=args.min_open_interest,
        min_volume=args.min_volume,
        min_contract_score=args.min_contract_score,
        max_candidates_per_symbol=args.max_candidates_per_symbol,
    )

    summary = write_contract_candidate_scoring_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
