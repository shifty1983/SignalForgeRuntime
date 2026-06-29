from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping


class ResearchHypothesisStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    TESTED = "tested"
    REJECTED = "rejected"
    PROMOTED = "promoted"
    ARCHIVED = "archived"


class ResearchHypothesisCategory(str, Enum):
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    VOLATILITY = "volatility"
    REGIME = "regime"
    OPTIONS = "options"
    RISK = "risk"
    LIQUIDITY = "liquidity"
    MACRO = "macro"
    CROSS_SECTIONAL = "cross_sectional"
    OTHER = "other"


class ExpectedDirection(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"


@dataclass(frozen=True)
class HypothesisValidationIssue:
    field: str
    message: str


@dataclass(frozen=True)
class HypothesisValidationResult:
    passed: bool
    issues: tuple[HypothesisValidationIssue, ...] = field(default_factory=tuple)

    @property
    def failed(self) -> bool:
        return not self.passed


@dataclass(frozen=True)
class ResearchHypothesis:
    name: str
    description: str
    category: ResearchHypothesisCategory | str
    asset_class: str
    required_features: tuple[str, ...]
    expected_direction: ExpectedDirection | str
    rationale: str
    status: ResearchHypothesisStatus | str = ResearchHypothesisStatus.DRAFT
    tags: tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "category",
            _coerce_enum(self.category, ResearchHypothesisCategory, "category"),
        )
        object.__setattr__(
            self,
            "expected_direction",
            _coerce_enum(
                self.expected_direction,
                ExpectedDirection,
                "expected_direction",
            ),
        )
        object.__setattr__(
            self,
            "status",
            _coerce_enum(self.status, ResearchHypothesisStatus, "status"),
        )
        object.__setattr__(
            self,
            "required_features",
            _clean_string_tuple(self.required_features, "required_features"),
        )
        object.__setattr__(
            self,
            "tags",
            _clean_string_tuple(self.tags, "tags"),
        )
        object.__setattr__(self, "metadata", dict(self.metadata))

        validation = validate_hypothesis(self)
        if validation.failed:
            messages = "; ".join(issue.message for issue in validation.issues)
            raise ValueError(f"Invalid research hypothesis: {messages}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "asset_class": self.asset_class,
            "required_features": list(self.required_features),
            "expected_direction": self.expected_direction.value,
            "rationale": self.rationale,
            "status": self.status.value,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ResearchHypothesis":
        return cls(
            name=payload["name"],
            description=payload["description"],
            category=payload["category"],
            asset_class=payload["asset_class"],
            required_features=tuple(payload.get("required_features", ())),
            expected_direction=payload["expected_direction"],
            rationale=payload["rationale"],
            status=payload.get("status", ResearchHypothesisStatus.DRAFT),
            tags=tuple(payload.get("tags", ())),
            metadata=dict(payload.get("metadata", {})),
        )


_ALLOWED_STATUS_TRANSITIONS: dict[
    ResearchHypothesisStatus,
    set[ResearchHypothesisStatus],
] = {
    ResearchHypothesisStatus.DRAFT: {
        ResearchHypothesisStatus.ACTIVE,
        ResearchHypothesisStatus.ARCHIVED,
    },
    ResearchHypothesisStatus.ACTIVE: {
        ResearchHypothesisStatus.TESTED,
        ResearchHypothesisStatus.REJECTED,
        ResearchHypothesisStatus.ARCHIVED,
    },
    ResearchHypothesisStatus.TESTED: {
        ResearchHypothesisStatus.REJECTED,
        ResearchHypothesisStatus.PROMOTED,
        ResearchHypothesisStatus.ARCHIVED,
    },
    ResearchHypothesisStatus.REJECTED: {
        ResearchHypothesisStatus.ARCHIVED,
    },
    ResearchHypothesisStatus.PROMOTED: {
        ResearchHypothesisStatus.ARCHIVED,
    },
    ResearchHypothesisStatus.ARCHIVED: set(),
}


def validate_hypothesis(
    hypothesis: ResearchHypothesis,
) -> HypothesisValidationResult:
    issues: list[HypothesisValidationIssue] = []

    if not hypothesis.name.strip():
        issues.append(
            HypothesisValidationIssue(
                field="name",
                message="Hypothesis name cannot be empty.",
            )
        )

    if not hypothesis.description.strip():
        issues.append(
            HypothesisValidationIssue(
                field="description",
                message="Hypothesis description cannot be empty.",
            )
        )

    if not hypothesis.asset_class.strip():
        issues.append(
            HypothesisValidationIssue(
                field="asset_class",
                message="Asset class cannot be empty.",
            )
        )

    if not hypothesis.required_features:
        issues.append(
            HypothesisValidationIssue(
                field="required_features",
                message="At least one required feature must be provided.",
            )
        )

    if len(set(hypothesis.required_features)) != len(hypothesis.required_features):
        issues.append(
            HypothesisValidationIssue(
                field="required_features",
                message="Required features cannot contain duplicates.",
            )
        )

    if not hypothesis.rationale.strip():
        issues.append(
            HypothesisValidationIssue(
                field="rationale",
                message="Hypothesis rationale cannot be empty.",
            )
        )

    return HypothesisValidationResult(
        passed=len(issues) == 0,
        issues=tuple(issues),
    )


def transition_hypothesis_status(
    hypothesis: ResearchHypothesis,
    new_status: ResearchHypothesisStatus | str,
) -> ResearchHypothesis:
    target_status = _coerce_enum(
        new_status,
        ResearchHypothesisStatus,
        "new_status",
    )

    allowed_targets = _ALLOWED_STATUS_TRANSITIONS[hypothesis.status]

    if target_status not in allowed_targets:
        raise ValueError(
            f"Invalid hypothesis status transition: "
            f"{hypothesis.status.value} -> {target_status.value}"
        )

    return replace(hypothesis, status=target_status)


def activate_hypothesis(hypothesis: ResearchHypothesis) -> ResearchHypothesis:
    return transition_hypothesis_status(hypothesis, ResearchHypothesisStatus.ACTIVE)


def mark_hypothesis_tested(hypothesis: ResearchHypothesis) -> ResearchHypothesis:
    return transition_hypothesis_status(hypothesis, ResearchHypothesisStatus.TESTED)


def reject_hypothesis(hypothesis: ResearchHypothesis) -> ResearchHypothesis:
    return transition_hypothesis_status(hypothesis, ResearchHypothesisStatus.REJECTED)


def promote_hypothesis(hypothesis: ResearchHypothesis) -> ResearchHypothesis:
    return transition_hypothesis_status(hypothesis, ResearchHypothesisStatus.PROMOTED)


def archive_hypothesis(hypothesis: ResearchHypothesis) -> ResearchHypothesis:
    return transition_hypothesis_status(hypothesis, ResearchHypothesisStatus.ARCHIVED)


def _coerce_enum(value: Any, enum_type: type[Enum], field_name: str) -> Enum:
    if isinstance(value, enum_type):
        return value

    try:
        return enum_type(value)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise ValueError(
            f"Invalid {field_name}: {value!r}. Allowed values: {allowed}"
        ) from exc


def _clean_string_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    cleaned = tuple(str(value).strip() for value in values)

    if any(not value for value in cleaned):
        raise ValueError(f"{field_name} cannot contain empty values.")

    return cleaned
