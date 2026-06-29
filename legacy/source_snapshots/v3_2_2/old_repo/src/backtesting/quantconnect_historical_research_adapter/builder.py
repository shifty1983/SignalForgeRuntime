from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


SCHEMA_VERSION = "quantconnect_historical_research_input.v1"
ADAPTER_TYPE = "quantconnect_final_summary_to_historical_research_evidence"

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


def build_quantconnect_historical_research_input(
    final_summary_result: Any,
) -> dict[str, Any]:
    """Adapt a QuantConnect final summary into historical-research evidence input.

    This builder does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only converts an existing local QuantConnect
    final summary artifact into downstream historical research evidence payloads.
    """

    if not isinstance(final_summary_result, Mapping):
        return _blocked_invalid_shape("final_summary_result must be a mapping/dict")

    source = deepcopy(dict(final_summary_result))
    final_summary = _extract_final_summary(source)

    if not final_summary:
        return _blocked_invalid_shape(
            "final summary result is missing final_summary payload"
        )

    final_status = str(final_summary.get("status", "needs_review"))
    summary = _as_mapping(final_summary.get("summary"))
    evidence_items = _as_list(final_summary.get("final_evidence_items"))

    warnings = _sorted_unique_text(_as_text_list(final_summary.get("warnings")))
    blocked_reasons = _sorted_unique_text(
        _as_text_list(final_summary.get("blocked_reasons"))
    )

    ready_payloads: list[dict[str, Any]] = []
    needs_review_payloads: list[dict[str, Any]] = []
    blocked_payloads: list[dict[str, Any]] = []

    for evidence_item in evidence_items:
        if not isinstance(evidence_item, Mapping):
            continue

        payload = _build_research_payload(evidence_item, summary)
        evidence_status = str(evidence_item.get("status", "needs_review"))

        if evidence_status == "ready":
            ready_payloads.append(payload)
        elif evidence_status == "blocked":
            blocked_payloads.append(payload)
        else:
            needs_review_payloads.append(payload)

    status = _classify_adapter_status(
        final_status=final_status,
        ready_count=len(ready_payloads),
        needs_review_count=len(needs_review_payloads),
        blocked_count=len(blocked_payloads),
        blocked_reasons=blocked_reasons,
    )

    if status == "blocked" and not blocked_reasons:
        blocked_reasons.append("QuantConnect historical research input is blocked")

    blocked_reasons = _sorted_unique_text(blocked_reasons)

    return {
        "schema_version": SCHEMA_VERSION,
        "adapter_type": ADAPTER_TYPE,
        "status": status,
        "summary": {
            "source_final_status": final_status,
            "backtest_id": summary.get("backtest_id"),
            "ready_payload_count": len(ready_payloads),
            "needs_review_payload_count": len(needs_review_payloads),
            "blocked_payload_count": len(blocked_payloads),
            "source_ready_evidence_count": _safe_int(
                summary.get("ready_evidence_count")
            ),
            "source_needs_review_evidence_count": _safe_int(
                summary.get("needs_review_evidence_count")
            ),
            "source_blocked_evidence_count": _safe_int(
                summary.get("blocked_evidence_count")
            ),
            "expected_strategy_count": _safe_int(
                summary.get("expected_strategy_count")
            ),
            "observed_strategy_count": _safe_int(
                summary.get("observed_strategy_count")
            ),
            "expected_symbol_count": _safe_int(summary.get("expected_symbol_count")),
            "observed_symbol_count": _safe_int(summary.get("observed_symbol_count")),
            "decision_event_count": _safe_int(summary.get("decision_event_count")),
            "performance_metric_count": _safe_int(
                summary.get("performance_metric_count")
            ),
            "warning_count": len(warnings),
            "blocked_reason_count": len(blocked_reasons),
        },
        "ready_payloads": ready_payloads,
        "needs_review_payloads": needs_review_payloads,
        "blocked_payloads": blocked_payloads,
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "source_final_summary": {
            "schema_version": final_summary.get("schema_version"),
            "summary_type": final_summary.get("summary_type"),
            "status": final_summary.get("status"),
            "summary": _json_safe_mapping(summary),
        },
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _blocked_invalid_shape(reason: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "adapter_type": ADAPTER_TYPE,
        "status": "blocked",
        "summary": {
            "source_final_status": "invalid_shape",
            "backtest_id": None,
            "ready_payload_count": 0,
            "needs_review_payload_count": 0,
            "blocked_payload_count": 0,
            "source_ready_evidence_count": 0,
            "source_needs_review_evidence_count": 0,
            "source_blocked_evidence_count": 0,
            "expected_strategy_count": 0,
            "observed_strategy_count": 0,
            "expected_symbol_count": 0,
            "observed_symbol_count": 0,
            "decision_event_count": 0,
            "performance_metric_count": 0,
            "warning_count": 0,
            "blocked_reason_count": 1,
        },
        "ready_payloads": [],
        "needs_review_payloads": [],
        "blocked_payloads": [],
        "warnings": [],
        "blocked_reasons": [reason],
        "source_final_summary": {},
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _extract_final_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    final_summary = source.get("final_summary")
    if isinstance(final_summary, Mapping):
        return dict(final_summary)

    if source.get("schema_version") == "quantconnect_review_final_summary.v1":
        return dict(source)

    operation_result = source.get("operation_result")
    if isinstance(operation_result, Mapping):
        final_summary = operation_result.get("final_summary")
        if isinstance(final_summary, Mapping):
            return dict(final_summary)

    return {}


def _build_research_payload(
    evidence_item: Mapping[str, Any],
    final_summary: Mapping[str, Any],
) -> dict[str, Any]:
    performance_snapshot = _as_mapping(evidence_item.get("performance_snapshot"))
    decision_snapshot = _as_mapping(evidence_item.get("decision_snapshot"))
    alignment_status = _as_mapping(evidence_item.get("alignment_status"))

    evidence_status = str(evidence_item.get("status", "needs_review"))

    return {
        "payload_type": "historical_research_backtest_evidence",
        "evidence_source": "quantconnect",
        "evidence_method": "manual_cloud_backtest",
        "status": evidence_status,
        "backtest_id": evidence_item.get("backtest_id")
        or final_summary.get("backtest_id"),
        "review_status": evidence_item.get("review_status"),
        "export_status": evidence_item.get("export_status"),
        "import_status": evidence_item.get("import_status"),
        "strategy_ids": _as_text_list(evidence_item.get("strategy_ids")),
        "symbols": _as_text_list(evidence_item.get("symbols")),
        "expected_strategy_count": _safe_int(
            evidence_item.get("expected_strategy_count")
        ),
        "observed_strategy_count": _safe_int(
            evidence_item.get("observed_strategy_count")
        ),
        "expected_symbol_count": _safe_int(evidence_item.get("expected_symbol_count")),
        "observed_symbol_count": _safe_int(evidence_item.get("observed_symbol_count")),
        "decision_event_count": _safe_int(evidence_item.get("decision_event_count")),
        "performance_metric_count": _safe_int(
            evidence_item.get("performance_metric_count")
        ),
        "alignment_status": _json_safe_mapping(alignment_status),
        "performance_snapshot": _json_safe_mapping(performance_snapshot),
        "decision_snapshot": _json_safe_mapping(decision_snapshot),
        "research_readiness": _build_research_readiness(
            evidence_status=evidence_status,
            alignment_status=alignment_status,
            performance_snapshot=performance_snapshot,
            decision_event_count=_safe_int(evidence_item.get("decision_event_count")),
            performance_metric_count=_safe_int(
                evidence_item.get("performance_metric_count")
            ),
        ),
        "recommended_research_actions": _build_recommended_research_actions(
            evidence_status=evidence_status,
            alignment_status=alignment_status,
            performance_snapshot=performance_snapshot,
            decision_event_count=_safe_int(evidence_item.get("decision_event_count")),
            performance_metric_count=_safe_int(
                evidence_item.get("performance_metric_count")
            ),
        ),
        "warnings": _sorted_unique_text(_as_text_list(evidence_item.get("warnings"))),
        "blocked_reasons": _sorted_unique_text(
            _as_text_list(evidence_item.get("blocked_reasons"))
        ),
    }


def _build_research_readiness(
    *,
    evidence_status: str,
    alignment_status: Mapping[str, Any],
    performance_snapshot: Mapping[str, Any],
    decision_event_count: int,
    performance_metric_count: int,
) -> dict[str, Any]:
    return {
        "can_enter_historical_research_review": evidence_status == "ready",
        "has_strategy_alignment": bool(alignment_status.get("strategies_match")),
        "has_symbol_alignment": bool(alignment_status.get("symbols_match")),
        "has_reported_count_alignment": bool(
            alignment_status.get("reported_count_matches_export")
        ),
        "has_decision_evidence": decision_event_count > 0,
        "has_performance_evidence": performance_metric_count > 0,
        "has_trade_count": performance_snapshot.get("total_trades") is not None,
        "has_risk_metric": performance_snapshot.get("drawdown") is not None,
        "has_return_or_quality_metric": (
            performance_snapshot.get("net_profit") is not None
            or performance_snapshot.get("sharpe_ratio") is not None
            or performance_snapshot.get("probabilistic_sharpe_ratio") is not None
        ),
    }


def _build_recommended_research_actions(
    *,
    evidence_status: str,
    alignment_status: Mapping[str, Any],
    performance_snapshot: Mapping[str, Any],
    decision_event_count: int,
    performance_metric_count: int,
) -> list[str]:
    actions: list[str] = []

    if evidence_status == "ready":
        actions.append("review QuantConnect backtest evidence for historical research")

    if not alignment_status.get("strategies_match"):
        actions.append("investigate strategy-id mismatch before historical review")

    if not alignment_status.get("symbols_match"):
        actions.append("investigate symbol mismatch before historical review")

    if not alignment_status.get("reported_count_matches_export"):
        actions.append("verify exported strategy count against QuantConnect logs")

    if decision_event_count == 0:
        actions.append("include SignalForge decision events from QuantConnect logs")

    if performance_metric_count == 0:
        actions.append("include QuantConnect performance statistics")

    if performance_snapshot.get("total_trades") is None:
        actions.append("confirm trade count from QuantConnect statistics")

    if evidence_status == "blocked":
        actions.append("resolve blocked QuantConnect evidence before historical review")

    return sorted(set(actions))


def _classify_adapter_status(
    *,
    final_status: str,
    ready_count: int,
    needs_review_count: int,
    blocked_count: int,
    blocked_reasons: list[str],
) -> str:
    if final_status == "blocked" or blocked_count > 0 or blocked_reasons:
        return "blocked"

    if final_status == "ready" and ready_count > 0 and needs_review_count == 0:
        return "ready"

    if final_status == "needs_review" or needs_review_count > 0:
        return "needs_review"

    return "needs_review"


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
