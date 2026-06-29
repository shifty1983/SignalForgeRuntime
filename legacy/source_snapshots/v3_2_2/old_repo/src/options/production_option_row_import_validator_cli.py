from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.options.production_option_row_import_validator import (
    build_signalforge_production_option_row_import_validator,
)
from src.options.production_option_row_import_validator_file_writer import (
    write_production_option_row_import_validator_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate production option rows before Options Behavior builders."
    )
    parser.add_argument(
        "--universe-source",
        required=False,
        default=None,
        help="Optional path to a universe, asset behavior, or symbol-list JSON file.",
    )
    parser.add_argument(
        "--option-source",
        required=True,
        help="Path to option row JSON using the option_rows contract.",
    )
    parser.add_argument(
        "--min-structural-rows-per-symbol",
        required=False,
        type=int,
        default=3,
        help="Minimum complete rows required to prove structural validity.",
    )
    parser.add_argument(
        "--min-production-rows-per-symbol",
        required=False,
        type=int,
        default=20,
        help="Minimum relevant filtered rows required for production decision readiness.",
    )
    parser.add_argument("--min-expiration-count", required=False, type=int, default=2)
    parser.add_argument("--min-liquid-contract-count", required=False, type=int, default=4)
    parser.add_argument("--min-rows-per-expiration", required=False, type=int, default=4)
    parser.add_argument("--min-dte", required=False, type=int, default=7)
    parser.add_argument("--max-dte", required=False, type=int, default=90)
    parser.add_argument("--moneyness-lower-bound", required=False, type=float, default=0.80)
    parser.add_argument("--moneyness-upper-bound", required=False, type=float, default=1.20)
    parser.add_argument("--max-spread-pct", required=False, type=float, default=0.15)
    parser.add_argument("--min-open-interest", required=False, type=int, default=100)
    parser.add_argument("--min-volume", required=False, type=int, default=1)
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")

    args = parser.parse_args(argv)

    result = build_signalforge_production_option_row_import_validator(
        universe_source=_read_json(args.universe_source) if args.universe_source else None,
        option_source=_read_json(args.option_source),
        min_structural_rows_per_symbol=args.min_structural_rows_per_symbol,
        min_production_rows_per_symbol=args.min_production_rows_per_symbol,
        min_expiration_count=args.min_expiration_count,
        min_liquid_contract_count=args.min_liquid_contract_count,
        min_rows_per_expiration=args.min_rows_per_expiration,
        min_dte=args.min_dte,
        max_dte=args.max_dte,
        moneyness_lower_bound=args.moneyness_lower_bound,
        moneyness_upper_bound=args.moneyness_upper_bound,
        max_spread_pct=args.max_spread_pct,
        min_open_interest=args.min_open_interest,
        min_volume=args.min_volume,
    )

    summary = write_production_option_row_import_validator_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
