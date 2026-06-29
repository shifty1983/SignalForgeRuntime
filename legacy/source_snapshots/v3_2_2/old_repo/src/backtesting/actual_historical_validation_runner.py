# src/backtesting/actual_historical_validation_runner.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.backtesting.historical_data_readiness_adapter import EXPLICIT_EXCLUSIONS
from src.backtesting.historical_data_readiness_adapter_runner import (
    run_historical_data_readiness_adapter_operation,
)
from src.backtesting.historical_strategy_validation_runner import (
    run_historical_strategy_validation,
)
from src.backtesting.historical_validation_promotion_runner import (
    run_historical_validation_promotion_operation,
)
from src.backtesting.historical_validation_summary_export import (
    export_historical_validation_summary,
)


OPERATION_TYPE = "actual_historical_validation_runner"


def run_actual_historical_validation(
    candidate_records: Iterable[Mapping[str, Any]],
    price_records: Iterable[Mapping[str, Any]],
    *,
    forward_windows: Sequence[int] = (1,),
    neutral_bands: Sequence[float] = (0.01,),
    candidate_field_map: Mapping[str, str] | None = None,
    price_field_map: Mapping[str, str] | None = None,
    operation_name: str = OPERATION_TYPE,
    adapter_operation_name: str | None = None,
    validation_operation_name: str | None = None,
    promotion_operation_name: str | None = None,
    summary_export_name: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    adapter_log_path: str | Path | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})

    resolved_adapter_operation_name = (
        adapter_operation_name or f"{operation_name}.adapter"
    )
    resolved_validation_operation_name = (
        validation_operation_name or f"{operation_name}.validation"
    )
    resolved_promotion_operation_name = (
        promotion_operation_name or f"{operation_name}.promotion"
    )
    resolved_summary_export_name = (
        summary_export_name or f"{operation_name}.summary_export"
    )

    adapter_operation = run_historical_data_readiness_adapter_operation(
        candidate_records,
        price_records,
        forward_windows=forward_windows,
        candidate_field_map=candidate_field_map,
        price_field_map=price_field_map,
        operation_name=resolved_adapter_operation_name,
        metadata=metadata_dict,
        log_path=adapter_log_path,
    )

    if adapter_operation.get("is_blocked") is True:
        blocked_reasons = _collect_blocked_reasons(adapter_operation)
        warnings = _collect_warnings(adapter_operation)

        validation_result = _build_skipped_validation_result(blocked_reasons)
        promotion_result = _build_skipped_promotion_result(blocked_reasons)
        summary_export = _build_blocked_summary_export(
            blocked_reasons,
            warnings=warnings,
            export_name=resolved_summary_export_name,
            metadata=metadata_dict,
        )

        return _build_runner_result(
            operation_name=operation_name,
            adapter_operation=adapter_operation,
            validation_result=validation_result,
            promotion_result=promotion_result,
            summary_export=summary_export,
            metadata=metadata_dict,
        )

    adapter_result = dict(adapter_operation.get("adapter_result", {}))

    validation_result = run_historical_strategy_validation(
        adapter_result.get("candidate_rows", []),
        adapter_result.get("price_rows", []),
        forward_windows=forward_windows,
        neutral_bands=neutral_bands,
        operation_name=resolved_validation_operation_name,
    )

    promotion_result = run_historical_validation_promotion_operation(
        validation_result,
        operation_name=resolved_promotion_operation_name,
    )

    summary_export = export_historical_validation_summary(
        validation_result,
        promotion_result,
        export_name=resolved_summary_export_name,
        metadata=metadata_dict,
    )

    return _build_runner_result(
        operation_name=operation_name,
        adapter_operation=adapter_operation,
        validation_result=validation_result,
        promotion_result=promotion_result,
        summary_export=summary_export,
        metadata=metadata_dict,
    )


