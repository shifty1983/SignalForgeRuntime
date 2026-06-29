from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


def _to_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}

    if isinstance(value, dict):
        return dict(value)

    if is_dataclass(value):
        return asdict(value)

    if hasattr(value, "to_dict"):
        result = value.to_dict()
        if isinstance(result, dict):
            return result

    if hasattr(value, "__dict__"):
        return dict(value.__dict__)

    return {}


def _get(report_data: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in report_data:
            return report_data[name]
    return default


def build_model_quality_operation_summary(report: Any) -> dict[str, Any]:
    """
    Convert a ModelQualityReport into a compact operation-safe summary.

    This intentionally avoids storing the entire report in operation records/logs.
    The full report remains owned by the research/model-quality layer.
    """
    data = _to_mapping(report)

    passed = _get(
        data,
        "passed",
        "is_passing",
        "promotion_passed",
        "eligible_for_promotion",
        default=None,
    )

    status = _get(data, "status", "promotion_status", default=None)

    failures = _get(
        data,
        "failures",
        "failure_reasons",
        "blocking_failures",
        "model_quality_failures",
        default=[],
    )

    if failures is None:
        failures = []

    if isinstance(failures, str):
        failures = [failures]

    summary = {
        "passed": bool(passed) if passed is not None else False,
        "status": status or ("passed" if passed else "failed"),
        "failure_reasons": list(failures),
        "robustness_passed": _get(data, "robustness_passed", default=None),
        "walk_forward_passed": _get(data, "walk_forward_passed", default=None),
        "stability_score": _get(data, "stability_score", default=None),
        "evaluated_dates": _get(data, "evaluated_dates", "date_count", default=None),
        "missing_data_rate": _get(data, "missing_data_rate", default=None),
    }

    return summary


def model_quality_failed(summary: dict[str, Any] | None) -> bool:
    if not summary:
        return False

    return summary.get("passed") is False or bool(summary.get("failure_reasons"))


def model_quality_failure_messages(summary: dict[str, Any] | None) -> list[str]:
    if not summary:
        return []

    failures = summary.get("failure_reasons") or []

    if isinstance(failures, str):
        return [failures]

    return [str(reason) for reason in failures]
