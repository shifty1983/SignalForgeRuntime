from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.engines.options.options_behavior_production_input_plan import (
    build_signalforge_options_behavior_production_input_plan,
)
from src.signalforge.engines.options.options_behavior_production_input_plan_file_writer import (
    write_options_behavior_production_input_plan_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a SignalForge Options Behavior production input plan."
    )
    parser.add_argument(
        "--universe-source",
        required=False,
        default=None,
        help="Optional path to a universe, asset behavior, or symbol-list JSON file.",
    )
    parser.add_argument(
        "--option-source",
        required=False,
        default=None,
        help="Optional path to option row JSON using the option_rows contract.",
    )
    parser.add_argument(
        "--min-rows-per-symbol",
        required=False,
        type=int,
        default=3,
        help="Minimum option rows required per symbol for production input readiness.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")

    args = parser.parse_args(argv)

    result = build_signalforge_options_behavior_production_input_plan(
        universe_source=_read_json(args.universe_source) if args.universe_source else None,
        option_source=_read_json(args.option_source) if args.option_source else None,
        min_rows_per_symbol=args.min_rows_per_symbol,
    )

    summary = write_options_behavior_production_input_plan_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())


