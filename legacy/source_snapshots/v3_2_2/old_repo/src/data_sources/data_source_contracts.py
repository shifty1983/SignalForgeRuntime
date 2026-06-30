from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


CONTRACT_SCHEMA_VERSION = "signalforge_data_source_contracts.v1"

DATA_SOURCE_CONTRACTS = (
    {
        "contract": "universe_config",
        "data_category": "static_config",
        "description": "Defines symbols, asset groups, and eligibility rules SignalForge is allowed to consider.",
        "expected_source": "local user-maintained config",
        "adapter_type": "manual_config",
        "required_fields": [
            "universe_id",
            "symbols",
            "asset_groups",
            "eligibility_rules",
            "source",
        ],
        "preferred_fields": [
            "blocked_symbols",
            "max_positions",
            "strategy_eligibility",
            "liquidity_requirements",
            "earnings_restrictions",
        ],
        "optional_fields": [
            "notes",
            "tags",
            "reviewed_by",
            "reviewed_at",
        ],
        "consumed_by_modules": [
            "universe",
            "regime_classification",
            "asset_behavior_classification",
            "options_strategy_candidate_builder",
        ],
    },
    {
        "contract": "market_price_history",
        "data_category": "market_price_data",
        "description": "Normalized underlying OHLCV history for regime, behavior, outcome, and evidence checks.",
        "expected_source": "CSV, QuantConnect, broker export, or market-data vendor",
        "adapter_type": "market_price_import",
        "required_fields": [
            "symbol",
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "source",
        ],
        "preferred_fields": [
            "volume",
            "adjusted_close",
            "timeframe",
            "currency",
            "warnings",
        ],
        "optional_fields": [
            "dividend",
            "split_factor",
            "vwap",
            "provider_symbol",
        ],
        "consumed_by_modules": [
            "regime_classification",
            "asset_behavior_classification",
            "manual_action_outcome_record",
            "edge_validation_summary",
        ],
    },
    {
        "contract": "option_chain_snapshot",
        "data_category": "options_chain_data",
        "description": "Normalized option chain snapshot with quotes, IV, Greeks, liquidity, and expirations.",
        "expected_source": "broker snapshot, QuantConnect, or options data vendor",
        "adapter_type": "option_chain_import",
        "required_fields": [
            "underlying",
            "quote_timestamp",
            "expiration",
            "strike",
            "option_type",
            "bid",
            "ask",
            "source",
        ],
        "preferred_fields": [
            "mid",
            "volume",
            "open_interest",
            "implied_volatility",
            "delta",
            "dte",
            "currency",
            "warnings",
        ],
        "optional_fields": [
            "last",
            "gamma",
            "theta",
            "vega",
            "rho",
            "contract_symbol",
            "multiplier",
        ],
        "consumed_by_modules": [
            "option_behavior_classification",
            "options_strategy_candidate_builder",
            "weekly_option_trade_plan",
            "position_risk_monitor",
            "options_defense_review",
            "edge_validation_summary",
        ],
    },
    {
        "contract": "account_snapshot",
        "data_category": "broker_account_data",
        "description": "Normalized broker/account snapshot with balances, open positions, and risk context.",
        "expected_source": "IBKR statement/export first; IBKR API later",
        "adapter_type": "broker_account_import",
        "required_fields": [
            "snapshot_timestamp",
            "net_liquidation_value",
            "open_positions",
            "source",
        ],
        "preferred_fields": [
            "account_id_alias",
            "cash",
            "buying_power",
            "unrealized_pnl",
            "realized_pnl",
            "currency",
            "warnings",
        ],
        "optional_fields": [
            "maintenance_margin",
            "initial_margin",
            "excess_liquidity",
            "day_trades_remaining",
        ],
        "position_required_fields": [
            "symbol",
            "asset_type",
            "quantity",
            "source",
        ],
        "position_preferred_fields": [
            "average_cost",
            "market_price",
            "market_value",
            "unrealized_pnl",
            "expiration",
            "strike",
            "option_type",
            "multiplier",
        ],
        "consumed_by_modules": [
            "weekly_option_trade_plan",
            "position_risk_monitor",
            "weekly_options_portfolio_review",
            "manual_execution_record",
            "manual_action_outcome_record",
        ],
    },
    {
        "contract": "backtest_evidence",
        "data_category": "backtest_evidence_data",
        "description": "Normalized strategy backtest evidence used to determine whether logic has edge support.",
        "expected_source": "QuantConnect manual result export or local manual backtest summary",
        "adapter_type": "backtest_evidence_import",
        "required_fields": [
            "strategy_name",
            "symbol_universe",
            "test_start",
            "test_end",
            "trade_count",
            "source",
        ],
        "preferred_fields": [
            "win_rate",
            "average_win",
            "average_loss",
            "expectancy",
            "max_drawdown",
            "profit_factor",
            "total_return",
            "equity_curve",
            "trade_list",
            "parameter_set",
            "warnings",
        ],
        "optional_fields": [
            "sharpe",
            "sortino",
            "benchmark_return",
            "regime_tags",
            "setup_tags",
            "source_backtest_id",
            "source_project_id",
        ],
        "consumed_by_modules": [
            "edge_validation_summary",
            "edge_validation_review",
            "strategy_improvement_queue",
            "strategy_decision_log",
        ],
    },
    {
        "contract": "manual_decision",
        "data_category": "human_manual_decision_data",
        "description": "Normalized manual review, approval, rejection, defer, or strategy decision input.",
        "expected_source": "manual JSON entry, review artifact, or decision log",
        "adapter_type": "manual_source_builder",
        "required_fields": [
            "decision_id",
            "decision_timestamp",
            "decision",
            "requires_manual_approval",
            "automatic_action",
        ],
        "preferred_fields": [
            "reviewer",
            "reason",
            "related_artifact_id",
            "manual_notes",
            "source",
        ],
        "optional_fields": [
            "decision_context",
            "review_tags",
            "follow_up_required",
            "follow_up_reason",
        ],
        "consumed_by_modules": [
            "manual_action_review",
            "manual_execution_record",
            "edge_validation_review",
            "strategy_improvement_review",
            "strategy_decision_log",
        ],
    },
)


