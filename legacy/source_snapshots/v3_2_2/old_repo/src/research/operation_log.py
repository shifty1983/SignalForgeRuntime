from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.research.operation_record import (
    ResearchOperationRecord,
    enforce_research_operation_record,
)


@dataclass(frozen=True)
class ResearchOperationLogConfig:
    path: str | Path
    require_passed: bool = False
    create_parent_dirs: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        path = Path(self.path)

        if path.suffix not in {".jsonl", ".json"}:
            raise ValueError("Research operation log path must end with .jsonl or .json.")

        object.__setattr__(self, "path", path)
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class ResearchOperationLogWriteResult:
    path: Path
    record: Mapping[str, Any]
    line_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "record": dict(self.record),
            "line_count": self.line_count,
        }


def append_research_operation_record(
    record: ResearchOperationRecord,
    config: ResearchOperationLogConfig,
    timestamp: str | None = None,
) -> ResearchOperationLogWriteResult:
    enforced = enforce_research_operation_record(
        record,
        require_passed=config.require_passed,
    )

    path = Path(config.path)

    if config.create_parent_dirs:
        path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = timestamp or _utc_timestamp()

    payload = {
        "timestamp": timestamp,
        "record": enforced.to_dict(),
        "metadata": dict(config.metadata),
    }

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, sort_keys=True))
        file.write("\n")

    return ResearchOperationLogWriteResult(
        path=path,
        record=payload,
        line_count=count_research_operation_log_lines(path),
    )


def read_research_operation_log(path: str | Path) -> tuple[dict[str, Any], ...]:
    path = Path(path)

    if not path.exists():
        return ()

    records: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()

            if not stripped:
                continue

            records.append(json.loads(stripped))

    return tuple(records)


def summarize_research_operation_log(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    total = len(records)
    pass_count = 0
    fail_count = 0

    operation_names: dict[str, int] = {}

    for entry in records:
        record = dict(entry.get("record", {}) or {})
        status = record.get("status")
        operation_name = str(record.get("operation_name", "unknown"))

        operation_names[operation_name] = operation_names.get(operation_name, 0) + 1

        if status == "pass":
            pass_count += 1
        elif status == "fail":
            fail_count += 1

    latest = dict(records[-1]) if records else None
    latest_record = dict(latest.get("record", {}) or {}) if latest else None
    latest_backtest_handoff_payload = (
        latest_record.get("backtest_handoff_summary")
        if latest_record
        else None
    )
    latest_backtest_handoff_summary = (
        dict(latest_backtest_handoff_payload)
        if isinstance(latest_backtest_handoff_payload, Mapping)
        else None
    )
    latest_backtest_handoff_failures = (
        list(latest_record.get("backtest_handoff_failures") or [])
        if latest_record
        else []
    )
    latest_backtest_handoff_performance = (
        dict(latest_record.get("backtest_handoff_performance") or {})
        if latest_record and isinstance(latest_record.get("backtest_handoff_performance"), Mapping)
        else None
    )
    latest_model_quality_summary = (
        dict(latest_record.get("model_quality_summary") or {})
        if latest_record
        else None
    )
    latest_model_quality_failures = (
        list(latest_record.get("model_quality_failures") or [])
        if latest_record
        else []
    )
    latest_model_testing_payload = (
        latest_record.get("model_testing_summary")
        if latest_record
        else None
    )
    latest_model_testing_summary = (
        dict(latest_model_testing_payload)
        if isinstance(latest_model_testing_payload, Mapping)
        else None
    )
    latest_experiment_regression_payload = (
        latest_record.get("experiment_regression_report")
        if latest_record
        else None
    )
    latest_experiment_regression_report = (
        dict(latest_experiment_regression_payload)
        if isinstance(latest_experiment_regression_payload, Mapping)
        else None
    )
    latest_experiment_regression_failures = (
        list(latest_record.get("experiment_regression_failures") or [])
        if latest_record
        else []
    )

    return {
        "total_records": total,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "pass_rate": pass_count / total if total else 0.0,
        "operation_names": operation_names,
        "latest_status": latest_record.get("status") if latest_record else None,
        "latest_run_id": latest_record.get("run_id") if latest_record else None,
        "latest_backtest_handoff_summary": latest_backtest_handoff_summary,
        "latest_backtest_handoff_attached": (
            latest_record.get("backtest_handoff_attached")
            if latest_record
            else None
        ),
        "latest_backtest_handoff_passed": (
            latest_record.get("backtest_handoff_passed")
            if latest_record
            else None
        ),
        "latest_backtest_handoff_failure_count": (
            latest_record.get(
                "backtest_handoff_failure_count",
                len(latest_backtest_handoff_failures),
            )
            if latest_record
            else None
        ),
        "latest_backtest_handoff_failures": latest_backtest_handoff_failures,
        "latest_backtest_handoff_fixture_id": (
            latest_record.get("backtest_handoff_fixture_id")
            if latest_record
            else None
        ),
        "latest_backtest_handoff_candidate_id": (
            latest_record.get("backtest_handoff_candidate_id")
            if latest_record
            else None
        ),
        "latest_backtest_handoff_performance": latest_backtest_handoff_performance,
        "latest_model_quality_passed": (
            latest_model_quality_summary.get("passed")
            if latest_model_quality_summary
            else None
        ),
        "latest_model_quality_summary": latest_model_quality_summary,
        "latest_model_quality_failures": latest_model_quality_failures,
        "latest_model_quality_failure_count": len(latest_model_quality_failures),
        "latest_model_testing_summary": latest_model_testing_summary,
        "latest_model_testing_candidate_count": (
            latest_model_testing_summary.get("candidate_count")
            if latest_model_testing_summary
            else None
        ),
        "latest_model_testing_promoted_candidate_count": (
            latest_model_testing_summary.get("promoted_candidate_count")
            if latest_model_testing_summary
            else None
        ),
        "latest_model_testing_rejected_candidate_count": (
            latest_model_testing_summary.get("rejected_candidate_count")
            if latest_model_testing_summary
            else None
        ),
        "latest_model_testing_best_candidate_id": (
            latest_model_testing_summary.get("best_candidate_id")
            if latest_model_testing_summary
            else None
        ),
        "latest_model_testing_has_promoted_candidate": (
            latest_model_testing_summary.get("has_promoted_candidate")
            if latest_model_testing_summary
            else None
        ),
        "latest_experiment_regression_report": latest_experiment_regression_report,
        "latest_experiment_regression_attached": (
            latest_record.get("experiment_regression_attached")
            if latest_record
            else None
        ),
        "latest_experiment_regression_passed": (
            latest_record.get("experiment_regression_passed")
            if latest_record
            else None
        ),
        "latest_experiment_regression_failure_count": (
            latest_record.get(
                "experiment_regression_failure_count",
                len(latest_experiment_regression_failures),
            )
            if latest_record
            else None
        ),
        "latest_experiment_regression_failures": latest_experiment_regression_failures,
        "latest_experiment_regression_has_regression": (
            latest_experiment_regression_report.get("has_regression")
            if latest_experiment_regression_report
            else None
        ),
    }


def count_research_operation_log_lines(path: str | Path) -> int:
    path = Path(path)

    if not path.exists():
        return 0

    with path.open("r", encoding="utf-8") as file:
        return sum(1 for line in file if line.strip())


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
