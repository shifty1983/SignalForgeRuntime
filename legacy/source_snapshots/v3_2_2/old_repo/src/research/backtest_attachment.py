from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping

import polars as pl

from src.research.backtest_bridge import run_backtest_from_research_output
from src.research.backtest_report_bridge import (
    BacktestResearchReport,
    build_backtest_research_report,
)


BacktestRunner = Callable[["MinimalBacktestFixture"], Any]


@dataclass(frozen=True)
class MinimalBacktestFixture:
    """Minimal JSON-safe input produced from accepted research output."""

    fixture_id: str
    source_operation_id: str
    candidate_id: str
    weights_by_asset: dict[str, float]
    signals_by_asset: dict[str, float]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BacktestPerformanceSummary:
    """Performance payload persisted through operation records/logs."""

    total_return: float
    max_drawdown: float
    sharpe_ratio: float
    trade_count: int
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "total_return": self.total_return,
            "max_drawdown": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
            "trade_count": self.trade_count,
        }
        data.update(dict(self.extra))
        return data


@dataclass(frozen=True)
class ResearchBacktestHandoffResult:
    """JSON-safe result for research-to-backtest validation."""

    status: str
    source_operation_id: str | None
    fixture_id: str | None
    candidate_id: str | None
    performance: dict[str, Any] | None
    failure_reason: str | None

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_minimal_backtest_fixture(
    logged_operation_output: Mapping[str, Any],
) -> MinimalBacktestFixture:
    """Convert an accepted logged research output into a minimal backtest fixture."""

    operation_id = _extract_operation_id(logged_operation_output)
    candidate_id = _extract_accepted_candidate_id(logged_operation_output)

    if _explicitly_not_accepted(logged_operation_output):
        raise ValueError("no accepted research output exists for backtest handoff")

    if not operation_id:
        raise ValueError("accepted operation output is missing operation_id")

    if not candidate_id:
        raise ValueError("accepted operation output is missing accepted candidate id")

    weights = _extract_weights_by_asset(logged_operation_output)
    signals = _extract_signals_by_asset(logged_operation_output)

    if not weights:
        raise ValueError("accepted operation output cannot produce backtest weights")

    if not signals:
        signals = {asset: 1.0 for asset in weights}

    return MinimalBacktestFixture(
        fixture_id=f"minimal_backtest_fixture__{operation_id}__{candidate_id}",
        source_operation_id=operation_id,
        candidate_id=candidate_id,
        weights_by_asset=weights,
        signals_by_asset=signals,
        metadata={
            "source": "research_operation_output",
            "conversion": "minimal_backtest_fixture",
        },
    )


def run_research_to_backtest_validation(
    logged_operation_output: Mapping[str, Any],
    backtest_runner: BacktestRunner,
) -> ResearchBacktestHandoffResult:
    """Build a fixture, execute a backtest runner, and return a JSON-safe result."""

    source_operation_id = _extract_operation_id(logged_operation_output)

    try:
        fixture = build_minimal_backtest_fixture(logged_operation_output)
    except ValueError as exc:
        return ResearchBacktestHandoffResult(
            status="failed",
            source_operation_id=source_operation_id,
            fixture_id=None,
            candidate_id=None,
            performance=None,
            failure_reason=str(exc),
        )

    try:
        raw_backtest_result = backtest_runner(fixture)
        performance = build_backtest_performance_summary(raw_backtest_result)
    except Exception as exc:
        return ResearchBacktestHandoffResult(
            status="failed",
            source_operation_id=fixture.source_operation_id,
            fixture_id=fixture.fixture_id,
            candidate_id=fixture.candidate_id,
            performance=None,
            failure_reason=f"backtest handoff failed: {exc}",
        )

    return ResearchBacktestHandoffResult(
        status="passed",
        source_operation_id=fixture.source_operation_id,
        fixture_id=fixture.fixture_id,
        candidate_id=fixture.candidate_id,
        performance=performance.to_dict(),
        failure_reason=None,
    )


