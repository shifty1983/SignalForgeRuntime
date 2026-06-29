from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


SCHEMA_VERSION = "quantconnect_api_config.v1"
CONFIG_TYPE = "quantconnect_backtest_result_api_config"

DEFAULT_API_BASE_URL = "https://www.quantconnect.com/api/v2"
DEFAULT_USER_ID_ENV = "SIGNALFORGE_QUANTCONNECT_USER_ID"
DEFAULT_API_TOKEN_ENV = "SIGNALFORGE_QUANTCONNECT_API_TOKEN"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 0

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "local_fill_simulation",
    "local_slippage_modeling",
    "external_data_warehouse_access",
]


def build_quantconnect_api_config(
    source: Any,
    *,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build a safe QuantConnect API config contract.

    This builder does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses.

    API tokens are never written to the returned artifact. The result only records
    which environment variable should be used later by the API client wrapper.
    """

    if not isinstance(source, Mapping):
        return _blocked_invalid_shape("source must be a mapping/dict")

    source_copy = deepcopy(dict(source))
    config_source = _extract_config_source(source_copy)
    env = dict(environment or {})

    api_base_url = _clean_text(
        config_source.get("api_base_url"),
        fallback=DEFAULT_API_BASE_URL,
    )
    user_id_env = _clean_text(
        config_source.get("user_id_env"),
        fallback=DEFAULT_USER_ID_ENV,
    )
    api_token_env = _clean_text(
        config_source.get("api_token_env"),
        fallback=DEFAULT_API_TOKEN_ENV,
    )

    request_timeout_seconds = _safe_int(
        config_source.get("request_timeout_seconds"),
        DEFAULT_REQUEST_TIMEOUT_SECONDS,
    )
    max_retries = _safe_int(
        config_source.get("max_retries"),
        DEFAULT_MAX_RETRIES,
    )

    project_id = _clean_optional_text(config_source.get("project_id"))
    backtest_id = _clean_optional_text(config_source.get("backtest_id"))

    direct_user_id = _clean_optional_text(config_source.get("user_id"))
    env_user_id = _clean_optional_text(env.get(user_id_env))
    user_id = direct_user_id or env_user_id

    token_value = _clean_optional_text(env.get(api_token_env))
    token_present = token_value is not None

    warnings: list[str] = []
    blocked_reasons: list[str] = []

    if not _is_http_url(api_base_url):
        blocked_reasons.append("api_base_url must be an http or https URL")

    if request_timeout_seconds <= 0:
        blocked_reasons.append("request_timeout_seconds must be greater than zero")

    if max_retries < 0:
        blocked_reasons.append("max_retries must be zero or greater")

    if "api_token" in config_source:
        warnings.append(
            "api_token value was ignored; provide the token through an environment variable"
        )

    if not user_id:
        warnings.append("QuantConnect user id is missing")

    if not token_present:
        warnings.append(
            f"QuantConnect API token is missing from environment variable: {api_token_env}"
        )

    warnings = _sorted_unique_text(warnings)
    blocked_reasons = _sorted_unique_text(blocked_reasons)

    status = _classify_status(
        user_id_present=bool(user_id),
        token_present=token_present,
        blocked_reasons=blocked_reasons,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "config_type": CONFIG_TYPE,
        "status": status,
        "summary": {
            "api_base_url": api_base_url,
            "user_id_present": bool(user_id),
            "api_token_present": token_present,
            "project_id_present": bool(project_id),
            "backtest_id_present": bool(backtest_id),
            "request_timeout_seconds": request_timeout_seconds,
            "max_retries": max_retries,
            "warning_count": len(warnings),
            "blocked_reason_count": len(blocked_reasons),
        },
        "connection": {
            "api_base_url": api_base_url,
            "request_timeout_seconds": request_timeout_seconds,
            "max_retries": max_retries,
        },
        "credentials": {
            "user_id": user_id,
            "user_id_source": "direct"
            if direct_user_id
            else "environment"
            if env_user_id
            else "missing",
            "user_id_env": user_id_env,
            "user_id_present": bool(user_id),
            "api_token_env": api_token_env,
            "api_token_source": "environment" if token_present else "missing",
            "api_token_present": token_present,
            "api_token_value_persisted": False,
        },
        "backtest_context": {
            "project_id": project_id,
            "backtest_id": backtest_id,
            "project_id_present": bool(project_id),
            "backtest_id_present": bool(backtest_id),
        },
        "requested_api_capabilities": [
            "read_project",
            "read_backtest",
            "read_backtest_results",
        ],
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _blocked_invalid_shape(reason: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "config_type": CONFIG_TYPE,
        "status": "blocked",
        "summary": {
            "api_base_url": DEFAULT_API_BASE_URL,
            "user_id_present": False,
            "api_token_present": False,
            "project_id_present": False,
            "backtest_id_present": False,
            "request_timeout_seconds": DEFAULT_REQUEST_TIMEOUT_SECONDS,
            "max_retries": DEFAULT_MAX_RETRIES,
            "warning_count": 0,
            "blocked_reason_count": 1,
        },
        "connection": {
            "api_base_url": DEFAULT_API_BASE_URL,
            "request_timeout_seconds": DEFAULT_REQUEST_TIMEOUT_SECONDS,
            "max_retries": DEFAULT_MAX_RETRIES,
        },
        "credentials": {
            "user_id": None,
            "user_id_source": "missing",
            "user_id_env": DEFAULT_USER_ID_ENV,
            "user_id_present": False,
            "api_token_env": DEFAULT_API_TOKEN_ENV,
            "api_token_source": "missing",
            "api_token_present": False,
            "api_token_value_persisted": False,
        },
        "backtest_context": {
            "project_id": None,
            "backtest_id": None,
            "project_id_present": False,
            "backtest_id_present": False,
        },
        "requested_api_capabilities": [
            "read_project",
            "read_backtest",
            "read_backtest_results",
        ],
        "warnings": [],
        "blocked_reasons": [reason],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _extract_config_source(source: Mapping[str, Any]) -> dict[str, Any]:
    if source.get("schema_version") == SCHEMA_VERSION:
        return dict(source)

    config = source.get("config")
    if isinstance(config, Mapping):
        return dict(config)

    quantconnect_api_config = source.get("quantconnect_api_config")
    if isinstance(quantconnect_api_config, Mapping):
        return dict(quantconnect_api_config)

    return dict(source)


def _classify_status(
    *,
    user_id_present: bool,
    token_present: bool,
    blocked_reasons: list[str],
) -> str:
    if blocked_reasons:
        return "blocked"

    if user_id_present and token_present:
        return "ready"

    return "needs_review"


def _clean_text(value: Any, *, fallback: str) -> str:
    if value is None:
        return fallback

    text = str(value).strip()
    return text if text else fallback


def _clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text if text else None


def _is_http_url(value: str) -> bool:
    return value.startswith("https://") or value.startswith("http://")


def _safe_int(value: Any, default: int) -> int:
    if value is None:
        return default

    if isinstance(value, bool):
        return default

    if isinstance(value, int):
        return value

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _sorted_unique_text(values: list[str]) -> list[str]:
    return sorted({value.strip() for value in values if value and value.strip()})
