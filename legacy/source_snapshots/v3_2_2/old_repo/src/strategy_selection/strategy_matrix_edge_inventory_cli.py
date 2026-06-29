from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.strategy_selection.strategy_matrix_edge_inventory import (
    build_signalforge_strategy_matrix_edge_inventory,
)
from src.strategy_selection.strategy_matrix_edge_inventory_file_writer import (
    write_strategy_matrix_edge_inventory_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge strategy matrix edge inventory."
    )
    parser.add_argument(
        "--strategy-family-eligibility-source",
        default=None,
        help="Optional strategy family eligibility JSON artifact.",
    )
    parser.add_argument(
        "--option-strategy-candidate-source",
        default=None,
        help="Optional defined-risk option strategy candidate JSON artifact.",
    )
    parser.add_argument(
        "--historical-edge-source",
        default=None,
        help="Optional historical edge validation JSON artifact.",
    )
    parser.add_argument(
        "--portfolio-candidate-selection-source",
        default=None,
        help="Optional portfolio candidate selection summary JSON artifact.",
    )
    parser.add_argument(
        "--strategy-catalog-source",
        default=None,
        help="Optional strategy catalog JSON artifact. Defaults to src.options_strategy.catalog.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")

    args = parser.parse_args(argv)

    result = build_signalforge_strategy_matrix_edge_inventory(
        strategy_family_eligibility_source=_read_optional_json(args.strategy_family_eligibility_source),
        option_strategy_candidate_source=_read_optional_json(args.option_strategy_candidate_source),
        historical_edge_source=_read_optional_json(args.historical_edge_source),
        portfolio_candidate_selection_source=_read_optional_json(args.portfolio_candidate_selection_source),
        strategy_catalog_source=_read_optional_json(args.strategy_catalog_source),
    )

    summary = write_strategy_matrix_edge_inventory_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _read_optional_json(path_text: str | None) -> Any:
    if not path_text:
        return None
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
