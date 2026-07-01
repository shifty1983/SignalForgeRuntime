from __future__ import annotations

import argparse
import json

from signalforge.backtesting.qc_5y_data_inventory_split import build_qc_5y_data_inventory_split


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build split summary from QC 5-year data inventory."
    )

    parser.add_argument(
        "--inventory-path",
        required=True,
        help="Path to signalforge_qc_5y_data_inventory.json.",
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for split inventory artifacts.",
    )

    args = parser.parse_args()

    artifact = build_qc_5y_data_inventory_split(
        inventory_path=args.inventory_path,
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
        "warnings": artifact["warnings"],
        "cross_checks": artifact["cross_checks"],
        "groups": {
            name: {
                "file_count": group["file_count"],
                "row_count": group["row_count"],
                "date_min": group["date_min"],
                "date_max": group["date_max"],
                "market_price_symbol_count": group["market_price_symbol_count"],
                "option_underlying_symbol_count": group["option_underlying_symbol_count"],
                "option_contract_symbol_count": group["option_contract_symbol_count"],
                "contract_outcome_underlying_symbol_count": group["contract_outcome_underlying_symbol_count"],
                "contract_outcome_option_contract_symbol_count": group["contract_outcome_option_contract_symbol_count"],
            }
            for name, group in artifact["groups"].items()
        },
    }

    print(json.dumps(printable, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

