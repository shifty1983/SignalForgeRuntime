from __future__ import annotations

import polars as pl
from collections.abc import Mapping, Sequence
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS
from src.signalforge.engines.regime.classifier import combine_regimes, simplified_regime_label
from src.signalforge.engines.regime.credit import classify_credit, classify_credit_level
from src.signalforge.engines.regime.diagnostics import (
    missing_regime_rows,
    regime_distribution,
    validate_regime_labels,
)
from src.signalforge.engines.regime.fred_source_builder import build_signalforge_fred_regime_source
from src.signalforge.engines.regime.growth import classify_growth
from src.signalforge.engines.regime.inflation import classify_inflation
from src.signalforge.engines.regime.liquidity import classify_liquidity
from src.signalforge.engines.regime.options_policy import build_regime_options_policy_from_row
from src.signalforge.engines.regime.rates import classify_rates
from src.signalforge.engines.regime.yield_curve import classify_yield_curve, yield_curve_direction
from src.signalforge.engines.regime.risk_environment import classify_risk_environment
from src.signalforge.engines.regime.scoring import regime_risk_bias, score_regime


FRED_REGIME_PIPELINE_SCHEMA_VERSION = "signalforge_fred_regime_pipeline.v1"


CLASSIFICATION_METRICS = {
    "growth_regime": "growth_metric",
    "inflation_regime": "inflation_metric",
    "rates_regime": "rates_metric",
    "liquidity_regime": "liquidity_metric",
    "risk_environment": "risk_metric",
    "credit_regime": "credit_metric",
    "yield_curve_regime": "yield_curve_spread",
}


