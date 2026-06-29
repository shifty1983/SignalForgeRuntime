from __future__ import annotations

import argparse
import json

from src.paper_trading.primary_strategy_paper_order_intent_operation import (
    run_primary_strategy_paper_order_intent_operation,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the primary strategy paper order intent operation."
    )
    parser.add_argument(
        "--strategy-profile-operation",
        required=True,
        help="Path to primary strategy candidate profile export operation record JSON.",
    )
    parser.add_argument(
        "--account-snapshot-operation",
        required=True,
        help="Path to IBKR paper account snapshot import operation record JSON.",
    )
    parser.add_argument(
        "--order-intent-config",
        required=True,
        help="Path to local paper order intent config JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where paper order intent operation artifacts should be written.",
    )

    args = parser.parse_args()

    result = run_primary_strategy_paper_order_intent_operation(
        strategy_profile_operation_path=args.strategy_profile_operation,
        account_snapshot_operation_path=args.account_snapshot_operation,
        order_intent_config_path=args.order_intent_config,
        output_dir=args.output_dir,
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())