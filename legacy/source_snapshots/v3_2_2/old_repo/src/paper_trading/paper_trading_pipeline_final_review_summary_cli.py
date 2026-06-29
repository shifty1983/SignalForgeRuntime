from __future__ import annotations

import argparse
import json

from src.paper_trading.paper_trading_pipeline_final_review_summary import (
    export_paper_trading_pipeline_final_review_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export paper trading pipeline final review summary."
    )
    parser.add_argument("--primary-strategy-candidate-profile-operation", required=True)
    parser.add_argument("--ibkr-paper-trading-readiness-operation", required=True)
    parser.add_argument("--ibkr-paper-connection-smoke-test-operation", required=True)
    parser.add_argument("--ibkr-paper-account-snapshot-operation", required=True)
    parser.add_argument("--primary-strategy-paper-order-intent-operation", required=True)
    parser.add_argument("--ibkr-option-contract-resolver-operation", required=True)
    parser.add_argument("--ibkr-option-quote-validation-operation", required=True)
    parser.add_argument("--paper-order-preview-operation", required=True)
    parser.add_argument("--manual-approval-ticket-operation", required=True)
    parser.add_argument("--output-dir", required=True)

    args = parser.parse_args()

    result = export_paper_trading_pipeline_final_review_summary(
        primary_strategy_candidate_profile_operation_path=args.primary_strategy_candidate_profile_operation,
        ibkr_paper_trading_readiness_operation_path=args.ibkr_paper_trading_readiness_operation,
        ibkr_paper_connection_smoke_test_operation_path=args.ibkr_paper_connection_smoke_test_operation,
        ibkr_paper_account_snapshot_operation_path=args.ibkr_paper_account_snapshot_operation,
        primary_strategy_paper_order_intent_operation_path=args.primary_strategy_paper_order_intent_operation,
        ibkr_option_contract_resolver_operation_path=args.ibkr_option_contract_resolver_operation,
        ibkr_option_quote_validation_operation_path=args.ibkr_option_quote_validation_operation,
        paper_order_preview_operation_path=args.paper_order_preview_operation,
        manual_approval_ticket_operation_path=args.manual_approval_ticket_operation,
        output_dir=args.output_dir,
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())