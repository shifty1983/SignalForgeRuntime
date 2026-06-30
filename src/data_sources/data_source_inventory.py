from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


EXPLICIT_EXCLUSIONS = (
    "broker_api_calls",
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
)

DATA_SOURCE_CATEGORIES = (
    {
        "category": "static_config",
        "description": "Rules and definitions controlled by SignalForge.",
        "example_sources": [
            "universe config",
            "strategy catalog",
            "risk limits",
            "allowed strategy policy",
        ],
    },
    {
        "category": "market_price_data",
        "description": "Underlying price and volume data.",
        "example_sources": [
            "CSV export",
            "QuantConnect data",
            "broker export",
            "market-data vendor",
        ],
    },
    {
        "category": "options_chain_data",
        "description": "Option quotes, implied volatility, Greeks, liquidity, and expirations.",
        "example_sources": [
            "broker option chain snapshot",
            "QuantConnect option data",
            "historical options provider",
        ],
    },
    {
        "category": "broker_account_data",
        "description": "Portfolio state, positions, balances, executions, and account history.",
        "example_sources": [
            "IBKR statement export",
            "IBKR activity export",
            "manual account snapshot",
            "IBKR API later",
        ],
    },
    {
        "category": "backtest_evidence_data",
        "description": "Strategy test results and evidence of edge.",
        "example_sources": [
            "QuantConnect manual backtest result export",
            "local manual backtest summary",
        ],
    },
    {
        "category": "human_manual_decision_data",
        "description": "Manual reviews, approvals, rejections, execution notes, and strategy decisions.",
        "example_sources": [
            "manual JSON entry",
            "review artifact",
            "decision log",
        ],
    },
    {
        "category": "generated_artifacts",
        "description": "Output from earlier SignalForge modules.",
        "example_sources": [
            "local JSON artifacts under artifacts/",
            "review artifacts",
            "operation artifacts",
        ],
    },
)

