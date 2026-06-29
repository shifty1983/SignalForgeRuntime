from __future__ import annotations

import argparse
import json

from src.backtesting.historical_decision_rows import (
    build_historical_decision_rows,
    load_json,
    load_records,
    write_historical_decision_rows,
)


def _split_symbols(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build historical daily decision rows using as-of weekly regime."
    )

    parser.add_argument("--inventory-gate", required=True)
    parser.add_argument("--weekly-regime-source", required=True)
    parser.add_argument("--asset-behavior-source", required=True)
    parser.add_argument("--option-behavior-source", default=None)
    parser.add_argument("--market-price-source", default=None)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--symbols",
        default=None,
        help="Optional comma-separated symbol filter.",
    )

    args = parser.parse_args()

    inventory_gate = load_json(args.inventory_gate)

    weekly_regime_rows = load_records(
        args.weekly_regime_source,
        candidate_keys=[
            "regime_rows",
            "weekly_regime_rows",
            "historical_regime_rows",
            "rows",
            "records",
        ],
    )

    asset_behavior_rows = load_records(
        args.asset_behavior_source,
        candidate_keys=[
            "asset_behavior_rows",
            "historical_asset_behavior_rows",
            "decision_rows",
            "rows",
            "records",
        ],
    )

    option_behavior_rows = (
        load_records(
            args.option_behavior_source,
            candidate_keys=[
                "option_behavior_rows",
                "historical_option_behavior_rows",
                "decision_rows",
                "rows",
                "records",
            ],
        )
        if args.option_behavior_source
        else None
    )

    market_price_rows = (
        load_records(
            args.market_price_source,
            candidate_keys=[
                "market_price_rows",
                "price_rows",
                "history",
                "rows",
                "records",
            ],
        )
        if args.market_price_source
        else None
    )

    artifact = build_historical_decision_rows(
        inventory_gate=inventory_gate,
        regime_rows=weekly_regime_rows,
        asset_behavior_rows=asset_behavior_rows,
        option_behavior_rows=option_behavior_rows,
        market_price_rows=market_price_rows,
        start_date=args.start_date,
        end_date=args.end_date,
        symbol_overrides=_split_symbols(args.symbols),
    )

    paths = write_historical_decision_rows(artifact, args.output_dir)

    print(
        json.dumps(
            {
                "adapter_type": artifact["adapter_type"],
                "artifact_type": artifact["artifact_type"],
                "contract": artifact["contract"],
                "is_ready": artifact["is_ready"],
                "blocker_count": artifact["blocker_count"],
                "blockers": artifact["blockers"],
                "regime_asof_rule": artifact["regime_asof_rule"],
                "summary": artifact["summary"],
                "paths": paths,
            },
            indent=2,
            sort_keys=True,
        )
    )

    return 0 if artifact["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
