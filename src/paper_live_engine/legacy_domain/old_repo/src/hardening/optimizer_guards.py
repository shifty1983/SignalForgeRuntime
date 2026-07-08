from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


VALID_SEVERITIES = {"INFO", "WARN", "BLOCK", "FAIL"}


@dataclass(frozen=True)
class GreekLimit:
    """
    Portfolio-level Greek exposure limit.

    Exposure is calculated as:

        sum(weight * greek_value)

    Example:
        GreekLimit(column="delta", min_exposure=-0.25, max_exposure=0.25)
    """

    column: str
    min_exposure: float | None = None
    max_exposure: float | None = None
    severity: str = "BLOCK"


@dataclass(frozen=True)
class OptimizerGuardConfig:
    """
    Configuration for optimizer safety checks.

    This can be used against optimizer inputs, candidate sets, or optimizer outputs.
    """

    candidate_id_column: str = "candidate_id"
    weight_column: str = "weight"
    expected_value_column: str = "expected_value"
    expected_return_column: str = "expected_return"
    liquidity_column: str | None = None

    require_non_empty: bool = True
    require_candidate_id: bool = True
    require_edge_column: bool = False
    require_positive_edge: bool = False
    require_weight_column: bool = False

    check_weight_sum: bool = False
    target_weight_sum: float = 1.0
    weight_sum_tolerance: float = 1e-6

    min_weight: float = 0.0
    max_weight: float = 1.0
    allow_negative_weights: bool = False

    min_active_positions: int | None = None
    max_active_positions: int | None = None
    min_active_weight: float = 0.0

    max_concentration: float | None = None

    min_liquidity: float | None = None

    greek_limits: Sequence[GreekLimit] = field(default_factory=tuple)


@dataclass(frozen=True)
class OptimizerGuardIssue:
    severity: str
    message: str
    guard_name: str
    column: str | None = None
    expected: Any | None = None
    actual: Any | None = None


@dataclass(frozen=True)
class OptimizerGuardResult:
    passed: bool
    total_rows: int
    issues: tuple[OptimizerGuardIssue, ...]

    @property
    def failed(self) -> bool:
        return not self.passed

    @property
    def blocking_issues(self) -> tuple[OptimizerGuardIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.severity in {"BLOCK", "FAIL"}
        )

    @property
    def warnings(self) -> tuple[OptimizerGuardIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "WARN")


def _validate_severity(severity: str) -> None:
    if severity not in VALID_SEVERITIES:
        raise ValueError(
            f"Invalid severity '{severity}'. Expected one of {sorted(VALID_SEVERITIES)}."
        )


def _get_columns(df: Any) -> list[str]:
    if hasattr(df, "columns"):
        return list(df.columns)

    raise TypeError("Object does not expose a columns attribute.")


def _row_count(df: Any) -> int:
    if hasattr(df, "height"):
        return int(df.height)

    try:
        return len(df)
    except TypeError as exc:
        raise TypeError("Object does not expose a usable row count.") from exc


def _to_values(series: Any) -> list[Any]:
    if hasattr(series, "to_list"):
        return list(series.to_list())

    if hasattr(series, "tolist"):
        return list(series.tolist())

    return list(series)


def _column_values(df: Any, column: str) -> list[Any]:
    return _to_values(df[column])


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _to_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(converted):
        return None

    return converted


def _numeric_values(values: Sequence[Any]) -> list[float | None]:
    return [_to_float(value) for value in values]


def _find_duplicate_values(values: Sequence[Any]) -> set[Any]:
    seen: set[Any] = set()
    duplicates: set[Any] = set()

    for value in values:
        if _is_blank(value):
            continue

        if value in seen:
            duplicates.add(value)
        else:
            seen.add(value)

    return duplicates


def _edge_column(config: OptimizerGuardConfig, columns: set[str]) -> str | None:
    if config.expected_value_column in columns:
        return config.expected_value_column

    if config.expected_return_column in columns:
        return config.expected_return_column

    return None


