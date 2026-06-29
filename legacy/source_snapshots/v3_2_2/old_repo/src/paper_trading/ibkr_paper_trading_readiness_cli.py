from __future__ import annotations

import argparse
import json

from src.paper_trading.ibkr_paper_trading_readiness import (
    run_ibkr_paper_trading_readiness_operation,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the IBKR paper trading readiness operation."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the local IBKR paper trading config JSON.",
    )
    parser.add_argument(
        "--strategy-profile-operation",
        required=True,
        help="Path to the primary strategy candidate profile export operation record.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where readiness operation artifacts should be written.",
    )

    args = parser.parse_args()

    result = run_ibkr_paper_trading_readiness_operation(
        config_path=args.config,
        strategy_profile_operation_path=args.strategy_profile_operation,
        output_dir=args.output_dir,
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())