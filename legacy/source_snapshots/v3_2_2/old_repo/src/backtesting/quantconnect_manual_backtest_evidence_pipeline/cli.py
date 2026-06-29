from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.backtesting.quantconnect_manual_backtest_evidence_pipeline.builder import (
    StageFunction,
)
from src.backtesting.quantconnect_manual_backtest_evidence_pipeline.file_writer import (
    write_quantconnect_manual_backtest_evidence_pipeline_files,
)


CLI_SUMMARY_SCHEMA_VERSION = (
    "quantconnect_manual_backtest_evidence_pipeline_cli_summary.v1"
)


def main(
    argv: Sequence[str] | None = None,
    *,
    stage_functions: Mapping[str, StageFunction] | None = None,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        source = _read_json(args.source)
    except FileNotFoundError:
        print(f"source file not found: {args.source}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as error:
        print(f"source file is not valid JSON: {error}", file=sys.stderr)
        return 2

    result = write_quantconnect_manual_backtest_evidence_pipeline_files(
        source,
        output_dir=args.output_dir,
        stage_functions=stage_functions,
    )

    summary = _build_cli_summary(result)
    print(json.dumps(summary, indent=2, sort_keys=True))

    if result.get("status") == "blocked":
        return 1

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the local manual QuantConnect backtest evidence pipeline from a "
            "manual QuantConnect result import source JSON. This command writes "
            "local files only and does not call QuantConnect, brokers, market-data "
            "APIs, order-routing systems, live execution systems, fill engines, "
            "slippage engines, or external data warehouses."
        )
    )

    parser.add_argument(
        "--source",
        required=True,
        help="Path to manual QuantConnect result import source JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where pipeline artifacts should be written.",
    )

    return parser


def _read_json(path: str) -> Any:
    source_path = Path(path)
    with source_path.open(encoding="utf-8") as file:
        return json.load(file)


def _build_cli_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    operation_result = result.get("operation_result")
    operation_result = operation_result if isinstance(operation_result, dict) else {}

    operation_record = operation_result.get("operation_record")
    operation_record = operation_record if isinstance(operation_record, dict) else {}

    health_report = operation_result.get("health_report")
    health_report = health_report if isinstance(health_report, dict) else {}

    pipeline_result = operation_result.get("pipeline_result")
    pipeline_result = pipeline_result if isinstance(pipeline_result, dict) else {}

    final_summary = operation_result.get("final_summary")
    final_summary = final_summary if isinstance(final_summary, dict) else {}

    stage_statuses = pipeline_result.get("stage_statuses")
    stage_statuses = stage_statuses if isinstance(stage_statuses, dict) else {}
    
    promotion_handoff = operation_result.get("promotion_handoff")
    promotion_handoff = (
        promotion_handoff
        if isinstance(promotion_handoff, dict)
        else {}
    )

    handoff_summary = promotion_handoff.get("summary")
    handoff_summary = (
        handoff_summary
        if isinstance(handoff_summary, dict)
        else {}
    )

    promoted_items = promotion_handoff.get("promoted_items")
    promoted_items = (
        promoted_items
        if isinstance(promoted_items, list)
        else []
    )

    strategy_ids = promotion_handoff.get("strategy_ids")
    strategy_ids = strategy_ids if isinstance(strategy_ids, list) else []

    symbols = promotion_handoff.get("symbols")
    symbols = symbols if isinstance(symbols, list) else []

    backtest_ids = promotion_handoff.get("backtest_ids")
    backtest_ids = backtest_ids if isinstance(backtest_ids, list) else []

    evidence_ids = promotion_handoff.get("evidence_ids")
    evidence_ids = evidence_ids if isinstance(evidence_ids, list) else []

    downstream_intake = operation_result.get("downstream_intake")
    downstream_intake = (
        downstream_intake
        if isinstance(downstream_intake, dict)
        else {}
    )

    downstream_summary = downstream_intake.get("summary")
    downstream_summary = (
        downstream_summary
        if isinstance(downstream_summary, dict)
        else {}
    )

    intake_items = downstream_intake.get("intake_items")
    intake_items = intake_items if isinstance(intake_items, list) else []

    intake_strategy_ids = downstream_intake.get("strategy_ids")
    intake_strategy_ids = (
        intake_strategy_ids
        if isinstance(intake_strategy_ids, list)
        else []
    )

    intake_symbols = downstream_intake.get("symbols")
    intake_symbols = intake_symbols if isinstance(intake_symbols, list) else []

    intake_backtest_ids = downstream_intake.get("backtest_ids")
    intake_backtest_ids = (
        intake_backtest_ids
        if isinstance(intake_backtest_ids, list)
        else []
    )

    intake_evidence_ids = downstream_intake.get("evidence_ids")
    intake_evidence_ids = (
        intake_evidence_ids
        if isinstance(intake_evidence_ids, list)
        else []
    )

    return {
        "schema_version": CLI_SUMMARY_SCHEMA_VERSION,
        "status": result.get("status", "needs_review"),
        "output_dir": result.get("output_dir"),
        "files": result.get("files", {}),
        "file_summary": result.get("file_summary", {}),
        "operation_summary": operation_record.get("summary", {}),
        "health_status": health_report.get("status"),
        "health_recommendations": health_report.get("recommendations", []),
        "stage_counts": {
            "completed": len(stage_statuses),
            "ready": sum(1 for status in stage_statuses.values() if status == "ready"),
            "needs_review": sum(
                1 for status in stage_statuses.values() if status == "needs_review"
            ),
            "blocked": sum(
                1 for status in stage_statuses.values() if status == "blocked"
            ),
        },
        "stage_statuses": stage_statuses,
        "final_summary_status": final_summary.get("status"),
        "promotion_handoff_status": promotion_handoff.get("status"),
        "handoff_counts": {
            "promoted_items": len(promoted_items),
            "strategies": len(strategy_ids),
            "symbols": len(symbols),
            "backtests": len(backtest_ids),
            "evidence": len(evidence_ids),
        },
        "can_enter_downstream_historical_research": bool(
            handoff_summary.get("can_enter_downstream_historical_research")
        ),
        "strategy_ids": strategy_ids,
        "symbols": symbols,
        "backtest_ids": backtest_ids,
        "evidence_ids": evidence_ids,
        "downstream_intake_status": downstream_intake.get("status"),
        "intake_counts": {
            "items": len(intake_items),
            "strategies": len(intake_strategy_ids),
            "symbols": len(intake_symbols),
            "backtests": len(intake_backtest_ids),
            "evidence": len(intake_evidence_ids),
        },
        "can_enter_expected_value_research": bool(
            downstream_summary.get("can_enter_expected_value_research")
        ),
        "can_enter_strategy_selection": bool(
            downstream_summary.get("can_enter_strategy_selection")
        ),
        "intake_strategy_ids": intake_strategy_ids,
        "intake_symbols": intake_symbols,
        "intake_backtest_ids": intake_backtest_ids,
        "intake_evidence_ids": intake_evidence_ids,
        "warnings": pipeline_result.get("warnings", []),
        "blocked_reasons": pipeline_result.get("blocked_reasons", []),
        "explicit_exclusions": result.get("explicit_exclusions", []),
    }


if __name__ == "__main__":
    raise SystemExit(main())