def check_optimizer_guards(
    df: Any,
    config: OptimizerGuardConfig | None = None,
) -> OptimizerGuardResult:
    """
    Run optimizer safety checks.

    This function is intentionally defensive. It is designed to stop bad optimizer
    inputs or outputs from silently becoming portfolio decisions.
    """
    config = config or OptimizerGuardConfig()

    issues: list[OptimizerGuardIssue] = []
    columns = set(_get_columns(df))
    total_rows = _row_count(df)

    for greek_limit in config.greek_limits:
        _validate_severity(greek_limit.severity)

        if (
            greek_limit.min_exposure is not None
            and greek_limit.max_exposure is not None
            and greek_limit.min_exposure > greek_limit.max_exposure
        ):
            raise ValueError(
                f"Invalid GreekLimit for '{greek_limit.column}': "
                "min_exposure cannot be greater than max_exposure."
            )

    if config.weight_sum_tolerance < 0:
        raise ValueError("weight_sum_tolerance must be >= 0.")

    if config.max_concentration is not None and config.max_concentration < 0:
        raise ValueError("max_concentration must be >= 0.")

    if config.min_liquidity is not None and config.min_liquidity < 0:
        raise ValueError("min_liquidity must be >= 0.")

    if total_rows == 0 and config.require_non_empty:
        return OptimizerGuardResult(
            passed=False,
            total_rows=total_rows,
            issues=(
                OptimizerGuardIssue(
                    severity="FAIL",
                    guard_name="non_empty",
                    message="Optimizer candidate set is empty.",
                    expected="at least one row",
                    actual=0,
                ),
            ),
        )

    if config.require_candidate_id:
        if config.candidate_id_column not in columns:
            issues.append(
                OptimizerGuardIssue(
                    severity="FAIL",
                    guard_name="candidate_id_present",
                    column=config.candidate_id_column,
                    message=f"Required candidate id column is missing: {config.candidate_id_column}",
                    expected="present",
                    actual="missing",
                )
            )
        else:
            candidate_ids = _column_values(df, config.candidate_id_column)

            blank_count = sum(1 for value in candidate_ids if _is_blank(value))
            if blank_count > 0:
                issues.append(
                    OptimizerGuardIssue(
                        severity="FAIL",
                        guard_name="candidate_id_not_blank",
                        column=config.candidate_id_column,
                        message="Candidate id column contains blank values.",
                        expected=0,
                        actual=blank_count,
                    )
                )

            duplicates = _find_duplicate_values(candidate_ids)
            if duplicates:
                issues.append(
                    OptimizerGuardIssue(
                        severity="FAIL",
                        guard_name="candidate_id_unique",
                        column=config.candidate_id_column,
                        message="Candidate id column contains duplicate values.",
                        expected="unique ids",
                        actual=sorted(duplicates),
                    )
                )

    edge_column = _edge_column(config, columns)

    if config.require_edge_column and edge_column is None:
        issues.append(
            OptimizerGuardIssue(
                severity="BLOCK",
                guard_name="edge_column_present",
                message=(
                    "No optimizer edge column found. Expected either "
                    f"'{config.expected_value_column}' or '{config.expected_return_column}'."
                ),
                expected=(config.expected_value_column, config.expected_return_column),
                actual="missing",
            )
        )

    if config.require_positive_edge and edge_column is not None:
        edge_values = _numeric_values(_column_values(df, edge_column))
        valid_edges = [value for value in edge_values if value is not None]

        if not valid_edges:
            issues.append(
                OptimizerGuardIssue(
                    severity="BLOCK",
                    guard_name="positive_edge_available",
                    column=edge_column,
                    message="Edge column contains no usable numeric values.",
                    expected="at least one numeric edge value",
                    actual="none",
                )
            )
        elif max(valid_edges) <= 0:
            issues.append(
                OptimizerGuardIssue(
                    severity="BLOCK",
                    guard_name="positive_edge_available",
                    column=edge_column,
                    message="Optimizer candidate set contains no positive-edge candidates.",
                    expected="at least one positive edge",
                    actual=max(valid_edges),
                )
            )

    weight_required = (
        config.require_weight_column
        or config.check_weight_sum
        or config.max_concentration is not None
        or bool(config.greek_limits)
        or config.min_active_positions is not None
        or config.max_active_positions is not None
    )

    weight_values: list[float | None] = []

    if weight_required and config.weight_column not in columns:
        issues.append(
            OptimizerGuardIssue(
                severity="FAIL",
                guard_name="weight_column_present",
                column=config.weight_column,
                message=f"Required weight column is missing: {config.weight_column}",
                expected="present",
                actual="missing",
            )
        )

    if config.weight_column in columns:
        raw_weights = _column_values(df, config.weight_column)
        weight_values = _numeric_values(raw_weights)

        invalid_count = sum(1 for value in weight_values if value is None)
        if invalid_count > 0:
            issues.append(
                OptimizerGuardIssue(
                    severity="FAIL",
                    guard_name="weights_numeric_and_finite",
                    column=config.weight_column,
                    message="Weight column contains missing, non-numeric, NaN, or infinite values.",
                    expected=0,
                    actual=invalid_count,
                )
            )

        valid_weights = [value for value in weight_values if value is not None]

        if not config.allow_negative_weights:
            negative_count = sum(1 for value in valid_weights if value < 0)
            if negative_count > 0:
                issues.append(
                    OptimizerGuardIssue(
                        severity="FAIL",
                        guard_name="weights_non_negative",
                        column=config.weight_column,
                        message="Negative weights are not allowed.",
                        expected="all weights >= 0",
                        actual=negative_count,
                    )
                )

        below_min_count = sum(value < config.min_weight for value in valid_weights)
        if below_min_count > 0:
            issues.append(
                OptimizerGuardIssue(
                    severity="BLOCK",
                    guard_name="min_weight",
                    column=config.weight_column,
                    message="One or more weights are below the configured minimum.",
                    expected=f">= {config.min_weight}",
                    actual=below_min_count,
                )
            )

        above_max_count = sum(value > config.max_weight for value in valid_weights)
        if above_max_count > 0:
            issues.append(
                OptimizerGuardIssue(
                    severity="BLOCK",
                    guard_name="max_weight",
                    column=config.weight_column,
                    message="One or more weights are above the configured maximum.",
                    expected=f"<= {config.max_weight}",
                    actual=above_max_count,
                )
            )

        if config.check_weight_sum and valid_weights:
            weight_sum = sum(valid_weights)
            deviation = abs(weight_sum - config.target_weight_sum)

            if deviation > config.weight_sum_tolerance:
                issues.append(
                    OptimizerGuardIssue(
                        severity="BLOCK",
                        guard_name="weight_sum",
                        column=config.weight_column,
                        message="Portfolio weights do not sum to the configured target.",
                        expected=config.target_weight_sum,
                        actual=weight_sum,
                    )
                )

        active_weights = [
            value for value in valid_weights if abs(value) > config.min_active_weight
        ]
        active_count = len(active_weights)

        if (
            config.min_active_positions is not None
            and active_count < config.min_active_positions
        ):
            issues.append(
                OptimizerGuardIssue(
                    severity="BLOCK",
                    guard_name="min_active_positions",
                    column=config.weight_column,
                    message="Portfolio has too few active positions.",
                    expected=f">= {config.min_active_positions}",
                    actual=active_count,
                )
            )

        if (
            config.max_active_positions is not None
            and active_count > config.max_active_positions
        ):
            issues.append(
                OptimizerGuardIssue(
                    severity="BLOCK",
                    guard_name="max_active_positions",
                    column=config.weight_column,
                    message="Portfolio has too many active positions.",
                    expected=f"<= {config.max_active_positions}",
                    actual=active_count,
                )
            )

        if config.max_concentration is not None and valid_weights:
            largest_abs_weight = max(abs(value) for value in valid_weights)

            if largest_abs_weight > config.max_concentration:
                issues.append(
                    OptimizerGuardIssue(
                        severity="BLOCK",
                        guard_name="max_concentration",
                        column=config.weight_column,
                        message="Portfolio exceeds maximum single-position concentration.",
                        expected=f"<= {config.max_concentration}",
                        actual=largest_abs_weight,
                    )
                )

    if config.liquidity_column and config.min_liquidity is not None:
        if config.liquidity_column not in columns:
            issues.append(
                OptimizerGuardIssue(
                    severity="BLOCK",
                    guard_name="liquidity_column_present",
                    column=config.liquidity_column,
                    message=f"Required liquidity column is missing: {config.liquidity_column}",
                    expected="present",
                    actual="missing",
                )
            )
        else:
            liquidity_values = _numeric_values(_column_values(df, config.liquidity_column))

            low_liquidity_count = sum(
                1
                for value in liquidity_values
                if value is None or value < config.min_liquidity
            )

            if low_liquidity_count > 0:
                issues.append(
                    OptimizerGuardIssue(
                        severity="BLOCK",
                        guard_name="minimum_liquidity",
                        column=config.liquidity_column,
                        message="One or more candidates fail the minimum liquidity requirement.",
                        expected=f">= {config.min_liquidity}",
                        actual=low_liquidity_count,
                    )
                )

    if config.greek_limits:
        if config.weight_column not in columns:
            pass
        else:
            valid_weights = [value for value in weight_values if value is not None]

            for greek_limit in config.greek_limits:
                if greek_limit.column not in columns:
                    issues.append(
                        OptimizerGuardIssue(
                            severity=greek_limit.severity,
                            guard_name="greek_column_present",
                            column=greek_limit.column,
                            message=f"Required Greek column is missing: {greek_limit.column}",
                            expected="present",
                            actual="missing",
                        )
                    )
                    continue

                greek_values = _numeric_values(_column_values(df, greek_limit.column))

                if len(valid_weights) != len(greek_values):
                    issues.append(
                        OptimizerGuardIssue(
                            severity=greek_limit.severity,
                            guard_name="greek_exposure_shape",
                            column=greek_limit.column,
                            message="Weight and Greek columns have mismatched lengths.",
                            expected=len(valid_weights),
                            actual=len(greek_values),
                        )
                    )
                    continue

                if any(value is None for value in greek_values):
                    issues.append(
                        OptimizerGuardIssue(
                            severity=greek_limit.severity,
                            guard_name="greek_values_numeric",
                            column=greek_limit.column,
                            message="Greek column contains missing, non-numeric, NaN, or infinite values.",
                            expected="all finite numeric values",
                            actual="invalid values present",
                        )
                    )
                    continue

                exposure = sum(
                    weight * greek
                    for weight, greek in zip(valid_weights, greek_values, strict=True)
                    if weight is not None and greek is not None
                )

                if (
                    greek_limit.min_exposure is not None
                    and exposure < greek_limit.min_exposure
                ):
                    issues.append(
                        OptimizerGuardIssue(
                            severity=greek_limit.severity,
                            guard_name="greek_min_exposure",
                            column=greek_limit.column,
                            message=f"Portfolio {greek_limit.column} exposure is below minimum.",
                            expected=f">= {greek_limit.min_exposure}",
                            actual=exposure,
                        )
                    )

                if (
                    greek_limit.max_exposure is not None
                    and exposure > greek_limit.max_exposure
                ):
                    issues.append(
                        OptimizerGuardIssue(
                            severity=greek_limit.severity,
                            guard_name="greek_max_exposure",
                            column=greek_limit.column,
                            message=f"Portfolio {greek_limit.column} exposure is above maximum.",
                            expected=f"<= {greek_limit.max_exposure}",
                            actual=exposure,
                        )
                    )

    passed = not any(issue.severity in {"BLOCK", "FAIL"} for issue in issues)

    return OptimizerGuardResult(
        passed=passed,
        total_rows=total_rows,
        issues=tuple(issues),
    )