MODULE_DATA_SOURCES = (
    {
        "module": "universe",
        "required_input_artifact": "universe_config",
        "data_categories": ["static_config"],
        "expected_source": "user-maintained universe config",
        "acquisition_method": "manual YAML/JSON",
        "current_state": "partially_defined",
        "adapter_needed": True,
        "blocking_questions": [
            "Which symbols, asset groups, and eligibility rules are in scope?",
        ],
    },
    {
        "module": "regime_classification",
        "required_input_artifact": "regime_source_artifact",
        "data_categories": ["market_price_data", "static_config"],
        "expected_source": "SPY, QQQ, IWM, VIX, rates, and sector proxies",
        "acquisition_method": "market data adapter or CSV import",
        "current_state": "logic_exists",
        "adapter_needed": True,
        "blocking_questions": [
            "Which regime inputs are mandatory versus optional?",
        ],
    },
    {
        "module": "asset_behavior_classification",
        "required_input_artifact": "asset_behavior_artifact",
        "data_categories": ["market_price_data"],
        "expected_source": "historical OHLCV per underlying",
        "acquisition_method": "market data adapter or CSV import",
        "current_state": "logic_exists",
        "adapter_needed": True,
        "blocking_questions": [
            "What lookback windows and indicators are required for production?",
        ],
    },
    {
        "module": "option_behavior_classification",
        "required_input_artifact": "option_behavior_artifact",
        "data_categories": ["options_chain_data"],
        "expected_source": "option chain snapshots, implied volatility, Greeks, and liquidity",
        "acquisition_method": "options data adapter or broker/export import",
        "current_state": "logic_exists",
        "adapter_needed": True,
        "blocking_questions": [
            "Will options behavior use broker snapshots, QuantConnect data, or paid historical options data?",
        ],
    },
    {
        "module": "options_strategy_catalog",
        "required_input_artifact": "strategy_catalog_artifact",
        "data_categories": ["static_config"],
        "expected_source": "code-owned catalog and policy config",
        "acquisition_method": "static module/config",
        "current_state": "built",
        "adapter_needed": False,
        "blocking_questions": [
            "Which strategies remain enabled for live/manual review?",
        ],
    },
    {
        "module": "options_strategy_candidate_builder",
        "required_input_artifact": "strategy_candidate_artifact",
        "data_categories": ["generated_artifacts"],
        "expected_source": "regime, asset behavior, option behavior, and strategy catalog artifacts",
        "acquisition_method": "local artifact inputs",
        "current_state": "built",
        "adapter_needed": False,
        "blocking_questions": [
            "Are candidate inputs complete enough for actual weekly planning?",
        ],
    },
    {
        "module": "weekly_option_trade_plan",
        "required_input_artifact": "weekly_trade_plan_artifact",
        "data_categories": ["generated_artifacts", "broker_account_data"],
        "expected_source": "strategy candidates and account/risk snapshot",
        "acquisition_method": "local artifacts plus account snapshot importer",
        "current_state": "built",
        "adapter_needed": True,
        "blocking_questions": [
            "What account constraints must be imported from broker data?",
        ],
    },
    {
        "module": "position_risk_monitor",
        "required_input_artifact": "position_risk_artifact",
        "data_categories": ["broker_account_data", "options_chain_data"],
        "expected_source": "current positions, quotes, Greeks, P/L, and DTE",
        "acquisition_method": "broker export now; broker API later",
        "current_state": "built",
        "adapter_needed": True,
        "blocking_questions": [
            "What is the first supported broker export shape?",
        ],
    },
    {
        "module": "manual_action_review",
        "required_input_artifact": "manual_action_review_artifact",
        "data_categories": ["human_manual_decision_data"],
        "expected_source": "user approval, rejection, or defer decision",
        "acquisition_method": "manual JSON/review file",
        "current_state": "built",
        "adapter_needed": True,
        "blocking_questions": [
            "What exact review input format will be easiest to maintain?",
        ],
    },
    {
        "module": "manual_execution_record",
        "required_input_artifact": "manual_execution_record_artifact",
        "data_categories": ["human_manual_decision_data", "broker_account_data"],
        "expected_source": "what the user actually did in the broker account",
        "acquisition_method": "manual entry now; broker activity export later",
        "current_state": "built",
        "adapter_needed": True,
        "blocking_questions": [
            "Should first version be manual entry or IBKR trade activity import?",
        ],
    },
    {
        "module": "manual_action_outcome_record",
        "required_input_artifact": "manual_action_outcome_record_artifact",
        "data_categories": ["broker_account_data", "market_price_data"],
        "expected_source": "post-execution P/L, price movement, and position result",
        "acquisition_method": "broker history plus market prices",
        "current_state": "built",
        "adapter_needed": True,
        "blocking_questions": [
            "What outcome horizon should be tracked first: same day, weekly, or expiration?",
        ],
    },
    {
        "module": "edge_validation_summary",
        "required_input_artifact": "edge_validation_summary_artifact",
        "data_categories": ["backtest_evidence_data", "broker_account_data"],
        "expected_source": "QuantConnect/manual backtest result plus realized outcomes",
        "acquisition_method": "backtest evidence importer",
        "current_state": "downstream_built_importer_missing",
        "adapter_needed": True,
        "blocking_questions": [
            "What minimum evidence fields are required to claim edge support?",
        ],
    },
    {
        "module": "edge_validation_review",
        "required_input_artifact": "edge_validation_review_artifact",
        "data_categories": ["generated_artifacts", "human_manual_decision_data"],
        "expected_source": "edge summary and manual judgment",
        "acquisition_method": "local artifact plus manual review",
        "current_state": "built",
        "adapter_needed": True,
        "blocking_questions": [
            "What manual labels are allowed: supported, weak, invalid, or inconclusive?",
        ],
    },
    {
        "module": "strategy_improvement_queue",
        "required_input_artifact": "strategy_improvement_queue_artifact",
        "data_categories": ["generated_artifacts"],
        "expected_source": "edge review and weak/failed cases",
        "acquisition_method": "local artifact input",
        "current_state": "built",
        "adapter_needed": False,
        "blocking_questions": [
            "What failures create improvement tasks automatically?",
        ],
    },
    {
        "module": "strategy_improvement_review",
        "required_input_artifact": "strategy_improvement_review_artifact",
        "data_categories": ["human_manual_decision_data"],
        "expected_source": "manual decision on improvement task",
        "acquisition_method": "manual JSON/review file",
        "current_state": "built",
        "adapter_needed": True,
        "blocking_questions": [
            "What approvals are needed before changing strategy logic?",
        ],
    },
    {
        "module": "strategy_decision_log",
        "required_input_artifact": "strategy_decision_log_artifact",
        "data_categories": ["human_manual_decision_data"],
        "expected_source": "final human-approved strategy decision",
        "acquisition_method": "manual JSON/log file",
        "current_state": "built",
        "adapter_needed": True,
        "blocking_questions": [
            "What decision log format should become canonical?",
        ],
    },
    {
        "module": "control_report_autodiscovery_pipeline",
        "required_input_artifact": "local_artifact_folder",
        "data_categories": ["generated_artifacts"],
        "expected_source": "local artifact folder",
        "acquisition_method": "one-command local CLI",
        "current_state": "built",
        "adapter_needed": False,
        "blocking_questions": [],
    },
    {
        "module": "quantconnect_manual_backtest_bridge",
        "required_input_artifact": "options_backtest_evidence_artifact",
        "data_categories": ["backtest_evidence_data"],
        "expected_source": "QuantConnect manual result export",
        "acquisition_method": "new importer needed",
        "current_state": "not_built",
        "adapter_needed": True,
        "blocking_questions": [
            "What exact QuantConnect export fields will be available?",
        ],
    },
    {
        "module": "ibkr_account_snapshot_bridge",
        "required_input_artifact": "account_snapshot_artifact",
        "data_categories": ["broker_account_data"],
        "expected_source": "IBKR statement/export or API later",
        "acquisition_method": "importer needed",
        "current_state": "not_built",
        "adapter_needed": True,
        "blocking_questions": [
            "Which IBKR export should be supported first?",
        ],
    },
    {
        "module": "market_price_bridge",
        "required_input_artifact": "price_history_artifact",
        "data_categories": ["market_price_data"],
        "expected_source": "CSV, QuantConnect, broker, or vendor",
        "acquisition_method": "importer needed",
        "current_state": "not_built",
        "adapter_needed": True,
        "blocking_questions": [
            "Which source is lowest-cost and sufficient for initial validation?",
        ],
    },
    {
        "module": "options_chain_bridge",
        "required_input_artifact": "option_chain_snapshot_artifact",
        "data_categories": ["options_chain_data"],
        "expected_source": "broker export, QuantConnect, or data vendor",
        "acquisition_method": "importer needed",
        "current_state": "not_built",
        "adapter_needed": True,
        "blocking_questions": [
            "Do we need historical chains now, or only current snapshots first?",
        ],
    },
)

