from __future__ import annotations

import argparse
import json

from src.paper_trading.ibkr_paper_account_snapshot_import import (
    DEFAULT_TIMEOUT_SECONDS,
    run_ibkr_paper_account_snapshot_import_operation,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the IBKR paper account snapshot import operation."
    )
    parser.add_argument(
        "--smoke-test-operation",
        required=True,
        help="Path to the IBKR paper connection smoke test operation record JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where account snapshot operation artifacts should be written.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="IBKR API wait timeout in seconds. Defaults to 8 seconds.",
    )

    args = parser.parse_args()

    result = run_ibkr_paper_account_snapshot_import_operation(
        smoke_test_operation_path=args.smoke_test_operation,
        output_dir=args.output_dir,
        timeout_seconds=args.timeout_seconds,
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())