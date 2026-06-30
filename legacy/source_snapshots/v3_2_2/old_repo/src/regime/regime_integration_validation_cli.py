from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.signalforge.engines.regime.regime_integration_validation import (
    build_signalforge_regime_integration_validation,
)

DEFAULT_QC_5Y_MARKET_PRICE_HISTORY = Path(
    "artifacts/qc_replay_5y_behavior_inputs/signalforge_qc_replay_market_price_behavior_input.json"
)
DEFAULT_FRED_REGIME_PIPELINE = Path(
    "artifacts/fred_regime_pipeline/signalforge_fred_regime_pipeline.json"
)
DEFAULT_OUTPUT = Path(
    "artifacts/regime_integration_validation/signalforge_regime_integration_validation.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate integrated SignalForge Regime inputs using the QC 5-year "
            "market price artifact by default. This command does not call brokers, "
            "route or submit orders, model fills, perform live execution, model "
            "slippage, or create automatic strategy/parameter actions."
        )
    )
    parser.add_argument(
        "--market-price-history",
        default=str(DEFAULT_QC_5Y_MARKET_PRICE_HISTORY),
        help=(
            "Market price history import JSON. Defaults to the QC 5-year behavior "
            f"input artifact: {DEFAULT_QC_5Y_MARKET_PRICE_HISTORY}"
        ),
    )
    parser.add_argument(
        "--fred-regime-pipeline",
        default=str(DEFAULT_FRED_REGIME_PIPELINE),
        help=(
            "Optional FRED regime pipeline JSON. Defaults to the stable FRED regime "
            f"artifact: {DEFAULT_FRED_REGIME_PIPELINE}. Use an empty string to skip."
        ),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"Output JSON artifact path. Defaults to: {DEFAULT_OUTPUT}",
    )
    parser.add_argument("--as-of-date")
    parser.add_argument("--breadth-window", type=int, default=200)
    parser.add_argument("--breadth-trend-periods", type=int, default=20)
    parser.add_argument("--risk-lookback-periods", type=int, default=60)
    parser.add_argument("--min-breadth-symbols", type=int, default=8)
    args = parser.parse_args()

    market_price_history = _read_json_required(
        args.market_price_history,
        label="market price history",
    )

    fred_regime_pipeline = None
    if str(args.fred_regime_pipeline or "").strip():
        fred_regime_pipeline = _read_json_required(
            args.fred_regime_pipeline,
            label="FRED regime pipeline",
        )

    result = build_signalforge_regime_integration_validation(
        fred_regime_pipeline=fred_regime_pipeline,
        market_price_history=market_price_history,
        as_of_date=args.as_of_date,
        breadth_window=args.breadth_window,
        breadth_trend_periods=args.breadth_trend_periods,
        risk_lookback_periods=args.risk_lookback_periods,
        min_breadth_symbols=args.min_breadth_symbols,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 1 if result.get("status") == "blocked" else 0


def _read_json_required(path_text: str | None, *, label: str) -> Any:
    path = Path(str(path_text or "").strip())
    if not path.exists():
        raise SystemExit(f"{label} input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