OPEN_DECISIONS = (
    {
        "decision": "primary_backtest_source",
        "status": "open",
        "default_candidate": "QuantConnect manual export",
        "notes": "Likely first source for strategy evidence.",
    },
    {
        "decision": "primary_broker_account_source",
        "status": "open",
        "default_candidate": "IBKR export first, API later",
        "notes": "Needed for account snapshot, positions, executions, and outcomes.",
    },
    {
        "decision": "primary_market_price_source",
        "status": "open",
        "default_candidate": "CSV, QuantConnect, broker export, or market-data vendor",
        "notes": "Needed by regime, asset behavior, and outcome review.",
    },
    {
        "decision": "primary_options_chain_source",
        "status": "open",
        "default_candidate": "broker snapshot, QuantConnect, or options data vendor",
        "notes": "Most important unresolved source for options behavior and risk.",
    },
    {
        "decision": "canonical_universe_config",
        "status": "open",
        "default_candidate": "local universe config",
        "notes": "Needed to define eligible symbols and asset groups.",
    },
    {
        "decision": "canonical_human_decision_input_format",
        "status": "partially_open",
        "default_candidate": "manual JSON files",
        "notes": "Several downstream artifacts exist, but source builders may still be needed.",
    },
)

RECOMMENDED_BUILD_ORDER = (
    "data_source_inventory_file_writer_cli",
    "market_price_source_contract",
    "options_chain_source_contract",
    "ibkr_account_snapshot_source_contract",
    "quantconnect_backtest_evidence_source_contract",
    "manual_decision_source_contract",
    "options_backtest_evidence_import",
    "ibkr_account_snapshot_import",
    "market_price_history_import",
    "option_chain_snapshot_import",
)


