from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence


ADAPTER_TYPE = "paper_trading_pipeline_final_review_summary"

ARTIFACT_TYPE = "signalforge_paper_trading_pipeline_final_review_summary"
WRITE_RESULT_ARTIFACT_TYPE = "paper_trading_pipeline_final_review_summary_write_result"

SUMMARY_FILENAME = "signalforge_paper_trading_pipeline_final_review_summary.json"

EXPLICIT_EXCLUSIONS = [
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
]

PIPELINE_STAGES = [
    "primary_strategy_candidate_profile",
    "ibkr_paper_trading_readiness",
    "ibkr_paper_connection_smoke_test",
    "ibkr_paper_account_snapshot",
    "primary_strategy_paper_order_intent",
    "ibkr_option_contract_resolver",
    "ibkr_option_quote_validation",
    "paper_order_preview",
    "manual_approval_ticket",
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


def export_paper_trading_pipeline_final_review_summary(
    *,
    primary_strategy_candidate_profile_operation_path: str | Path,
    ibkr_paper_trading_readiness_operation_path: str | Path,
    ibkr_paper_connection_smoke_test_operation_path: str | Path,
    ibkr_paper_account_snapshot_operation_path: str | Path,
    primary_strategy_paper_order_intent_operation_path: str | Path,
    ibkr_option_contract_resolver_operation_path: str | Path,
    ibkr_option_quote_validation_operation_path: str | Path,
    paper_order_preview_operation_path: str | Path,
    manual_approval_ticket_operation_path: str | Path,
    output_dir: str | Path,
) -> Dict[str, Any]:
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir_obj / SUMMARY_FILENAME

    stage_inputs = {
        "primary_strategy_candidate_profile": _load_stage(
            primary_strategy_candidate_profile_operation_path
        ),
        "ibkr_paper_trading_readiness": _load_stage(
            ibkr_paper_trading_readiness_operation_path
        ),
        "ibkr_paper_connection_smoke_test": _load_stage(
            ibkr_paper_connection_smoke_test_operation_path
        ),
        "ibkr_paper_account_snapshot": _load_stage(
            ibkr_paper_account_snapshot_operation_path
        ),
        "primary_strategy_paper_order_intent": _load_stage(
            primary_strategy_paper_order_intent_operation_path
        ),
        "ibkr_option_contract_resolver": _load_stage(
            ibkr_option_contract_resolver_operation_path
        ),
        "ibkr_option_quote_validation": _load_stage(
            ibkr_option_quote_validation_operation_path
        ),
        "paper_order_preview": _load_stage(paper_order_preview_operation_path),
        "manual_approval_ticket": _load_stage(manual_approval_ticket_operation_path),
    }

    source_paths = {
        "primary_strategy_candidate_profile": str(
            primary_strategy_candidate_profile_operation_path
        ),
        "ibkr_paper_trading_readiness": str(
            ibkr_paper_trading_readiness_operation_path
        ),
        "ibkr_paper_connection_smoke_test": str(
            ibkr_paper_connection_smoke_test_operation_path
        ),
        "ibkr_paper_account_snapshot": str(
            ibkr_paper_account_snapshot_operation_path
        ),
        "primary_strategy_paper_order_intent": str(
            primary_strategy_paper_order_intent_operation_path
        ),
        "ibkr_option_contract_resolver": str(
            ibkr_option_contract_resolver_operation_path
        ),
        "ibkr_option_quote_validation": str(
            ibkr_option_quote_validation_operation_path
        ),
        "paper_order_preview": str(paper_order_preview_operation_path),
        "manual_approval_ticket": str(manual_approval_ticket_operation_path),
    }

    summary = build_paper_trading_pipeline_final_review_summary(
        stage_inputs,
        source_paths=source_paths,
        summary_path=str(summary_path),
    )

    write_json(summary_path, summary)

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": WRITE_RESULT_ARTIFACT_TYPE,
        "final_review_state": summary["final_review_state"],
        "pipeline_ready_for_order_submission": summary[
            "pipeline_ready_for_order_submission"
        ],
        "safe_stop_required": summary["safe_stop_required"],
        "safe_stop_stage": summary["safe_stop_stage"],
        "safe_stop_reason": summary["safe_stop_reason"],
        "blocked_stage_count": summary["blocked_stage_count"],
        "needs_review_stage_count": summary["needs_review_stage_count"],
        "ready_stage_count": summary["ready_stage_count"],
        "order_submission_enabled": summary["order_submission_enabled"],
        "submit_order": summary["submit_order"],
        "manual_approval_granted": summary["manual_approval_granted"],
        "summary_path": str(summary_path),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_paper_trading_pipeline_final_review_summary(
    stage_inputs: Mapping[str, Any],
    *,
    source_paths: Optional[Mapping[str, str]] = None,
    summary_path: Optional[str] = None,
) -> Dict[str, Any]:
    stage_summaries = []

    for stage_name in PIPELINE_STAGES:
        payload = stage_inputs.get(stage_name)
        stage_summaries.append(
            _summarize_stage(
                stage_name,
                payload,
                source_path=(source_paths or {}).get(stage_name),
            )
        )

    blocked_stages = [
        stage for stage in stage_summaries if stage["stage_state"] == "blocked"
    ]
    needs_review_stages = [
        stage for stage in stage_summaries if stage["stage_state"] == "needs_review"
    ]
    ready_stages = [
        stage for stage in stage_summaries if stage["stage_state"] == "ready"
    ]

    blocked_reasons = _dedupe_strings(
        reason
        for stage in stage_summaries
        for reason in stage.get("blocked_reasons", [])
    )
    warnings = _dedupe_strings(
        warning
        for stage in stage_summaries
        for warning in stage.get("warnings", [])
    )

    final_review_state = _classify_final_review_state(
        blocked_stage_count=len(blocked_stages),
        needs_review_stage_count=len(needs_review_stages),
        warning_count=len(warnings),
    )

    safe_stop_stage = blocked_stages[0]["stage_name"] if blocked_stages else None
    safe_stop_reason = (
        blocked_stages[0]["blocked_reasons"][0]
        if blocked_stages and blocked_stages[0]["blocked_reasons"]
        else None
    )

    order_submission_enabled = any(
        stage.get("order_submission_enabled") is True for stage in stage_summaries
    )
    submit_order = any(stage.get("submit_order") is True for stage in stage_summaries)
    manual_approval_granted = any(
        stage.get("manual_approval_granted") is True for stage in stage_summaries
    )

    pipeline_ready_for_order_submission = (
        final_review_state == "ready"
        and order_submission_enabled is False
        and submit_order is False
        and manual_approval_granted is False
    )

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": ARTIFACT_TYPE,
        "final_review_state": final_review_state,
        "pipeline_ready_for_order_submission": pipeline_ready_for_order_submission,
        "safe_stop_required": final_review_state == "blocked",
        "safe_stop_stage": safe_stop_stage,
        "safe_stop_reason": safe_stop_reason,
        "paper_trading_mode": True,
        "order_submission_enabled": False,
        "submit_order": False,
        "manual_approval_granted": False,
        "manual_approval_required": True,
        "blocked_stage_count": len(blocked_stages),
        "needs_review_stage_count": len(needs_review_stages),
        "ready_stage_count": len(ready_stages),
        "total_stage_count": len(stage_summaries),
        "stage_summaries": stage_summaries,
        "pipeline_milestones": _build_pipeline_milestones(stage_summaries),
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "summary_path": summary_path,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def _summarize_stage(
    stage_name: str,
    payload: Any,
    *,
    source_path: Optional[str],
) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {
            "stage_name": stage_name,
            "stage_state": "blocked",
            "operation_state": "blocked",
            "domain_state": "blocked",
            "source_path": source_path,
            "symbol": None,
            "blocked_reasons": [
                f"{stage_name}_operation_invalid_shape",
                f"{stage_name}_operation_must_be_json_object",
            ],
            "warnings": [],
            "order_submission_enabled": False,
            "submit_order": False,
            "manual_approval_granted": False,
        }

    operation_state = _clean_string(payload.get("operation_state"))
    domain_state = _domain_state_for(stage_name, payload)
    stage_state = _combine_stage_state(operation_state, domain_state)

    return {
        "stage_name": stage_name,
        "stage_state": stage_state,
        "operation_state": operation_state,
        "domain_state": domain_state,
        "source_path": source_path,
        "adapter_type": payload.get("adapter_type"),
        "artifact_type": payload.get("artifact_type"),
        "operation_id": payload.get("operation_id"),
        "symbol": payload.get("symbol"),
        "spread_type": payload.get("spread_type"),
        "expiration": payload.get("expiration"),
        "quantity": payload.get("quantity"),
        "limit_price": payload.get("limit_price"),
        "max_loss_amount": payload.get("max_loss_amount"),
        "approval_state": payload.get("approval_state"),
        "order_submission_enabled": payload.get("order_submission_enabled") is True,
        "submit_order": payload.get("submit_order") is True,
        "manual_approval_granted": payload.get("manual_approval_granted") is True,
        "blocked_reasons": _dedupe_strings(payload.get("blocked_reasons", [])),
        "warnings": _dedupe_strings(payload.get("warnings", [])),
    }


def _domain_state_for(stage_name: str, payload: Mapping[str, Any]) -> Optional[str]:
    state_fields = {
        "primary_strategy_candidate_profile": [
            "profile_export_state",
            "candidate_profile_state",
        ],
        "ibkr_paper_trading_readiness": ["readiness_state"],
        "ibkr_paper_connection_smoke_test": [
            "connection_state",
            "smoke_test_state",
        ],
        "ibkr_paper_account_snapshot": ["snapshot_state"],
        "primary_strategy_paper_order_intent": ["intent_state"],
        "ibkr_option_contract_resolver": ["contract_resolution_state"],
        "ibkr_option_quote_validation": ["quote_validation_state"],
        "paper_order_preview": ["paper_order_preview_state"],
        "manual_approval_ticket": ["manual_approval_ticket_state"],
    }

    for field in state_fields.get(stage_name, []):
        if payload.get(field) is not None:
            return _clean_string(payload.get(field))

    return _clean_string(payload.get("operation_state"))


def _combine_stage_state(
    operation_state: Optional[str],
    domain_state: Optional[str],
) -> str:
    states = [state for state in [operation_state, domain_state] if state]

    if not states:
        return "blocked"

    if "blocked" in states:
        return "blocked"

    if "needs_review" in states:
        return "needs_review"

    if all(state == "ready" for state in states):
        return "ready"

    return "blocked"


def _build_pipeline_milestones(stage_summaries: Sequence[Mapping[str, Any]]) -> Dict[str, bool]:
    by_stage = {stage["stage_name"]: stage for stage in stage_summaries}

    return {
        "research_edge_selected_strategy": _stage_not_blocked(
            by_stage,
            "primary_strategy_candidate_profile",
        ),
        "ibkr_paper_readiness_ready": _stage_ready(
            by_stage,
            "ibkr_paper_trading_readiness",
        ),
        "ibkr_connection_verified": _stage_ready(
            by_stage,
            "ibkr_paper_connection_smoke_test",
        ),
        "ibkr_account_snapshot_ready": _stage_ready(
            by_stage,
            "ibkr_paper_account_snapshot",
        ),
        "paper_order_intent_built": _stage_ready(
            by_stage,
            "primary_strategy_paper_order_intent",
        ),
        "option_contract_resolved": _stage_not_blocked(
            by_stage,
            "ibkr_option_contract_resolver",
        ),
        "option_quotes_validated": _stage_ready(
            by_stage,
            "ibkr_option_quote_validation",
        ),
        "paper_order_preview_ready": _stage_ready(
            by_stage,
            "paper_order_preview",
        ),
        "manual_approval_ticket_ready": _stage_ready(
            by_stage,
            "manual_approval_ticket",
        ),
        "order_submission_disabled": True,
        "manual_approval_not_granted": True,
    }


def _stage_ready(
    by_stage: Mapping[str, Mapping[str, Any]],
    stage_name: str,
) -> bool:
    return by_stage.get(stage_name, {}).get("stage_state") == "ready"


def _stage_not_blocked(
    by_stage: Mapping[str, Mapping[str, Any]],
    stage_name: str,
) -> bool:
    return by_stage.get(stage_name, {}).get("stage_state") in {
        "ready",
        "needs_review",
    }


def _classify_final_review_state(
    *,
    blocked_stage_count: int,
    needs_review_stage_count: int,
    warning_count: int,
) -> str:
    if blocked_stage_count:
        return "blocked"

    if needs_review_stage_count or warning_count:
        return "needs_review"

    return "ready"


def _load_stage(path: str | Path) -> Any:
    try:
        return load_json(path)
    except Exception as exc:  # pragma: no cover
        return {
            "operation_state": "blocked",
            "blocked_reasons": [
                "stage_load_failed",
                f"{type(exc).__name__}: {exc}",
            ],
            "warnings": [],
        }


def _clean_string(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None

    return str(value).strip()


def _dedupe_strings(values: Any) -> list[str]:
    if values is None:
        return []

    if isinstance(values, str):
        values = [values]

    deduped: list[str] = []
    seen: set[str] = set()

    for value in values:
        clean_value = str(value).strip()
        if clean_value and clean_value not in seen:
            seen.add(clean_value)
            deduped.append(clean_value)

    return deduped