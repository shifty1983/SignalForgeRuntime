from __future__ import annotations

import argparse
import json

from src.signalforge.data_sources.quantconnect_backtest_result_transport_feasibility.feasibility import (
    evaluate_signalforge_backtest_result_transport_feasibility,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate whether SignalForge replay result files fit in API-readable QuantConnect backtest result transport."
    )
    parser.add_argument("--replay-result-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--runtime-stat-chunk-size", type=int, default=750)
    parser.add_argument("--runtime-stat-chunk-budget", type=int, default=250)
    parser.add_argument("--chart-point-budget", type=int, default=4000)
    parser.add_argument("--chart-bytes-per-point-budget", type=int, default=6)

    args = parser.parse_args()

    result = evaluate_signalforge_backtest_result_transport_feasibility(
        replay_result_dir=args.replay_result_dir,
        output_dir=args.output_dir,
        runtime_stat_chunk_size=args.runtime_stat_chunk_size,
        runtime_stat_chunk_budget=args.runtime_stat_chunk_budget,
        chart_point_budget=args.chart_point_budget,
        chart_bytes_per_point_budget=args.chart_bytes_per_point_budget,
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("is_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
