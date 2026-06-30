from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.signalforge.data_sources.portfolio_equity_reconstruction.comparison_summary import (
    build_portfolio_equity_reconstruction_comparison_summary,
    discover_reconstruction_sources,
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
        description="Build a SignalForge portfolio equity reconstruction comparison summary."
    )
    parser.add_argument(
        "--reconstruction-source",
        action="append",
        nargs="+",
        required=True,
        help=(
            "One or more reconstruction JSON files or directories containing "
            "signalforge_portfolio_equity_reconstruction.json."
        ),
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--period-id", default=None)

    args = parser.parse_args()

    sources = discover_reconstruction_sources(_flatten_sources(args.reconstruction_source))

    if not sources:
        raise SystemExit("No portfolio equity reconstruction sources found.")

    reconstructions = [read_json(source) for source in sources]

    summary = build_portfolio_equity_reconstruction_comparison_summary(
        reconstructions,
        source_paths=sources,
        period_id=args.period_id,
    )

    output_dir = Path(args.output_dir)
    output_path = output_dir / "signalforge_portfolio_equity_reconstruction_comparison_summary.json"
    write_json(output_path, summary)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
