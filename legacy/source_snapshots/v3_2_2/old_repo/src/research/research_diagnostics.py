from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from itertools import combinations
from typing import Any, Mapping

from src.research.evaluation_contracts import (
    is_finite_number,
    is_null,
    table_columns,
    table_records,
    table_row_count,
    validate_research_evaluation_output,
)


class DiagnosticStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


@dataclass(frozen=True)
class ResearchDiagnostic:
    name: str
    status: DiagnosticStatus
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResearchDiagnosticsReport:
    diagnostics: tuple[ResearchDiagnostic, ...]

    @property
    def passed(self) -> bool:
        return not any(diagnostic.status == DiagnosticStatus.FAIL for diagnostic in self.diagnostics)

    @property
    def warnings(self) -> tuple[ResearchDiagnostic, ...]:
        return tuple(
            diagnostic
            for diagnostic in self.diagnostics
            if diagnostic.status == DiagnosticStatus.WARNING
        )

    @property
    def failures(self) -> tuple[ResearchDiagnostic, ...]:
        return tuple(
            diagnostic
            for diagnostic in self.diagnostics
            if diagnostic.status == DiagnosticStatus.FAIL
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "diagnostics": [
                {
                    "name": diagnostic.name,
                    "status": diagnostic.status.value,
                    "message": diagnostic.message,
                    "details": dict(diagnostic.details),
                }
                for diagnostic in self.diagnostics
            ],
        }

_IDENTIFIER_COLUMNS = {
    "date",
    "symbol",
    "ticker",
    "asset",
    "asset_id",
    "id",
    "name",
    "bucket",
    "rank",
    "candidate",
}


def _numeric_columns(
    records: list[Mapping[str, Any]],
    columns: list[str],
    excluded_columns: set[str] | None = None,
) -> list[str]:
    excluded = excluded_columns or set()
    numeric_columns: list[str] = []

    for column in columns:
        if column in excluded:
            continue

        values = [
            row.get(column)
            for row in records
            if not is_null(row.get(column))
        ]

        if values and all(is_finite_number(value) for value in values):
            numeric_columns.append(column)

    return numeric_columns


def _coverage_ratio(
    records: list[Mapping[str, Any]],
    column: str,
) -> float:
    if not records:
        return 0.0

    valid_count = sum(
        1
        for row in records
        if not is_null(row.get(column)) and is_finite_number(row.get(column))
    )

    return valid_count / len(records)


def _unique_finite_count(
    records: list[Mapping[str, Any]],
    column: str,
) -> int:
    values = {
        float(row.get(column))
        for row in records
        if not is_null(row.get(column)) and is_finite_number(row.get(column))
    }

    return len(values)


def _pearson_correlation(
    pairs: list[tuple[float, float]],
) -> float | None:
    if len(pairs) < 2:
        return None

    x_values = [pair[0] for pair in pairs]
    y_values = [pair[1] for pair in pairs]

    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)

    numerator = sum(
        (x - x_mean) * (y - y_mean)
        for x, y in pairs
    )

    x_denominator = sum((x - x_mean) ** 2 for x in x_values)
    y_denominator = sum((y - y_mean) ** 2 for y in y_values)

    denominator = math.sqrt(x_denominator * y_denominator)

    if denominator <= 0:
        return None

    return numerator / denominator


def _find_signal_value_column(columns: set[str]) -> str | None:
    return next(
        (
            column
            for column in (
                "signal",
                "signal_value",
                "research_consensus_signal",
                "direction",
                "score",
            )
            if column in columns
        ),
        None,
    )

def _contract_diagnostic(output: Mapping[str, Any]) -> ResearchDiagnostic:
    result = validate_research_evaluation_output(output)

    if result.passed:
        warning_count = len(result.warnings)

        status = DiagnosticStatus.WARNING if warning_count else DiagnosticStatus.PASS
        message = (
            "Research output contract passed with warnings."
            if warning_count
            else "Research output contract passed."
        )

        return ResearchDiagnostic(
            name="output_contract",
            status=status,
            message=message,
            details=result.to_dict(),
        )

    return ResearchDiagnostic(
        name="output_contract",
        status=DiagnosticStatus.FAIL,
        message="Research output contract failed.",
        details=result.to_dict(),
    )