def build_signalforge_data_source_contracts(source: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build deterministic source contracts for SignalForge data adapters.

    The contract registry defines what normalized local artifacts should contain.
    It does not call brokers, route orders, submit orders, model fills, perform
    live execution, model slippage, create automatic close/roll/defense orders,
    change strategies automatically, update parameters automatically, or pause
    strategies automatically.
    """

    if source is not None and not isinstance(source, Mapping):
        return _blocked_result("source must be a mapping")

    source = source or {}
    selected_contracts = _selected_contracts(source)
    requested_contracts = _requested_contracts(source)
    unknown_contracts = sorted(set(requested_contracts) - {item["contract"] for item in DATA_SOURCE_CONTRACTS})

    if unknown_contracts:
        return _blocked_result(
            "unknown_contract_requested",
            blocked_items=[
                {
                    "reason": "unknown_contract_requested",
                    "contract": contract,
                }
                for contract in unknown_contracts
            ],
        )

    resolved_sources = _as_mapping(source.get("resolved_sources"))
    contracts = [
        _contract_with_summary(contract, resolved_sources=resolved_sources)
        for contract in selected_contracts
    ]

    source_open_count = sum(1 for contract in contracts if contract["source_status"] != "resolved")
    status = "ready" if source_open_count == 0 and contracts else "needs_review"

    return {
        "artifact_type": "signalforge_data_source_contracts",
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "design_rule": (
            "Data-source contracts define normalized local artifact fields. "
            "External systems are handled only by adapters/importers."
        ),
        "contracts": contracts,
        "contract_summary": _contract_summary(contracts),
        "category_summary": _category_summary(contracts),
        "open_source_count": source_open_count,
        "resolved_source_count": len(contracts) - source_open_count,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _selected_contracts(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    requested = _requested_contracts(source)
    if not requested:
        return [dict(contract) for contract in DATA_SOURCE_CONTRACTS]

    requested_set = set(requested)
    return [
        dict(contract)
        for contract in DATA_SOURCE_CONTRACTS
        if contract["contract"] in requested_set
    ]


def _requested_contracts(source: Mapping[str, Any]) -> list[str]:
    enabled = source.get("enabled_contracts")
    if not isinstance(enabled, Sequence) or isinstance(enabled, (str, bytes, bytearray)):
        return []

    return [str(item).strip() for item in enabled if str(item).strip()]


def _contract_with_summary(
    contract: Mapping[str, Any],
    *,
    resolved_sources: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = dict(contract)
    contract_name = str(normalized["contract"])
    selected_source = resolved_sources.get(contract_name)

    normalized["required_field_count"] = len(_as_list(normalized.get("required_fields")))
    normalized["preferred_field_count"] = len(_as_list(normalized.get("preferred_fields")))
    normalized["optional_field_count"] = len(_as_list(normalized.get("optional_fields")))
    normalized["consumed_by_module_count"] = len(_as_list(normalized.get("consumed_by_modules")))
    normalized["selected_source"] = str(selected_source).strip() if selected_source else None
    normalized["source_status"] = "resolved" if normalized["selected_source"] else "open"
    normalized["requires_normalization"] = True
    normalized["external_source_boundary"] = True
    return normalized


def _contract_summary(contracts: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "contract_count": len(contracts),
        "required_field_count": sum(_safe_int(item.get("required_field_count")) for item in contracts),
        "preferred_field_count": sum(_safe_int(item.get("preferred_field_count")) for item in contracts),
        "optional_field_count": sum(_safe_int(item.get("optional_field_count")) for item in contracts),
        "open_source_count": sum(1 for item in contracts if item.get("source_status") != "resolved"),
        "resolved_source_count": sum(1 for item in contracts if item.get("source_status") == "resolved"),
    }


def _category_summary(contracts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counter: Counter[str] = Counter(str(item.get("data_category", "")) for item in contracts)
    return {
        "category_count": len(counter),
        "usage_by_category": dict(sorted(counter.items())),
    }


def _blocked_result(
    reason: str,
    *,
    blocked_items: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_data_source_contracts",
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "blocked_items": [dict(item) for item in blocked_items]
        if blocked_items is not None
        else [{"reason": reason}],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0

