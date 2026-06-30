from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.engines.strategy_selection.historical_edge_matrix_coverage_audit import (
    build_signalforge_historical_edge_matrix_coverage_audit,
)
from src.signalforge.engines.strategy_selection.historical_edge_matrix_coverage_audit_file_writer import (
    write_historical_edge_matrix_coverage_audit_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit whether historical edge evidence can map to strategy matrix cells."
    )
    parser.add_argument(
        "--strategy-matrix-edge-inventory-source",
        default=None,
        help="Optional strategy matrix edge inventory JSON artifact.",
    )
    parser.add_argument(
        "--historical-edge-source",
        default=None,
        help="Optional historical edge validation JSON artifact.",
    )
    parser.add_argument(
        "--historical-edge-diagnostics-source",
        default=None,
        help="Optional historical edge diagnostics JSON artifact.",
    )
    parser.add_argument(
        "--portfolio-candidate-selection-source",
        default=None,
        help="Optional portfolio candidate selection JSON artifact.",
    )
    parser.add_argument(
        "--quantconnect-replay-window-plan-source",
        default=None,
        help="Optional QuantConnect historical replay window plan JSON artifact.",
    )
    parser.add_argument(
        "--additional-source",
        action="append",
        default=[],
        help="Additional JSON source to include in the audit. May be repeated.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")

    args = parser.parse_args(argv)

    additional_sources = [
        _read_required_json(path_text) for path_text in args.additional_source
    ]
    additional_source_payload: Any = additional_sources or None

    result = build_signalforge_historical_edge_matrix_coverage_audit(
        strategy_matrix_edge_inventory_source=_read_optional_json(
            args.strategy_matrix_edge_inventory_source
        ),
        historical_edge_source=_read_optional_json(args.historical_edge_source),
        historical_edge_diagnostics_source=_read_optional_json(
            args.historical_edge_diagnostics_source
        ),
        portfolio_candidate_selection_source=_read_optional_json(
            args.portfolio_candidate_selection_source
        ),
        quantconnect_replay_window_plan_source=_read_optional_json(
            args.quantconnect_replay_window_plan_source
        ),
        additional_sources=additional_source_payload,
    )

    summary = write_historical_edge_matrix_coverage_audit_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _read_optional_json(path_text: str | None) -> Any:
    if not path_text:
        return None
    return _read_required_json(path_text)


def _read_required_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
