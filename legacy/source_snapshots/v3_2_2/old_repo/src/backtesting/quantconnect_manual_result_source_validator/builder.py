from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


SCHEMA_VERSION = "quantconnect_manual_result_source_validation.v1"
VALIDATION_TYPE = "quantconnect_manual_result_source_validation"

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

REQUIRED_STATISTICS = [
    "total_trades",
    "win_rate",
    "drawdown",
    "sharpe_ratio",
    "net_profit",
]

SENSITIVE_KEY_FRAGMENTS = [
    "api_key",
    "apikey",
    "api_token",
    "token",
    "secret",
    "password",
    "credential",
]


def build_quantconnect_manual_result_source_validation(
    source: Any,
) -> dict[str, Any]:
    """Validate a filled manual QuantConnect result source.

    This validator does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses.

    It only validates a local JSON-like source before the manual backtest
    evidence pipeline is run.
    """

    if not isinstance(source, Mapping):
        return _blocked_invalid_shape("source must be a mapping/dict")

    source_copy = deepcopy(dict(source))

    result_import_source = _as_mapping(source_copy.get("result_import_source"))
    export_operation_result = _as_mapping(
        source_copy.get("export_operation_result")
    )
    export_payload = _extract_export_payload(export_operation_result)
    generated_payloads = _as_mapping(export_payload.get("generated_payloads"))
    backtest_manifest = _as_mapping(generated_payloads.get("backtest_manifest"))

    placeholders = _find_placeholders(source_copy)
    sensitive_fields = _find_sensitive_fields(source_copy)

    source_strategy_ids = _as_text_list(result_import_source.get("strategy_ids"))
    source_symbols = _as_text_list(result_import_source.get("symbols"))
    manifest_strategy_ids = _as_text_list(backtest_manifest.get("strategy_ids"))
    manifest_symbols = _as_text_list(backtest_manifest.get("symbols"))

    source_statistics = _as_mapping(result_import_source.get("statistics"))

    checks = [
        _check(
            name="no_unfilled_placeholders",
            passed=len(placeholders) == 0,
            severity="blocker",
            message="manual result source has no REPLACE_WITH placeholders",
            failure_message="manual result source still contains REPLACE_WITH placeholders",
        ),
        _check(
            name="no_sensitive_credential_fields",
            passed=len(sensitive_fields) == 0,
            severity="blocker",
            message="manual result source does not contain credential-like fields",
            failure_message="manual result source contains credential-like fields",
        ),
        _check(
            name="result_import_source_present",
            passed=bool(result_import_source),
            severity="blocker",
            message="result import source is present",
            failure_message="result_import_source is missing",
        ),
        _check(
            name="export_operation_result_present",
            passed=bool(export_operation_result),
            severity="blocker",
            message="export operation result is present",
            failure_message="export_operation_result is missing",
        ),
        _check(
            name="result_import_source_schema_version_expected",
            passed=(
                result_import_source.get("schema_version")
                == "quantconnect_result_import_source.v1"
            ),
            severity="blocker",
            message="result import source schema version is expected",
            failure_message="result import source schema version is missing or unexpected",
        ),
        _check(
            name="result_import_source_type_expected",
            passed=(
                result_import_source.get("source_type")
                == "manual_quantconnect_backtest_result"
            ),
            severity="blocker",
            message="result import source type is expected",
            failure_message="result import source type is missing or unexpected",
        ),
        _check(
            name="backtest_id_present",
            passed=bool(str(result_import_source.get("backtest_id") or "").strip()),
            severity="blocker",
            message="backtest id is present",
            failure_message="result_import_source.backtest_id is missing",
        ),
        _check(
            name="project_name_present",
            passed=bool(str(result_import_source.get("project_name") or "").strip()),
            severity="blocker",
            message="project name is present",
            failure_message="result_import_source.project_name is missing",
        ),
        _check(
            name="backtest_name_present",
            passed=bool(str(result_import_source.get("backtest_name") or "").strip()),
            severity="blocker",
            message="backtest name is present",
            failure_message="result_import_source.backtest_name is missing",
        ),
        _check(
            name="strategy_ids_present",
            passed=len(source_strategy_ids) > 0,
            severity="blocker",
            message="strategy ids are present",
            failure_message="result_import_source.strategy_ids is empty or missing",
        ),
        _check(
            name="symbols_present",
            passed=len(source_symbols) > 0,
            severity="blocker",
            message="symbols are present",
            failure_message="result_import_source.symbols is empty or missing",
        ),
        _check(
            name="statistics_present",
            passed=bool(source_statistics),
            severity="blocker",
            message="statistics are present",
            failure_message="result_import_source.statistics is missing",
        ),
        _check(
            name="required_statistics_present",
            passed=_has_required_statistics(source_statistics),
            severity="blocker",
            message="required statistics are present",
            failure_message=(
                "result_import_source.statistics is missing one or more "
                "required metrics"
            ),
        ),
        _check(
            name="export_operation_status_ready",
            passed=export_operation_result.get("status") == "ready",
            severity="blocker",
            message="export operation result is ready",
            failure_message="export_operation_result.status is not ready",
        ),
        _check(
            name="export_payload_present",
            passed=bool(export_payload),
            severity="blocker",
            message="export payload is present",
            failure_message="export_operation_result.export is missing",
        ),
        _check(
            name="generated_payloads_present",
            passed=bool(generated_payloads),
            severity="blocker",
            message="generated payloads are present",
            failure_message="export.generated_payloads is missing",
        ),
        _check(
            name="backtest_manifest_present",
            passed=bool(backtest_manifest),
            severity="blocker",
            message="backtest manifest is present",
            failure_message="export.generated_payloads.backtest_manifest is missing",
        ),
        _check(
            name="manifest_strategy_ids_present",
            passed=len(manifest_strategy_ids) > 0,
            severity="blocker",
            message="manifest strategy ids are present",
            failure_message="backtest_manifest.strategy_ids is empty or missing",
        ),
        _check(
            name="manifest_symbols_present",
            passed=len(manifest_symbols) > 0,
            severity="blocker",
            message="manifest symbols are present",
            failure_message="backtest_manifest.symbols is empty or missing",
        ),
        _check(
            name="strategy_ids_align_with_manifest",
            passed=_sets_match(source_strategy_ids, manifest_strategy_ids),
            severity="warning",
            message="source strategy ids align with manifest strategy ids",
            failure_message="source strategy ids do not align with manifest strategy ids",
        ),
        _check(
            name="symbols_align_with_manifest",
            passed=_sets_match(source_symbols, manifest_symbols),
            severity="warning",
            message="source symbols align with manifest symbols",
            failure_message="source symbols do not align with manifest symbols",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(source_copy),
            severity="blocker",
            message="manual-only exclusions are present",
            failure_message="one or more required manual-only exclusions are missing",
        ),
    ]

    status = _classify_status(checks)

    validation_warnings = [
        str(check.get("message"))
        for check in checks
        if check.get("status") == "warning"
    ]
    source_warnings = _collect_source_warnings(source_copy)

    blocked_reasons = [
        str(check.get("message"))
        for check in checks
        if check.get("status") == "failed"
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "validation_type": VALIDATION_TYPE,
        "status": status,
        "summary": {
            "source_schema_version": source_copy.get("schema_version"),
            "source_type": source_copy.get("source_type"),
            "backtest_id": result_import_source.get("backtest_id"),
            "project_name": result_import_source.get("project_name"),
            "backtest_name": result_import_source.get("backtest_name"),
            "strategy_count": len(_sorted_unique_text(source_strategy_ids)),
            "symbol_count": len(_sorted_unique_text(source_symbols)),
            "manifest_strategy_count": len(
                _sorted_unique_text(manifest_strategy_ids)
            ),
            "manifest_symbol_count": len(_sorted_unique_text(manifest_symbols)),
            "placeholder_count": len(placeholders),
            "sensitive_field_count": len(sensitive_fields),
            "check_count": len(checks),
            "passed_check_count": sum(
                1 for check in checks if check.get("status") == "passed"
            ),
            "warning_check_count": sum(
                1 for check in checks if check.get("status") == "warning"
            ),
            "failed_check_count": sum(
                1 for check in checks if check.get("status") == "failed"
            ),
            "blocked_reason_count": len(blocked_reasons),
            "warning_count": len(
                _sorted_unique_text(validation_warnings + source_warnings)
            ),
            "can_enter_manual_backtest_pipeline": status == "ready",
        },
        "checks": checks,
        "placeholders": placeholders,
        "sensitive_fields": sensitive_fields,
        "result_import_source_summary": {
            "schema_version": result_import_source.get("schema_version"),
            "source_type": result_import_source.get("source_type"),
            "backtest_id": result_import_source.get("backtest_id"),
            "project_name": result_import_source.get("project_name"),
            "backtest_name": result_import_source.get("backtest_name"),
            "strategy_ids": _sorted_unique_text(source_strategy_ids),
            "symbols": _sorted_unique_text(source_symbols),
            "statistics_keys": sorted(source_statistics.keys()),
        },
        "export_operation_summary": {
            "schema_version": export_operation_result.get("schema_version"),
            "operation_type": export_operation_result.get("operation_type"),
            "status": export_operation_result.get("status"),
            "export_schema_version": export_payload.get("schema_version"),
            "export_status": export_payload.get("status"),
            "manifest_id": backtest_manifest.get("manifest_id"),
            "manifest_backtest_id": backtest_manifest.get("backtest_id"),
            "manifest_strategy_ids": _sorted_unique_text(manifest_strategy_ids),
            "manifest_symbols": _sorted_unique_text(manifest_symbols),
        },
        "warnings": _sorted_unique_text(validation_warnings + source_warnings),
        "blocked_reasons": blocked_reasons,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _blocked_invalid_shape(reason: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "validation_type": VALIDATION_TYPE,
        "status": "blocked",
        "summary": {
            "source_schema_version": None,
            "source_type": None,
            "backtest_id": None,
            "project_name": None,
            "backtest_name": None,
            "strategy_count": 0,
            "symbol_count": 0,
            "manifest_strategy_count": 0,
            "manifest_symbol_count": 0,
            "placeholder_count": 0,
            "sensitive_field_count": 0,
            "check_count": 0,
            "passed_check_count": 0,
            "warning_check_count": 0,
            "failed_check_count": 0,
            "blocked_reason_count": 1,
            "warning_count": 0,
            "can_enter_manual_backtest_pipeline": False,
        },
        "checks": [],
        "placeholders": [],
        "sensitive_fields": [],
        "result_import_source_summary": {},
        "export_operation_summary": {},
        "warnings": [],
        "blocked_reasons": [reason],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _extract_export_payload(
    export_operation_result: Mapping[str, Any],
) -> dict[str, Any]:
    export = export_operation_result.get("export")

    if isinstance(export, Mapping):
        return dict(export)

    operation_result = export_operation_result.get("operation_result")

    if isinstance(operation_result, Mapping):
        export = operation_result.get("export")

        if isinstance(export, Mapping):
            return dict(export)

    return {}


def _find_placeholders(value: Any, path: str = "$") -> list[dict[str, str]]:
    placeholders: list[dict[str, str]] = []

    if isinstance(value, Mapping):
        for key, item in value.items():
            placeholders.extend(
                _find_placeholders(item, f"{path}.{str(key)}")
            )

    elif isinstance(value, list):
        for index, item in enumerate(value):
            placeholders.extend(_find_placeholders(item, f"{path}[{index}]"))

    elif isinstance(value, str) and "REPLACE_WITH_" in value:
        placeholders.append(
            {
                "path": path,
                "value": value,
            }
        )

    return placeholders


def _find_sensitive_fields(value: Any, path: str = "$") -> list[dict[str, str]]:
    sensitive_fields: list[dict[str, str]] = []

    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).lower()

            if any(fragment in key_text for fragment in SENSITIVE_KEY_FRAGMENTS):
                sensitive_fields.append(
                    {
                        "path": f"{path}.{str(key)}",
                        "key": str(key),
                    }
                )

            sensitive_fields.extend(
                _find_sensitive_fields(item, f"{path}.{str(key)}")
            )

    elif isinstance(value, list):
        for index, item in enumerate(value):
            sensitive_fields.extend(
                _find_sensitive_fields(item, f"{path}[{index}]")
            )

    return sensitive_fields


def _collect_source_warnings(source: Mapping[str, Any]) -> list[str]:
    return _collect_text_values_by_key(source, "warnings")


def _collect_text_values_by_key(value: Any, key: str) -> list[str]:
    values: list[str] = []

    if isinstance(value, Mapping):
        for item_key, item_value in value.items():
            if item_key == key:
                values.extend(_as_text_list(item_value))
            else:
                values.extend(_collect_text_values_by_key(item_value, key))

    elif isinstance(value, list):
        for item in value:
            values.extend(_collect_text_values_by_key(item, key))

    return values


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

    return {
        "name": name,
        "status": "failed" if severity == "blocker" else "warning",
        "severity": severity,
        "message": failure_message,
    }


def _classify_status(checks: list[Mapping[str, Any]]) -> str:
    if any(check.get("status") == "failed" for check in checks):
        return "blocked"

    if any(check.get("status") == "warning" for check in checks):
        return "needs_review"

    return "ready"


def _has_required_statistics(statistics: Mapping[str, Any]) -> bool:
    return all(
        key in statistics
        and str(statistics.get(key)).strip()
        and "REPLACE_WITH_" not in str(statistics.get(key))
        for key in REQUIRED_STATISTICS
    )


def _has_required_exclusions(source: Mapping[str, Any]) -> bool:
    exclusions = source.get("explicit_exclusions")

    if not isinstance(exclusions, list):
        return False

    return set(EXPLICIT_EXCLUSIONS).issubset({str(item) for item in exclusions})


def _sets_match(left: list[str], right: list[str]) -> bool:
    if not left or not right:
        return False

    return set(_sorted_unique_text(left)) == set(_sorted_unique_text(right))


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
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    if isinstance(value, tuple):
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    return [str(value).strip()] if str(value).strip() else []


def _sorted_unique_text(values: list[str]) -> list[str]:
    return sorted(
        {
            value.strip()
            for value in values
            if value and value.strip()
        }
    )
