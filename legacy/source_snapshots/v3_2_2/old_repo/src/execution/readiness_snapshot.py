from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

EXPLICIT_EXECUTION_EXCLUSIONS: tuple[str, ...] = (
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
)

READINESS_COMPONENTS: tuple[str, ...] = (
    "execution_input_contract",
    "execution_planning",
    "dispatch",
    "end_to_end_dry_run",
    "operation_logging",
    "audit",
    "health_gate",
    "blocked_state_behavior",
    "broker_live_execution_exclusions",
)

_READY_STATUSES = {
    "ready",
    "passed",
    "pass",
    "ok",
    "healthy",
    "success",
    "successful",
    "completed",
    "complete",
}

_NOT_READY_STATUSES = {
    "not_ready",
    "blocked",
    "failed",
    "failure",
    "error",
    "invalid",
    "unhealthy",
}

_REASON_KEYS = (
    "blocked_reasons",
    "validation_errors",
    "errors",
    "failure_reasons",
    "not_ready_reasons",
    "reasons",
)


def build_execution_readiness_snapshot(
    *,
    component_results: Mapping[str, Any] | None = None,
    dry_run_result: Mapping[str, Any] | None = None,
    invalid_downstream_result: Mapping[str, Any] | None = None,
    explicit_exclusions: Sequence[str] = EXPLICIT_EXECUTION_EXCLUSIONS,
) -> dict[str, Any]:
    """Build a broker-neutral execution readiness report.

    This is only a readiness checkpoint. It does not call brokers, route orders,
    submit orders, model fills, run live execution, or model slippage.
    """

    merged_components: dict[str, Any] = {}

    if dry_run_result is not None:
        merged_components.update(_derive_components_from_dry_run(dry_run_result))

    if component_results:
        merged_components.update(dict(component_results))

    if invalid_downstream_result is not None:
        merged_components.setdefault(
            "blocked_state_behavior",
            _invalid_downstream_state_was_blocked(invalid_downstream_result),
        )

    merged_components.setdefault(
        "broker_live_execution_exclusions",
        {
            "is_ready": True,
            "evidence": "snapshot explicitly excludes broker/live execution fields",
        },
    )

    ready_components: list[str] = []
    not_ready_components: list[str] = []
    blocked_reasons: list[str] = []
    component_summary: dict[str, dict[str, Any]] = {}

    for component in READINESS_COMPONENTS:
        evaluation = _evaluate_component(component, merged_components.get(component))
        component_summary[component] = evaluation

        if evaluation["is_ready"]:
            ready_components.append(component)
        else:
            not_ready_components.append(component)
            blocked_reasons.extend(evaluation["blocked_reasons"])

    is_ready = not not_ready_components and not blocked_reasons

    return {
        "readiness_status": "ready" if is_ready else "not_ready",
        "is_ready": is_ready,
        "ready_components": ready_components,
        "not_ready_components": not_ready_components,
        "blocked_reasons": _dedupe_preserve_order(blocked_reasons),
        "explicit_exclusions": list(explicit_exclusions),
        "summary": {
            "component_count": len(READINESS_COMPONENTS),
            "ready_component_count": len(ready_components),
            "not_ready_component_count": len(not_ready_components),
            "explicit_exclusion_count": len(explicit_exclusions),
            "component_readiness": component_summary,
            "source_summary": _extract_mapping(dry_run_result, "summary")
            if dry_run_result is not None
            else {},
        },
    }


def _derive_components_from_dry_run(dry_run_result: Mapping[str, Any]) -> dict[str, Any]:
    summary = _extract_mapping(dry_run_result, "summary")

    return {
        "execution_input_contract": {
            "is_ready": _first_positive_count(
                summary,
                "execution_intent_count",
                "intent_count",
                "execution_input_count",
            ),
            "source": "dry_run_result.summary",
        },
        "execution_planning": {
            "is_ready": _first_positive_count(
                summary,
                "planned_instruction_count",
                "planned_order_instruction_count",
                "planned_order_count",
            ),
            "source": "dry_run_result.summary",
        },
        "dispatch": {
            "is_ready": _first_positive_count(
                summary,
                "dispatch_intent_count",
                "dispatch_count",
                "dispatch_row_count",
            ),
            "source": "dry_run_result.summary",
        },
        "end_to_end_dry_run": {
            "is_ready": _result_looks_successful(dry_run_result),
            "blocked_reasons": _collect_reasons(dry_run_result),
        },
        "operation_logging": {
            "is_ready": _has_any_key(
                dry_run_result,
                "operation_log_path",
                "jsonl_log_path",
                "log_path",
                "operation_event_log_path",
            ),
            "source": "dry_run_result",
        },
        "audit": _derive_audit_result(dry_run_result),
        "health_gate": _derive_health_gate_result(dry_run_result),
    }