def _row_count_diagnostics(output: Mapping[str, Any]) -> list[ResearchDiagnostic]:
    diagnostics: list[ResearchDiagnostic] = []

    for section in ("factors", "signals", "portfolio_targets"):
        if section not in output:
            continue

        row_count = table_row_count(output[section])

        status = DiagnosticStatus.PASS if row_count > 0 else DiagnosticStatus.FAIL
        message = (
            f"{section} contains {row_count} rows."
            if row_count > 0
            else f"{section} is empty."
        )

        diagnostics.append(
            ResearchDiagnostic(
                name=f"{section}.row_count",
                status=status,
                message=message,
                details={"row_count": row_count},
            )
        )

    return diagnostics


def _missing_value_diagnostics(output: Mapping[str, Any]) -> list[ResearchDiagnostic]:
    diagnostics: list[ResearchDiagnostic] = []

    for section in ("factors", "signals", "portfolio_targets"):
        if section not in output:
            continue

        records = table_records(output[section])
        columns = table_columns(output[section])

        if not records:
            continue

        missing_by_column: dict[str, int] = {}

        for column in columns:
            missing_by_column[column] = sum(
                1 for row in records if is_null(row.get(column))
            )

        columns_with_missing = {
            column: missing
            for column, missing in missing_by_column.items()
            if missing > 0
        }

        if columns_with_missing:
            diagnostics.append(
                ResearchDiagnostic(
                    name=f"{section}.missing_values",
                    status=DiagnosticStatus.WARNING,
                    message=f"{section} contains missing values.",
                    details={
                        "row_count": len(records),
                        "missing_by_column": columns_with_missing,
                    },
                )
            )
        else:
            diagnostics.append(
                ResearchDiagnostic(
                    name=f"{section}.missing_values",
                    status=DiagnosticStatus.PASS,
                    message=f"{section} contains no missing values.",
                    details={"row_count": len(records)},
                )
            )

    return diagnostics


def _signal_distribution_diagnostics(output: Mapping[str, Any]) -> list[ResearchDiagnostic]:
    if "signals" not in output:
        return []

    records = table_records(output["signals"])
    columns = set(table_columns(output["signals"]))

    signal_value_column = _find_signal_value_column(columns)

    if signal_value_column is None:
        return [
            ResearchDiagnostic(
                name="signals.distribution",
                status=DiagnosticStatus.WARNING,
                message="Signal distribution check skipped because no signal value column was found.",
                details={"available_columns": sorted(columns)},
            )
        ]

    values = [row.get(signal_value_column) for row in records if row.get(signal_value_column) is not None]
    distribution = Counter(values)

    if not values:
        return [
            ResearchDiagnostic(
                name="signals.distribution",
                status=DiagnosticStatus.FAIL,
                message="Signals contain no usable signal values.",
                details={"signal_value_column": signal_value_column},
            )
        ]

    unique_count = len(distribution)

    status = DiagnosticStatus.PASS if unique_count > 1 else DiagnosticStatus.WARNING
    message = (
        "Signals contain multiple signal values."
        if unique_count > 1
        else "Signals contain only one unique signal value."
    )

    return [
        ResearchDiagnostic(
            name="signals.distribution",
            status=status,
            message=message,
            details={
                "signal_value_column": signal_value_column,
                "unique_count": unique_count,
                "distribution": dict(distribution),
            },
        )
    ]

