from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ReproducibilityConfig:
    """
    Configuration for deterministic dataframe fingerprinting.

    columns:
        Optional subset of columns to include in the fingerprint.

    sort_by:
        Optional columns used to sort rows before hashing.
        Use this when row order should not affect reproducibility.

    normalize_column_order:
        If True, columns are sorted alphabetically before hashing.
        Use this when column order should not affect reproducibility.

    include_schema:
        If True, dtype/schema information contributes to the final fingerprint.

    float_precision:
        Optional rounding precision for floating-point values before hashing.
    """

    name: str = "artifact"
    columns: Sequence[str] | None = None
    sort_by: Sequence[str] | None = None
    normalize_column_order: bool = False
    include_schema: bool = True
    float_precision: int | None = 12


@dataclass(frozen=True)
class ReproducibilityArtifact:
    """
    Deterministic fingerprint of a dataframe-like object.
    """

    name: str
    row_count: int
    columns: tuple[str, ...]
    schema_digest: str | None
    data_digest: str
    combined_digest: str


@dataclass(frozen=True)
class ReproducibilityIssue:
    severity: str
    message: str
    field: str
    expected: Any | None = None
    actual: Any | None = None


@dataclass(frozen=True)
class ReproducibilityResult:
    passed: bool
    expected: ReproducibilityArtifact
    actual: ReproducibilityArtifact
    issues: tuple[ReproducibilityIssue, ...]

    @property
    def failed(self) -> bool:
        return not self.passed

    @property
    def blocking_issues(self) -> tuple[ReproducibilityIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.severity in {"BLOCK", "FAIL"}
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


def _get_schema(df: Any) -> Mapping[str, Any]:
    schema = getattr(df, "schema", None)

    if schema is None:
        return {}

    if isinstance(schema, Mapping):
        return schema

    try:
        return dict(schema)
    except Exception:
        return {}


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def _normalize_value(value: Any, *, float_precision: int | None) -> Any:
    """
    Convert values into stable JSON-serializable representations.
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, int) and not isinstance(value, bool):
        return value

    if isinstance(value, float):
        if math.isnan(value):
            return "__NaN__"

        if math.isinf(value):
            return "__INF__" if value > 0 else "__NEG_INF__"

        normalized = round(value, float_precision) if float_precision is not None else value

        # Canonicalize integer-like floats so 1 and 1.0 fingerprint the same
        # when schema comparison is disabled.
        if normalized.is_integer():
            return int(normalized)

        return normalized

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, str):
        return value

    if isinstance(value, Mapping):
        return {
            str(key): _normalize_value(val, float_precision=float_precision)
            for key, val in sorted(value.items(), key=lambda item: str(item[0]))
        }

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            _normalize_value(item, float_precision=float_precision)
            for item in value
        ]

    return repr(value)


def _resolve_columns(df: Any, config: ReproducibilityConfig) -> tuple[str, ...]:
    available_columns = _get_columns(df)

    if config.columns is None:
        selected_columns = list(available_columns)
    else:
        selected_columns = list(config.columns)

    missing_columns = sorted(set(selected_columns) - set(available_columns))

    if missing_columns:
        raise ValueError(f"Fingerprint columns are missing from dataframe: {missing_columns}")

    if config.normalize_column_order:
        selected_columns = sorted(selected_columns)

    return tuple(selected_columns)


def _validate_sort_columns(
    columns: Sequence[str],
    sort_by: Sequence[str] | None,
) -> tuple[str, ...]:
    if sort_by is None:
        return ()

    missing_sort_columns = sorted(set(sort_by) - set(columns))

    if missing_sort_columns:
        raise ValueError(
            f"Sort columns must be included in fingerprint columns: {missing_sort_columns}"
        )

    return tuple(sort_by)


def fingerprint_dataframe(
    df: Any,
    config: ReproducibilityConfig | None = None,
) -> ReproducibilityArtifact:
    """
    Create a deterministic fingerprint for a dataframe-like object.

    This is useful for validating:

    - same raw data -> same features
    - same features -> same signals
    - same candidates -> same optimizer output
    - same optimizer output -> same report dataset
    """
    config = config or ReproducibilityConfig()

    columns = _resolve_columns(df, config)
    sort_by = _validate_sort_columns(columns, config.sort_by)
    row_count = _row_count(df)
    schema = _get_schema(df)

    values_by_column = {
        column: _to_values(df[column])
        for column in columns
    }

    rows: list[dict[str, Any]] = []

    for row_index in range(row_count):
        row = {
            column: _normalize_value(
                values_by_column[column][row_index],
                float_precision=config.float_precision,
            )
            for column in columns
        }
        rows.append(row)

    if sort_by:
        rows.sort(
            key=lambda row: tuple(
                json.dumps(
                    row[column],
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                )
                for column in sort_by
            )
        )

    schema_payload: tuple[tuple[str, str], ...] | None = None
    schema_digest: str | None = None

    if config.include_schema:
        schema_payload = tuple(
            (column, repr(schema.get(column)))
            for column in columns
        )
        schema_digest = _hash_payload(schema_payload)

    data_payload = {
        "columns": columns,
        "rows": rows,
    }

    data_digest = _hash_payload(data_payload)

    combined_payload = {
        "name": config.name,
        "row_count": row_count,
        "columns": columns,
        "schema_digest": schema_digest,
        "data_digest": data_digest,
    }

    combined_digest = _hash_payload(combined_payload)

    return ReproducibilityArtifact(
        name=config.name,
        row_count=row_count,
        columns=columns,
        schema_digest=schema_digest,
        data_digest=data_digest,
        combined_digest=combined_digest,
    )


def compare_reproducibility_artifacts(
    expected: ReproducibilityArtifact,
    actual: ReproducibilityArtifact,
    *,
    check_schema: bool = True,
) -> ReproducibilityResult:
    """
    Compare two reproducibility artifacts.
    """
    issues: list[ReproducibilityIssue] = []

    if expected.row_count != actual.row_count:
        issues.append(
            ReproducibilityIssue(
                severity="FAIL",
                field="row_count",
                message="Row count changed between reproducibility artifacts.",
                expected=expected.row_count,
                actual=actual.row_count,
            )
        )

    if expected.columns != actual.columns:
        issues.append(
            ReproducibilityIssue(
                severity="FAIL",
                field="columns",
                message="Column set or column order changed between reproducibility artifacts.",
                expected=expected.columns,
                actual=actual.columns,
            )
        )

    if check_schema and expected.schema_digest != actual.schema_digest:
        issues.append(
            ReproducibilityIssue(
                severity="FAIL",
                field="schema_digest",
                message="Schema digest changed between reproducibility artifacts.",
                expected=expected.schema_digest,
                actual=actual.schema_digest,
            )
        )

    if expected.data_digest != actual.data_digest:
        issues.append(
            ReproducibilityIssue(
                severity="FAIL",
                field="data_digest",
                message="Data digest changed between reproducibility artifacts.",
                expected=expected.data_digest,
                actual=actual.data_digest,
            )
        )

    if expected.combined_digest != actual.combined_digest:
        issues.append(
            ReproducibilityIssue(
                severity="FAIL",
                field="combined_digest",
                message="Combined digest changed between reproducibility artifacts.",
                expected=expected.combined_digest,
                actual=actual.combined_digest,
            )
        )

    passed = not issues

    return ReproducibilityResult(
        passed=passed,
        expected=expected,
        actual=actual,
        issues=tuple(issues),
    )


def check_reproducibility(
    expected_df: Any,
    actual_df: Any,
    config: ReproducibilityConfig | None = None,
    *,
    check_schema: bool = True,
) -> ReproducibilityResult:
    """
    Fingerprint and compare two dataframe-like objects.
    """
    config = config or ReproducibilityConfig()

    expected = fingerprint_dataframe(expected_df, config)
    actual = fingerprint_dataframe(actual_df, config)

    return compare_reproducibility_artifacts(
        expected=expected,
        actual=actual,
        check_schema=check_schema,
    )


def require_reproducible(
    expected_df: Any,
    actual_df: Any,
    config: ReproducibilityConfig | None = None,
    *,
    check_schema: bool = True,
) -> None:
    """
    Raise ValueError when two dataframe-like objects are not reproducible.
    """
    result = check_reproducibility(
        expected_df=expected_df,
        actual_df=actual_df,
        config=config,
        check_schema=check_schema,
    )

    if result.failed:
        issue_messages = "; ".join(issue.message for issue in result.blocking_issues)
        raise ValueError(f"Reproducibility validation failed: {issue_messages}")


FEATURE_REPRODUCIBILITY_CONFIG = ReproducibilityConfig(
    name="features",
    sort_by=("symbol", "date"),
    include_schema=True,
    float_precision=12,
)


SIGNAL_REPRODUCIBILITY_CONFIG = ReproducibilityConfig(
    name="signals",
    sort_by=("symbol", "date"),
    include_schema=True,
    float_precision=12,
)


OPTIMIZER_REPRODUCIBILITY_CONFIG = ReproducibilityConfig(
    name="optimizer_output",
    sort_by=("candidate_id",),
    include_schema=True,
    float_precision=12,
)


REPORT_REPRODUCIBILITY_CONFIG = ReproducibilityConfig(
    name="report_data",
    include_schema=True,
    float_precision=12,
)
