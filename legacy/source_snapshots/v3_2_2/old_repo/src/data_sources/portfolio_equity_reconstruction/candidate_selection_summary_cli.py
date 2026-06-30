from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.signalforge.data_sources.portfolio_equity_reconstruction.candidate_selection_summary import (
    build_portfolio_candidate_selection_summary,
    read_json,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a SignalForge portfolio candidate selection summary."
    )
    parser.add_argument("--comparison-summary-source", required=True)
    parser.add_argument("--stress-diagnostics-source", required=True)
    parser.add_argument("--multi-window-edge-summary-source", default=None)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--period-id", default=None)

    args = parser.parse_args()

    comparison_summary = read_json(args.comparison_summary_source)
    stress_diagnostics = read_json(args.stress_diagnostics_source)
    multi_window_edge_summary = (
        read_json(args.multi_window_edge_summary_source)
        if args.multi_window_edge_summary_source
        else None
    )

    summary = build_portfolio_candidate_selection_summary(
        comparison_summary=comparison_summary,
        stress_diagnostics=stress_diagnostics,
        multi_window_edge_summary=multi_window_edge_summary,
        period_id=args.period_id,
    )

    output_dir = Path(args.output_dir)
    output_path = output_dir / "signalforge_portfolio_candidate_selection_summary.json"
    write_json(output_path, summary)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
