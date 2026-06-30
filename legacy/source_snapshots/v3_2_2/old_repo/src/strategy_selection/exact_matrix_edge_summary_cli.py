from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.engines.strategy_selection.exact_matrix_edge_summary import (
    build_signalforge_exact_matrix_edge_summary,
)
from src.signalforge.engines.strategy_selection.exact_matrix_edge_summary_file_writer import (
    write_exact_matrix_edge_summary_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build exact strategy-matrix edge summary.")
    parser.add_argument(
        "--matrix-metadata-source",
        action="append",
        default=[],
        help="JSON artifact containing matrix_metadata-stamped records. May be repeated.",
    )
    parser.add_argument(
        "--strategy-matrix-edge-inventory-source",
        default=None,
        help="Optional strategy matrix edge inventory JSON artifact.",
    )
    parser.add_argument(
        "--min-records-per-cell",
        type=int,
        default=1,
        help="Minimum exact records required for each ready matrix edge cell.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")
    args = parser.parse_args(argv)

    result = build_signalforge_exact_matrix_edge_summary(
        matrix_metadata_sources=[_read_json(path) for path in args.matrix_metadata_source],
        strategy_matrix_edge_inventory_source=_read_optional_json(
            args.strategy_matrix_edge_inventory_source
        ),
        min_records_per_cell=args.min_records_per_cell,
    )
    summary = write_exact_matrix_edge_summary_result(result, args.output_dir)
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
