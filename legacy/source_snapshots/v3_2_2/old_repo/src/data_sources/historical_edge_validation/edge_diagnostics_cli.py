from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.data_sources.historical_edge_validation.edge_diagnostics import (
    build_historical_edge_validation_diagnostics,
    discover_decoded_window_roots,
    discover_window_summary_sources,
    read_json,
    write_json,
)


def _flatten_sources(source_groups: list[list[str]] | None) -> list[str]:
    if not source_groups:
        return []

    flattened: list[str] = []
    for group in source_groups:
        flattened.extend(group)

    return flattened


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge historical edge validation diagnostics."
    )
    parser.add_argument(
        "--decoded-window-root",
        action="append",
        nargs="+",
        required=True,
        help=(
            "One or more decoded window directories or parent directories containing "
            "quantconnect_research_export_decoded_batches_<window_id> folders."
        ),
    )
    parser.add_argument(
        "--window-summary-source",
        action="append",
        nargs="+",
        default=None,
        help=(
            "Optional combined window summary JSON files or parent directories containing "
            "signalforge_historical_edge_validation_combined_summary.json files."
        ),
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--period-id", default=None)
    parser.add_argument("--worst-outcome-limit", type=int, default=50)
    parser.add_argument("--symbol-limit", type=int, default=50)

    args = parser.parse_args()

    decoded_inputs = _flatten_sources(args.decoded_window_root)
    decoded_roots = discover_decoded_window_roots(decoded_inputs)

    if not decoded_roots:
        raise SystemExit("No decoded window roots found.")

    window_summary_records = []
    if args.window_summary_source:
        window_summary_inputs = _flatten_sources(args.window_summary_source)
        window_summary_sources = discover_window_summary_sources(window_summary_inputs)
        window_summary_records = [read_json(source) for source in window_summary_sources]

    diagnostics = build_historical_edge_validation_diagnostics(
        decoded_window_roots=decoded_roots,
        window_summary_records=window_summary_records,
        period_id=args.period_id,
        worst_outcome_limit=args.worst_outcome_limit,
        symbol_limit=args.symbol_limit,
    )

    output_dir = Path(args.output_dir)
    output_path = output_dir / "signalforge_historical_edge_validation_diagnostics.json"
    write_json(output_path, diagnostics)

    print(json.dumps(diagnostics, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
