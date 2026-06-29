from __future__ import annotations

import argparse
import json

from src.paper_trading.paper_order_preview_operation import (
    run_paper_order_preview_operation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run paper order preview operation.")
    parser.add_argument(
        "--paper-order-intent-operation",
        required=True,
        help="Path to primary strategy paper order intent operation record JSON.",
    )
    parser.add_argument(
        "--option-contract-resolver-operation",
        required=True,
        help="Path to IBKR option contract resolver operation record JSON.",
    )
    parser.add_argument(
        "--option-quote-validation-operation",
        required=True,
        help="Path to IBKR option quote validation operation record JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where paper order preview operation artifacts should be written.",
    )

    args = parser.parse_args()

    result = run_paper_order_preview_operation(
        paper_order_intent_operation_path=args.paper_order_intent_operation,
        option_contract_resolver_operation_path=args.option_contract_resolver_operation,
        option_quote_validation_operation_path=args.option_quote_validation_operation,
        output_dir=args.output_dir,
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())