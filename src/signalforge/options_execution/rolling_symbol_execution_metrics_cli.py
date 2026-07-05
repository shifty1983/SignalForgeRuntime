from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.signalforge.options_execution.rolling_symbol_execution_metrics import (
    build_rolling_symbol_execution_metrics,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build rolling/as-of symbol execution metrics from symbol/date execution metrics."
    )
    parser.add_argument("--symbol-date-metrics", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--windows", nargs="+", type=int, default=[20, 60, 252])

    args = parser.parse_args()

    summary = build_rolling_symbol_execution_metrics(
        symbol_date_metrics_path=Path(args.symbol_date_metrics),
        output_dir=Path(args.output_dir),
        windows=args.windows,
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("is_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
