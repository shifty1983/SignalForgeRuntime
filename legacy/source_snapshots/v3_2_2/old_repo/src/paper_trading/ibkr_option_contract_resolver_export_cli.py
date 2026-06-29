from __future__ import annotations

import argparse
import json

from src.paper_trading.ibkr_option_contract_resolver_export import (
    DEFAULT_TIMEOUT_SECONDS,
    export_ibkr_option_contract_resolver,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export IBKR option contract resolver candidates."
    )
    parser.add_argument(
        "--paper-order-intent-operation",
        required=True,
        help="Path to primary strategy paper order intent operation record JSON.",
    )
    parser.add_argument(
        "--account-snapshot-operation",
        required=True,
        help="Path to IBKR paper account snapshot operation record JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where option contract resolver artifacts should be written.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="IBKR API timeout in seconds. Defaults to 12 seconds.",
    )

    args = parser.parse_args()

    result = export_ibkr_option_contract_resolver(
        paper_order_intent_operation_path=args.paper_order_intent_operation,
        account_snapshot_operation_path=args.account_snapshot_operation,
        output_dir=args.output_dir,
        timeout_seconds=args.timeout_seconds,
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())