from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


SCHEMA_VERSION = "historical_research_evidence_intake_bundle.v1"
INTAKE_TYPE = "normalized_historical_research_evidence_intake"

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


def build_historical_research_evidence_intake(
    source: Any,
) -> dict[str, Any]:
    """Build normalized historical research evidence intake payloads.

    This builder does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only normalizes an existing local historical
    research adapter result into cross-source evidence intake payloads.
    """

    if not isinstance(source, Mapping):
        return _blocked_invalid_shape("source must be a mapping/dict")

    source_copy = deepcopy(dict(source))
    research_input = _extract_research_input(source_copy)

    if not research_input:
        return _blocked_invalid_shape(
            "source is missing historical research input payload"
        )

    input_status = str(research_input.get("status", "needs_review"))
    input_summary = _as_mapping(research_input.get("summary"))

    ready_payloads = _normalize_payloads(
        _as_list(research_input.get("ready_payloads")),
        status="ready",
        research_input=research_input,
    )
    needs_review_payloads = _normalize_payloads(
        _as_list(research_input.get("needs_review_payloads")),
        status="needs_review",
        research_input=research_input,
    )
    blocked_payloads = _normalize_payloads(
        _as_list(research_input.get("blocked_payloads")),
        status="blocked",
        research_input=research_input,
    )

    warnings = []
    warnings.extend(_as_text_list(research_input.get("warnings")))
    warnings.extend(_payload_warnings(ready_payloads))
    warnings.extend(_payload_warnings(needs_review_payloads))
    warnings.extend(_payload_warnings(blocked_payloads))

    blocked_reasons = []
    blocked_reasons.extend(_as_text_list(research_input.get("blocked_reasons")))
    blocked_reasons.extend(_payload_blocked_reasons(blocked_payloads))

    warnings = _sorted_unique_text(warnings)
    blocked_reasons = _sorted_unique_text(blocked_reasons)

    status = _classify_intake_status(
        input_status=input_status,
        ready_count=len(ready_payloads),
        needs_review_count=len(needs_review_payloads),
        blocked_count=len(blocked_payloads),
        blocked_reasons=blocked_reasons,
    )

    if status == "blocked" and not blocked_reasons:
        blocked_reasons.append("historical research evidence intake is blocked")

    blocked_reasons = _sorted_unique_text(blocked_reasons)

    return {
        "schema_version": SCHEMA_VERSION,
        "intake_type": INTAKE_TYPE,
        "status": status,
        "summary": {
            "source_input_status": input_status,
            "source_adapter_type": research_input.get("adapter_type"),
            "source_schema_version": research_input.get("schema_version"),
            "backtest_id": input_summary.get("backtest_id"),
            "ready_evidence_count": len(ready_payloads),
            "needs_review_evidence_count": len(needs_review_payloads),
            "blocked_evidence_count": len(blocked_payloads),
            "source_ready_payload_count": _safe_int(
                input_summary.get("ready_payload_count")
            ),
            "source_needs_review_payload_count": _safe_int(
                input_summary.get("needs_review_payload_count")
            ),
            "source_blocked_payload_count": _safe_int(
                input_summary.get("blocked_payload_count")
            ),
            "decision_event_count": _safe_int(input_summary.get("decision_event_count")),
            "performance_metric_count": _safe_int(
                input_summary.get("performance_metric_count")
            ),
            "expected_strategy_count": _safe_int(
                input_summary.get("expected_strategy_count")
            ),
            "observed_strategy_count": _safe_int(
                input_summary.get("observed_strategy_count")
            ),
            "expected_symbol_count": _safe_int(
                input_summary.get("expected_symbol_count")
            ),
            "observed_symbol_count": _safe_int(
                input_summary.get("observed_symbol_count")
            ),
            "warning_count": len(warnings),
            "blocked_reason_count": len(blocked_reasons),
        },
        "ready_evidence": ready_payloads,
        "needs_review_evidence": needs_review_payloads,
        "blocked_evidence": blocked_payloads,
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "source_input_summary": {
            "schema_version": research_input.get("schema_version"),
            "adapter_type": research_input.get("adapter_type"),
            "status": research_input.get("status"),
            "summary": _json_safe_mapping(input_summary),
        },
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _blocked_invalid_shape(reason: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "intake_type": INTAKE_TYPE,
        "status": "blocked",
        "summary": {
            "source_input_status": "invalid_shape",
            "source_adapter_type": None,
            "source_schema_version": None,
            "backtest_id": None,
            "ready_evidence_count": 0,
            "needs_review_evidence_count": 0,
            "blocked_evidence_count": 0,
            "source_ready_payload_count": 0,
            "source_needs_review_payload_count": 0,
            "source_blocked_payload_count": 0,
            "decision_event_count": 0,
            "performance_metric_count": 0,
            "expected_strategy_count": 0,
            "observed_strategy_count": 0,
            "expected_symbol_count": 0,
            "observed_symbol_count": 0,
            "warning_count": 0,
            "blocked_reason_count": 1,
        },
        "ready_evidence": [],
        "needs_review_evidence": [],
        "blocked_evidence": [],
        "warnings": [],
        "blocked_reasons": [reason],
        "source_input_summary": {},
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _extract_research_input(source: Mapping[str, Any]) -> dict[str, Any]:
    research_input = source.get("research_input")
    if isinstance(research_input, Mapping):
        return dict(research_input)

    if source.get("schema_version") == "quantconnect_historical_research_input.v1":
        return dict(source)

    operation_result = source.get("operation_result")
    if isinstance(operation_result, Mapping):
        research_input = operation_result.get("research_input")
        if isinstance(research_input, Mapping):
            return dict(research_input)

    return {}


def _normalize_payloads(
    payloads: list[Any],
    *,
    status: str,
    research_input: Mapping[str, Any],
) -> list[dict[str, Any]]:
    normalized = []

    for index, payload in enumerate(payloads, start=1):
        if not isinstance(payload, Mapping):
            continue

        normalized.append(
            _normalize_payload(
                payload,
                status=status,
                sequence=index,
                research_input=research_input,
            )
        )

    return sorted(
        normalized,
        key=lambda item: (
            item.get("evidence_source") or "",
            item.get("backtest_id") or "",
            ",".join(item.get("symbols", [])),
            item.get("sequence", 0),
        ),
    )


def _normalize_payload(
    payload: Mapping[str, Any],
    *,
    status: str,
    sequence: int,
    research_input: Mapping[str, Any],
) -> dict[str, Any]:
    research_readiness = _as_mapping(payload.get("research_readiness"))
    performance_snapshot = _as_mapping(payload.get("performance_snapshot"))
    decision_snapshot = _as_mapping(payload.get("decision_snapshot"))
    alignment_status = _as_mapping(payload.get("alignment_status"))

    evidence_source = str(payload.get("evidence_source") or "unknown")
    backtest_id = payload.get("backtest_id")

    return {
        "intake_payload_type": "historical_research_evidence",
        "source_payload_type": payload.get("payload_type"),
        "evidence_category": "backtest",
        "evidence_source": evidence_source,
        "evidence_method": payload.get("evidence_method"),
        "evidence_id": _build_evidence_id(
            evidence_source=evidence_source,
            backtest_id=backtest_id,
            sequence=sequence,
        ),
        "status": status,
        "sequence": sequence,
        "backtest_id": backtest_id,
        "review_status": payload.get("review_status"),
        "export_status": payload.get("export_status"),
        "import_status": payload.get("import_status"),
        "strategy_ids": _as_text_list(payload.get("strategy_ids")),
        "symbols": _as_text_list(payload.get("symbols")),
        "expected_strategy_count": _safe_int(payload.get("expected_strategy_count")),
        "observed_strategy_count": _safe_int(payload.get("observed_strategy_count")),
        "expected_symbol_count": _safe_int(payload.get("expected_symbol_count")),
        "observed_symbol_count": _safe_int(payload.get("observed_symbol_count")),
        "decision_event_count": _safe_int(payload.get("decision_event_count")),
        "performance_metric_count": _safe_int(
            payload.get("performance_metric_count")
        ),
        "research_readiness": _json_safe_mapping(research_readiness),
        "recommended_research_actions": _as_text_list(
            payload.get("recommended_research_actions")
        ),
        "alignment_status": _json_safe_mapping(alignment_status),
        "performance_snapshot": _json_safe_mapping(performance_snapshot),
        "decision_snapshot": _json_safe_mapping(decision_snapshot),
        "warnings": _sorted_unique_text(_as_text_list(payload.get("warnings"))),
        "blocked_reasons": _sorted_unique_text(
            _as_text_list(payload.get("blocked_reasons"))
        ),
        "source_adapter": {
            "schema_version": research_input.get("schema_version"),
            "adapter_type": research_input.get("adapter_type"),
            "status": research_input.get("status"),
        },
    }


def _build_evidence_id(
    *,
    evidence_source: str,
    backtest_id: Any,
    sequence: int,
) -> str:
    safe_backtest_id = str(backtest_id or "unknown_backtest")
    return f"{evidence_source}::{safe_backtest_id}::{sequence}"


def _classify_intake_status(
    *,
    input_status: str,
    ready_count: int,
    needs_review_count: int,
    blocked_count: int,
    blocked_reasons: list[str],
) -> str:
    if input_status == "blocked" or blocked_count > 0 or blocked_reasons:
        return "blocked"

    if input_status == "ready" and ready_count > 0 and needs_review_count == 0:
        return "ready"

    if input_status == "needs_review" or needs_review_count > 0:
        return "needs_review"

    return "needs_review"


def _payload_warnings(payloads: list[Mapping[str, Any]]) -> list[str]:
    warnings: list[str] = []

    for payload in payloads:
        warnings.extend(_as_text_list(payload.get("warnings")))

    return warnings


def _payload_blocked_reasons(payloads: list[Mapping[str, Any]]) -> list[str]:
    blocked_reasons: list[str] = []

    for payload in payloads:
        blocked_reasons.extend(_as_text_list(payload.get("blocked_reasons")))

    return blocked_reasons


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


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


def _json_safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}

    for key, item in value.items():
        if isinstance(item, Mapping):
            safe[str(key)] = _json_safe_mapping(item)
        elif isinstance(item, list):
            safe[str(key)] = [_json_safe_value(child) for child in item]
        elif isinstance(item, tuple):
            safe[str(key)] = [_json_safe_value(child) for child in item]
        elif isinstance(item, (str, int, float, bool)) or item is None:
            safe[str(key)] = item
        else:
            safe[str(key)] = str(item)

    return safe


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _json_safe_mapping(value)
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
