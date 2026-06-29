from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence


ADAPTER_TYPE = "ibkr_option_quote_validation_export"

ARTIFACT_TYPE = "signalforge_ibkr_option_quote_validation_export"
SUMMARY_ARTIFACT_TYPE = "signalforge_ibkr_option_quote_validation_export_summary"
WRITE_RESULT_ARTIFACT_TYPE = "ibkr_option_quote_validation_export_write_result"

EXPORT_FILENAME = "signalforge_ibkr_option_quote_validation_export.json"
SUMMARY_FILENAME = "signalforge_ibkr_option_quote_validation_export_summary.json"

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

OptionQuoteFetcher = Callable[
    [Mapping[str, Any], Mapping[str, Any], str, int, int, float],
    Mapping[str, Any],
]


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, sort_keys=True)
        file.write("\n")


def export_ibkr_option_quote_validation(
    *,
    option_contract_resolver_operation_path: str | Path,
    account_snapshot_operation_path: str | Path,
    output_dir: str | Path,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    option_quote_fetcher: Optional[OptionQuoteFetcher] = None,
) -> Dict[str, Any]:
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    export_path = output_dir_obj / EXPORT_FILENAME
    summary_path = output_dir_obj / SUMMARY_FILENAME

    try:
        resolver_operation = load_json(option_contract_resolver_operation_path)
        resolver_operation = hydrate_resolver_operation_details(
            resolver_operation,
            operation_path=option_contract_resolver_operation_path,
        )
    except Exception as exc:  # pragma: no cover
        resolver_operation = {
            "operation_state": "blocked",
            "contract_resolution_state": "blocked",
            "blocked_reasons": [
                "option_contract_resolver_operation_load_failed",
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

    export_payload = build_ibkr_option_quote_validation_export(
        resolver_operation,
        account_snapshot_operation,
        option_contract_resolver_operation_path=str(
            option_contract_resolver_operation_path
        ),
        account_snapshot_operation_path=str(account_snapshot_operation_path),
        timeout_seconds=timeout_seconds,
        option_quote_fetcher=option_quote_fetcher,
    )

    summary_payload = build_ibkr_option_quote_validation_export_summary(
        export_payload,
        export_path=str(export_path),
        summary_path=str(summary_path),
    )

    write_json(export_path, export_payload)
    write_json(summary_path, summary_payload)

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": WRITE_RESULT_ARTIFACT_TYPE,
        "quote_validation_state": export_payload["quote_validation_state"],
        "paper_trading_mode": export_payload["paper_trading_mode"],
        "order_submission_enabled": export_payload["order_submission_enabled"],
        "requires_manual_approval": export_payload["requires_manual_approval"],
        "symbol": export_payload["symbol"],
        "spread_type": export_payload["spread_type"],
        "expiration": export_payload["expiration"],
        "underlying_price": export_payload["underlying_price"],
        "conservative_net_debit": export_payload["conservative_net_debit"],
        "mid_net_debit": export_payload["mid_net_debit"],
        "max_loss_amount": export_payload["max_loss_amount"],
        "max_profit_amount": export_payload["max_profit_amount"],
        "blocked_reasons": export_payload["blocked_reasons"],
        "warnings": export_payload["warnings"],
        "export_path": str(export_path),
        "summary_path": str(summary_path),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_option_quote_validation_export(
    option_contract_resolver_operation: Any,
    account_snapshot_operation: Any,
    *,
    option_contract_resolver_operation_path: Optional[str] = None,
    account_snapshot_operation_path: Optional[str] = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    option_quote_fetcher: Optional[OptionQuoteFetcher] = None,
) -> Dict[str, Any]:
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if not isinstance(option_contract_resolver_operation, Mapping):
        option_contract_resolver_operation = {}
        blocked_reasons.extend(
            [
                "option_contract_resolver_operation_invalid_shape",
                "option_contract_resolver_operation_must_be_json_object",
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
        _dedupe_strings(option_contract_resolver_operation.get("blocked_reasons", []))
    )
    blocked_reasons.extend(
        _dedupe_strings(account_snapshot_operation.get("blocked_reasons", []))
    )

    warnings.extend(
        _resolver_warnings_to_carry(
            option_contract_resolver_operation.get("warnings", [])
        )
    )
    warnings.extend(_dedupe_strings(account_snapshot_operation.get("warnings", [])))

    resolver_operation_state = option_contract_resolver_operation.get(
        "operation_state"
    )
    contract_resolution_state = option_contract_resolver_operation.get(
        "contract_resolution_state"
    )
    snapshot_operation_state = account_snapshot_operation.get("operation_state")
    snapshot_state = account_snapshot_operation.get("snapshot_state")

    if resolver_operation_state == "blocked":
        blocked_reasons.append("option_contract_resolver_operation_must_not_be_blocked")
    elif resolver_operation_state not in {"ready", "needs_review"}:
        blocked_reasons.append(
            "option_contract_resolver_operation_must_be_ready_or_needs_review"
        )

    if contract_resolution_state == "blocked":
        blocked_reasons.append("contract_resolution_state_must_not_be_blocked")
    elif contract_resolution_state not in {"ready", "needs_review"}:
        blocked_reasons.append(
            "contract_resolution_state_must_be_ready_or_needs_review"
        )

    if snapshot_operation_state != "ready":
        blocked_reasons.append("account_snapshot_operation_must_be_ready")

    if snapshot_state != "ready":
        blocked_reasons.append("account_snapshot_state_must_be_ready")

    if option_contract_resolver_operation.get("order_submission_enabled") is True:
        blocked_reasons.append("order_submission_must_be_disabled_for_quote_validation")

    broker = (
        option_contract_resolver_operation.get("broker")
        or account_snapshot_operation.get("broker")
    )
    trading_mode = (
        option_contract_resolver_operation.get("trading_mode")
        or account_snapshot_operation.get("trading_mode")
    )
    host = (
        option_contract_resolver_operation.get("host")
        or account_snapshot_operation.get("host")
    )
    port = _as_int(
        option_contract_resolver_operation.get("port")
        or account_snapshot_operation.get("port")
    )
    client_id = _as_int(
        option_contract_resolver_operation.get("client_id")
        or account_snapshot_operation.get("client_id")
    )

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

    symbol = _clean_string(option_contract_resolver_operation.get("symbol"))
    spread_type = _clean_string(option_contract_resolver_operation.get("spread_type"))
    expiration = _clean_string(option_contract_resolver_operation.get("expiration"))
    underlying_price = _as_float(
        option_contract_resolver_operation.get("underlying_price")
    )
    long_leg = option_contract_resolver_operation.get("long_leg")
    short_leg = option_contract_resolver_operation.get("short_leg")

    if not symbol:
        blocked_reasons.append("symbol_required")

    if spread_type != "bull_call_spread":
        blocked_reasons.append("spread_type_must_be_bull_call_spread")

    if not expiration:
        blocked_reasons.append("expiration_required")

    if underlying_price is None:
        warnings.append("underlying_price_not_available_for_quote_validation")

    if not isinstance(long_leg, Mapping):
        long_leg = {}
        blocked_reasons.append("long_leg_required")

    if not isinstance(short_leg, Mapping):
        short_leg = {}
        blocked_reasons.append("short_leg_required")

    contract_selection_rules = option_contract_resolver_operation.get(
        "contract_selection_rules"
    )
    if not isinstance(contract_selection_rules, Mapping):
        contract_selection_rules = {}

    max_bid_ask_spread = _as_float(
        contract_selection_rules.get("max_bid_ask_spread")
    )
    max_trade_risk_amount = _as_float(
        option_contract_resolver_operation.get("max_trade_risk_amount")
    )
    quantity = _as_int(option_contract_resolver_operation.get("max_contract_quantity")) or 1

    fetch_result: Mapping[str, Any] = {}
    broker_api_protocol_handshake_attempted = False
    option_quote_request_attempted = False
    market_data_request_attempted = False

    if not blocked_reasons:
        fetcher = option_quote_fetcher or _default_ibkr_option_quote_fetcher

        try:
            fetch_result = fetcher(
                long_leg,
                short_leg,
                str(host),
                int(port),
                int(client_id),
                float(timeout_seconds),
            )
        except Exception as exc:  # pragma: no cover
            fetch_result = {
                "connection_succeeded": False,
                "long_leg_quote": {},
                "short_leg_quote": {},
                "warnings": [],
                "errors": [f"{type(exc).__name__}: {exc}"],
                "informational_messages": [],
                "market_data_delayed": False,
            }

        broker_api_protocol_handshake_attempted = True
        option_quote_request_attempted = True
        market_data_request_attempted = True

        warnings.extend(_dedupe_strings(fetch_result.get("warnings", [])))
        warnings.extend(_dedupe_strings(fetch_result.get("errors", [])))

        if bool(fetch_result.get("market_data_delayed")):
            warnings.append("delayed_market_data_used_for_option_quote_validation")

        if not bool(fetch_result.get("connection_succeeded")):
            blocked_reasons.append("ibkr_option_quote_fetch_failed")

    long_leg_quote = _normalize_quote(fetch_result.get("long_leg_quote", {}))
    short_leg_quote = _normalize_quote(fetch_result.get("short_leg_quote", {}))

    quote_metrics = _build_quote_metrics(
        long_leg=long_leg,
        short_leg=short_leg,
        long_leg_quote=long_leg_quote,
        short_leg_quote=short_leg_quote,
        quantity=quantity,
    )

    validation_checks = _build_validation_checks(
        quote_metrics=quote_metrics,
        max_trade_risk_amount=max_trade_risk_amount,
        max_bid_ask_spread=max_bid_ask_spread,
    )

    if not blocked_reasons:
        blocked_reasons.extend(
            _quote_validation_blockers(
                quote_metrics=quote_metrics,
                validation_checks=validation_checks,
            )
        )

    quote_validation_state = _classify_state(
        blocked_reasons=blocked_reasons,
        warnings=warnings,
    )

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": ARTIFACT_TYPE,
        "quote_validation_state": quote_validation_state,
        "paper_trading_mode": True,
        "order_submission_enabled": False,
        "requires_manual_approval": True,
        "broker": broker,
        "trading_mode": trading_mode,
        "host": host,
        "port": port,
        "client_id": client_id,
        "symbol": symbol,
        "spread_type": spread_type,
        "expiration": expiration,
        "underlying_price": underlying_price,
        "long_leg": _json_safe(long_leg),
        "short_leg": _json_safe(short_leg),
        "long_leg_quote": long_leg_quote,
        "short_leg_quote": short_leg_quote,
        "quantity": quantity,
        "multiplier": quote_metrics["multiplier"],
        "spread_width": quote_metrics["spread_width"],
        "conservative_net_debit": quote_metrics["conservative_net_debit"],
        "mid_net_debit": quote_metrics["mid_net_debit"],
        "max_loss_amount": quote_metrics["max_loss_amount"],
        "max_profit_amount": quote_metrics["max_profit_amount"],
        "long_leg_bid_ask_spread": quote_metrics["long_leg_bid_ask_spread"],
        "short_leg_bid_ask_spread": quote_metrics["short_leg_bid_ask_spread"],
        "max_bid_ask_spread": max_bid_ask_spread,
        "max_trade_risk_amount": max_trade_risk_amount,
        "quote_validation_checks": validation_checks,
        "broker_api_protocol_handshake_attempted": broker_api_protocol_handshake_attempted,
        "option_quote_request_attempted": option_quote_request_attempted,
        "market_data_request_attempted": market_data_request_attempted,
        "order_submission_attempted": False,
        "market_data_delayed": bool(fetch_result.get("market_data_delayed")),
        "informational_messages": _dedupe_strings(
            fetch_result.get("informational_messages", [])
        ),
        "option_contract_resolver_operation_path": (
            option_contract_resolver_operation_path
        ),
        "account_snapshot_operation_path": account_snapshot_operation_path,
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "warnings": _dedupe_strings(warnings),
        **EXECUTION_DISABLED_FIELDS,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_option_quote_validation_export_summary(
    export_payload: Mapping[str, Any],
    *,
    export_path: Optional[str] = None,
    summary_path: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": SUMMARY_ARTIFACT_TYPE,
        "quote_validation_state": export_payload.get("quote_validation_state"),
        "paper_trading_mode": export_payload.get("paper_trading_mode"),
        "order_submission_enabled": export_payload.get("order_submission_enabled"),
        "requires_manual_approval": export_payload.get("requires_manual_approval"),
        "symbol": export_payload.get("symbol"),
        "spread_type": export_payload.get("spread_type"),
        "expiration": export_payload.get("expiration"),
        "underlying_price": export_payload.get("underlying_price"),
        "quantity": export_payload.get("quantity"),
        "multiplier": export_payload.get("multiplier"),
        "spread_width": export_payload.get("spread_width"),
        "conservative_net_debit": export_payload.get("conservative_net_debit"),
        "mid_net_debit": export_payload.get("mid_net_debit"),
        "max_loss_amount": export_payload.get("max_loss_amount"),
        "max_profit_amount": export_payload.get("max_profit_amount"),
        "long_leg_bid_ask_spread": export_payload.get("long_leg_bid_ask_spread"),
        "short_leg_bid_ask_spread": export_payload.get("short_leg_bid_ask_spread"),
        "max_bid_ask_spread": export_payload.get("max_bid_ask_spread"),
        "max_trade_risk_amount": export_payload.get("max_trade_risk_amount"),
        "market_data_delayed": export_payload.get("market_data_delayed"),
        "broker_api_protocol_handshake_attempted": export_payload.get(
            "broker_api_protocol_handshake_attempted"
        ),
        "option_quote_request_attempted": export_payload.get(
            "option_quote_request_attempted"
        ),
        "market_data_request_attempted": export_payload.get(
            "market_data_request_attempted"
        ),
        "order_submission_attempted": export_payload.get(
            "order_submission_attempted"
        ),
        "quote_validation_checks": export_payload.get("quote_validation_checks", {}),
        "blocked_reason_count": len(export_payload.get("blocked_reasons", [])),
        "warning_count": len(export_payload.get("warnings", [])),
        "informational_message_count": len(
            export_payload.get("informational_messages", [])
        ),
        "blocked_reasons": export_payload.get("blocked_reasons", []),
        "warnings": export_payload.get("warnings", []),
        "informational_messages": export_payload.get("informational_messages", []),
        "output_files": {
            "export": export_path,
            "summary": summary_path,
        },
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def hydrate_resolver_operation_details(
    resolver_operation: Any,
    *,
    operation_path: str | Path,
) -> Any:
    if not isinstance(resolver_operation, Mapping):
        return resolver_operation

    if (
        isinstance(resolver_operation.get("long_leg"), Mapping)
        and isinstance(resolver_operation.get("short_leg"), Mapping)
        and isinstance(resolver_operation.get("contract_selection_rules"), Mapping)
    ):
        return resolver_operation

    output_files = resolver_operation.get("output_files")

    if not isinstance(output_files, Mapping):
        return resolver_operation

    export_path = output_files.get("export")

    if not export_path:
        return resolver_operation

    export_path_obj = Path(export_path)

    if not export_path_obj.exists():
        operation_path_obj = Path(operation_path)
        candidate_path = operation_path_obj.parent / export_path_obj.name

        if candidate_path.exists():
            export_path_obj = candidate_path

    if not export_path_obj.exists():
        return resolver_operation

    export_payload = load_json(export_path_obj)

    if not isinstance(export_payload, Mapping):
        return resolver_operation

    hydrated = dict(resolver_operation)

    for key in [
        "contract_resolution_state",
        "paper_trading_mode",
        "order_submission_enabled",
        "requires_manual_approval",
        "broker",
        "trading_mode",
        "host",
        "port",
        "client_id",
        "symbol",
        "instrument_type",
        "strategy_direction",
        "spread_type",
        "selected_window_days",
        "expiration",
        "underlying_price",
        "long_leg",
        "short_leg",
        "max_trade_risk_amount",
        "max_contract_quantity",
        "contract_selection_rules",
        "blocked_reasons",
        "warnings",
        "informational_messages",
    ]:
        if key in export_payload:
            hydrated[key] = export_payload[key]

    return hydrated


def _default_ibkr_option_quote_fetcher(
    long_leg: Mapping[str, Any],
    short_leg: Mapping[str, Any],
    host: str,
    port: int,
    client_id: int,
    timeout_seconds: float,
) -> Mapping[str, Any]:
    try:
        from ibapi.client import EClient
        from ibapi.wrapper import EWrapper
    except ModuleNotFoundError:
        return {
            "connection_succeeded": False,
            "long_leg_quote": {},
            "short_leg_quote": {},
            "warnings": [],
            "errors": ["ibapi_package_not_installed"],
            "informational_messages": [],
            "market_data_delayed": False,
        }

    class QuoteApp(EWrapper, EClient):
        def __init__(self) -> None:
            EWrapper.__init__(self)
            EClient.__init__(self, self)

            self.connected_event = threading.Event()
            self.snapshot_events = {
                9501: threading.Event(),
                9502: threading.Event(),
            }
            self.quotes = {
                9501: {},
                9502: {},
            }
            self.errors: list[str] = []
            self.warnings: list[str] = []
            self.informational_messages: list[str] = []
            self.market_data_delayed = False

        def nextValidId(self, orderId: int) -> None:
            self.connected_event.set()

        def tickPrice(self, reqId: int, tickType: int, price: float, attrib: Any) -> None:
            if reqId not in self.quotes or price is None or price < 0:
                return

            quote = self.quotes[reqId]

            if tickType in {1, 66}:
                quote["bid"] = float(price)
            elif tickType in {2, 67}:
                quote["ask"] = float(price)
            elif tickType in {4, 68}:
                quote["last"] = float(price)
            elif tickType in {9, 75}:
                quote["close"] = float(price)
                
            
            if quote.get("bid") is not None and quote.get("ask") is not None:
                self.snapshot_events[reqId].set()

        def tickSize(self, reqId: int, tickType: int, size: float) -> None:
            if reqId not in self.quotes or size is None:
                return

            quote = self.quotes[reqId]

            if tickType in {0, 69}:
                quote["bid_size"] = float(size)
            elif tickType in {3, 70}:
                quote["ask_size"] = float(size)
            elif tickType in {5, 71}:
                quote["last_size"] = float(size)

        def tickSnapshotEnd(self, reqId: int) -> None:
            if reqId in self.snapshot_events:
                self.snapshot_events[reqId].set()

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

            if _is_ibkr_market_data_warning(errorCode):
                self.market_data_delayed = True
                self.warnings.append(message)
                return

            self.errors.append(message)

    app = QuoteApp()

    try:
        app.connect(host, port, clientId=client_id)

        thread = threading.Thread(target=app.run, daemon=True)
        thread.start()

        connected = app.connected_event.wait(timeout=timeout_seconds)

        if not connected:
            app.disconnect()
            return {
                "connection_succeeded": False,
                "long_leg_quote": {},
                "short_leg_quote": {},
                "warnings": app.warnings,
                "errors": ["ibkr_api_next_valid_id_timeout"],
                "informational_messages": app.informational_messages,
                "market_data_delayed": app.market_data_delayed,
            }

        app.reqMarketDataType(3)

        app.reqMktData(9501, _build_ibkr_option_contract(long_leg), "", False, False, [])
        app.reqMktData(9502, _build_ibkr_option_contract(short_leg), "", False, False, [])

        deadline = time.time() + timeout_seconds

        while time.time() < deadline:
            if app.snapshot_events[9501].is_set() and app.snapshot_events[9502].is_set():
                break

            time.sleep(0.25)

        try:
            app.cancelMktData(9501)
            app.cancelMktData(9502)
        except Exception:
            pass

        time.sleep(0.25)
        app.disconnect()

        return {
            "connection_succeeded": True,
            "long_leg_quote": app.quotes[9501],
            "short_leg_quote": app.quotes[9502],
            "warnings": app.warnings,
            "errors": app.errors,
            "informational_messages": app.informational_messages,
            "market_data_delayed": app.market_data_delayed,
        }

    except Exception as exc:  # pragma: no cover
        try:
            app.disconnect()
        except Exception:
            pass

        return {
            "connection_succeeded": False,
            "long_leg_quote": {},
            "short_leg_quote": {},
            "warnings": app.warnings,
            "errors": [f"{type(exc).__name__}: {exc}"],
            "informational_messages": app.informational_messages,
            "market_data_delayed": app.market_data_delayed,
        }


def _build_ibkr_option_contract(leg: Mapping[str, Any]) -> Any:
    from ibapi.contract import Contract

    contract = Contract()
    contract.symbol = str(leg.get("symbol"))
    contract.secType = str(leg.get("sec_type") or leg.get("secType") or "OPT")
    contract.exchange = "SMART"
    contract.currency = str(leg.get("currency") or "USD")
    contract.lastTradeDateOrContractMonth = str(
        leg.get("last_trade_date_or_contract_month")
        or leg.get("lastTradeDateOrContractMonth")
    )
    contract.strike = float(leg.get("strike"))
    contract.right = str(leg.get("right"))
    contract.multiplier = str(leg.get("multiplier") or "100")

    trading_class = leg.get("trading_class") or leg.get("tradingClass")
    if trading_class:
        contract.tradingClass = str(trading_class)

    return contract


def _build_quote_metrics(
    *,
    long_leg: Mapping[str, Any],
    short_leg: Mapping[str, Any],
    long_leg_quote: Mapping[str, Any],
    short_leg_quote: Mapping[str, Any],
    quantity: int,
) -> Dict[str, Any]:
    long_bid = _as_float(long_leg_quote.get("bid"))
    long_ask = _as_float(long_leg_quote.get("ask"))
    short_bid = _as_float(short_leg_quote.get("bid"))
    short_ask = _as_float(short_leg_quote.get("ask"))

    long_mid = _mid_price(long_bid, long_ask)
    short_mid = _mid_price(short_bid, short_ask)

    long_strike = _as_float(long_leg.get("strike"))
    short_strike = _as_float(short_leg.get("strike"))
    multiplier = _as_float(long_leg.get("multiplier")) or 100.0

    conservative_net_debit = None
    if long_ask is not None and short_bid is not None:
        conservative_net_debit = round(long_ask - short_bid, 4)

    mid_net_debit = None
    if long_mid is not None and short_mid is not None:
        mid_net_debit = round(long_mid - short_mid, 4)

    spread_width = None
    if long_strike is not None and short_strike is not None:
        spread_width = round(short_strike - long_strike, 4)

    max_loss_amount = None
    if conservative_net_debit is not None:
        max_loss_amount = round(conservative_net_debit * multiplier * quantity, 2)

    max_profit_amount = None
    if spread_width is not None and conservative_net_debit is not None:
        max_profit_amount = round(
            max(spread_width - conservative_net_debit, 0) * multiplier * quantity,
            2,
        )

    return {
        "long_bid": long_bid,
        "long_ask": long_ask,
        "short_bid": short_bid,
        "short_ask": short_ask,
        "long_mid": long_mid,
        "short_mid": short_mid,
        "multiplier": multiplier,
        "spread_width": spread_width,
        "conservative_net_debit": conservative_net_debit,
        "mid_net_debit": mid_net_debit,
        "max_loss_amount": max_loss_amount,
        "max_profit_amount": max_profit_amount,
        "long_leg_bid_ask_spread": _bid_ask_spread(long_bid, long_ask),
        "short_leg_bid_ask_spread": _bid_ask_spread(short_bid, short_ask),
    }


def _build_validation_checks(
    *,
    quote_metrics: Mapping[str, Any],
    max_trade_risk_amount: Optional[float],
    max_bid_ask_spread: Optional[float],
) -> Dict[str, bool]:
    conservative_net_debit = _as_float(quote_metrics.get("conservative_net_debit"))
    max_loss_amount = _as_float(quote_metrics.get("max_loss_amount"))
    spread_width = _as_float(quote_metrics.get("spread_width"))
    long_spread = _as_float(quote_metrics.get("long_leg_bid_ask_spread"))
    short_spread = _as_float(quote_metrics.get("short_leg_bid_ask_spread"))

    return {
        "long_leg_bid_available": quote_metrics.get("long_bid") is not None,
        "long_leg_ask_available": quote_metrics.get("long_ask") is not None,
        "short_leg_bid_available": quote_metrics.get("short_bid") is not None,
        "short_leg_ask_available": quote_metrics.get("short_ask") is not None,
        "spread_width_positive": spread_width is not None and spread_width > 0,
        "conservative_net_debit_available": conservative_net_debit is not None,
        "conservative_net_debit_positive": (
            conservative_net_debit is not None and conservative_net_debit > 0
        ),
        "max_loss_amount_available": max_loss_amount is not None,
        "max_loss_within_budget": (
            max_trade_risk_amount is not None
            and max_loss_amount is not None
            and max_loss_amount <= max_trade_risk_amount
        ),
        "long_leg_bid_ask_spread_within_limit": (
            max_bid_ask_spread is not None
            and long_spread is not None
            and long_spread <= max_bid_ask_spread
        ),
        "short_leg_bid_ask_spread_within_limit": (
            max_bid_ask_spread is not None
            and short_spread is not None
            and short_spread <= max_bid_ask_spread
        ),
    }


def _quote_validation_blockers(
    *,
    quote_metrics: Mapping[str, Any],
    validation_checks: Mapping[str, bool],
) -> list[str]:
    blockers: list[str] = []

    required_checks = {
        "long_leg_bid_available": "long_leg_bid_required",
        "long_leg_ask_available": "long_leg_ask_required",
        "short_leg_bid_available": "short_leg_bid_required",
        "short_leg_ask_available": "short_leg_ask_required",
        "spread_width_positive": "spread_width_must_be_positive",
        "conservative_net_debit_available": "conservative_net_debit_required",
        "conservative_net_debit_positive": "conservative_net_debit_must_be_positive",
        "max_loss_amount_available": "max_loss_amount_required",
        "max_loss_within_budget": "max_loss_exceeds_max_trade_risk_amount",
        "long_leg_bid_ask_spread_within_limit": (
            "long_leg_bid_ask_spread_exceeds_limit"
        ),
        "short_leg_bid_ask_spread_within_limit": (
            "short_leg_bid_ask_spread_exceeds_limit"
        ),
    }

    for check, blocker in required_checks.items():
        if validation_checks.get(check) is not True:
            blockers.append(blocker)

    return blockers


def _normalize_quote(value: Any) -> dict[str, Optional[float]]:
    if not isinstance(value, Mapping):
        value = {}

    return {
        "bid": _as_float(value.get("bid")),
        "ask": _as_float(value.get("ask")),
        "last": _as_float(value.get("last")),
        "close": _as_float(value.get("close")),
        "bid_size": _as_float(value.get("bid_size")),
        "ask_size": _as_float(value.get("ask_size")),
        "last_size": _as_float(value.get("last_size")),
    }


def _resolver_warnings_to_carry(values: Any) -> list[str]:
    return [
        warning
        for warning in _dedupe_strings(values)
        if warning != "option_liquidity_rules_not_verified_by_contract_resolver"
    ]


def _mid_price(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    if bid is None or ask is None:
        return None

    return round((bid + ask) / 2, 4)


def _bid_ask_spread(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    if bid is None or ask is None:
        return None

    return round(ask - bid, 4)


def _is_ibkr_informational_message(error_code: Any) -> bool:
    return _as_int(error_code) in {
        2104,
        2106,
        2158,
        2176,
    }


def _is_ibkr_market_data_warning(error_code: Any) -> bool:
    return _as_int(error_code) in {
        10167,
        10168,
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