def _factor_coverage_diagnostics(
    output: Mapping[str, Any],
    min_factor_coverage: float = 0.75,
) -> list[ResearchDiagnostic]:
    if "factors" not in output:
        return []

    records = table_records(output["factors"])
    columns = table_columns(output["factors"])

    if not records:
        return []

    factor_columns = _numeric_columns(
        records=records,
        columns=columns,
        excluded_columns=_IDENTIFIER_COLUMNS,
    )

    if not factor_columns:
        return [
            ResearchDiagnostic(
                name="factors.coverage",
                status=DiagnosticStatus.WARNING,
                message="Factor coverage check skipped because no numeric factor columns were found.",
                details={"available_columns": columns},
            )
        ]

    coverage_by_column = {
        column: _coverage_ratio(records, column)
        for column in factor_columns
    }

    low_coverage = {
        column: coverage
        for column, coverage in coverage_by_column.items()
        if coverage < min_factor_coverage
    }

    if low_coverage:
        return [
            ResearchDiagnostic(
                name="factors.coverage",
                status=DiagnosticStatus.WARNING,
                message="Some factor columns have low usable-value coverage.",
                details={
                    "min_factor_coverage": min_factor_coverage,
                    "coverage_by_column": coverage_by_column,
                    "low_coverage": low_coverage,
                },
            )
        ]

    return [
        ResearchDiagnostic(
            name="factors.coverage",
            status=DiagnosticStatus.PASS,
            message="Factor columns meet usable-value coverage threshold.",
            details={
                "min_factor_coverage": min_factor_coverage,
                "coverage_by_column": coverage_by_column,
            },
        )
    ]


def _factor_dispersion_diagnostics(
    output: Mapping[str, Any],
    min_factor_unique_values: int = 2,
) -> list[ResearchDiagnostic]:
    if "factors" not in output:
        return []

    records = table_records(output["factors"])
    columns = table_columns(output["factors"])

    if not records:
        return []

    factor_columns = _numeric_columns(
        records=records,
        columns=columns,
        excluded_columns=_IDENTIFIER_COLUMNS,
    )

    if not factor_columns:
        return [
            ResearchDiagnostic(
                name="factors.dispersion",
                status=DiagnosticStatus.WARNING,
                message="Factor dispersion check skipped because no numeric factor columns were found.",
                details={"available_columns": columns},
            )
        ]

    unique_counts = {
        column: _unique_finite_count(records, column)
        for column in factor_columns
    }

    low_dispersion = {
        column: unique_count
        for column, unique_count in unique_counts.items()
        if unique_count < min_factor_unique_values
    }

    if low_dispersion:
        return [
            ResearchDiagnostic(
                name="factors.dispersion",
                status=DiagnosticStatus.WARNING,
                message="Some factor columns have low cross-sectional dispersion.",
                details={
                    "min_factor_unique_values": min_factor_unique_values,
                    "unique_counts": unique_counts,
                    "low_dispersion": low_dispersion,
                },
            )
        ]

    return [
        ResearchDiagnostic(
            name="factors.dispersion",
            status=DiagnosticStatus.PASS,
            message="Factor columns have sufficient dispersion.",
            details={
                "min_factor_unique_values": min_factor_unique_values,
                "unique_counts": unique_counts,
            },
        )
    ]


def _factor_correlation_diagnostics(
    output: Mapping[str, Any],
    max_factor_abs_correlation: float = 0.95,
    min_pair_observations: int = 3,
) -> list[ResearchDiagnostic]:
    if "factors" not in output:
        return []

    records = table_records(output["factors"])
    columns = table_columns(output["factors"])

    if not records:
        return []

    factor_columns = _numeric_columns(
        records=records,
        columns=columns,
        excluded_columns=_IDENTIFIER_COLUMNS,
    )

    if len(factor_columns) < 2:
        return [
            ResearchDiagnostic(
                name="factors.correlation",
                status=DiagnosticStatus.WARNING,
                message="Factor correlation check skipped because fewer than two numeric factor columns were found.",
                details={"factor_columns": factor_columns},
            )
        ]

    correlations: dict[str, float] = {}
    high_correlations: dict[str, float] = {}

    for left, right in combinations(factor_columns, 2):
        pairs = [
            (float(row[left]), float(row[right]))
            for row in records
            if (
                not is_null(row.get(left))
                and not is_null(row.get(right))
                and is_finite_number(row.get(left))
                and is_finite_number(row.get(right))
            )
        ]

        if len(pairs) < min_pair_observations:
            continue

        correlation = _pearson_correlation(pairs)

        if correlation is None:
            continue

        pair_name = f"{left}::{right}"
        correlations[pair_name] = correlation

        if abs(correlation) > max_factor_abs_correlation:
            high_correlations[pair_name] = correlation

    if not correlations:
        return [
            ResearchDiagnostic(
                name="factors.correlation",
                status=DiagnosticStatus.WARNING,
                message="Factor correlation check skipped because no factor pairs had enough observations.",
                details={
                    "factor_columns": factor_columns,
                    "min_pair_observations": min_pair_observations,
                },
            )
        ]

    if high_correlations:
        return [
            ResearchDiagnostic(
                name="factors.correlation",
                status=DiagnosticStatus.WARNING,
                message="Some factor pairs are highly correlated.",
                details={
                    "max_factor_abs_correlation": max_factor_abs_correlation,
                    "high_correlations": high_correlations,
                    "correlations": correlations,
                },
            )
        ]

    return [
        ResearchDiagnostic(
            name="factors.correlation",
            status=DiagnosticStatus.PASS,
            message="Factor correlations are within diagnostic threshold.",
            details={
                "max_factor_abs_correlation": max_factor_abs_correlation,
                "correlations": correlations,
            },
        )
    ]


