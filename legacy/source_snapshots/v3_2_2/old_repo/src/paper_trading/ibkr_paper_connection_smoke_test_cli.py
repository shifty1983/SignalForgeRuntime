from __future__ import annotations

import argparse
import json

from src.paper_trading.ibkr_paper_connection_smoke_test import (
    DEFAULT_TIMEOUT_SECONDS,
    run_ibkr_paper_connection_smoke_test_operation,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the IBKR paper connection smoke test operation."
    )
    parser.add_argument(
        "--readiness-operation",
        required=True,
        help="Path to the IBKR paper trading readiness operation record JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where connection smoke test operation artifacts should be written.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Socket timeout in seconds. Defaults to 3 seconds.",
    )

    args = parser.parse_args()

    result = run_ibkr_paper_connection_smoke_test_operation(
        readiness_operation_path=args.readiness_operation,
        output_dir=args.output_dir,
        timeout_seconds=args.timeout_seconds,
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())