from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.engines.behavior.market_price_behavior import (
    DEFAULT_LONG_WINDOW,
    DEFAULT_SHORT_WINDOW,
    build_signalforge_asset_behavior_from_market_price_history,
)
from src.signalforge.engines.behavior.market_price_behavior_file_writer import (
    build_asset_behavior_from_market_price_history_summary,
    write_asset_behavior_from_market_price_history_result,
)


DEFAULT_MARKET_PRICE_SOURCE = "artifacts/qc_replay_5y_behavior_inputs/signalforge_qc_replay_market_price_behavior_input.json"
DEFAULT_OUTPUT_DIR = "artifacts/asset_behavior_from_market_price_history"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge asset behavior from imported market price history."
    )

    parser.add_argument(
        "--source",
        default=DEFAULT_MARKET_PRICE_SOURCE,
        help=(
            "Path to market price input JSON. Defaults to the stable QC 5Y "
            "behavior input artifact."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for output artifacts.",
    )
    parser.add_argument(
        "--symbol",
        action="append",
        default=[],
        help="Optional symbol filter. Can be repeated.",
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help="Optional comma-separated symbol filter.",
    )
    parser.add_argument("--short-window", type=int, default=DEFAULT_SHORT_WINDOW)
    parser.add_argument("--long-window", type=int, default=DEFAULT_LONG_WINDOW)
    parser.add_argument("--annualization-factor", type=int, default=252)

    args = parser.parse_args(argv)

    source_path = Path(args.source)
    if not source_path.exists():
        raise SystemExit(f"source file does not exist: {source_path}")

    source = _read_json(source_path)
    symbols = _merge_symbols(args.symbol, args.symbols)

    result = build_signalforge_asset_behavior_from_market_price_history(
        source,
        symbols=symbols,
        short_window=args.short_window,
        long_window=args.long_window,
        annualization_factor=args.annualization_factor,
    )

    summary = write_asset_behavior_from_market_price_history_result(
        result=result,
        output_dir=args.output_dir,
    )

    # Refresh summary file size now that the summary has been written.
    summary_path = Path(summary["files"]["summary"])
    result_path = Path(summary["files"]["asset_behavior_result"])
    summary["file_summary"]["file_sizes"]["summary"] = (
        summary_path.stat().st_size if summary_path.exists() else 0
    )
    summary["file_summary"]["file_sizes"]["asset_behavior_result"] = (
        result_path.stat().st_size if result_path.exists() else 0
    )

    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))

    return 0 if result.get("status") in {"ready", "needs_review"} else 1


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _merge_symbols(repeated_symbols: Sequence[str], comma_symbols: str | None) -> list[str] | None:
    merged: list[str] = []

    for symbol in repeated_symbols:
        cleaned = str(symbol).strip().upper()
        if cleaned:
            merged.append(cleaned)

    if comma_symbols:
        for symbol in comma_symbols.split(","):
            cleaned = symbol.strip().upper()
            if cleaned:
                merged.append(cleaned)

    unique = sorted(set(merged))
    return unique or None


if __name__ == "__main__":
    raise SystemExit(main())

