from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.signalforge.data_sources.historical_edge_validation.multi_window_summary import (
    build_historical_edge_validation_multi_window_summary,
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
        description="Build a multi-window SignalForge historical edge validation summary."
    )
    parser.add_argument(
        "--window-summary-source",
        action="append",
        nargs="+",
        required=True,
        help=(
            "One or more combined window summary JSON files or directories containing "
            "signalforge_historical_edge_validation_combined_summary.json. Can be repeated."
        ),
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--period-id", default=None)

    args = parser.parse_args()

    source_inputs = _flatten_sources(args.window_summary_source)
    sources = discover_window_summary_sources(source_inputs)

    if not sources:
        raise SystemExit(
            "No signalforge_historical_edge_validation_combined_summary.json sources found."
        )

    records = [read_json(source) for source in sources]

    summary = build_historical_edge_validation_multi_window_summary(
        records,
        source_paths=sources,
        period_id=args.period_id,
    )

    output_dir = Path(args.output_dir)
    output_path = output_dir / "signalforge_historical_edge_validation_multi_window_summary.json"
    write_json(output_path, summary)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
