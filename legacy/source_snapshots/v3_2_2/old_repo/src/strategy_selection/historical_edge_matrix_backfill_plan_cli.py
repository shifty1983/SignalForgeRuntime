from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.strategy_selection.historical_edge_matrix_backfill_plan import (
    build_signalforge_historical_edge_matrix_backfill_plan,
)
from src.strategy_selection.historical_edge_matrix_backfill_plan_file_writer import (
    write_historical_edge_matrix_backfill_plan_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge historical edge matrix backfill plan."
    )
    parser.add_argument(
        "--historical-edge-matrix-coverage-audit-source",
        required=True,
        help="Historical edge matrix coverage audit JSON artifact.",
    )
    parser.add_argument(
        "--strategy-matrix-edge-inventory-source",
        default=None,
        help="Optional strategy matrix edge inventory JSON artifact.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")

    args = parser.parse_args(argv)

    result = build_signalforge_historical_edge_matrix_backfill_plan(
        historical_edge_matrix_coverage_audit_source=_read_json(
            args.historical_edge_matrix_coverage_audit_source
        ),
        strategy_matrix_edge_inventory_source=_read_optional_json(
            args.strategy_matrix_edge_inventory_source
        ),
    )
    summary = write_historical_edge_matrix_backfill_plan_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_optional_json(path_text: str | None) -> Any:
    if not path_text:
        return None
    return _read_json(path_text)


if __name__ == "__main__":
    raise SystemExit(main())
