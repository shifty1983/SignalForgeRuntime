from __future__ import annotations

import argparse
import json

from src.paper_trading.manual_approval_ticket_operation import (
    run_manual_approval_ticket_operation,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run manual approval ticket operation."
    )
    parser.add_argument(
        "--paper-order-preview-operation",
        required=True,
        help="Path to paper order preview operation record JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where manual approval ticket operation artifacts should be written.",
    )

    args = parser.parse_args()

    result = run_manual_approval_ticket_operation(
        paper_order_preview_operation_path=args.paper_order_preview_operation,
        output_dir=args.output_dir,
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())