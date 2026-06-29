from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.quantconnect_export.builder import build_quantconnect_export


OPERATION_SCHEMA_VERSION = "quantconnect_export_operation.v1"
EVENT_SCHEMA_VERSION = "quantconnect_export_operation_event.v1"
AUDIT_SCHEMA_VERSION = "quantconnect_export_audit.v1"
HEALTH_SCHEMA_VERSION = "quantconnect_export_health.v1"

OPERATION_TYPE = "quantconnect_export_operation"


def run_quantconnect_export_operation(
    source: Mapping[str, Any],
    *,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run a deterministic QuantConnect export operation.

    This operation does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, or fill/slippage engines. It only
    wraps the export builder with operation/audit/health artifacts.
    """

    export = build_quantconnect_export(source)
    audit_report = build_quantconnect_export_audit_report(export)
    health_report = build_quantconnect_export_health_report(export)

    events = [
        _build_event(
            export=export,
            event_type="quantconnect_export_operation_started",
            sequence=1,
        ),
        _build_event(
            export=export,
            event_type="quantconnect_export_operation_completed",
            sequence=2,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        export=export,
        audit_report=audit_report,
        health_report=health_report,
        event_log_path=normalized_log_path,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": export["status"],
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "export": export,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(export.get("explicit_exclusions", [])),
    }


def build_quantconnect_export_audit_report(
    export: Mapping[str, Any],
) -> dict[str, Any]:
    payloads = _generated_payloads(export)
    strategy_configs = _as_list(payloads.get("strategy_configs"))
    universe = _as_list(payloads.get("universe"))
    decision_rules = _as_list(payloads.get("decision_rules"))
    manifest = payloads.get("backtest_manifest")
    manifest = manifest if isinstance(manifest, Mapping) else {}

    checks = [
        _check(
            name="export_schema_version_present",
            passed=bool(export.get("schema_version")),
            severity="blocker",
            message="export schema version is present",
            failure_message="export schema version is missing",
        ),
        _check(
            name="platform_is_quantconnect",
            passed=export.get("platform") == "quantconnect",
            severity="blocker",
            message="export platform is quantconnect",
            failure_message="export platform is not quantconnect",
        ),
        _check(
            name="engine_is_lean",
            passed=export.get("engine") == "lean",
            severity="blocker",
            message="export engine is lean",
            failure_message="export engine is not lean",
        ),
        _check(
            name="manual_execution_mode_only",
            passed=export.get("execution_mode") == "manual_cloud_backtest",
            severity="blocker",
            message="manual cloud backtest execution mode is preserved",
            failure_message="unexpected execution mode detected",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(export),
            severity="blocker",
            message="broker/live/slippage exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="strategy_configs_match_manifest",
            passed=_strategy_configs_match_manifest(strategy_configs, manifest),
            severity="blocker",
            message="strategy config count matches manifest",
            failure_message="strategy config count does not match manifest",
        ),
        _check(
            name="decision_rules_match_strategy_configs",
            passed=_decision_rules_match_strategy_configs(strategy_configs, decision_rules),
            severity="blocker",
            message="decision rules match exported strategy configs",
            failure_message="decision rules do not match exported strategy configs",
        ),
        _check(
            name="universe_contains_strategy_symbols",
            passed=_universe_contains_strategy_symbols(strategy_configs, universe),
            severity="blocker",
            message="universe contains all strategy symbols",
            failure_message="universe is missing one or more strategy symbols",
        ),
        _check(
            name="blocked_exports_have_blocked_reason",
            passed=_blocked_exports_have_reason(export),
            severity="warning",
            message="blocked export reason handling is valid",
            failure_message="blocked export is missing blocked reasons",
        ),
    ]

    summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(export_status=str(export.get("status")), checks=checks),
        "summary": summary,
        "checks": checks,
        "explicit_exclusions": list(export.get("explicit_exclusions", [])),
    }


def build_quantconnect_export_health_report(
    export: Mapping[str, Any],
) -> dict[str, Any]:
    export_status = str(export.get("status", "needs_review"))
    summary = export.get("summary")
    summary = summary if isinstance(summary, Mapping) else {}

    warning_count = _safe_int(summary.get("warning_count"))
    blocked_reason_count = _safe_int(summary.get("blocked_reason_count"))
    exportable_strategy_count = _safe_int(summary.get("exportable_strategy_count"))

    indicators = {
        "export_status": export_status,
        "exportable_strategy_count": exportable_strategy_count,
        "warning_count": warning_count,
        "blocked_reason_count": blocked_reason_count,
        "manual_execution_only": export.get("execution_mode") == "manual_cloud_backtest",
        "has_strategy_configs": exportable_strategy_count > 0,
        "has_warnings": warning_count > 0,
        "has_blocked_reasons": blocked_reason_count > 0,
    }

    recommendations = _build_health_recommendations(
        export_status=export_status,
        exportable_strategy_count=exportable_strategy_count,
        warning_count=warning_count,
        blocked_reason_count=blocked_reason_count,
    )

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(export_status),
        "indicators": indicators,
        "recommendations": recommendations,
        "explicit_exclusions": list(export.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    export: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    event_log_path: Path | None,
) -> dict[str, Any]:
    payloads = _generated_payloads(export)
    manifest = payloads.get("backtest_manifest")
    manifest = manifest if isinstance(manifest, Mapping) else {}

    summary = export.get("summary")
    summary = summary if isinstance(summary, Mapping) else {}

    operation_id = _build_operation_id(manifest)

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_id": operation_id,
        "status": export.get("status", "needs_review"),
        "summary": {
            "source_status": summary.get("source_status", "needs_review"),
            "export_status": export.get("status", "needs_review"),
            "audit_status": audit_report.get("status", "needs_review"),
            "health_status": health_report.get("status", "degraded"),
            "ready_item_count": _safe_int(summary.get("ready_item_count")),
            "needs_review_item_count": _safe_int(summary.get("needs_review_item_count")),
            "blocked_item_count": _safe_int(summary.get("blocked_item_count")),
            "exportable_strategy_count": _safe_int(
                summary.get("exportable_strategy_count")
            ),
            "warning_count": _safe_int(summary.get("warning_count")),
            "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
        },
        "generated_payload_counts": {
            "strategy_config_count": len(_as_list(payloads.get("strategy_configs"))),
            "universe_count": len(_as_list(payloads.get("universe"))),
            "decision_rule_count": len(_as_list(payloads.get("decision_rules"))),
            "manifest_count": 1 if isinstance(manifest, Mapping) and manifest else 0,
        },
        "event_log_path": str(event_log_path) if event_log_path else None,
        "explicit_exclusions": list(export.get("explicit_exclusions", [])),
    }


def _build_event(
    *,
    export: Mapping[str, Any],
    event_type: str,
    sequence: int,
) -> dict[str, Any]:
    summary = export.get("summary")
    summary = summary if isinstance(summary, Mapping) else {}

    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": export.get("status", "needs_review"),
        "summary": {
            "source_status": summary.get("source_status", "needs_review"),
            "export_status": export.get("status", "needs_review"),
            "exportable_strategy_count": _safe_int(
                summary.get("exportable_strategy_count")
            ),
            "warning_count": _safe_int(summary.get("warning_count")),
            "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
        },
        "explicit_exclusions": list(export.get("explicit_exclusions", [])),
    }


def _write_jsonl_event_log(path: Path, events: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        for event in events:
            file.write(json.dumps(event, sort_keys=True))
            file.write("\n")


def _normalize_event_log_path(path: str | PathLike[str] | None) -> Path | None:
    if path is None:
        return None
    return Path(path)


def _generated_payloads(export: Mapping[str, Any]) -> Mapping[str, Any]:
    payloads = export.get("generated_payloads")
    if isinstance(payloads, Mapping):
        return payloads
    return {}


def _check(
    *,
    name: str,
    passed: bool,
    severity: str,
    message: str,
    failure_message: str,
) -> dict[str, Any]:
    if passed:
        return {
            "name": name,
            "status": "passed",
            "severity": severity,
            "message": message,
        }

    failed_status = "failed" if severity == "blocker" else "warning"
    return {
        "name": name,
        "status": failed_status,
        "severity": severity,
        "message": failure_message,
    }


def _summarize_checks(checks: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "passed_count": sum(1 for check in checks if check.get("status") == "passed"),
        "warning_count": sum(1 for check in checks if check.get("status") == "warning"),
        "failed_count": sum(1 for check in checks if check.get("status") == "failed"),
        "check_count": len(checks),
    }


def _classify_audit_status(
    *,
    export_status: str,
    checks: list[Mapping[str, Any]],
) -> str:
    if any(check.get("status") == "failed" for check in checks):
        return "blocked"

    if export_status == "blocked":
        return "blocked"

    if export_status == "needs_review":
        return "needs_review"

    if any(check.get("status") == "warning" for check in checks):
        return "needs_review"

    return "ready"


def _classify_health_status(export_status: str) -> str:
    if export_status == "ready":
        return "healthy"
    if export_status == "blocked":
        return "blocked"
    return "degraded"


def _build_health_recommendations(
    *,
    export_status: str,
    exportable_strategy_count: int,
    warning_count: int,
    blocked_reason_count: int,
) -> list[str]:
    recommendations: list[str] = []

    if exportable_strategy_count == 0:
        recommendations.append("add at least one ready item with a valid symbol")

    if warning_count > 0:
        recommendations.append("review export warnings before manual QuantConnect backtest")

    if blocked_reason_count > 0:
        recommendations.append("resolve blocked reasons before promoting the export")

    if export_status == "ready":
        recommendations.append("manual QuantConnect cloud backtest package is ready")

    if not recommendations:
        recommendations.append("no health actions required")

    return sorted(set(recommendations))


def _strategy_configs_match_manifest(
    strategy_configs: list[Any],
    manifest: Mapping[str, Any],
) -> bool:
    manifest_count = _safe_int(manifest.get("strategy_count"))
    manifest_ids = manifest.get("strategy_ids")

    strategy_ids = sorted(
        str(config.get("strategy_id"))
        for config in strategy_configs
        if isinstance(config, Mapping) and config.get("strategy_id")
    )

    if not isinstance(manifest_ids, list):
        manifest_ids = []

    normalized_manifest_ids = sorted(str(strategy_id) for strategy_id in manifest_ids)

    return manifest_count == len(strategy_configs) and normalized_manifest_ids == strategy_ids


def _decision_rules_match_strategy_configs(
    strategy_configs: list[Any],
    decision_rules: list[Any],
) -> bool:
    strategy_ids = sorted(
        str(config.get("strategy_id"))
        for config in strategy_configs
        if isinstance(config, Mapping) and config.get("strategy_id")
    )
    decision_rule_ids = sorted(
        str(rule.get("strategy_id"))
        for rule in decision_rules
        if isinstance(rule, Mapping) and rule.get("strategy_id")
    )

    return strategy_ids == decision_rule_ids


def _universe_contains_strategy_symbols(
    strategy_configs: list[Any],
    universe: list[Any],
) -> bool:
    strategy_symbols = {
        str(config.get("symbol"))
        for config in strategy_configs
        if isinstance(config, Mapping) and config.get("symbol")
    }
    universe_symbols = {
        str(item.get("symbol"))
        for item in universe
        if isinstance(item, Mapping) and item.get("symbol")
    }

    return strategy_symbols.issubset(universe_symbols)


def _blocked_exports_have_reason(export: Mapping[str, Any]) -> bool:
    if export.get("status") != "blocked":
        return True

    blocked_reasons = export.get("blocked_reasons")
    return isinstance(blocked_reasons, list) and len(blocked_reasons) > 0


def _has_required_exclusions(export: Mapping[str, Any]) -> bool:
    required = {
        "broker_api_calls",
        "order_routing",
        "order_submission",
        "fills",
        "live_execution",
        "slippage_modeling",
    }

    exclusions = export.get("explicit_exclusions")
    if not isinstance(exclusions, list):
        return False

    return required.issubset({str(item) for item in exclusions})


def _build_operation_id(manifest: Mapping[str, Any]) -> str:
    manifest_id = str(manifest.get("manifest_id", "quantconnect_export_manifest"))
    return f"{OPERATION_TYPE}::{manifest_id}"


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
