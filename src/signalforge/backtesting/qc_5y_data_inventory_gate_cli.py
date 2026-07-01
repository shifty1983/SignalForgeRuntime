from __future__ import annotations

import argparse
import json

from signalforge.backtesting.qc_5y_data_inventory_gate import (
    build_qc_5y_data_inventory_gate,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build QC 5-year data inventory coverage gate."
    )

    parser.add_argument(
        "--split-inventory-path",
        required=True,
        help="Path to signalforge_qc_5y_data_inventory_split.json.",
    )

    parser.add_argument(
        "--policy-path",
        required=True,
        help="Path to qc_5y_data_inventory_symbol_policy.json.",
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for gate artifacts.",
    )

    args = parser.parse_args()

    artifact = build_qc_5y_data_inventory_gate(
        split_inventory_path=args.split_inventory_path,
        policy_path=args.policy_path,
        output_dir=args.output_dir,
    )

    printable = {
        "adapter_type": artifact["adapter_type"],
        "artifact_type": artifact["artifact_type"],
        "contract": artifact["contract"],
        "status": artifact["status"],
        "is_ready": artifact["is_ready"],
        "blocker_count": artifact["blocker_count"],
        "blockers": artifact["blockers"],
        "source_coverage": artifact["source_coverage"],
        "required_coverage_failures": artifact["required_coverage_failures"],
        "gap_classification": {
            "market_symbols_missing_option_behavior_count": artifact[
                "gap_classification"
            ]["market_symbols_missing_option_behavior_count"],
            "accepted_missing_option_behavior_count": artifact["gap_classification"][
                "accepted_missing_option_behavior_count"
            ],
            "unclassified_market_symbols_missing_option_behavior_count": artifact[
                "gap_classification"
            ]["unclassified_market_symbols_missing_option_behavior_count"],
            "option_underlyings_missing_contract_outcomes_count": artifact[
                "gap_classification"
            ]["option_underlyings_missing_contract_outcomes_count"],
            "accepted_missing_contract_outcomes_count": artifact["gap_classification"][
                "accepted_missing_contract_outcomes_count"
            ],
            "unclassified_option_underlyings_missing_contract_outcomes_count": artifact[
                "gap_classification"
            ]["unclassified_option_underlyings_missing_contract_outcomes_count"],
        },
        "policy_conflicts": artifact["policy_conflicts"],
    }

    print(json.dumps(printable, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
