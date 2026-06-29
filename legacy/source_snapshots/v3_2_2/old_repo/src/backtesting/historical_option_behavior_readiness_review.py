# src/backtesting/historical_option_behavior_readiness_review.py

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


REVIEW_TYPE = "historical_option_behavior_readiness_review"

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
]

REQUIRED_OPTIONS_ANALYTICS_FIELDS = {
    "symbol",
    "implied_volatility",
    "volume",
    "open_interest",
    "spread_pct",
}

PREFERRED_OPTIONS_ANALYTICS_FIELDS = {
    "liquidity_regime",
    "iv_rv_ratio",
    "vol_premium_regime",
    "skew_regime",
    "term_structure_regime",
    "delta",
    "gamma",
    "theta",
    "vega",
}

REQUIRED_OPTION_BEHAVIOR_FIELDS = {
    "iv_behavior",
    "vol_premium_behavior",
    "liquidity_behavior",
    "skew_behavior",
    "term_structure_behavior",
    "greek_behavior",
    "option_behavior_score",
    "option_behavior_state",
}

REQUIRED_STRATEGY_HANDOFF_FIELDS = {
    "artifact_type",
    "status",
    "symbol",
    "strategy_generation_mode",
    "option_behavior_context",
    "strategy_generation_constraints",
}

REQUIRED_HISTORICAL_EVALUATION_FIELDS = {
    "evaluation_status",
    "is_blocked",
    "summary",
    "evaluated_rows",
}

REQUIRED_FINAL_REVIEW_EXPORT_FIELDS = {
    "export_status",
    "is_blocked",
}