def _derive_audit_result(dry_run_result: Mapping[str, Any]) -> dict[str, Any]:
    for key in ("audit_report", "audit", "audit_result"):
        value = dry_run_result.get(key)
        if isinstance(value, Mapping):
            evaluation = _evaluate_component("audit", value)
            return {
                "is_ready": evaluation["is_ready"],
                "blocked_reasons": evaluation["blocked_reasons"],
                "source": f"dry_run_result.{key}",
            }
        if value is not None:
            return {"is_ready": bool(value), "source": f"dry_run_result.{key}"}

    return {"is_ready": False, "blocked_reasons": ["audit missing readiness evidence"]}


def _derive_health_gate_result(dry_run_result: Mapping[str, Any]) -> dict[str, Any]:
    for key in ("health_gate", "health_report", "health_result", "operation_health"):
        value = dry_run_result.get(key)
        if isinstance(value, Mapping):
            evaluation = _evaluate_component("health_gate", value)
            return {
                "is_ready": evaluation["is_ready"],
                "blocked_reasons": evaluation["blocked_reasons"],
                "source": f"dry_run_result.{key}",
            }
        if value is not None:
            return {"is_ready": bool(value), "source": f"dry_run_result.{key}"}

    return {"is_ready": False, "blocked_reasons": ["health_gate missing readiness evidence"]}


def _invalid_downstream_state_was_blocked(result: Mapping[str, Any]) -> dict[str, Any]:
    reasons = _collect_reasons(result)
    is_blocked = bool(result.get("is_blocked")) or _status_is_not_ready(result.get("status"))

    return {
        "is_ready": is_blocked,
        "blocked_reasons": [] if is_blocked else ["invalid downstream state was not blocked"],
        "evidence": reasons,
    }


def _evaluate_component(component: str, value: Any) -> dict[str, Any]:
    if value is None:
        return {
            "is_ready": False,
            "blocked_reasons": [f"{component} missing readiness evidence"],
        }

    if isinstance(value, bool):
        return {
            "is_ready": value,
            "blocked_reasons": [] if value else [f"{component} is not ready"],
        }

    if isinstance(value, str):
        is_ready = _status_is_ready(value)
        return {
            "is_ready": is_ready,
            "blocked_reasons": [] if is_ready else [f"{component} status is {value}"],
        }

    if not isinstance(value, Mapping):
        return {
            "is_ready": bool(value),
            "blocked_reasons": [] if bool(value) else [f"{component} is not ready"],
        }

    reasons = _collect_reasons(value)
    if bool(value.get("is_blocked")):
        reasons.append(f"{component} is blocked")

    explicit_ready = _first_existing_bool(
        value,
        "is_ready",
        "ready",
        "is_healthy",
        "passed",
    )
    if explicit_ready is not None:
        is_ready = explicit_ready and not reasons
        return {
            "is_ready": is_ready,
            "blocked_reasons": [] if is_ready else reasons or [f"{component} is not ready"],
        }

    for status_key in ("readiness_status", "health_status", "status"):
        if status_key in value:
            status = value[status_key]
            is_ready = _status_is_ready(status) and not reasons
            return {
                "is_ready": is_ready,
                "blocked_reasons": [] if is_ready else reasons or [f"{component} status is {status}"],
            }

    return {
        "is_ready": False,
        "blocked_reasons": reasons or [f"{component} missing explicit readiness status"],
    }


def _result_looks_successful(result: Mapping[str, Any]) -> bool:
    if bool(result.get("is_blocked")):
        return False
    if _collect_reasons(result):
        return False
    if "status" in result:
        return _status_is_ready(result["status"])
    if "readiness_status" in result:
        return _status_is_ready(result["readiness_status"])
    return True


def _first_positive_count(mapping: Mapping[str, Any], *keys: str) -> bool:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float) and value > 0:
            return True
    return False


def _first_existing_bool(mapping: Mapping[str, Any], *keys: str) -> bool | None:
    for key in keys:
        if key in mapping:
            return bool(mapping[key])
    return None


def _has_any_key(mapping: Mapping[str, Any], *keys: str) -> bool:
    return any(bool(mapping.get(key)) for key in keys)


def _extract_mapping(mapping: Mapping[str, Any] | None, key: str) -> dict[str, Any]:
    if not mapping:
        return {}
    value = mapping.get(key)
    return dict(value) if isinstance(value, Mapping) else {}


def _collect_reasons(mapping: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for key in _REASON_KEYS:
        value = mapping.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            reasons.append(value)
        elif isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
            reasons.extend(str(item) for item in value if str(item))
        else:
            reasons.append(str(value))
    return reasons


def _status_is_ready(status: Any) -> bool:
    return str(status).strip().lower() in _READY_STATUSES


def _status_is_not_ready(status: Any) -> bool:
    return str(status).strip().lower() in _NOT_READY_STATUSES


def _dedupe_preserve_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


__all__ = [
    "EXPLICIT_EXECUTION_EXCLUSIONS",
    "READINESS_COMPONENTS",
    "build_execution_readiness_snapshot",
]