def build_signalforge_data_source_inventory(source: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build a deterministic data-source inventory artifact.

    This artifact defines data needs and adapter backlog. It does not call brokers,
    route orders, submit orders, model fills, perform live execution, model slippage,
    create automatic close/roll/defense orders, change strategies automatically,
    update parameters automatically, or pause strategies automatically.
    """

    if source is not None and not isinstance(source, Mapping):
        return _blocked_result("source must be a mapping")

    source = source or {}
    resolved_decisions = _as_mapping(source.get("resolved_decisions"))
    modules = [_module_with_resolution(module) for module in MODULE_DATA_SOURCES]
    decisions = [_decision_with_resolution(decision, resolved_decisions) for decision in OPEN_DECISIONS]

    category_summary = _category_summary(modules)
    module_summary = _module_summary(modules)
    open_decision_count = sum(1 for decision in decisions if decision.get("status") != "resolved")
    adapter_backlog = _adapter_backlog(modules)

    status = "ready" if open_decision_count == 0 and not adapter_backlog else "needs_review"

    return {
        "artifact_type": "signalforge_data_source_inventory",
        "schema_version": "1.0",
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
            "External data acquisition belongs at adapter/importer boundaries. "
            "Core SignalForge modules consume normalized local artifacts."
        ),
        "data_source_categories": [dict(category) for category in DATA_SOURCE_CATEGORIES],
        "module_data_sources": modules,
        "category_summary": category_summary,
        "module_summary": module_summary,
        "open_decisions": decisions,
        "open_decision_count": open_decision_count,
        "adapter_backlog": adapter_backlog,
        "adapter_backlog_count": len(adapter_backlog),
        "recommended_build_order": list(RECOMMENDED_BUILD_ORDER),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _module_with_resolution(module: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(module)
    normalized["blocking_question_count"] = len(_as_list(module.get("blocking_questions")))
    normalized["data_category_count"] = len(_as_list(module.get("data_categories")))
    return normalized


def _decision_with_resolution(
    decision: Mapping[str, Any],
    resolved_decisions: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = dict(decision)
    key = str(normalized.get("decision", ""))

    if key in resolved_decisions:
        resolution = resolved_decisions.get(key)
        normalized["status"] = "resolved"
        normalized["selected_source"] = str(resolution).strip() if resolution is not None else None
    else:
        normalized["selected_source"] = None

    return normalized


def _category_summary(modules: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counter: Counter[str] = Counter()
    for module in modules:
        for category in _as_list(module.get("data_categories")):
            counter[str(category)] += 1

    return {
        "category_count": len(DATA_SOURCE_CATEGORIES),
        "usage_by_category": dict(sorted(counter.items())),
    }


def _module_summary(modules: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    adapter_needed_count = sum(1 for module in modules if module.get("adapter_needed") is True)
    built_count = sum(1 for module in modules if module.get("current_state") == "built")
    not_built_count = sum(1 for module in modules if module.get("current_state") == "not_built")
    blocking_question_count = sum(
        len(_as_list(module.get("blocking_questions"))) for module in modules
    )

    return {
        "module_count": len(modules),
        "adapter_needed_count": adapter_needed_count,
        "adapter_not_needed_count": len(modules) - adapter_needed_count,
        "built_module_count": built_count,
        "not_built_module_count": not_built_count,
        "blocking_question_count": blocking_question_count,
    }


def _adapter_backlog(modules: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    backlog = []
    for module in modules:
        if module.get("adapter_needed") is True:
            backlog.append(
                {
                    "module": module.get("module"),
                    "required_input_artifact": module.get("required_input_artifact"),
                    "data_categories": list(_as_list(module.get("data_categories"))),
                    "expected_source": module.get("expected_source"),
                    "acquisition_method": module.get("acquisition_method"),
                    "current_state": module.get("current_state"),
                    "blocking_questions": list(_as_list(module.get("blocking_questions"))),
                }
            )

    return sorted(backlog, key=lambda item: str(item.get("module", "")))


def _blocked_result(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_data_source_inventory",
        "schema_version": "1.0",
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "blocked_items": [{"reason": reason}],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []

