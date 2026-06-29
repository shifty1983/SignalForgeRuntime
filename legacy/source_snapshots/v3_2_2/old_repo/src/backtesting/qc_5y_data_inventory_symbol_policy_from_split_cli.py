from __future__ import annotations

import argparse
import json

from src.backtesting.qc_5y_data_inventory_symbol_policy_from_split import (
    build_symbol_policy_from_split_inventory,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate QC 5Y inventory symbol policy from split inventory."
    )

    parser.add_argument(
        "--split-inventory-path",
        required=True,
        help="Path to signalforge_qc_5y_data_inventory_split.json.",
    )

    parser.add_argument(
        "--output-path",
        required=True,
        help="Output path for qc_5y_data_inventory_symbol_policy.json.",
    )

    args = parser.parse_args()

    policy = build_symbol_policy_from_split_inventory(
        split_inventory_path=args.split_inventory_path,
        output_path=args.output_path,
    )

    printable = {
        "artifact_type": policy["artifact_type"],
        "schema_version": policy["schema_version"],
        "source_split_inventory_path": policy["source_split_inventory_path"],
        "tradable_option_symbol_count": len(policy["tradable_option_symbols"]),
        "context_only_symbol_count": len(policy["context_only_symbols"]),
        "accepted_missing_option_behavior_symbol_count": len(
            policy["accepted_missing_option_behavior_symbols"]
        ),
        "accepted_missing_contract_outcome_symbol_count": len(
            policy["accepted_missing_contract_outcome_symbols"]
        ),
        "diagnostics": policy["diagnostics"],
    }

    print(json.dumps(printable, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())