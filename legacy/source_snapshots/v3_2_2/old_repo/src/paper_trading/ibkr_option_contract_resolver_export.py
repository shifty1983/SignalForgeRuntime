from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence


ADAPTER_TYPE = "ibkr_option_contract_resolver_export"

ARTIFACT_TYPE = "signalforge_ibkr_option_contract_resolver_export"
SUMMARY_ARTIFACT_TYPE = "signalforge_ibkr_option_contract_resolver_export_summary"
WRITE_RESULT_ARTIFACT_TYPE = "ibkr_option_contract_resolver_export_write_result"

EXPORT_FILENAME = "signalforge_ibkr_option_contract_resolver_export.json"
SUMMARY_FILENAME = "signalforge_ibkr_option_contract_resolver_export_summary.json"

DEFAULT_TIMEOUT_SECONDS = 12.0

EXPLICIT_EXCLUSIONS = [
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
    "automatic_close_orders",
    "automatic_roll_orders",
    "automatic_defense_orders",
    "automatic_strategy_changes",
    "automatic_parameter_changes",
    "automatic_pause_actions",
]

EXECUTION_DISABLED_FIELDS = {
    "automatic_action": None,
    "automatic_close_order": None,
    "automatic_defense_order": None,
    "automatic_parameter_change": None,
    "automatic_pause_action": None,
    "automatic_roll_order": None,
    "automatic_strategy_change": None,
}

OptionChainFetcher = Callable[[str, str, int, int, float], Mapping[str, Any]]


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, sort_keys=True)
        file.write("\n")