def build_signalforge_fred_regime_pipeline(
    source: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    *,
    periods: int = 3,
    inflation_yoy_periods: int = 12,
) -> dict[str, Any]:
    """Run the FRED macro source builder through the existing regime logic."""

    source_artifact = build_signalforge_fred_regime_source(
        source,
        periods=periods,
        inflation_yoy_periods=inflation_yoy_periods,
    )

    if source_artifact.get("status") == "blocked":
        return _blocked_pipeline(source_artifact)

    regime_rows = source_artifact.get("regime_rows")
    if not isinstance(regime_rows, Sequence) or isinstance(regime_rows, (str, bytes, bytearray)):
        return _blocked_pipeline(source_artifact, reason="source artifact regime_rows must be a sequence")

    if not regime_rows:
        return _blocked_pipeline(source_artifact, reason="source artifact regime_rows are empty")

    df = pl.DataFrame([dict(row) for row in regime_rows if isinstance(row, Mapping)], infer_schema_length=None)
    if df.is_empty():
        return _blocked_pipeline(source_artifact, reason="source artifact regime_rows contain no mappings")

    try:
        classified_df = _classify(df)
    except ValueError as error:
        return _blocked_pipeline(source_artifact, reason=str(error))

    invalid_labels = validate_regime_labels(classified_df)
    distribution = regime_distribution(classified_df).to_dicts()
    missing_rows = missing_regime_rows(classified_df).to_dicts()
    output_rows = classified_df.to_dicts()
    latest_ready_row = _latest_ready_row(output_rows)

    warnings = list(_warning_reasons(source_artifact))
    if invalid_labels:
        warnings.append(f"invalid regime labels: {invalid_labels}")
    if latest_ready_row is None:
        warnings.append("no complete latest regime row is available after macro lookbacks")

    latest_policy = (
        build_regime_options_policy_from_row(latest_ready_row)
        if latest_ready_row is not None
        else None
    )

    status = "ready" if latest_ready_row is not None and not invalid_labels and not warnings else "needs_review"

    return {
        "artifact_type": "signalforge_fred_regime_pipeline",
        "schema_version": FRED_REGIME_PIPELINE_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "source_artifact_summary": _source_summary(source_artifact),
        "periods": periods,
        "inflation_yoy_periods": inflation_yoy_periods,
        "regime_rows": output_rows,
        "regime_row_count": len(output_rows),
        "latest_date": output_rows[-1].get("date") if output_rows else None,
        "latest_ready_regime_row": latest_ready_row,
        "latest_regime_options_policy": latest_policy,
        "invalid_regime_labels": invalid_labels,
        "regime_distribution": distribution,
        "missing_regime_row_count": len(missing_rows),
        "missing_regime_rows": missing_rows,
        "warnings": _dedupe(warnings),
        "blocked_reasons": [],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _classify(df: pl.DataFrame) -> pl.DataFrame:
    result = df.sort("date")
    result = classify_growth(result, column="growth_metric")
    result = classify_inflation(result, column="inflation_metric")
    result = classify_rates(result, column="rates_metric")
    result = classify_liquidity(result, column="liquidity_metric")
    result = classify_risk_environment(result, column="risk_metric")
    result = classify_credit(result, column="credit_metric")
    result = classify_credit_level(result, column="credit_spread_level")
    result = yield_curve_direction(result, column="yield_curve_spread")
    result = classify_yield_curve(result)
    result = _null_out_incomplete_classifications(result)
    result = combine_regimes(result)
    result = simplified_regime_label(result)
    result = result.with_columns(
        pl.when(_complete_classification_expr())
        .then(pl.col("regime_label"))
        .otherwise(None)
        .alias("regime_label")
    )
    result = score_regime(result)
    result = regime_risk_bias(result)
    return result


def _null_out_incomplete_classifications(df: pl.DataFrame) -> pl.DataFrame:
    expressions = []
    for output_col, metric_col in CLASSIFICATION_METRICS.items():
        expressions.append(
            pl.when(pl.col(metric_col).is_null())
            .then(None)
            .otherwise(pl.col(output_col))
            .alias(output_col)
        )
    return df.with_columns(expressions)


def _complete_classification_expr() -> pl.Expr:
    expr = pl.lit(True)
    for column in CLASSIFICATION_METRICS:
        expr = expr & pl.col(column).is_not_null()
    return expr


def _latest_ready_row(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    for row in reversed(rows):
        if row.get("regime_label"):
            return dict(row)
    return None


def _blocked_pipeline(source_artifact: Mapping[str, Any], reason: str | None = None) -> dict[str, Any]:
    blocked_reasons = []
    for item in _as_list(source_artifact.get("blocker_items")):
        if isinstance(item, Mapping):
            blocked_reasons.append(str(item.get("reason", item)))
        else:
            blocked_reasons.append(str(item))
    if reason:
        blocked_reasons.append(reason)

    return {
        "artifact_type": "signalforge_fred_regime_pipeline",
        "schema_version": FRED_REGIME_PIPELINE_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "source_artifact_summary": _source_summary(source_artifact),
        "regime_rows": [],
        "regime_row_count": 0,
        "latest_ready_regime_row": None,
        "latest_regime_options_policy": None,
        "invalid_regime_labels": [],
        "regime_distribution": [],
        "missing_regime_row_count": 0,
        "missing_regime_rows": [],
        "warnings": [],
        "blocked_reasons": _dedupe(blocked_reasons),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _source_summary(source_artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": source_artifact.get("artifact_type"),
        "status": source_artifact.get("status"),
        "available_series": list(_as_list(source_artifact.get("available_series"))),
        "regime_row_count": source_artifact.get("regime_row_count", 0),
        "latest_date": source_artifact.get("latest_date"),
        "warning_count": len(_as_list(source_artifact.get("warning_items"))),
        "blocker_count": len(_as_list(source_artifact.get("blocker_items"))),
    }


def _warning_reasons(source_artifact: Mapping[str, Any]) -> list[str]:
    output = []
    for item in _as_list(source_artifact.get("warning_items")):
        if isinstance(item, Mapping):
            reason = item.get("reason")
            if reason:
                output.append(str(reason))
        elif item:
            output.append(str(item))
    return output


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _dedupe(values: Sequence[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output




