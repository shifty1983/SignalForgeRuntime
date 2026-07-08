from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class SchemaIssue:
    """
    A single schema validation issue.

    severity:
        INFO  - informational only
        WARN  - suspicious but not blocking
        BLOCK - blocks downstream usage
        FAIL  - invalid schema
    """

    severity: str
    message: str
    column: str | None = None
    expected: Any | None = None
    actual: Any | None = None


@dataclass(frozen=True)
class SchemaSpec:
    """
    Defines the expected schema for a dataframe-like object.

    required_columns:
        Columns that must exist.

    optional_columns:
        Columns that may exist but are not required.

    dtypes:
        Optional mapping of column name to expected dtype.
        For Polars, use values like pl.Float64, pl.Utf8, pl.Date, etc.
    """

    name: str
    required_columns: Sequence[str]
    optional_columns: Sequence[str] = field(default_factory=list)
    dtypes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SchemaValidationResult:
    spec_name: str
    passed: bool
    issues: tuple[SchemaIssue, ...]

    @property
    def failed(self) -> bool:
        return not self.passed

    @property
    def blocking_issues(self) -> tuple[SchemaIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.severity in {"BLOCK", "FAIL"}
        )

    @property
    def warnings(self) -> tuple[SchemaIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "WARN")


def _get_columns(df: Any) -> list[str]:
    if hasattr(df, "columns"):
        return list(df.columns)

    raise TypeError("Object does not expose a columns attribute.")


def _get_schema(df: Any) -> Mapping[str, Any]:
    """
    Supports Polars-style schema access.

    If dtype information is unavailable, returns an empty mapping.
    """
    schema = getattr(df, "schema", None)

    if schema is None:
        return {}

    if isinstance(schema, Mapping):
        return schema

    try:
        return dict(schema)
    except Exception:
        return {}


def validate_schema(
    df: Any,
    spec: SchemaSpec,
    *,
    allow_extra_columns: bool = True,
    strict_dtypes: bool = True,
) -> SchemaValidationResult:
    """
    Validate dataframe columns and optional dtypes against a SchemaSpec.

    This function is intentionally lightweight and dependency-flexible.
    It works with Polars and most dataframe-like objects that expose:
        - .columns
        - optionally .schema

    Parameters
    ----------
    df:
        Dataframe-like object.

    spec:
        Expected schema definition.

    allow_extra_columns:
        If False, columns outside required/optional are treated as warnings.

    strict_dtypes:
        If True, dtype mismatches are blocking failures.
        If False, dtype mismatches are warnings.
    """
    issues: list[SchemaIssue] = []

    columns = _get_columns(df)
    column_set = set(columns)

    required_set = set(spec.required_columns)
    optional_set = set(spec.optional_columns)
    allowed_set = required_set | optional_set

    for column in spec.required_columns:
        if column not in column_set:
            issues.append(
                SchemaIssue(
                    severity="FAIL",
                    column=column,
                    message=f"Missing required column: {column}",
                    expected="present",
                    actual="missing",
                )
            )

    if not allow_extra_columns:
        extra_columns = sorted(column_set - allowed_set)

        for column in extra_columns:
            issues.append(
                SchemaIssue(
                    severity="WARN",
                    column=column,
                    message=f"Unexpected extra column: {column}",
                    expected="not present",
                    actual="present",
                )
            )

    schema = _get_schema(df)

    for column, expected_dtype in spec.dtypes.items():
        if column not in column_set:
            continue

        actual_dtype = schema.get(column)

        if actual_dtype is None:
            issues.append(
                SchemaIssue(
                    severity="WARN",
                    column=column,
                    message=f"Could not determine dtype for column: {column}",
                    expected=expected_dtype,
                    actual=None,
                )
            )
            continue

        if actual_dtype != expected_dtype:
            severity = "FAIL" if strict_dtypes else "WARN"

            issues.append(
                SchemaIssue(
                    severity=severity,
                    column=column,
                    message=f"Invalid dtype for column: {column}",
                    expected=expected_dtype,
                    actual=actual_dtype,
                )
            )

    passed = not any(issue.severity in {"BLOCK", "FAIL"} for issue in issues)

    return SchemaValidationResult(
        spec_name=spec.name,
        passed=passed,
        issues=tuple(issues),
    )


def require_schema(
    df: Any,
    spec: SchemaSpec,
    *,
    allow_extra_columns: bool = True,
    strict_dtypes: bool = True,
) -> None:
    """
    Validate schema and raise ValueError if it fails.

    Useful at layer boundaries where invalid data should stop execution.
    """
    result = validate_schema(
        df=df,
        spec=spec,
        allow_extra_columns=allow_extra_columns,
        strict_dtypes=strict_dtypes,
    )

    if result.failed:
        issue_messages = "; ".join(issue.message for issue in result.blocking_issues)
        raise ValueError(f"Schema validation failed for {spec.name}: {issue_messages}")


# Common layer schemas.
# These are intentionally conservative and can be expanded as your system evolves.

MARKET_DATA_SCHEMA = SchemaSpec(
    name="market_data",
    required_columns=("symbol", "date", "open", "high", "low", "close", "volume"),
)

FEATURE_SCHEMA = SchemaSpec(
    name="features",
    required_columns=("symbol", "date"),
    optional_columns=(
        "return",
        "returns",
        "volatility",
        "momentum",
        "drawdown",
        "moving_average",
        "z_score",
        "rank",
    ),
)

SIGNAL_SCHEMA = SchemaSpec(
    name="signals",
    required_columns=("symbol", "date", "signal"),
    optional_columns=("score", "direction", "confidence", "rank"),
)

STRATEGY_CANDIDATE_SCHEMA = SchemaSpec(
    name="strategy_candidates",
    required_columns=("symbol", "date", "strategy"),
    optional_columns=(
        "expected_value",
        "expected_return",
        "risk_score",
        "reward_risk",
        "confidence",
        "direction",
        "delta",
        "gamma",
        "theta",
        "vega",
    ),
)

OPTIMIZER_INPUT_SCHEMA = SchemaSpec(
    name="optimizer_inputs",
    required_columns=("candidate_id",),
    optional_columns=(
        "symbol",
        "date",
        "strategy",
        "expected_return",
        "expected_value",
        "risk",
        "risk_score",
        "weight",
        "max_weight",
        "min_weight",
        "delta",
        "gamma",
        "theta",
        "vega",
    ),
)

OPTIMIZER_OUTPUT_SCHEMA = SchemaSpec(
    name="optimizer_outputs",
    required_columns=("candidate_id", "weight"),
    optional_columns=(
        "symbol",
        "date",
        "strategy",
        "expected_return",
        "expected_value",
        "risk",
        "delta",
        "gamma",
        "theta",
        "vega",
    ),
)