def _signal_concentration_diagnostics(
    output: Mapping[str, Any],
    max_signal_share: float = 0.80,
    min_active_signal_share: float = 0.01,
) -> list[ResearchDiagnostic]:
    if "signals" not in output:
        return []

    records = table_records(output["signals"])
    columns = set(table_columns(output["signals"]))

    signal_value_column = _find_signal_value_column(columns)

    if signal_value_column is None:
        return [
            ResearchDiagnostic(
                name="signals.concentration",
                status=DiagnosticStatus.WARNING,
                message="Signal concentration check skipped because no signal value column was found.",
                details={"available_columns": sorted(columns)},
            )
        ]

    values = [
        row.get(signal_value_column)
        for row in records
        if row.get(signal_value_column) is not None
    ]

    if not values:
        return [
            ResearchDiagnostic(
                name="signals.concentration",
                status=DiagnosticStatus.FAIL,
                message="Signals contain no usable values for concentration diagnostics.",
                details={"signal_value_column": signal_value_column},
            )
        ]

    total_count = len(values)
    long_count = sum(1 for value in values if is_finite_number(value) and float(value) > 0)
    short_count = sum(1 for value in values if is_finite_number(value) and float(value) < 0)
    neutral_count = sum(1 for value in values if is_finite_number(value) and float(value) == 0)

    active_count = long_count + short_count
    active_share = active_count / total_count
    long_share = long_count / total_count
    short_share = short_count / total_count
    neutral_share = neutral_count / total_count
    max_directional_share = max(long_share, short_share, neutral_share)

    details = {
        "signal_value_column": signal_value_column,
        "total_count": total_count,
        "long_count": long_count,
        "short_count": short_count,
        "neutral_count": neutral_count,
        "active_share": active_share,
        "long_share": long_share,
        "short_share": short_share,
        "neutral_share": neutral_share,
        "max_signal_share": max_signal_share,
        "min_active_signal_share": min_active_signal_share,
    }

    if active_share < min_active_signal_share:
        return [
            ResearchDiagnostic(
                name="signals.concentration",
                status=DiagnosticStatus.WARNING,
                message="Signals have very low active exposure.",
                details=details,
            )
        ]

    if max_directional_share > max_signal_share:
        return [
            ResearchDiagnostic(
                name="signals.concentration",
                status=DiagnosticStatus.WARNING,
                message="Signals are concentrated in one direction or neutral state.",
                details=details,
            )
        ]

    return [
        ResearchDiagnostic(
            name="signals.concentration",
            status=DiagnosticStatus.PASS,
            message="Signal concentration is within diagnostic thresholds.",
            details=details,
        )
    ]