def _build_runner_result(
    *,
    operation_name: str,
    adapter_operation: Mapping[str, Any],
    validation_result: Mapping[str, Any],
    promotion_result: Mapping[str, Any],
    summary_export: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    warnings = _collect_warnings(
        adapter_operation,
        validation_result,
        promotion_result,
        summary_export,
    )
    blocked_reasons = _collect_blocked_reasons(
        adapter_operation,
        validation_result,
        promotion_result,
        summary_export,
    )

    is_blocked = bool(
        _stage_is_blocked(adapter_operation)
        or _stage_is_blocked(validation_result)
        or _stage_is_blocked(promotion_result)
        or _stage_is_blocked(summary_export)
        or blocked_reasons
    )

    runner_status = "blocked" if is_blocked else "completed"

    adapter_summary = dict(adapter_operation.get("summary", {}))

    return {
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "runner_status": runner_status,
        "is_blocked": is_blocked,
        "adapter_operation": dict(adapter_operation),
        "validation_result": dict(validation_result),
        "promotion_result": dict(promotion_result),
        "summary_export": dict(summary_export),
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "summary": {
            "adapter_runner_status": adapter_operation.get("runner_status"),
            "adapter_status": adapter_summary.get("adapter_status"),
            "validation_status": _get_stage_status(
                validation_result,
                preferred_keys=(
                    "validation_status",
                    "status",
                    "runner_status",
                    "operation_status",
                ),
            ),
            "promotion_status": _get_stage_status(
                promotion_result,
                preferred_keys=(
                    "promotion_status",
                    "status",
                    "runner_status",
                    "operation_status",
                ),
            ),
            "summary_export_status": _get_stage_status(
                summary_export,
                preferred_keys=(
                    "export_status",
                    "summary_status",
                    "status",
                ),
            ),
            "candidate_count": adapter_summary.get("candidate_count", 0),
            "price_row_count": adapter_summary.get("price_row_count", 0),
            "accepted_candidate_count": adapter_summary.get(
                "accepted_candidate_count",
                0,
            ),
            "rejected_candidate_count": adapter_summary.get(
                "rejected_candidate_count",
                0,
            ),
            "symbol_count": adapter_summary.get("symbol_count", 0),
            "candidate_symbol_count": adapter_summary.get(
                "candidate_symbol_count",
                0,
            ),
            "max_forward_window": adapter_summary.get("max_forward_window"),
            "warning_count": len(warnings),
            "blocked_reason_count": len(blocked_reasons),
        },
        "metadata": dict(metadata),
    }


def _build_skipped_validation_result(blocked_reasons: list[str]) -> dict[str, Any]:
    return {
        "validation_status": "skipped",
        "is_blocked": True,
        "validation_errors": [],
        "warnings": [],
        "blocked_reasons": list(blocked_reasons),
        "summary": {
            "skip_reason": "historical data readiness adapter is blocked",
        },
    }


def _build_skipped_promotion_result(blocked_reasons: list[str]) -> dict[str, Any]:
    return {
        "promotion_status": "skipped",
        "is_blocked": True,
        "validation_errors": [],
        "warnings": [],
        "blocked_reasons": list(blocked_reasons),
        "summary": {
            "skip_reason": "historical data readiness adapter is blocked",
        },
    }


def _build_blocked_summary_export(
    blocked_reasons: list[str],
    *,
    warnings: list[str],
    export_name: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "export_status": "blocked",
        "is_ready": False,
        "is_blocked": True,
        "export_type": "historical_validation_summary_export",
        "export_name": export_name,
        "validation_errors": [],
        "warnings": list(warnings),
        "blocked_reasons": list(blocked_reasons),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "source_summary": {
            "skip_reason": "historical data readiness adapter is blocked",
        },
        "metadata": dict(metadata),
    }


def _get_stage_status(
    stage_result: Mapping[str, Any],
    *,
    preferred_keys: Sequence[str],
) -> str | None:
    for key in preferred_keys:
        value = stage_result.get(key)
        if value is not None:
            return str(value)

    summary = stage_result.get("summary", {})
    if isinstance(summary, Mapping):
        for key in preferred_keys:
            value = summary.get(key)
            if value is not None:
                return str(value)

    return None


def _stage_is_blocked(stage_result: Mapping[str, Any]) -> bool:
    if stage_result.get("is_blocked") is True:
        return True

    for status_key in [
        "runner_status",
        "operation_status",
        "adapter_status",
        "validation_status",
        "promotion_status",
        "export_status",
        "summary_status",
        "status",
    ]:
        if stage_result.get(status_key) in {"blocked", "failed"}:
            return True

    summary = stage_result.get("summary", {})
    if isinstance(summary, Mapping):
        for status_key in [
            "runner_status",
            "operation_status",
            "adapter_status",
            "validation_status",
            "promotion_status",
            "export_status",
            "summary_status",
            "status",
        ]:
            if summary.get(status_key) in {"blocked", "failed"}:
                return True

    return False


def _collect_warnings(*stage_results: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []

    for stage_result in stage_results:
        warnings.extend(str(item) for item in stage_result.get("warnings", []))

        operation_record = stage_result.get("operation_record", {})
        if isinstance(operation_record, Mapping):
            warnings.extend(str(item) for item in operation_record.get("warnings", []))

        health_report = stage_result.get("health_report", {})
        if isinstance(health_report, Mapping):
            warnings.extend(str(item) for item in health_report.get("warnings", []))

    return _unique_ordered(warnings)


def _collect_blocked_reasons(*stage_results: Mapping[str, Any]) -> list[str]:
    blocked_reasons: list[str] = []

    for stage_result in stage_results:
        blocked_reasons.extend(
            str(item) for item in stage_result.get("blocked_reasons", [])
        )

        validation_errors = stage_result.get("validation_errors", [])
        blocked_reasons.extend(str(item) for item in validation_errors)

        operation_record = stage_result.get("operation_record", {})
        if isinstance(operation_record, Mapping):
            blocked_reasons.extend(
                str(item) for item in operation_record.get("blocked_reasons", [])
            )
            blocked_reasons.extend(
                str(item) for item in operation_record.get("validation_errors", [])
            )

        health_report = stage_result.get("health_report", {})
        if isinstance(health_report, Mapping):
            blocked_reasons.extend(
                str(item) for item in health_report.get("blocked_reasons", [])
            )

    return _unique_ordered(blocked_reasons)


def _unique_ordered(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)

    return result
