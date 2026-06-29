from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from src.research.operation_log import read_research_operation_log


@dataclass(frozen=True)
class ResearchOperationAuditConfig:
    require_records: bool = False
    max_failures_allowed: int | None = None
    min_pass_rate: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_failures_allowed is not None and self.max_failures_allowed < 0:
            raise ValueError("max_failures_allowed cannot be negative.")

        if self.min_pass_rate is not None and not 0 <= self.min_pass_rate <= 1:
            raise ValueError("min_pass_rate must be between 0 and 1.")

        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class ResearchOperationAuditResult:
    passed: bool
    total_records: int
    pass_count: int
    fail_count: int
    pass_rate: float
    latest_record: Mapping[str, Any] | None = None
    failed_records: tuple[Mapping[str, Any], ...] = ()
    promoted_records: tuple[Mapping[str, Any], ...] = ()
    gate_failure_count: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "total_records": self.total_records,
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "pass_rate": self.pass_rate,
            "latest_record": dict(self.latest_record) if self.latest_record is not None else None,
            "failed_records": [dict(record) for record in self.failed_records],
            "promoted_records": [dict(record) for record in self.promoted_records],
            "gate_failure_count": self.gate_failure_count,
            "metadata": dict(self.metadata),
        }


def audit_research_operation_records(
    records: Sequence[Mapping[str, Any]],
    config: ResearchOperationAuditConfig | None = None,
) -> ResearchOperationAuditResult:
    config = config or ResearchOperationAuditConfig()

    normalized_records = tuple(_extract_record(entry) for entry in records)
    total_records = len(normalized_records)

    pass_records = tuple(
        record for record in normalized_records if record.get("status") == "pass"
    )
    failed_records = tuple(
        record for record in normalized_records if record.get("status") == "fail"
    )
    promoted_records = tuple(
        record for record in normalized_records if record.get("evaluation_promoted") is True
    )

    pass_count = len(pass_records)
    fail_count = len(failed_records)
    pass_rate = pass_count / total_records if total_records else 0.0

    gate_failure_count = sum(
        int(record.get("model_gate_failure_count", 0) or 0)
        for record in normalized_records
    )

    checks_passed = True

    if config.require_records and total_records == 0:
        checks_passed = False

    if (
        config.max_failures_allowed is not None
        and fail_count > config.max_failures_allowed
    ):
        checks_passed = False

    if config.min_pass_rate is not None and pass_rate < config.min_pass_rate:
        checks_passed = False

    return ResearchOperationAuditResult(
        passed=checks_passed,
        total_records=total_records,
        pass_count=pass_count,
        fail_count=fail_count,
        pass_rate=pass_rate,
        latest_record=normalized_records[-1] if normalized_records else None,
        failed_records=failed_records,
        promoted_records=promoted_records,
        gate_failure_count=gate_failure_count,
        metadata=dict(config.metadata),
    )


def audit_research_operation_log(
    path: str,
    config: ResearchOperationAuditConfig | None = None,
) -> ResearchOperationAuditResult:
    records = read_research_operation_log(path)
    return audit_research_operation_records(records, config=config)


def _extract_record(entry: Mapping[str, Any]) -> dict[str, Any]:
    if "record" in entry and isinstance(entry["record"], Mapping):
        return dict(entry["record"])

    return dict(entry)