def _factor_forward_return_diagnostics(
    output: Mapping[str, Any],
    forward_return_column: str = "forward_return",
    min_pair_observations: int = 3,
) -> list[ResearchDiagnostic]:
    if "factors" not in output:
        return []

    records = table_records(output["factors"])
    columns = table_columns(output["factors"])

    if forward_return_column not in columns:
        return []

    factor_columns = _numeric_columns(
        records=records,
        columns=columns,
        excluded_columns=_IDENTIFIER_COLUMNS | {forward_return_column},
    )

    if not factor_columns:
        return [
            ResearchDiagnostic(
                name="factors.forward_return_relationship",
                status=DiagnosticStatus.WARNING,
                message="Forward-return diagnostic skipped because no numeric factor columns were found.",
                details={"forward_return_column": forward_return_column},
            )
        ]

    correlations: dict[str, float] = {}
    observation_counts: dict[str, int] = {}

    for factor_column in factor_columns:
        pairs = [
            (float(row[factor_column]), float(row[forward_return_column]))
            for row in records
            if (
                not is_null(row.get(factor_column))
                and not is_null(row.get(forward_return_column))
                and is_finite_number(row.get(factor_column))
                and is_finite_number(row.get(forward_return_column))
            )
        ]

        observation_counts[factor_column] = len(pairs)

        if len(pairs) < min_pair_observations:
            continue

        correlation = _pearson_correlation(pairs)

        if correlation is not None:
            correlations[factor_column] = correlation

    if not correlations:
        return [
            ResearchDiagnostic(
                name="factors.forward_return_relationship",
                status=DiagnosticStatus.WARNING,
                message="Forward-return diagnostic could not calculate any factor relationships.",
                details={
                    "forward_return_column": forward_return_column,
                    "min_pair_observations": min_pair_observations,
                    "observation_counts": observation_counts,
                },
            )
        ]

    return [
        ResearchDiagnostic(
            name="factors.forward_return_relationship",
            status=DiagnosticStatus.PASS,
            message="Forward-return relationships calculated.",
            details={
                "forward_return_column": forward_return_column,
                "correlations": correlations,
                "observation_counts": observation_counts,
            },
        )
    ]

def _portfolio_target_diagnostics(
    output: Mapping[str, Any],
    max_gross_exposure: float = 2.0,
    max_single_position: float = 0.35,
) -> list[ResearchDiagnostic]:
    if "portfolio_targets" not in output:
        return []

    records = table_records(output["portfolio_targets"])
    columns = set(table_columns(output["portfolio_targets"]))

    required = {"date", "symbol", "target_weight"}
    if not required.issubset(columns):
        return [
            ResearchDiagnostic(
                name="portfolio_targets.exposure",
                status=DiagnosticStatus.FAIL,
                message="Portfolio target exposure check requires date, symbol, and target_weight.",
                details={"required_columns": sorted(required), "available_columns": sorted(columns)},
            )
        ]

    exposure_by_date: dict[Any, dict[str, float]] = defaultdict(
        lambda: {"gross": 0.0, "net": 0.0, "max_abs_weight": 0.0}
    )

    invalid_weight_count = 0

    for row in records:
        date = row.get("date")
        weight = row.get("target_weight")

        if not is_finite_number(weight):
            invalid_weight_count += 1
            continue

        weight_float = float(weight)

        exposure_by_date[date]["gross"] += abs(weight_float)
        exposure_by_date[date]["net"] += weight_float
        exposure_by_date[date]["max_abs_weight"] = max(
            exposure_by_date[date]["max_abs_weight"],
            abs(weight_float),
        )

    if invalid_weight_count:
        return [
            ResearchDiagnostic(
                name="portfolio_targets.exposure",
                status=DiagnosticStatus.FAIL,
                message="Portfolio targets contain invalid target weights.",
                details={"invalid_weight_count": invalid_weight_count},
            )
        ]

    gross_breaches = {
        str(date): exposure["gross"]
        for date, exposure in exposure_by_date.items()
        if exposure["gross"] > max_gross_exposure
    }

    concentration_breaches = {
        str(date): exposure["max_abs_weight"]
        for date, exposure in exposure_by_date.items()
        if exposure["max_abs_weight"] > max_single_position
    }

    diagnostics: list[ResearchDiagnostic] = []

    if gross_breaches:
        diagnostics.append(
            ResearchDiagnostic(
                name="portfolio_targets.gross_exposure",
                status=DiagnosticStatus.WARNING,
                message="Portfolio targets exceed diagnostic gross exposure threshold.",
                details={
                    "max_gross_exposure": max_gross_exposure,
                    "breaches": gross_breaches,
                },
            )
        )
    else:
        diagnostics.append(
            ResearchDiagnostic(
                name="portfolio_targets.gross_exposure",
                status=DiagnosticStatus.PASS,
                message="Portfolio targets are within diagnostic gross exposure threshold.",
                details={"max_gross_exposure": max_gross_exposure},
            )
        )

    if concentration_breaches:
        diagnostics.append(
            ResearchDiagnostic(
                name="portfolio_targets.concentration",
                status=DiagnosticStatus.WARNING,
                message="Portfolio targets exceed diagnostic single-position concentration threshold.",
                details={
                    "max_single_position": max_single_position,
                    "breaches": concentration_breaches,
                },
            )
        )
    else:
        diagnostics.append(
            ResearchDiagnostic(
                name="portfolio_targets.concentration",
                status=DiagnosticStatus.PASS,
                message="Portfolio targets are within diagnostic concentration threshold.",
                details={"max_single_position": max_single_position},
            )
        )

    diagnostics.append(
        ResearchDiagnostic(
            name="portfolio_targets.exposure_summary",
            status=DiagnosticStatus.PASS,
            message="Portfolio target exposure summary calculated.",
            details={
                str(date): {
                    "gross": exposure["gross"],
                    "net": exposure["net"],
                    "max_abs_weight": exposure["max_abs_weight"],
                }
                for date, exposure in exposure_by_date.items()
            },
        )
    )

    return diagnostics