def build_historical_option_behavior_readiness_review(
    *,
    options_analytics_rows: Sequence[Mapping[str, Any]] | None = None,
    option_behavior_result: Mapping[str, Any] | None = None,
    option_behavior_strategy_handoff: Mapping[str, Any] | None = None,
    historical_evaluation_report: Mapping[str, Any] | None = None,
    final_review_export: Mapping[str, Any] | None = None,
    review_name: str = REVIEW_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Review readiness of the option-aware historical pipeline.

    This is a pure readiness artifact. It does not calculate options analytics,
    classify option behavior, generate strategies, attach historical outcomes,
    create operation records, write logs, audit records, route orders, submit
    orders, model fills, model slippage, or perform live execution.
    """

    metadata_dict = dict(metadata or {})

    checks = [
        *_check_options_analytics_rows(options_analytics_rows),
        *_check_option_behavior_result(option_behavior_result),
        *_check_option_behavior_strategy_handoff(option_behavior_strategy_handoff),
        *_check_historical_evaluation_report(historical_evaluation_report),
        *_check_final_review_export(final_review_export),
    ]

    ready_checks = [check for check in checks if check["status"] == "ready"]
    needs_review_checks = [
        check for check in checks if check["status"] == "needs_review"
    ]
    blocked_checks = [check for check in checks if check["status"] == "blocked"]

    readiness_status = _readiness_status(
        blocked_checks=blocked_checks,
        needs_review_checks=needs_review_checks,
    )

    warnings = _unique_ordered(
        [
            reason
            for check in needs_review_checks
            for reason in check.get("reasons", [])
        ]
    )

    blocked_reasons = _unique_ordered(
        [
            reason
            for check in blocked_checks
            for reason in check.get("reasons", [])
        ]
    )

    return {
        "review_type": REVIEW_TYPE,
        "review_name": review_name,
        "readiness_status": readiness_status,
        "is_ready": readiness_status == "ready",
        "is_blocked": readiness_status == "blocked",
        "check_summary": {
            "total": len(checks),
            "ready": len(ready_checks),
            "needs_review": len(needs_review_checks),
            "blocked": len(blocked_checks),
        },
        "checks": checks,
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "ready_components": [
            check["component"]
            for check in ready_checks
        ],
        "not_ready_components": [
            check["component"]
            for check in needs_review_checks + blocked_checks
        ],
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "metadata": metadata_dict,
    }


def _check_options_analytics_rows(
    rows: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    component = "options_analytics_rows"

    if rows is None:
        return [
            _needs_review_check(
                component,
                ["options analytics rows were not provided"],
            )
        ]

    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return [
            _blocked_check(
                component,
                ["options analytics rows must be a sequence of mappings"],
            )
        ]

    if not rows:
        return [
            _blocked_check(
                component,
                ["options analytics rows are empty"],
            )
        ]

    required_missing_by_row: list[str] = []
    preferred_missing: set[str] = set(PREFERRED_OPTIONS_ANALYTICS_FIELDS)

    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            return [
                _blocked_check(
                    component,
                    [f"options analytics row {index} must be a mapping"],
                )
            ]

        missing_required = sorted(
            REQUIRED_OPTIONS_ANALYTICS_FIELDS - set(row.keys())
        )

        if missing_required:
            required_missing_by_row.append(
                f"row {index} missing required fields: {missing_required}"
            )

        preferred_missing &= PREFERRED_OPTIONS_ANALYTICS_FIELDS - set(row.keys())

    if required_missing_by_row:
        return [_blocked_check(component, required_missing_by_row)]

    if preferred_missing:
        return [
            _needs_review_check(
                component,
                [
                    "options analytics rows are missing preferred fields: "
                    f"{sorted(preferred_missing)}"
                ],
            )
        ]

    return [_ready_check(component)]


def _check_option_behavior_result(
    result: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    component = "option_behavior_result"

    if result is None:
        return [
            _needs_review_check(
                component,
                ["option behavior result was not provided"],
            )
        ]

    if not isinstance(result, Mapping):
        return [
            _blocked_check(
                component,
                ["option behavior result must be a mapping"],
            )
        ]

    missing = sorted(REQUIRED_OPTION_BEHAVIOR_FIELDS - set(result.keys()))

    if missing:
        return [
            _blocked_check(
                component,
                [f"option behavior result missing required fields: {missing}"],
            )
        ]

    option_behavior_state = result.get("option_behavior_state")

    if option_behavior_state not in {"supportive", "neutral", "constrained"}:
        return [
            _blocked_check(
                component,
                [
                    "option behavior result has invalid option_behavior_state: "
                    f"{option_behavior_state}"
                ],
            )
        ]

    if option_behavior_state == "constrained":
        return [
            _needs_review_check(
                component,
                ["option behavior result is constrained"],
            )
        ]

    return [_ready_check(component)]


def _check_option_behavior_strategy_handoff(
    handoff: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    component = "option_behavior_strategy_handoff"

    if handoff is None:
        return [
            _needs_review_check(
                component,
                ["option behavior strategy handoff was not provided"],
            )
        ]

    if not isinstance(handoff, Mapping):
        return [
            _blocked_check(
                component,
                ["option behavior strategy handoff must be a mapping"],
            )
        ]

    missing = sorted(REQUIRED_STRATEGY_HANDOFF_FIELDS - set(handoff.keys()))

    if missing:
        return [
            _blocked_check(
                component,
                [
                    "option behavior strategy handoff missing required fields: "
                    f"{missing}"
                ],
            )
        ]

    if handoff.get("status") == "blocked":
        return [
            _blocked_check(
                component,
                ["option behavior strategy handoff is blocked"],
            )
        ]

    constraints = handoff.get("strategy_generation_constraints", [])

    if (
        isinstance(constraints, list)
        and "block_options_candidate_generation" in constraints
    ):
        return [
            _needs_review_check(
                component,
                [
                    "option behavior strategy handoff blocks options candidate generation"
                ],
            )
        ]

    if handoff.get("status") == "needs_review":
        return [
            _needs_review_check(
                component,
                ["option behavior strategy handoff needs review"],
            )
        ]

    return [_ready_check(component)]


def _check_historical_evaluation_report(
    report: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    component = "historical_evaluation_report"

    if report is None:
        return [
            _needs_review_check(
                component,
                ["historical evaluation report was not provided"],
            )
        ]

    if not isinstance(report, Mapping):
        return [
            _blocked_check(
                component,
                ["historical evaluation report must be a mapping"],
            )
        ]

    missing = sorted(REQUIRED_HISTORICAL_EVALUATION_FIELDS - set(report.keys()))

    if missing:
        return [
            _blocked_check(
                component,
                [
                    "historical evaluation report missing required fields: "
                    f"{missing}"
                ],
            )
        ]

    if bool(report.get("is_blocked")):
        return [
            _blocked_check(
                component,
                ["historical evaluation report is blocked"],
            )
        ]

    summary = report.get("summary", {})
    evaluated_rows = report.get("evaluated_rows", [])

    if not isinstance(summary, Mapping):
        return [
            _blocked_check(
                component,
                ["historical evaluation summary must be a mapping"],
            )
        ]

    if not isinstance(evaluated_rows, list):
        return [
            _blocked_check(
                component,
                ["historical evaluation evaluated_rows must be a list"],
            )
        ]

    option_context_count = summary.get("option_behavior_context_count")

    if option_context_count is None:
        option_context_count = sum(
            1
            for row in evaluated_rows
            if isinstance(row, Mapping)
            and row.get("option_behavior_state") is not None
        )

    if int(option_context_count or 0) <= 0:
        return [
            _needs_review_check(
                component,
                ["historical evaluation has no option behavior context"],
            )
        ]

    return [_ready_check(component)]


def _check_final_review_export(
    final_review_export: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    component = "final_review_export"

    if final_review_export is None:
        return [
            _needs_review_check(
                component,
                ["final review export was not provided"],
            )
        ]

    if not isinstance(final_review_export, Mapping):
        return [
            _blocked_check(
                component,
                ["final review export must be a mapping"],
            )
        ]

    missing = sorted(REQUIRED_FINAL_REVIEW_EXPORT_FIELDS - set(final_review_export.keys()))

    if missing:
        return [
            _blocked_check(
                component,
                [f"final review export missing required fields: {missing}"],
            )
        ]

    if bool(final_review_export.get("is_blocked")):
        return [
            _blocked_check(
                component,
                ["final review export is blocked"],
            )
        ]

    final_items = _final_review_items(final_review_export)

    if not final_items:
        return [
            _needs_review_check(
                component,
                ["final review export has no final review items"],
            )
        ]

    missing_option_review_count = sum(
        1
        for item in final_items
        if not isinstance(item.get("option_behavior_review"), Mapping)
        or not item["option_behavior_review"].get("attached")
    )

    if missing_option_review_count:
        return [
            _needs_review_check(
                component,
                [
                    "final review export contains final review items without "
                    f"attached option behavior review: {missing_option_review_count}"
                ],
            )
        ]

    return [_ready_check(component)]


def _final_review_items(
    final_review_export: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    items: list[Mapping[str, Any]] = []

    for field_name in [
        "ready_final_review",
        "needs_review_final_review",
        "blocked_final_review",
        "ready_final_review_exports",
        "needs_review_final_review_exports",
        "blocked_final_review_exports",
    ]:
        value = final_review_export.get(field_name)

        if isinstance(value, list):
            items.extend(
                item
                for item in value
                if isinstance(item, Mapping)
            )

    return items


def _readiness_status(
    *,
    blocked_checks: list[dict[str, Any]],
    needs_review_checks: list[dict[str, Any]],
) -> str:
    if blocked_checks:
        return "blocked"

    if needs_review_checks:
        return "needs_review"

    return "ready"


def _ready_check(component: str) -> dict[str, Any]:
    return {
        "component": component,
        "status": "ready",
        "reasons": [],
    }


def _needs_review_check(
    component: str,
    reasons: list[str],
) -> dict[str, Any]:
    return {
        "component": component,
        "status": "needs_review",
        "reasons": reasons,
    }


def _blocked_check(
    component: str,
    reasons: list[str],
) -> dict[str, Any]:
    return {
        "component": component,
        "status": "blocked",
        "reasons": reasons,
    }


def _unique_ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)

    return result
