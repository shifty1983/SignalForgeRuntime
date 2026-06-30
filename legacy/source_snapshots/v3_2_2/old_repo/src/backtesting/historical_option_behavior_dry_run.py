# src/backtesting/historical_option_behavior_dry_run.py

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import polars as pl

from src.backtesting.historical_option_behavior_readiness_review import (
    build_historical_option_behavior_readiness_review,
)
from src.option_behavior import (
    build_option_behavior_strategy_handoff,
    classify_option_behavior,
)
from src.signalforge.engines.options.historical_option_analytics_contract import (
    build_historical_option_analytics_input_contract,
)


DRY_RUN_TYPE = "historical_option_behavior_dry_run"

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
]


def run_historical_option_behavior_dry_run(
    raw_option_rows: Sequence[Mapping[str, Any]] | None,
    asset_behavior_result: Mapping[str, Any],
    *,
    historical_evaluation_report: Mapping[str, Any] | None = None,
    final_review_export: Mapping[str, Any] | None = None,
    field_aliases: Mapping[str, Sequence[str]] | None = None,
    dry_run_name: str = DRY_RUN_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Run a real-data-style dry run for option behavior readiness.

    This dry run validates raw option rows, normalizes them into canonical option
    analytics rows, classifies option behavior, builds the strategy handoff, and
    runs the option-aware historical readiness review.

    It does not run full historical validation, attach outcomes, generate orders,
    route orders, submit orders, model fills, model slippage, or perform live
    execution.
    """

    metadata_dict = dict(metadata or {})

    contract = build_historical_option_analytics_input_contract(
        raw_option_rows,
        field_aliases=field_aliases,
        contract_name=f"{dry_run_name}_input_contract",
        metadata=metadata_dict,
    )

    if contract["is_blocked"]:
        return _dry_run_result(
            dry_run_name=dry_run_name,
            dry_run_status="blocked",
            contract=contract,
            option_behavior_result={},
            option_behavior_strategy_handoff={},
            readiness_review={},
            warnings=list(contract.get("warnings", [])),
            blocked_reasons=list(contract.get("blocked_reasons", [])),
            metadata=metadata_dict,
        )

    option_behavior_result = classify_option_behavior(
        pl.DataFrame(contract["normalized_rows"])
    )

    options_analytics_context = _options_analytics_context_from_contract(contract)

    strategy_handoff = build_option_behavior_strategy_handoff(
        asset_behavior_result=asset_behavior_result,
        option_behavior_result=option_behavior_result,
        options_analytics_context=options_analytics_context,
    )

    readiness_review = build_historical_option_behavior_readiness_review(
        options_analytics_rows=contract["normalized_rows"],
        option_behavior_result=option_behavior_result,
        option_behavior_strategy_handoff=strategy_handoff,
        historical_evaluation_report=historical_evaluation_report,
        final_review_export=final_review_export,
        review_name=f"{dry_run_name}_readiness_review",
        metadata=metadata_dict,
    )

    warnings = _unique_ordered(
        [
            *list(contract.get("warnings", [])),
            *list(strategy_handoff.get("warnings", [])),
            *list(readiness_review.get("warnings", [])),
        ]
    )

    blocked_reasons = _unique_ordered(
        [
            *list(contract.get("blocked_reasons", [])),
            *list(strategy_handoff.get("blocked_reasons", [])),
            *list(readiness_review.get("blocked_reasons", [])),
        ]
    )

    dry_run_status = _dry_run_status(
        contract_status=contract.get("contract_status"),
        handoff_status=strategy_handoff.get("status"),
        readiness_status=readiness_review.get("readiness_status"),
        blocked_reasons=blocked_reasons,
        warnings=warnings,
    )

    return _dry_run_result(
        dry_run_name=dry_run_name,
        dry_run_status=dry_run_status,
        contract=contract,
        option_behavior_result=option_behavior_result,
        option_behavior_strategy_handoff=strategy_handoff,
        readiness_review=readiness_review,
        warnings=warnings,
        blocked_reasons=blocked_reasons,
        metadata=metadata_dict,
    )


def _options_analytics_context_from_contract(
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    normalized_rows = contract.get("normalized_rows", [])

    if not normalized_rows:
        return {
            "status": contract.get("contract_status"),
            "source": "historical_option_analytics_input_contract",
            "contract_count": 0,
        }

    first_row = normalized_rows[0]

    if not isinstance(first_row, Mapping):
        first_row = {}

    return {
        "symbol": first_row.get("symbol"),
        "status": contract.get("contract_status"),
        "contract_count": len(normalized_rows),
        "liquidity_regime": first_row.get("liquidity_regime"),
        "vol_premium_regime": first_row.get("vol_premium_regime"),
        "skew_regime": first_row.get("skew_regime"),
        "term_structure_regime": first_row.get("term_structure_regime"),
        "source": "historical_option_analytics_input_contract",
    }


def _dry_run_status(
    *,
    contract_status: Any,
    handoff_status: Any,
    readiness_status: Any,
    blocked_reasons: list[str],
    warnings: list[str],
) -> str:
    if blocked_reasons:
        return "blocked"

    if contract_status == "blocked" or handoff_status == "blocked":
        return "blocked"

    if readiness_status == "blocked":
        return "blocked"

    if warnings:
        return "needs_review"

    if contract_status == "needs_review":
        return "needs_review"

    if handoff_status == "needs_review":
        return "needs_review"

    if readiness_status == "needs_review":
        return "needs_review"

    return "ready"


def _dry_run_result(
    *,
    dry_run_name: str,
    dry_run_status: str,
    contract: Mapping[str, Any],
    option_behavior_result: Mapping[str, Any],
    option_behavior_strategy_handoff: Mapping[str, Any],
    readiness_review: Mapping[str, Any],
    warnings: list[str],
    blocked_reasons: list[str],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "dry_run_type": DRY_RUN_TYPE,
        "dry_run_name": dry_run_name,
        "dry_run_status": dry_run_status,
        "is_ready": dry_run_status == "ready",
        "is_blocked": dry_run_status == "blocked",
        "input_contract": dict(contract),
        "option_behavior_result": dict(option_behavior_result),
        "option_behavior_strategy_handoff": dict(option_behavior_strategy_handoff),
        "readiness_review": dict(readiness_review),
        "summary": {
            "contract_status": contract.get("contract_status"),
            "normalized_row_count": contract.get("normalized_row_count", 0),
            "option_behavior_state": option_behavior_result.get(
                "option_behavior_state"
            ),
            "option_behavior_score": option_behavior_result.get(
                "option_behavior_score"
            ),
            "strategy_generation_mode": option_behavior_strategy_handoff.get(
                "strategy_generation_mode"
            ),
            "readiness_status": readiness_review.get("readiness_status"),
        },
        "warnings": _unique_ordered(warnings),
        "blocked_reasons": _unique_ordered(blocked_reasons),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "metadata": metadata,
    }


def _unique_ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)

    return result
