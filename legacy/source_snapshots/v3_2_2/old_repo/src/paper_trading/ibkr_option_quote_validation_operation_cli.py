from __future__ import annotations

import argparse
import json

from src.paper_trading.ibkr_option_quote_validation_export import (
    DEFAULT_TIMEOUT_SECONDS,
)
from src.paper_trading.ibkr_option_quote_validation_operation import (
    run_ibkr_option_quote_validation_operation,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the IBKR option quote validation operation."
    )
    parser.add_argument(
        "--option-contract-resolver-operation",
        required=True,
        help="Path to IBKR option contract resolver operation record JSON.",
    )
    parser.add_argument(
        "--account-snapshot-operation",
        required=True,
        help="Path to IBKR paper account snapshot operation record JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where option quote validation operation artifacts should be written.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="IBKR API timeout in seconds. Defaults to 12 seconds.",
    )

    args = parser.parse_args()

    result = run_ibkr_option_quote_validation_operation(
        option_contract_resolver_operation_path=args.option_contract_resolver_operation,
        account_snapshot_operation_path=args.account_snapshot_operation,
        output_dir=args.output_dir,
        timeout_seconds=args.timeout_seconds,
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())