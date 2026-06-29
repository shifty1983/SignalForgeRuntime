from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.data_sources.portfolio_equity_reconstruction.equity_reconstructor import (
    build_portfolio_equity_reconstruction,
    discover_decoded_window_roots,
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
        description="Build SignalForge historical portfolio equity reconstruction."
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
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--period-id", default=None)
    parser.add_argument("--starting-equity", type=float, default=100000.0)
    parser.add_argument("--portfolio-risk-budget-pct", type=float, default=0.10)
    parser.add_argument("--max-risk-per-trade-pct", type=float, default=0.01)
    parser.add_argument("--min-return-cap", type=float, default=-1.0)
    parser.add_argument("--max-return-cap", type=float, default=1.0)
    parser.add_argument(
        "--horizon",
        action="append",
        default=None,
        help="Fixed exit horizon to reconstruct. Can be repeated. Defaults to 1,5,10,21,45.",
    )
    parser.add_argument(
        "--exclude-symbol",
        action="append",
        default=None,
        help="Optional symbol to exclude from reconstruction. Can be repeated.",
    )

    args = parser.parse_args()

    decoded_roots = discover_decoded_window_roots(_flatten_sources(args.decoded_window_root))
    if not decoded_roots:
        raise SystemExit("No decoded window roots found.")

    horizons = args.horizon or ["1", "5", "10", "21", "45"]
    excluded_symbols = {symbol.strip().upper() for symbol in (args.exclude_symbol or []) if symbol.strip()}

    reconstruction = build_portfolio_equity_reconstruction(
        decoded_window_roots=decoded_roots,
        period_id=args.period_id,
        horizons=[str(horizon) for horizon in horizons],
        starting_equity=args.starting_equity,
        portfolio_risk_budget_pct=args.portfolio_risk_budget_pct,
        max_risk_per_trade_pct=args.max_risk_per_trade_pct,
        min_return_cap=args.min_return_cap,
        max_return_cap=args.max_return_cap,
        excluded_symbols=excluded_symbols,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    scenario_results = reconstruction.pop("scenario_results")

    summary_path = output_dir / "signalforge_portfolio_equity_reconstruction.json"
    write_json(summary_path, reconstruction)

    for scenario in scenario_results:
        scenario_id = scenario["summary"]["scenario_id"]
        write_json(
            output_dir / f"signalforge_portfolio_equity_curve_{scenario_id}.json",
            {
                "artifact_type": "signalforge_portfolio_equity_curve",
                "scenario_id": scenario_id,
                "period_id": args.period_id,
                "summary": scenario["summary"],
                "equity_curve": scenario["equity_curve"],
            },
        )
        write_json(
            output_dir / f"signalforge_portfolio_trade_events_{scenario_id}.json",
            {
                "artifact_type": "signalforge_portfolio_trade_events",
                "scenario_id": scenario_id,
                "period_id": args.period_id,
                "trade_events": scenario["trade_events"],
            },
        )

    print(json.dumps(reconstruction, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