def _portfolio_turnover_diagnostics(
    output: Mapping[str, Any],
    max_turnover: float = 1.0,
) -> list[ResearchDiagnostic]:
    if "portfolio_targets" not in output:
        return []

    records = table_records(output["portfolio_targets"])
    columns = set(table_columns(output["portfolio_targets"]))

    required = {"date", "symbol", "target_weight"}
    if not required.issubset(columns):
        return [
            ResearchDiagnostic(
                name="portfolio_targets.turnover",
                status=DiagnosticStatus.WARNING,
                message="Portfolio turnover check skipped because required columns are missing.",
                details={
                    "required_columns": sorted(required),
                    "available_columns": sorted(columns),
                },
            )
        ]

    weights_by_date: dict[Any, dict[Any, float]] = defaultdict(dict)
    invalid_weight_count = 0

    for row in records:
        date = row.get("date")
        symbol = row.get("symbol")
        weight = row.get("target_weight")

        if not is_finite_number(weight):
            invalid_weight_count += 1
            continue

        weights_by_date[date][symbol] = float(weight)

    if invalid_weight_count:
        return [
            ResearchDiagnostic(
                name="portfolio_targets.turnover",
                status=DiagnosticStatus.FAIL,
                message="Portfolio turnover check failed because target weights are invalid.",
                details={"invalid_weight_count": invalid_weight_count},
            )
        ]

    sorted_dates = sorted(weights_by_date.keys(), key=str)

    if len(sorted_dates) < 2:
        return [
            ResearchDiagnostic(
                name="portfolio_targets.turnover",
                status=DiagnosticStatus.WARNING,
                message="Portfolio turnover check skipped because fewer than two target dates were found.",
                details={"date_count": len(sorted_dates)},
            )
        ]

    turnover_by_date: dict[str, float] = {}

    for previous_date, current_date in zip(sorted_dates, sorted_dates[1:]):
        previous_weights = weights_by_date[previous_date]
        current_weights = weights_by_date[current_date]

        symbols = set(previous_weights) | set(current_weights)

        turnover = sum(
            abs(current_weights.get(symbol, 0.0) - previous_weights.get(symbol, 0.0))
            for symbol in symbols
        ) / 2.0

        turnover_by_date[str(current_date)] = turnover

    breaches = {
        date: turnover
        for date, turnover in turnover_by_date.items()
        if turnover > max_turnover
    }

    if breaches:
        return [
            ResearchDiagnostic(
                name="portfolio_targets.turnover",
                status=DiagnosticStatus.WARNING,
                message="Portfolio target turnover exceeds diagnostic threshold.",
                details={
                    "max_turnover": max_turnover,
                    "turnover_by_date": turnover_by_date,
                    "breaches": breaches,
                },
            )
        ]

    return [
        ResearchDiagnostic(
            name="portfolio_targets.turnover",
            status=DiagnosticStatus.PASS,
            message="Portfolio target turnover is within diagnostic threshold.",
            details={
                "max_turnover": max_turnover,
                "turnover_by_date": turnover_by_date,
            },
        )
    ]