def build_backtest_performance_summary(
    backtest_result: Any,
) -> BacktestPerformanceSummary:
    """Extract a performance summary from a raw backtest result/report."""

    payload = _result_to_mapping(backtest_result)
    performance_source = _performance_source(payload)
    trade_source = _trade_source(payload)

    total_return = _read_number(
        performance_source,
        "total_return",
        "return",
        "cumulative_return",
    )
    max_drawdown = _read_number(
        performance_source,
        "max_drawdown",
        "maximum_drawdown",
        "drawdown",
    )
    sharpe_ratio = _read_number(
        performance_source,
        "sharpe_ratio",
        "sharpe",
    )
    trade_count = _read_int(
        trade_source,
        "trade_count",
        "trades",
        "number_of_trades",
    )

    missing = []
    if total_return is None:
        missing.append("total_return")
    if max_drawdown is None:
        missing.append("max_drawdown")
    if sharpe_ratio is None:
        missing.append("sharpe_ratio")
    if trade_count is None:
        missing.append("trade_count")

    if missing:
        raise ValueError(
            "backtest result is missing performance fields: "
            + ", ".join(missing)
        )

    extra: dict[str, Any] = {}

    for key in (
        "equity_curve",
        "turnover",
        "rebalance_count",
        "diagnostics",
    ):
        value = _optional_performance_value(
            payload=payload,
            performance_source=performance_source,
            key=key,
        )
        if value is not None:
            extra[key] = _json_safe(value)

    return BacktestPerformanceSummary(
        total_return=float(total_return),
        max_drawdown=float(max_drawdown),
        sharpe_ratio=float(sharpe_ratio),
        trade_count=int(trade_count),
        extra=extra,
    )


def _extract_operation_id(output: Mapping[str, Any]) -> str | None:
    return _read_string(
        output,
        "operation_id",
        "run_id",
        "id",
        "source_operation_id",
    )


def _extract_accepted_candidate_id(output: Mapping[str, Any]) -> str | None:
    direct = _read_string(
        output,
        "accepted_candidate_id",
        "promotion_candidate_id",
        "selected_candidate_id",
        "best_candidate_id",
        "candidate_id",
    )
    if direct:
        return direct

    for key in (
        "model_testing_summary",
        "model_comparison",
        "model_comparison_report",
    ):
        nested = _read_mapping(output, key)
        if nested:
            candidate_id = _read_string(
                nested,
                "promotion_candidate_id",
                "selected_candidate_id",
                "best_candidate_id",
                "candidate_id",
            )
            if candidate_id:
                return candidate_id

    return None


def _explicitly_not_accepted(output: Mapping[str, Any]) -> bool:
    accepted = _read_value(output, "accepted")
    if accepted is False:
        return True

    passed = _read_value(output, "passed")
    if passed is False:
        return True

    promoted = _read_value(output, "evaluation_promoted")
    if promoted is False:
        return True

    status = _read_string(output, "status", "operation_status")
    if status in {"fail", "failed", "rejected"}:
        return True

    decision = _read_string(output, "evaluation_decision", "decision")
    if decision in {"reject", "rejected", "fail", "failed"}:
        return True

    return False


def _extract_weights_by_asset(output: Mapping[str, Any]) -> dict[str, float]:
    for key in (
        "weights_by_asset",
        "portfolio_weights",
        "target_weights",
        "positions",
    ):
        value = _read_mapping(output, key)
        if value:
            return _clean_numeric_mapping(value)

    model_output = _read_mapping(output, "model_output")
    if model_output:
        for key in (
            "weights_by_asset",
            "portfolio_weights",
            "target_weights",
            "positions",
        ):
            value = _read_mapping(model_output, key)
            if value:
                return _clean_numeric_mapping(value)

    scores = _extract_scores_by_asset(output)
    if scores:
        return _normalize_scores_to_weights(scores)

    assets = _extract_assets(output)
    if assets:
        equal_weight = 1.0 / len(assets)
        return {asset: equal_weight for asset in assets}

    return {}


def _extract_signals_by_asset(output: Mapping[str, Any]) -> dict[str, float]:
    for key in (
        "signals_by_asset",
        "signals",
        "scores_by_asset",
        "factor_scores",
    ):
        value = _read_mapping(output, key)
        if value:
            return _clean_numeric_mapping(value)

    model_output = _read_mapping(output, "model_output")
    if model_output:
        for key in (
            "signals_by_asset",
            "signals",
            "scores_by_asset",
            "factor_scores",
        ):
            value = _read_mapping(model_output, key)
            if value:
                return _clean_numeric_mapping(value)

    return {}


def _extract_scores_by_asset(output: Mapping[str, Any]) -> dict[str, float]:
    for key in (
        "scores_by_asset",
        "factor_scores",
        "signals_by_asset",
        "signals",
    ):
        value = _read_mapping(output, key)
        if value:
            return _clean_numeric_mapping(value)

    return {}


def _extract_assets(output: Mapping[str, Any]) -> list[str]:
    for key in ("assets", "symbols", "accepted_assets"):
        value = output.get(key)
        if isinstance(value, list | tuple):
            return [str(asset) for asset in value if str(asset)]

    return []


