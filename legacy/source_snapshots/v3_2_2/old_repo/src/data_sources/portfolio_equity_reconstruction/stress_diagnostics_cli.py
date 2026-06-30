from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.signalforge.data_sources.portfolio_equity_reconstruction.stress_diagnostics import (
    build_portfolio_equity_stress_diagnostics,
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
        description="Build SignalForge portfolio equity MAE stress diagnostics."
    )
    parser.add_argument("--decoded-window-root", action="append", nargs="+", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--period-id", default=None)
    parser.add_argument("--portfolio-risk-budget-pct", type=float, default=0.10)
    parser.add_argument("--max-risk-per-trade-pct", type=float, default=0.01)
    parser.add_argument("--min-return-cap", type=float, default=-1.0)
    parser.add_argument("--max-return-cap", type=float, default=1.0)
    parser.add_argument("--horizon", action="append", default=None)

    args = parser.parse_args()

    decoded_roots = discover_decoded_window_roots(_flatten_sources(args.decoded_window_root))
    if not decoded_roots:
        raise SystemExit("No decoded window roots found.")

    diagnostics = build_portfolio_equity_stress_diagnostics(
        decoded_window_roots=decoded_roots,
        period_id=args.period_id,
        horizons=args.horizon or ["1", "5", "10", "21", "45"],
        portfolio_risk_budget_pct=args.portfolio_risk_budget_pct,
        max_risk_per_trade_pct=args.max_risk_per_trade_pct,
        min_return_cap=args.min_return_cap,
        max_return_cap=args.max_return_cap,
    )

    output_dir = Path(args.output_dir)
    output_path = output_dir / "signalforge_portfolio_equity_stress_diagnostics.json"
    write_json(output_path, diagnostics)

    print(json.dumps(diagnostics, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