def _alignment_diagnostics(output: Mapping[str, Any]) -> list[ResearchDiagnostic]:
    diagnostics: list[ResearchDiagnostic] = []

    if "signals" not in output or "portfolio_targets" not in output:
        return diagnostics

    signal_records = table_records(output["signals"])
    target_records = table_records(output["portfolio_targets"])

    signal_pairs = {
        (row.get("date"), row.get("symbol"))
        for row in signal_records
    }

    target_pairs = {
        (row.get("date"), row.get("symbol"))
        for row in target_records
    }

    targets_without_signals = target_pairs - signal_pairs

    if targets_without_signals:
        diagnostics.append(
            ResearchDiagnostic(
                name="research_to_targets.alignment",
                status=DiagnosticStatus.WARNING,
                message="Some portfolio targets do not have matching signal rows.",
                details={"unmatched_target_count": len(targets_without_signals)},
            )
        )
    else:
        diagnostics.append(
            ResearchDiagnostic(
                name="research_to_targets.alignment",
                status=DiagnosticStatus.PASS,
                message="Portfolio targets align with signal rows.",
                details={"target_pair_count": len(target_pairs)},
            )
        )

    return diagnostics


def build_research_diagnostics(
    output: Mapping[str, Any],
    max_gross_exposure: float = 2.0,
    max_single_position: float = 0.35,
    min_factor_coverage: float = 0.75,
    min_factor_unique_values: int = 2,
    max_factor_abs_correlation: float = 0.95,
    max_signal_share: float = 0.80,
    min_active_signal_share: float = 0.01,
    max_turnover: float = 1.0,
    forward_return_column: str = "forward_return",
) -> ResearchDiagnosticsReport:
    diagnostics: list[ResearchDiagnostic] = []

    diagnostics.append(_contract_diagnostic(output))
    diagnostics.extend(_row_count_diagnostics(output))
    diagnostics.extend(_missing_value_diagnostics(output))
    diagnostics.extend(
        _factor_coverage_diagnostics(
            output=output,
            min_factor_coverage=min_factor_coverage,
        )
    )
    diagnostics.extend(
        _factor_dispersion_diagnostics(
            output=output,
            min_factor_unique_values=min_factor_unique_values,
        )
    )
    diagnostics.extend(
        _factor_correlation_diagnostics(
            output=output,
            max_factor_abs_correlation=max_factor_abs_correlation,
        )
    )
    diagnostics.extend(
        _factor_forward_return_diagnostics(
            output=output,
            forward_return_column=forward_return_column,
        )
    )
    diagnostics.extend(_signal_distribution_diagnostics(output))
    diagnostics.extend(
        _signal_concentration_diagnostics(
            output=output,
            max_signal_share=max_signal_share,
            min_active_signal_share=min_active_signal_share,
        )
    )
    diagnostics.extend(
        _portfolio_target_diagnostics(
            output=output,
            max_gross_exposure=max_gross_exposure,
            max_single_position=max_single_position,
        )
    )
    diagnostics.extend(
        _portfolio_turnover_diagnostics(
            output=output,
            max_turnover=max_turnover,
        )
    )
    diagnostics.extend(_alignment_diagnostics(output))

    return ResearchDiagnosticsReport(diagnostics=tuple(diagnostics))


def run_research_diagnostics(
    output: Mapping[str, Any],
    max_gross_exposure: float = 2.0,
    max_single_position: float = 0.35,
    min_factor_coverage: float = 0.75,
    min_factor_unique_values: int = 2,
    max_factor_abs_correlation: float = 0.95,
    max_signal_share: float = 0.80,
    min_active_signal_share: float = 0.01,
    max_turnover: float = 1.0,
    forward_return_column: str = "forward_return",
) -> ResearchDiagnosticsReport:
    return build_research_diagnostics(
        output=output,
        max_gross_exposure=max_gross_exposure,
        max_single_position=max_single_position,
        min_factor_coverage=min_factor_coverage,
        min_factor_unique_values=min_factor_unique_values,
        max_factor_abs_correlation=max_factor_abs_correlation,
        max_signal_share=max_signal_share,
        min_active_signal_share=min_active_signal_share,
        max_turnover=max_turnover,
        forward_return_column=forward_return_column,
    )