def _normalize_scores_to_weights(
    scores_by_asset: Mapping[str, float],
) -> dict[str, float]:
    positive_scores = {
        asset: score
        for asset, score in scores_by_asset.items()
        if isinstance(score, int | float) and score > 0
    }

    if not positive_scores:
        return {}

    total = sum(positive_scores.values())

    if total <= 0:
        return {}

    return {
        asset: float(score / total)
        for asset, score in positive_scores.items()
    }


def _clean_numeric_mapping(value: Mapping[str, Any]) -> dict[str, float]:
    clean: dict[str, float] = {}

    for key, raw_value in value.items():
        if raw_value is None:
            continue

        try:
            clean[str(key)] = float(raw_value)
        except (TypeError, ValueError):
            continue

    return clean


def _performance_source(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    report = _read_mapping(payload, "report")
    if report:
        performance = _read_mapping(report, "performance")
        if performance:
            return performance

    performance = _read_mapping(payload, "performance")
    if performance:
        return performance

    return payload


def _trade_source(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    report = _read_mapping(payload, "report")
    if report:
        trade_summary = _read_mapping(report, "trade_summary")
        if trade_summary:
            return trade_summary

    trade_summary = _read_mapping(payload, "trade_summary")
    if trade_summary:
        return trade_summary

    return payload


def _result_to_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        data = to_dict()
        if isinstance(data, Mapping):
            return data
        raise TypeError("backtest_result.to_dict() must return a mapping")

    return dict(getattr(value, "__dict__", {}) or {})


def _read_mapping(value: Any, key: str) -> Mapping[str, Any] | None:
    nested = _read_value(value, key)
    if isinstance(nested, Mapping):
        return nested

    return None


def _read_string(value: Any, *keys: str) -> str | None:
    for key in keys:
        raw_value = _read_value(value, key)
        if raw_value is not None and str(raw_value):
            return str(raw_value)

    return None


def _read_number(value: Any, *keys: str) -> float | None:
    for key in keys:
        raw_value = _read_value(value, key)

        if raw_value is None:
            continue

        try:
            return float(raw_value)
        except (TypeError, ValueError):
            continue

    return None


def _read_int(value: Any, *keys: str) -> int | None:
    for key in keys:
        raw_value = _read_value(value, key)

        if raw_value is None:
            continue

        try:
            return int(raw_value)
        except (TypeError, ValueError):
            continue

    return None


def _read_value(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)

    if hasattr(value, key):
        return getattr(value, key)

    return None


@dataclass(frozen=True)
class ResearchBacktestAttachment:
    """
    Serializable attachment for connecting research evaluation output
    to downstream backtest reporting.
    """

    report: BacktestResearchReport
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """
        Attachment-level pass flag.

        This confirms that a backtest report was successfully produced.
        It does not mean the strategy is profitable or promotable.
        """

        return bool(self.report.nav_series)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "report": self.report.to_dict(),
            "metadata": dict(self.metadata),
        }


def build_research_backtest_attachment(
    research_output: Mapping[str, Any],
    prices: pl.DataFrame,
    initial_cash: float = 100_000.0,
    rebalance_frequency: str = "daily",
    price_column: str = "close",
    date_column: str = "date",
    symbol_column: str = "symbol",
    drift_threshold: float | None = None,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
    metadata: Mapping[str, Any] | None = None,
) -> ResearchBacktestAttachment:
    """
    Build a serializable backtest/report attachment from research output.

    This is designed to be attached to operation results without changing
    the operation lifecycle itself.
    """

    attachment_metadata = dict(metadata or {})

    backtest_result = run_backtest_from_research_output(
        research_output=research_output,
        prices=prices,
        initial_cash=initial_cash,
        rebalance_frequency=rebalance_frequency,
        price_column=price_column,
        date_column=date_column,
        symbol_column=symbol_column,
        drift_threshold=drift_threshold,
    )

    report = build_backtest_research_report(
        result=backtest_result,
        risk_free_rate=risk_free_rate,
        periods_per_year=periods_per_year,
        metadata={
            **attachment_metadata,
            "initial_cash": initial_cash,
            "rebalance_frequency": rebalance_frequency,
            "price_column": price_column,
            "date_column": date_column,
            "symbol_column": symbol_column,
        },
    )

    return ResearchBacktestAttachment(
        report=report,
        metadata=attachment_metadata,
    )
    
def _optional_performance_value(
    *,
    payload: Mapping[str, Any],
    performance_source: Mapping[str, Any],
    key: str,
) -> Any:
    value = _read_value(performance_source, key)

    if value is not None:
        return value

    return _read_value(payload, key)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(nested) for key, nested in value.items()}

    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        data = to_dict()
        return _json_safe(data)

    return value
