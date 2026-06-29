from __future__ import annotations

from pathlib import Path
from typing import Any

from src.decision.decision_report import DecisionReport, build_decision_report
from src.decision.operation_audit import audit_decision_operation_record
from src.decision.operation_health import evaluate_decision_operation_health
from src.decision.operation_log import (
    append_decision_operation_log,
    build_decision_operation_log_entry,
)
from src.decision.operation_record import DecisionOperationRecord, attach_decision_report


def run_decision_dry_run(
    *,
    decision_id: str,
    ranked_candidates: list[dict[str, Any]],
    selected_candidates: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> DecisionReport:
    return build_decision_report(
        decision_id=decision_id,
        ranked_candidates=ranked_candidates,
        selected_candidates=selected_candidates,
        metadata=metadata,
    )


def run_decision_operation(
    *,
    operation_id: str,
    decision_id: str,
    ranked_candidates: list[dict[str, Any]],
    selected_candidates: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
    log_path: str | Path | None = None,
) -> dict[str, Any]:
    report = run_decision_dry_run(
        decision_id=decision_id,
        ranked_candidates=ranked_candidates,
        selected_candidates=selected_candidates,
        metadata=metadata,
    )

    record = DecisionOperationRecord(
        operation_id=operation_id,
        metadata=metadata or {},
    )
    attach_decision_report(record, report)

    log_entry = None
    if log_path is not None:
        log_entry = build_decision_operation_log_entry(record)
        append_decision_operation_log(entry=log_entry, log_path=log_path)

    audit = audit_decision_operation_record(record)
    health = evaluate_decision_operation_health(record)

    return {
        "report": report,
        "record": record,
        "log_entry": log_entry,
        "audit": audit,
        "health": health,
    }