def export_ibkr_option_contract_resolver(
    *,
    paper_order_intent_operation_path: str | Path,
    account_snapshot_operation_path: str | Path,
    output_dir: str | Path,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    option_chain_fetcher: Optional[OptionChainFetcher] = None,
) -> Dict[str, Any]:
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    export_path = output_dir_obj / EXPORT_FILENAME
    summary_path = output_dir_obj / SUMMARY_FILENAME

    try:
        paper_order_intent_operation = load_json(paper_order_intent_operation_path)
        paper_order_intent_operation = hydrate_paper_order_intent_operation_details(
            paper_order_intent_operation,
            operation_path=paper_order_intent_operation_path,
        )
    except Exception as exc:  # pragma: no cover
        paper_order_intent_operation = {
            "operation_state": "blocked",
            "intent_state": "blocked",
            "blocked_reasons": [
                "paper_order_intent_operation_load_failed",
                f"{type(exc).__name__}: {exc}",
            ],
            "warnings": [],
        }

    try:
        account_snapshot_operation = load_json(account_snapshot_operation_path)
    except Exception as exc:  # pragma: no cover
        account_snapshot_operation = {
            "operation_state": "blocked",
            "snapshot_state": "blocked",
            "blocked_reasons": [
                "account_snapshot_operation_load_failed",
                f"{type(exc).__name__}: {exc}",
            ],
            "warnings": [],
        }

    export_payload = build_ibkr_option_contract_resolver_export(
        paper_order_intent_operation,
        account_snapshot_operation,
        paper_order_intent_operation_path=str(paper_order_intent_operation_path),
        account_snapshot_operation_path=str(account_snapshot_operation_path),
        timeout_seconds=timeout_seconds,
        option_chain_fetcher=option_chain_fetcher,
    )

    summary_payload = build_ibkr_option_contract_resolver_export_summary(
        export_payload,
        export_path=str(export_path),
        summary_path=str(summary_path),
    )

    write_json(export_path, export_payload)
    write_json(summary_path, summary_payload)

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": WRITE_RESULT_ARTIFACT_TYPE,
        "contract_resolution_state": export_payload["contract_resolution_state"],
        "paper_trading_mode": export_payload["paper_trading_mode"],
        "order_submission_enabled": export_payload["order_submission_enabled"],
        "requires_manual_approval": export_payload["requires_manual_approval"],
        "symbol": export_payload["symbol"],
        "strategy_direction": export_payload["strategy_direction"],
        "spread_type": export_payload["spread_type"],
        "expiration": export_payload["expiration"],
        "underlying_price": export_payload["underlying_price"],
        "long_leg": export_payload["long_leg"],
        "short_leg": export_payload["short_leg"],
        "blocked_reasons": export_payload["blocked_reasons"],
        "warnings": export_payload["warnings"],
        "export_path": str(export_path),
        "summary_path": str(summary_path),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_option_contract_resolver_export(
    paper_order_intent_operation: Any,
    account_snapshot_operation: Any,
    *,
    paper_order_intent_operation_path: Optional[str] = None,
    account_snapshot_operation_path: Optional[str] = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    option_chain_fetcher: Optional[OptionChainFetcher] = None,
) -> Dict[str, Any]:
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if not isinstance(paper_order_intent_operation, Mapping):
        paper_order_intent_operation = {}
        blocked_reasons.extend(
            [
                "paper_order_intent_operation_invalid_shape",
                "paper_order_intent_operation_must_be_json_object",
            ]
        )

    if not isinstance(account_snapshot_operation, Mapping):
        account_snapshot_operation = {}
        blocked_reasons.extend(
            [
                "account_snapshot_operation_invalid_shape",
                "account_snapshot_operation_must_be_json_object",
            ]
        )

    blocked_reasons.extend(
        _dedupe_strings(paper_order_intent_operation.get("blocked_reasons", []))
    )
    blocked_reasons.extend(
        _dedupe_strings(account_snapshot_operation.get("blocked_reasons", []))
    )

    warnings.extend(_dedupe_strings(paper_order_intent_operation.get("warnings", [])))
    warnings.extend(_dedupe_strings(account_snapshot_operation.get("warnings", [])))

    intent_operation_state = paper_order_intent_operation.get("operation_state")
    intent_state = paper_order_intent_operation.get("intent_state")
    snapshot_operation_state = account_snapshot_operation.get("operation_state")
    snapshot_state = account_snapshot_operation.get("snapshot_state")

    if intent_operation_state != "ready":
        blocked_reasons.append("paper_order_intent_operation_must_be_ready")

    if intent_state != "ready":
        blocked_reasons.append("paper_order_intent_state_must_be_ready")

    if snapshot_operation_state != "ready":
        blocked_reasons.append("account_snapshot_operation_must_be_ready")

    if snapshot_state != "ready":
        blocked_reasons.append("account_snapshot_state_must_be_ready")

    if paper_order_intent_operation.get("order_submission_enabled") is True:
        blocked_reasons.append("order_submission_must_be_disabled_for_contract_resolver")

    symbol = _clean_string(paper_order_intent_operation.get("symbol"))
    instrument_type = _clean_string(paper_order_intent_operation.get("instrument_type"))
    strategy_direction = _clean_string(
        paper_order_intent_operation.get("strategy_direction")
    )
    selected_window_days = _as_int(
        paper_order_intent_operation.get("selected_window_days")
    ) or 21

    order_intent = paper_order_intent_operation.get("order_intent")
    if not isinstance(order_intent, Mapping):
        order_intent = {}

    contract_selection_rules = order_intent.get("contract_selection_rules")
    if not isinstance(contract_selection_rules, Mapping):
        contract_selection_rules = {}

    risk_budget = order_intent.get("risk_budget")
    if not isinstance(risk_budget, Mapping):
        risk_budget = {}

    right = _clean_string(contract_selection_rules.get("right"))
    expiration_selection = _clean_string(
        contract_selection_rules.get("expiration_selection")
    )
    strike_selection = _clean_string(contract_selection_rules.get("strike_selection"))

    if not symbol:
        blocked_reasons.append("symbol_required")

    if instrument_type not in {"option_strategy", "options", "option"}:
        blocked_reasons.append("instrument_type_must_be_option_strategy")

    if strategy_direction != "bullish_defined_risk":
        blocked_reasons.append("strategy_direction_must_be_bullish_defined_risk")

    if right != "CALL_SPREAD":
        blocked_reasons.append("right_must_be_CALL_SPREAD")

    if not expiration_selection:
        blocked_reasons.append("expiration_selection_required")

    if not strike_selection:
        blocked_reasons.append("strike_selection_required")

    broker = account_snapshot_operation.get("broker")
    trading_mode = account_snapshot_operation.get("trading_mode")
    host = account_snapshot_operation.get("host")
    port = _as_int(account_snapshot_operation.get("port"))
    client_id = _as_int(account_snapshot_operation.get("client_id"))

    if broker != "ibkr":
        blocked_reasons.append("broker_must_be_ibkr")

    if trading_mode != "paper":
        blocked_reasons.append("trading_mode_must_be_paper")

    if not host:
        blocked_reasons.append("host_required")

    if port is None:
        blocked_reasons.append("port_required")

    if client_id is None:
        blocked_reasons.append("client_id_required")

    fetch_result: Mapping[str, Any] = {}
    option_chain_request_attempted = False
    market_data_request_attempted = False
    broker_api_protocol_handshake_attempted = False

    if not blocked_reasons:
        fetcher = option_chain_fetcher or _default_ibkr_option_chain_fetcher

        try:
            fetch_result = fetcher(
                str(symbol),
                str(host),
                int(port),
                int(client_id),
                float(timeout_seconds),
            )
        except Exception as exc:  # pragma: no cover
            fetch_result = {
                "connection_succeeded": False,
                "underlying_price": None,
                "option_chains": [],
                "warnings": [],
                "errors": [f"{type(exc).__name__}: {exc}"],
                "informational_messages": [],
                "liquidity_checks_supported": False,
            }

        broker_api_protocol_handshake_attempted = True
        option_chain_request_attempted = True
        market_data_request_attempted = True

        warnings.extend(_dedupe_strings(fetch_result.get("warnings", [])))
        warnings.extend(_dedupe_strings(fetch_result.get("errors", [])))

        if not bool(fetch_result.get("connection_succeeded")):
            blocked_reasons.append("ibkr_option_chain_fetch_failed")

    underlying_price = _as_float(fetch_result.get("underlying_price"))
    option_chains = _normalize_option_chains(fetch_result.get("option_chains", []))

    if not blocked_reasons and underlying_price is None:
        blocked_reasons.append("underlying_price_required_for_contract_resolution")

    if not blocked_reasons and not option_chains:
        blocked_reasons.append("option_chain_required_for_contract_resolution")

    resolved_contract: Optional[Dict[str, Any]] = None

    if not blocked_reasons:
        resolved_contract, resolution_blockers, resolution_warnings = (
            _resolve_bull_call_spread(
                symbol=str(symbol),
                option_chains=option_chains,
                underlying_price=float(underlying_price),
                selected_window_days=selected_window_days,
                contract_selection_rules=contract_selection_rules,
            )
        )
        blocked_reasons.extend(resolution_blockers)
        warnings.extend(resolution_warnings)

    liquidity_checks_supported = bool(fetch_result.get("liquidity_checks_supported"))

    if (
        not liquidity_checks_supported
        and not blocked_reasons
        and (
            contract_selection_rules.get("max_bid_ask_spread") is not None
            or contract_selection_rules.get("min_open_interest") is not None
        )
    ):
        warnings.append("option_liquidity_rules_not_verified_by_contract_resolver")

    expiration = resolved_contract.get("expiration") if resolved_contract else None
    long_leg = resolved_contract.get("long_leg") if resolved_contract else None
    short_leg = resolved_contract.get("short_leg") if resolved_contract else None
    spread_type = resolved_contract.get("spread_type") if resolved_contract else None

    contract_resolution_state = _classify_state(
        blocked_reasons=blocked_reasons,
        warnings=warnings,
    )

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": ARTIFACT_TYPE,
        "contract_resolution_state": contract_resolution_state,
        "paper_trading_mode": True,
        "order_submission_enabled": False,
        "requires_manual_approval": True,
        "broker": broker,
        "trading_mode": trading_mode,
        "host": host,
        "port": port,
        "client_id": client_id,
        "symbol": symbol,
        "instrument_type": instrument_type,
        "strategy_direction": strategy_direction,
        "spread_type": spread_type,
        "selected_window_days": selected_window_days,
        "expiration": expiration,
        "underlying_price": underlying_price,
        "long_leg": long_leg,
        "short_leg": short_leg,
        "max_trade_risk_amount": _as_float(
            risk_budget.get("max_trade_risk_amount")
        ),
        "max_contract_quantity": _as_int(risk_budget.get("max_contract_quantity")),
        "contract_selection_rules": _json_safe(contract_selection_rules),
        "broker_api_protocol_handshake_attempted": broker_api_protocol_handshake_attempted,
        "option_chain_request_attempted": option_chain_request_attempted,
        "market_data_request_attempted": market_data_request_attempted,
        "order_submission_attempted": False,
        "option_chain_count": len(option_chains),
        "liquidity_checks_supported": liquidity_checks_supported,
        "informational_messages": _dedupe_strings(
            fetch_result.get("informational_messages", [])
        ),
        "paper_order_intent_operation_path": paper_order_intent_operation_path,
        "account_snapshot_operation_path": account_snapshot_operation_path,
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "warnings": _dedupe_strings(warnings),
        **EXECUTION_DISABLED_FIELDS,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_option_contract_resolver_export_summary(
    export_payload: Mapping[str, Any],
    *,
    export_path: Optional[str] = None,
    summary_path: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": SUMMARY_ARTIFACT_TYPE,
        "contract_resolution_state": export_payload.get("contract_resolution_state"),
        "paper_trading_mode": export_payload.get("paper_trading_mode"),
        "order_submission_enabled": export_payload.get("order_submission_enabled"),
        "requires_manual_approval": export_payload.get("requires_manual_approval"),
        "symbol": export_payload.get("symbol"),
        "strategy_direction": export_payload.get("strategy_direction"),
        "spread_type": export_payload.get("spread_type"),
        "expiration": export_payload.get("expiration"),
        "underlying_price": export_payload.get("underlying_price"),
        "long_leg": export_payload.get("long_leg"),
        "short_leg": export_payload.get("short_leg"),
        "option_chain_count": export_payload.get("option_chain_count", 0),
        "broker_api_protocol_handshake_attempted": export_payload.get(
            "broker_api_protocol_handshake_attempted"
        ),
        "option_chain_request_attempted": export_payload.get(
            "option_chain_request_attempted"
        ),
        "market_data_request_attempted": export_payload.get(
            "market_data_request_attempted"
        ),
        "order_submission_attempted": export_payload.get(
            "order_submission_attempted"
        ),
        "liquidity_checks_supported": export_payload.get(
            "liquidity_checks_supported"
        ),
        "blocked_reason_count": len(export_payload.get("blocked_reasons", [])),
        "warning_count": len(export_payload.get("warnings", [])),
        "blocked_reasons": export_payload.get("blocked_reasons", []),
        "warnings": export_payload.get("warnings", []),
        "output_files": {
            "export": export_path,
            "summary": summary_path,
        },
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def hydrate_paper_order_intent_operation_details(
    paper_order_intent_operation: Any,
    *,
    operation_path: str | Path,
) -> Any:
    if not isinstance(paper_order_intent_operation, Mapping):
        return paper_order_intent_operation

    if isinstance(paper_order_intent_operation.get("order_intent"), Mapping):
        return paper_order_intent_operation

    output_files = paper_order_intent_operation.get("output_files")

    if not isinstance(output_files, Mapping):
        return paper_order_intent_operation

    export_path = output_files.get("export")

    if not export_path:
        return paper_order_intent_operation

    export_path_obj = Path(export_path)

    if not export_path_obj.exists():
        operation_path_obj = Path(operation_path)
        candidate_path = operation_path_obj.parent / export_path_obj.name

        if candidate_path.exists():
            export_path_obj = candidate_path

    if not export_path_obj.exists():
        return paper_order_intent_operation

    export_payload = load_json(export_path_obj)

    if not isinstance(export_payload, Mapping):
        return paper_order_intent_operation

    hydrated = dict(paper_order_intent_operation)

    for key in [
        "selected_window_days",
        "symbol",
        "instrument_type",
        "strategy_direction",
        "max_trade_risk_amount",
        "max_account_allocation_fraction",
        "max_contract_quantity",
        "order_intent",
    ]:
        if key in export_payload:
            hydrated[key] = export_payload[key]

    return hydrated


def _resolve_bull_call_spread(
    *,
    symbol: str,
    option_chains: Sequence[Mapping[str, Any]],
    underlying_price: float,
    selected_window_days: int,
    contract_selection_rules: Mapping[str, Any],
) -> tuple[Optional[Dict[str, Any]], list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []

    expirations = _collect_expirations(option_chains)
    strikes = _collect_strikes(option_chains)

    if not expirations:
        return None, ["option_expirations_required"], warnings

    if len(strikes) < 2:
        return None, ["at_least_two_option_strikes_required"], warnings

    target_expiration = _select_expiration_at_or_after_days(
        expirations,
        selected_window_days,
    )

    if target_expiration is None:
        return None, ["no_expiration_at_or_after_selected_window_days"], warnings

    long_strike, short_strike = _select_bull_call_spread_strikes(
        strikes,
        underlying_price,
        contract_selection_rules,
    )

    if long_strike is None or short_strike is None:
        return None, ["unable_to_select_bull_call_spread_strikes"], warnings

    if short_strike <= long_strike:
        return None, ["short_call_strike_must_be_above_long_call_strike"], warnings

    chain = option_chains[0]
    exchange = chain.get("exchange") or "SMART"
    trading_class = chain.get("trading_class") or symbol
    multiplier = str(chain.get("multiplier") or "100")

    return (
        {
            "spread_type": "bull_call_spread",
            "underlying_symbol": symbol,
            "expiration": target_expiration,
            "underlying_price": underlying_price,
            "long_leg": {
                "action": "BUY",
                "symbol": symbol,
                "sec_type": "OPT",
                "exchange": exchange,
                "currency": "USD",
                "trading_class": trading_class,
                "last_trade_date_or_contract_month": target_expiration,
                "right": "C",
                "strike": long_strike,
                "multiplier": multiplier,
            },
            "short_leg": {
                "action": "SELL",
                "symbol": symbol,
                "sec_type": "OPT",
                "exchange": exchange,
                "currency": "USD",
                "trading_class": trading_class,
                "last_trade_date_or_contract_month": target_expiration,
                "right": "C",
                "strike": short_strike,
                "multiplier": multiplier,
            },
        },
        blockers,
        warnings,
    )


def _default_ibkr_option_chain_fetcher(
    symbol: str,
    host: str,
    port: int,
    client_id: int,
    timeout_seconds: float,
) -> Mapping[str, Any]:
    try:
        from ibapi.client import EClient
        from ibapi.contract import Contract
        from ibapi.wrapper import EWrapper
    except ModuleNotFoundError:
        return {
            "connection_succeeded": False,
            "underlying_price": None,
            "option_chains": [],
            "warnings": [],
            "errors": ["ibapi_package_not_installed"],
            "informational_messages": [],
            "liquidity_checks_supported": False,
        }

    class OptionChainApp(EWrapper, EClient):
        def __init__(self) -> None:
            EWrapper.__init__(self)
            EClient.__init__(self, self)

            self.connected_event = threading.Event()
            self.contract_details_end_event = threading.Event()
            self.secdef_end_event = threading.Event()
            self.price_event = threading.Event()

            self.underlying_con_id: Optional[int] = None
            self.underlying_price: Optional[float] = None
            self.option_chains: list[dict[str, Any]] = []
            self.errors: list[str] = []
            self.informational_messages: list[str] = []

        def nextValidId(self, orderId: int) -> None:
            self.connected_event.set()

        def contractDetails(self, reqId: int, contractDetails: Any) -> None:
            contract = contractDetails.contract
            self.underlying_con_id = getattr(contract, "conId", None)

        def contractDetailsEnd(self, reqId: int) -> None:
            self.contract_details_end_event.set()

        def securityDefinitionOptionParameter(
            self,
            reqId: int,
            exchange: str,
            underlyingConId: int,
            tradingClass: str,
            multiplier: str,
            expirations: set[str],
            strikes: set[float],
        ) -> None:
            self.option_chains.append(
                {
                    "exchange": exchange,
                    "underlying_con_id": underlyingConId,
                    "trading_class": tradingClass,
                    "multiplier": multiplier,
                    "expirations": sorted(expirations),
                    "strikes": sorted(float(strike) for strike in strikes),
                }
            )

        def securityDefinitionOptionParameterEnd(self, reqId: int) -> None:
            self.secdef_end_event.set()

        def tickPrice(self, reqId: int, tickType: int, price: float, attrib: Any) -> None:
            if price is not None and price > 0:
                self.underlying_price = float(price)
                self.price_event.set()

        def error(
            self,
            reqId: int,
            errorCode: int,
            errorString: str,
            advancedOrderRejectJson: str = "",
        ) -> None:
            message = f"{errorCode}: {errorString}"

            if _is_ibkr_informational_message(errorCode):
                self.informational_messages.append(message)
                return

            self.errors.append(message)

    app = OptionChainApp()
    warnings: list[str] = []

    stock = Contract()
    stock.symbol = symbol
    stock.secType = "STK"
    stock.exchange = "SMART"
    stock.currency = "USD"

    try:
        app.connect(host, port, clientId=client_id)

        thread = threading.Thread(target=app.run, daemon=True)
        thread.start()

        connected = app.connected_event.wait(timeout=timeout_seconds)

        if not connected:
            app.disconnect()
            return {
                "connection_succeeded": False,
                "underlying_price": None,
                "option_chains": [],
                "warnings": warnings,
                "errors": ["ibkr_api_next_valid_id_timeout"],
                "informational_messages": app.informational_messages,
                "liquidity_checks_supported": False,
            }

        app.reqContractDetails(9301, stock)
        app.contract_details_end_event.wait(timeout=timeout_seconds)

        if app.underlying_con_id is None:
            app.disconnect()
            return {
                "connection_succeeded": False,
                "underlying_price": None,
                "option_chains": [],
                "warnings": warnings,
                "errors": ["underlying_contract_details_not_resolved"],
                "informational_messages": app.informational_messages,
                "liquidity_checks_supported": False,
            }

        app.reqMarketDataType(3)
        app.reqMktData(9302, stock, "", True, False, [])
        app.price_event.wait(timeout=timeout_seconds)

        if app.underlying_price is None:
            warnings.append("underlying_price_snapshot_timeout")

        app.reqSecDefOptParams(9303, symbol, "", "STK", app.underlying_con_id)
        app.secdef_end_event.wait(timeout=timeout_seconds)

        time.sleep(0.25)
        app.disconnect()

        return {
            "connection_succeeded": True,
            "underlying_price": app.underlying_price,
            "option_chains": app.option_chains,
            "warnings": warnings,
            "errors": app.errors,
            "informational_messages": app.informational_messages,
            "liquidity_checks_supported": False,
        }

    except Exception as exc:  # pragma: no cover
        try:
            app.disconnect()
        except Exception:
            pass

        return {
            "connection_succeeded": False,
            "underlying_price": None,
            "option_chains": [],
            "warnings": warnings,
            "errors": [f"{type(exc).__name__}: {exc}"],
            "informational_messages": app.informational_messages,
            "liquidity_checks_supported": False,
        }


def _normalize_option_chains(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []

    chains: list[dict[str, Any]] = []

    for item in value:
        if not isinstance(item, Mapping):
            continue

        chains.append(
            {
                "exchange": item.get("exchange"),
                "trading_class": item.get("trading_class"),
                "multiplier": item.get("multiplier"),
                "expirations": list(item.get("expirations") or []),
                "strikes": list(item.get("strikes") or []),
            }
        )

    return chains


def _collect_expirations(option_chains: Sequence[Mapping[str, Any]]) -> list[str]:
    expirations: set[str] = set()

    for chain in option_chains:
        for expiration in chain.get("expirations") or []:
            parsed = _parse_expiration(expiration)
            if parsed is not None:
                expirations.add(parsed.strftime("%Y%m%d"))

    return sorted(expirations)


def _collect_strikes(option_chains: Sequence[Mapping[str, Any]]) -> list[float]:
    strikes: set[float] = set()

    for chain in option_chains:
        for strike in chain.get("strikes") or []:
            parsed = _as_float(strike)
            if parsed is not None and parsed > 0:
                strikes.add(parsed)

    return sorted(strikes)


def _select_expiration_at_or_after_days(
    expirations: Sequence[str],
    selected_window_days: int,
) -> Optional[str]:
    target_date = date.today() + timedelta(days=selected_window_days)
    parsed_expirations = []

    for expiration in expirations:
        parsed = _parse_expiration(expiration)
        if parsed is not None:
            parsed_expirations.append(parsed)

    eligible = [expiration for expiration in parsed_expirations if expiration >= target_date]

    if not eligible:
        return None

    return min(eligible).strftime("%Y%m%d")


def _select_bull_call_spread_strikes(
    strikes: Sequence[float],
    underlying_price: float,
    contract_selection_rules: Mapping[str, Any],
) -> tuple[Optional[float], Optional[float]]:
    preferred_spread_width = _as_float(
        contract_selection_rules.get("preferred_spread_width")
    )

    sorted_strikes = sorted(float(strike) for strike in strikes if strike > 0)

    if len(sorted_strikes) < 2:
        return None, None

    long_strike = min(sorted_strikes, key=lambda strike: abs(strike - underlying_price))

    higher_strikes = [strike for strike in sorted_strikes if strike > long_strike]

    if not higher_strikes:
        return None, None

    if preferred_spread_width is not None and preferred_spread_width > 0:
        target_short = long_strike + preferred_spread_width
        short_strike = min(higher_strikes, key=lambda strike: abs(strike - target_short))
    else:
        short_strike = higher_strikes[0]

    return long_strike, short_strike


def _parse_expiration(value: Any) -> Optional[date]:
    if value in (None, ""):
        return None

    text = str(value).strip()

    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    return None


def _is_ibkr_informational_message(error_code: Any) -> bool:
    return _as_int(error_code) in {
        2104,  # Market data farm connection is OK
        2106,  # HMDS / historical data farm connection is OK
        2158,  # Sec-def data farm connection is OK
        2176,  # API compatibility / fractional size rule warning
    }


def _clean_string(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None

    return str(value).strip()


def _as_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float) and value.is_integer():
        return int(value)

    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())

    return None


def _as_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None

    return None


def _classify_state(
    *,
    blocked_reasons: Sequence[str],
    warnings: Sequence[str],
) -> str:
    if blocked_reasons:
        return "blocked"

    if warnings:
        return "needs_review"

    return "ready"


def _dedupe_strings(values: Any) -> list[str]:
    if values is None:
        return []

    if isinstance(values, str):
        values = [values]

    if not isinstance(values, Sequence):
        return [str(values)]

    deduped: list[str] = []
    seen: set[str] = set()

    for value in values:
        clean_value = str(value).strip()
        if clean_value and clean_value not in seen:
            seen.add(clean_value)
            deduped.append(clean_value)

    return deduped


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))