def require_optimizer_guards(
    df: Any,
    config: OptimizerGuardConfig | None = None,
) -> None:
    """
    Raise ValueError if optimizer guards detect a blocking issue.
    """
    result = check_optimizer_guards(df=df, config=config)

    if result.failed:
        issue_messages = "; ".join(issue.message for issue in result.blocking_issues)
        raise ValueError(f"Optimizer guard validation failed: {issue_messages}")


OPTIMIZER_INPUT_GUARD_CONFIG = OptimizerGuardConfig(
    require_non_empty=True,
    require_candidate_id=True,
    require_edge_column=True,
    require_positive_edge=True,
    require_weight_column=False,
)


OPTIMIZER_OUTPUT_GUARD_CONFIG = OptimizerGuardConfig(
    require_non_empty=True,
    require_candidate_id=True,
    require_weight_column=True,
    check_weight_sum=True,
    target_weight_sum=1.0,
    weight_sum_tolerance=1e-6,
    min_weight=0.0,
    max_weight=1.0,
    allow_negative_weights=False,
    max_concentration=0.35,
)


OPTIONS_OPTIMIZER_GUARD_CONFIG = OptimizerGuardConfig(
    require_non_empty=True,
    require_candidate_id=True,
    require_weight_column=True,
    check_weight_sum=True,
    target_weight_sum=1.0,
    weight_sum_tolerance=1e-6,
    min_weight=0.0,
    max_weight=1.0,
    allow_negative_weights=False,
    max_concentration=0.35,
    greek_limits=(
        GreekLimit("delta", min_exposure=-0.30, max_exposure=0.30),
        GreekLimit("gamma", min_exposure=-0.10, max_exposure=0.10),
        GreekLimit("theta", min_exposure=-1.00, max_exposure=1.00),
        GreekLimit("vega", min_exposure=-1.00, max_exposure=1.00),
    ),
)
