from __future__ import annotations

import argparse
import json

from src.backtesting.historical_behavior_row_normalizer import (
    build_historical_behavior_rows,
    load_json,
    write_historical_behavior_rows,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize QC historical regime, market price, and option rows into Phase 2 historical behavior rows."
    )

    parser.add_argument("--regime-date-map", required=True)
    parser.add_argument("--market-price-input", required=True)
    parser.add_argument("--option-behavior-input-jsonl", default=None)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--short-window", type=int, default=20)
    parser.add_argument("--long-window", type=int, default=50)

    args = parser.parse_args()

    artifact = build_historical_behavior_rows(
        regime_date_map=load_json(args.regime_date_map),
        market_price_input=load_json(args.market_price_input),
        option_behavior_input_jsonl=args.option_behavior_input_jsonl,
        start_date=args.start_date,
        end_date=args.end_date,
        short_window=args.short_window,
        long_window=args.long_window,
    )

    files = write_historical_behavior_rows(artifact, args.output_dir)

    print(
        json.dumps(
            {
                "adapter_type": artifact["adapter_type"],
                "artifact_type": artifact["artifact_type"],
                "contract": artifact["contract"],
                "is_ready": artifact["is_ready"],
                "blocker_count": artifact["blocker_count"],
                "blockers": artifact["blockers"],
                "summary": artifact["summary"],
                "files": files,
            },
            indent=2,
            sort_keys=True,
        )
    )

    return 0 if artifact["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
