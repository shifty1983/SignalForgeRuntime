from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping

SCHEMA_VERSION = "quantconnect_manual_backtest_evidence_pipeline.v1"
PIPELINE_TYPE = "quantconnect_manual_backtest_evidence_pipeline"

EXPLICIT_EXCLUSIONS = [
    "quantconnect_api_calls",
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "local_fill_simulation",
    "local_slippage_modeling",
    "external_data_warehouse_access",
]


StageFunction = Callable[[Any], dict[str, Any]]


STAGE_ORDER = [
    "quantconnect_result_import",
    "quantconnect_review_summary",
    "quantconnect_review_handoff",
    "quantconnect_review_pipeline",
    "quantconnect_review_final_summary",
    "quantconnect_historical_research_adapter",
    "historical_research_evidence_intake",
    "historical_research_evidence_review",
    "historical_research_evidence_review_final_summary",
    "historical_research_evidence_promotion_gate",
    "historical_research_evidence_promotion_handoff",
    "historical_research_downstream_intake",
]


def build_quantconnect_manual_backtest_evidence_pipeline(
    source: Any,
    *,
    stage_functions: Mapping[str, StageFunction] | None = None,
) -> dict[str, Any]:
    """Run the manual QuantConnect backtest evidence pipeline in memory.

    This builder does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses.

    It composes already-local SignalForge operations from a manually imported
    QuantConnect result source into one deterministic pipeline result.
    """

    if not isinstance(source, Mapping):
        return _blocked_invalid_shape("source must be a mapping/dict")

    source_copy = deepcopy(dict(source))

    try:
        stages = (
            dict(stage_functions)
            if stage_functions is not None
            else _default_stage_functions(source_copy)
        )
    except Exception as error:  # pragma: no cover - defensive runtime guard
        return _blocked_invalid_shape(
            f"failed to load pipeline stage functions: {error}"
        )

    missing_stages = [
        stage_name for stage_name in STAGE_ORDER if stage_name not in stages
    ]
    if missing_stages:
        return _blocked_invalid_shape(
            "missing pipeline stage functions: " + ", ".join(missing_stages)
        )

    stage_results: dict[str, dict[str, Any]] = {}
    stage_statuses: dict[str, str] = {}
    current_payload: Any = source_copy
    blocked_stage_name: str | None = None

    for stage_name in STAGE_ORDER:
        stage_function = stages[stage_name]

        try:
            result = stage_function(current_payload)
        except Exception as error:
            blocked_stage_name = stage_name
            stage_results[stage_name] = _stage_exception_result(stage_name, error)
            stage_statuses[stage_name] = "blocked"
            break

        if not isinstance(result, Mapping):
            blocked_stage_name = stage_name
            stage_results[stage_name] = _stage_invalid_result(stage_name)
            stage_statuses[stage_name] = "blocked"
            break

        normalized_result = deepcopy(dict(result))
        stage_status = str(normalized_result.get("status", "needs_review"))

        stage_results[stage_name] = normalized_result
        stage_statuses[stage_name] = stage_status
        current_payload = normalized_result

        if stage_status == "blocked":
            blocked_stage_name = stage_name
            break

    warnings = _sorted_unique_text(_collect_texts(stage_results, "warnings"))
    blocked_reasons = _sorted_unique_text(
        _collect_texts(stage_results, "blocked_reasons")
    )

    if blocked_stage_name and not blocked_reasons:
        blocked_reasons = [
            f"pipeline blocked at stage: {blocked_stage_name}"
        ]

    status = _classify_pipeline_status(stage_statuses, blocked_reasons)

    final_summary_stage_result = stage_results.get(
        "historical_research_evidence_review_final_summary",
        {},
    )
    final_summary = _extract_final_summary(final_summary_stage_result)

    promotion_gate_stage_result = stage_results.get(
        "historical_research_evidence_promotion_gate",
        {},
    )
    promotion_gate = _extract_promotion_gate(promotion_gate_stage_result)
    
    promotion_handoff_stage_result = stage_results.get(
        "historical_research_evidence_promotion_handoff",
        {},
    )
    promotion_handoff = _extract_promotion_handoff(
        promotion_handoff_stage_result
    )

    downstream_intake_stage_result = stage_results.get(
        "historical_research_downstream_intake",
        {},
    )
    downstream_intake = _extract_downstream_intake(
        downstream_intake_stage_result
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "pipeline_type": PIPELINE_TYPE,
        "status": status,
        "summary": _build_pipeline_summary(
            stage_statuses=stage_statuses,
            blocked_stage_name=blocked_stage_name,
            final_summary=final_summary,
            promotion_gate=promotion_gate,
            promotion_handoff=promotion_handoff,
            downstream_intake=downstream_intake,
            warnings=warnings,
            blocked_reasons=blocked_reasons,
        ),
        "stage_order": list(STAGE_ORDER),
        "stage_statuses": stage_statuses,
        "stage_results": stage_results,
        "final_summary": final_summary,
        "promotion_gate": promotion_gate,
        "promotion_handoff": promotion_handoff,
        "downstream_intake": downstream_intake,
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _default_stage_functions(
    source: Mapping[str, Any],
) -> dict[str, StageFunction]:
    from src.backtesting.historical_research_evidence_intake import (
        run_historical_research_evidence_intake_operation,
    )
    from src.backtesting.historical_research_evidence_promotion_gate import (
        run_historical_research_evidence_promotion_gate_operation,
    )
    from src.backtesting.historical_research_evidence_review import (
        run_historical_research_evidence_review_operation,
    )
    from src.backtesting.historical_research_evidence_review_final_summary import (
        run_historical_research_evidence_review_final_summary_operation,
    )
    from src.backtesting.quantconnect_historical_research_adapter import (
        run_quantconnect_historical_research_adapter_operation,
    )
    from src.backtesting.quantconnect_result_import import (
        run_quantconnect_result_import_operation,
    )
    from src.backtesting.quantconnect_review_final_summary import (
        run_quantconnect_review_final_summary_operation,
    )
    from src.backtesting.quantconnect_review_handoff import (
        run_quantconnect_review_handoff_operation,
    )
    from src.backtesting.quantconnect_review_pipeline import (
        run_quantconnect_review_pipeline,
    )
    from src.backtesting.quantconnect_review_summary import (
        run_quantconnect_review_summary_operation,
    )
    from src.backtesting.historical_research_evidence_promotion_handoff import (
        run_historical_research_evidence_promotion_handoff_operation,
    )
    from src.backtesting.historical_research_downstream_intake import (
        run_historical_research_downstream_intake_operation,
    )

    result_import_source = _extract_result_import_source(source)
    export_operation_result = _extract_export_operation_result(source)

    stage_context: dict[str, dict[str, Any]] = {}


    def run_result_import_stage(_: Any) -> dict[str, Any]:
        result = run_quantconnect_result_import_operation(
            result_import_source
        )

        stage_context["result_import_operation_result"] = result

        return result


    def run_review_summary_stage(
        result_import_operation_result: Any,
    ) -> dict[str, Any]:
        result = run_quantconnect_review_summary_operation(
            export_operation_result,
            result_import_operation_result,
        )

        stage_context["review_summary_operation_result"] = result

        return result


    def run_review_handoff_stage(
        review_summary_operation_result: Any,
    ) -> dict[str, Any]:
        result = run_quantconnect_review_handoff_operation(
            review_summary_operation_result
        )

        stage_context["review_handoff_operation_result"] = result

        return result


    def run_review_pipeline_stage(
        _: Any,
    ) -> dict[str, Any]:
        result_import_operation_result = stage_context.get(
            "result_import_operation_result",
            {},
        )

        return run_quantconnect_review_pipeline(
            export_operation_result,
            result_import_operation_result,
        )

    return {
        "quantconnect_result_import": run_result_import_stage,
        "quantconnect_review_summary": run_review_summary_stage,
        "quantconnect_review_handoff": run_review_handoff_stage,
        "quantconnect_review_pipeline": run_review_pipeline_stage,
        "quantconnect_review_final_summary": (
            run_quantconnect_review_final_summary_operation
        ),
        "quantconnect_historical_research_adapter": (
            run_quantconnect_historical_research_adapter_operation
        ),
        "historical_research_evidence_intake": (
            run_historical_research_evidence_intake_operation
        ),
        "historical_research_evidence_review": (
            run_historical_research_evidence_review_operation
        ),
        "historical_research_evidence_review_final_summary": (
            run_historical_research_evidence_review_final_summary_operation
        ),
        "historical_research_evidence_promotion_gate": (
            run_historical_research_evidence_promotion_gate_operation
        ),
        "historical_research_evidence_promotion_handoff": (
            run_historical_research_evidence_promotion_handoff_operation
        ),
        "historical_research_downstream_intake": (
            run_historical_research_downstream_intake_operation
        ),
    }
    
def _extract_result_import_source(
    source: Mapping[str, Any],
) -> dict[str, Any]:
    direct_keys = [
        "result_import_source",
        "quantconnect_result_import_source",
        "source_result_import",
    ]

    for key in direct_keys:
        value = source.get(key)

        if isinstance(value, Mapping):
            return deepcopy(dict(value))

    return deepcopy(dict(source))


def _extract_export_operation_result(
    source: Mapping[str, Any],
) -> dict[str, Any]:
    direct_keys = [
        "export_operation_result",
        "quantconnect_export_operation_result",
        "source_export_operation_result",
    ]

    for key in direct_keys:
        value = source.get(key)

        if isinstance(value, Mapping):
            discovered = _find_mapping_with_export_payload(value)

            if discovered:
                return discovered

    return _find_mapping_with_export_payload(source)


def _find_mapping_with_export_payload(
    value: Any,
) -> dict[str, Any]:
    if isinstance(value, Mapping):
        if "export_payload" in value:
            return deepcopy(dict(value))

        for child in value.values():
            discovered = _find_mapping_with_export_payload(child)

            if discovered:
                return discovered

    if isinstance(value, list):
        for child in value:
            discovered = _find_mapping_with_export_payload(child)

            if discovered:
                return discovered

    return {}
    
def _extract_export_operation_result(
    source: Mapping[str, Any],
) -> dict[str, Any]:
    direct_keys = [
        "export_operation_result",
        "quantconnect_export_operation_result",
        "source_export_operation_result",
        "export",
    ]

    for key in direct_keys:
        value = source.get(key)

        if isinstance(value, Mapping):
            normalized = _normalize_export_operation_result(value)

            if normalized:
                return normalized

    return _find_export_operation_result(source)


def _normalize_export_operation_result(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    export = value.get("export")

    if isinstance(export, Mapping):
        return deepcopy(dict(value))

    if value.get("schema_version") == "quantconnect_export.v1":
        return deepcopy(dict(value))

    operation_result = value.get("operation_result")

    if isinstance(operation_result, Mapping):
        export = operation_result.get("export")

        if isinstance(export, Mapping):
            return deepcopy(dict(value))

    return {}


def _find_export_operation_result(
    value: Any,
) -> dict[str, Any]:
    if isinstance(value, Mapping):
        normalized = _normalize_export_operation_result(value)

        if normalized:
            return normalized

        for child in value.values():
            discovered = _find_export_operation_result(child)

            if discovered:
                return discovered

    if isinstance(value, list):
        for child in value:
            discovered = _find_export_operation_result(child)

            if discovered:
                return discovered

    return {}


def _build_pipeline_summary(
    *,
    stage_statuses: Mapping[str, str],
    blocked_stage_name: str | None,
    final_summary: Mapping[str, Any],
    promotion_gate: Mapping[str, Any],
    promotion_handoff: Mapping[str, Any],
    downstream_intake: Mapping[str, Any],
    warnings: list[str],
    blocked_reasons: list[str],
) -> dict[str, Any]:
    final_summary_payload = _as_mapping(final_summary.get("summary"))
    promotion_summary = _as_mapping(promotion_gate.get("summary"))
    handoff_summary = _as_mapping(promotion_handoff.get("summary"))
    downstream_summary = _as_mapping(downstream_intake.get("summary"))

    return {
        "pipeline_status": _classify_pipeline_status(
            stage_statuses,
            blocked_reasons,
        ),
        "stage_count": len(STAGE_ORDER),
        "completed_stage_count": len(stage_statuses),
        "ready_stage_count": sum(
            1
            for status in stage_statuses.values()
            if status == "ready"
        ),
        "needs_review_stage_count": sum(
            1
            for status in stage_statuses.values()
            if status == "needs_review"
        ),
        "blocked_stage_count": sum(
            1
            for status in stage_statuses.values()
            if status == "blocked"
        ),
        "blocked_stage_name": blocked_stage_name,
        "final_status": final_summary.get("status"),
        "promotion_gate_status": promotion_gate.get("status"),
        "promotion_handoff_status": promotion_handoff.get("status"),
        "backtest_id": (
            downstream_summary.get("backtest_id")
            or handoff_summary.get("backtest_id")
            or promotion_summary.get("backtest_id")
            or final_summary_payload.get("backtest_id")
        ),
        "ready_final_item_count": _safe_int(
            final_summary_payload.get("ready_final_item_count")
        ),
        "needs_review_final_item_count": _safe_int(
            final_summary_payload.get("needs_review_final_item_count")
        ),
        "blocked_final_item_count": _safe_int(
            final_summary_payload.get("blocked_final_item_count")
        ),
        "promotable_evidence_count": _safe_int(
            promotion_summary.get("promotable_evidence_count")
        ),
        "promotion_needs_review_evidence_count": _safe_int(
            promotion_summary.get("needs_review_evidence_count")
        ),
        "promotion_blocked_evidence_count": _safe_int(
            promotion_summary.get("blocked_evidence_count")
        ),
        "promoted_item_count": _safe_int(
            handoff_summary.get("promoted_item_count")
        ),
        "downstream_strategy_count": _safe_int(
            handoff_summary.get("strategy_count")
        ),
        "downstream_symbol_count": _safe_int(
            handoff_summary.get("symbol_count")
        ),
        "downstream_backtest_count": _safe_int(
            handoff_summary.get("backtest_count")
        ),
        "downstream_evidence_count": _safe_int(
            handoff_summary.get("evidence_count")
        ),
        "can_enter_downstream_historical_research": bool(
            handoff_summary.get(
                "can_enter_downstream_historical_research"
            )
        ),
        "downstream_intake_status": downstream_intake.get("status"),
        "downstream_intake_item_count": _safe_int(
            downstream_summary.get("intake_item_count")
        ),
        "expected_value_ready_item_count": _safe_int(
            downstream_summary.get("ready_intake_item_count")
        ),
        "expected_value_needs_review_item_count": _safe_int(
            downstream_summary.get("needs_review_intake_item_count")
        ),
        "expected_value_blocked_item_count": _safe_int(
            downstream_summary.get("blocked_intake_item_count")
        ),
        "can_enter_expected_value_research": bool(
            downstream_summary.get("can_enter_expected_value_research")
        ),
        "can_enter_strategy_selection": bool(
            downstream_summary.get("can_enter_strategy_selection")
        ),
        "decision_event_count": _safe_int(
            final_summary_payload.get("decision_event_count")
        ),
        "performance_metric_count": _safe_int(
            final_summary_payload.get("performance_metric_count")
        ),
        "expected_strategy_count": _safe_int(
            final_summary_payload.get("expected_strategy_count")
        ),
        "observed_strategy_count": _safe_int(
            final_summary_payload.get("observed_strategy_count")
        ),
        "expected_symbol_count": _safe_int(
            final_summary_payload.get("expected_symbol_count")
        ),
        "observed_symbol_count": _safe_int(
            final_summary_payload.get("observed_symbol_count")
        ),
        "warning_count": len(warnings),
        "blocked_reason_count": len(blocked_reasons),
    }

def _extract_final_summary(final_stage_result: Mapping[str, Any]) -> dict[str, Any]:
    final_summary = final_stage_result.get("final_summary")
    if isinstance(final_summary, Mapping):
        return deepcopy(dict(final_summary))

    if (
        final_stage_result.get("schema_version")
        == "historical_research_evidence_review_final_summary.v1"
    ):
        return deepcopy(dict(final_stage_result))

    return {}


def _stage_exception_result(stage_name: str, error: Exception) -> dict[str, Any]:
    return {
        "schema_version": "quantconnect_manual_backtest_evidence_pipeline_stage_error.v1",
        "stage_name": stage_name,
        "status": "blocked",
        "warnings": [],
        "blocked_reasons": [
            f"stage {stage_name} raised {error.__class__.__name__}: {error}"
        ],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _stage_invalid_result(stage_name: str) -> dict[str, Any]:
    return {
        "schema_version": "quantconnect_manual_backtest_evidence_pipeline_stage_error.v1",
        "stage_name": stage_name,
        "status": "blocked",
        "warnings": [],
        "blocked_reasons": [
            f"stage {stage_name} returned a non-mapping result"
        ],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _blocked_invalid_shape(reason: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "pipeline_type": PIPELINE_TYPE,
        "status": "blocked",
        "summary": {
            "pipeline_status": "blocked",
            "stage_count": len(STAGE_ORDER),
            "completed_stage_count": 0,
            "ready_stage_count": 0,
            "needs_review_stage_count": 0,
            "blocked_stage_count": 0,
            "blocked_stage_name": None,
            "final_status": None,
            "backtest_id": None,
            "ready_final_item_count": 0,
            "needs_review_final_item_count": 0,
            "blocked_final_item_count": 0,
            "decision_event_count": 0,
            "performance_metric_count": 0,
            "expected_strategy_count": 0,
            "observed_strategy_count": 0,
            "expected_symbol_count": 0,
            "observed_symbol_count": 0,
            "promotion_gate_status": None,
            "promotable_evidence_count": 0,
            "promotion_needs_review_evidence_count": 0,
            "promotion_blocked_evidence_count": 0,
            "promoted_item_count": 0,
            "downstream_strategy_count": 0,
            "downstream_symbol_count": 0,
            "downstream_backtest_count": 0,
            "downstream_evidence_count": 0,
            "can_enter_downstream_historical_research": False,
            "downstream_intake_status": None,
            "downstream_intake_item_count": 0,
            "expected_value_ready_item_count": 0,
            "expected_value_needs_review_item_count": 0,
            "expected_value_blocked_item_count": 0,
            "can_enter_expected_value_research": False,
            "can_enter_strategy_selection": False,
            "warning_count": 0,
            "blocked_reason_count": 1,
        },
        "stage_order": list(STAGE_ORDER),
        "stage_statuses": {},
        "stage_results": {},
        "final_summary": {},
        "promotion_gate": {},
        "promotion_handoff_status": None,
        "promotion_handoff": {},
        "downstream_intake": {},
        "warnings": [],
        "blocked_reasons": [reason],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _classify_pipeline_status(
    stage_statuses: Mapping[str, str],
    blocked_reasons: list[str],
) -> str:
    if blocked_reasons or any(status == "blocked" for status in stage_statuses.values()):
        return "blocked"

    if len(stage_statuses) < len(STAGE_ORDER):
        return "blocked"

    if any(status == "needs_review" for status in stage_statuses.values()):
        return "needs_review"

    return "ready"


def _collect_texts(value: Any, key: str) -> list[str]:
    texts: list[str] = []

    if isinstance(value, Mapping):
        for item_key, item_value in value.items():
            if item_key == key:
                texts.extend(_as_text_list(item_value))
            else:
                texts.extend(_collect_texts(item_value, key))

    elif isinstance(value, list):
        for item in value:
            texts.extend(_collect_texts(item, key))

    return texts


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        return [value.strip()] if value.strip() else []

    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]

    return [str(value).strip()] if str(value).strip() else []


def _sorted_unique_text(values: list[str]) -> list[str]:
    return sorted({value.strip() for value in values if value and value.strip()})


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
    
def _extract_promotion_gate(
    promotion_gate_stage_result: Mapping[str, Any],
) -> dict[str, Any]:
    promotion_gate = promotion_gate_stage_result.get("promotion_gate")

    if isinstance(promotion_gate, Mapping):
        return deepcopy(dict(promotion_gate))

    if (
        promotion_gate_stage_result.get("schema_version")
        == "historical_research_evidence_promotion_gate.v1"
    ):
        return deepcopy(dict(promotion_gate_stage_result))

    return {}

def _extract_promotion_handoff(
    promotion_handoff_stage_result: Mapping[str, Any],
) -> dict[str, Any]:
    promotion_handoff = promotion_handoff_stage_result.get(
        "promotion_handoff"
    )

    if isinstance(promotion_handoff, Mapping):
        return deepcopy(dict(promotion_handoff))

    if (
        promotion_handoff_stage_result.get("schema_version")
        == "historical_research_evidence_promotion_handoff.v1"
    ):
        return deepcopy(dict(promotion_handoff_stage_result))

    operation_result = promotion_handoff_stage_result.get(
        "operation_result"
    )

    if isinstance(operation_result, Mapping):
        promotion_handoff = operation_result.get(
            "promotion_handoff"
        )

        if isinstance(promotion_handoff, Mapping):
            return deepcopy(dict(promotion_handoff))

    return {}

def _extract_downstream_intake(
    downstream_intake_stage_result: Mapping[str, Any],
) -> dict[str, Any]:
    downstream_intake = downstream_intake_stage_result.get(
        "downstream_intake"
    )

    if isinstance(downstream_intake, Mapping):
        return deepcopy(dict(downstream_intake))

    if (
        downstream_intake_stage_result.get("schema_version")
        == "historical_research_downstream_intake.v1"
    ):
        return deepcopy(dict(downstream_intake_stage_result))

    operation_result = downstream_intake_stage_result.get(
        "operation_result"
    )

    if isinstance(operation_result, Mapping):
        downstream_intake = operation_result.get("downstream_intake")

        if isinstance(downstream_intake, Mapping):
            return deepcopy(dict(downstream_intake))

    return {}

