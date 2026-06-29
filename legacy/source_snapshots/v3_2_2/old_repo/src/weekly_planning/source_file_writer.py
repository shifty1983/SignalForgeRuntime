from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.weekly_planning.source_builder import (
    build_weekly_option_trade_plan_source_from_handoffs,
)


FILE_WRITER_SCHEMA_VERSION = "weekly_option_trade_plan_source_files.v1"
OPERATION_TYPE = "weekly_option_trade_plan_source_file_writer"

DEFAULT_FILENAMES = {
    "weekly_option_trade_plan_source": "weekly_option_trade_plan_source.json",
}


def write_weekly_option_trade_plan_source_file(
    source: Any,
    *,
    output_dir: str | PathLike[str],
    plan_date: str | None = None,
    market_regime: str | Mapping[str, Any] | None = None,
    setup_family: str | Mapping[str, Any] | None = None,
    has_underlying_positions: Sequence[str] | Mapping[str, Any] | None = None,
    portfolio_snapshot: Mapping[str, Any] | None = None,
    max_new_trades: int | None = None,
    max_candidates_per_symbol: int | None = 3,
    minimum_score: float = 2.0,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Write a weekly option trade plan source artifact from option-behavior handoffs.

    This writer bridges option behavior strategy handoffs into the existing weekly
    option trade plan source shape. It writes local files only and does not call
    broker APIs, route orders, submit orders, model fills, perform live execution,
    model slippage, or create maintenance/defense actions.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    source_args = _extract_source_args(
        source,
        plan_date=plan_date,
        market_regime=market_regime,
        setup_family=setup_family,
        has_underlying_positions=has_underlying_positions,
        portfolio_snapshot=portfolio_snapshot,
        max_new_trades=max_new_trades,
        max_candidates_per_symbol=max_candidates_per_symbol,
        minimum_score=minimum_score,
        metadata=metadata,
    )

    weekly_source = build_weekly_option_trade_plan_source_from_handoffs(
        source_args["option_behavior_strategy_handoffs"],
        plan_date=source_args["plan_date"],
        market_regime=source_args["market_regime"],
        setup_family=source_args["setup_family"],
        has_underlying_positions=source_args["has_underlying_positions"],
        portfolio_snapshot=source_args["portfolio_snapshot"],
        max_new_trades=source_args["max_new_trades"],
        max_candidates_per_symbol=source_args["max_candidates_per_symbol"],
        minimum_score=source_args["minimum_score"],
        metadata=source_args["metadata"],
    )

    files = {
        "weekly_option_trade_plan_source": output_path
        / DEFAULT_FILENAMES["weekly_option_trade_plan_source"],
    }
    _write_json(files["weekly_option_trade_plan_source"], weekly_source)

    return {
        "schema_version": FILE_WRITER_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": weekly_source.get("status", "needs_review"),
        "output_dir": str(output_path),
        "files": {key: str(path) for key, path in files.items()},
        "file_summary": _build_file_summary(files),
        "source_summary": _build_source_summary(source_args),
        "weekly_option_trade_plan_source": weekly_source,
        "explicit_exclusions": list(weekly_source.get("excluded", [])),
    }


def _extract_source_args(
    source: Any,
    *,
    plan_date: str | None,
    market_regime: str | Mapping[str, Any] | None,
    setup_family: str | Mapping[str, Any] | None,
    has_underlying_positions: Sequence[str] | Mapping[str, Any] | None,
    portfolio_snapshot: Mapping[str, Any] | None,
    max_new_trades: int | None,
    max_candidates_per_symbol: int | None,
    minimum_score: float,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    source_mapping = source if isinstance(source, Mapping) else {}

    return {
        "option_behavior_strategy_handoffs": _extract_handoffs(source),
        "plan_date": _string_or_none(plan_date)
        or _string_or_none(source_mapping.get("plan_date"))
        or _string_or_none(source_mapping.get("weekend_plan_date"))
        or "",
        "market_regime": _resolve_context_arg(
            explicit=market_regime,
            source_mapping=source_mapping,
            keys=("market_regime", "regime"),
        ),
        "setup_family": _resolve_optional_context_arg(
            explicit=setup_family,
            source_mapping=source_mapping,
            keys=("setup_family", "default_setup_family"),
        ),
        "has_underlying_positions": _resolve_underlying_positions(
            explicit=has_underlying_positions,
            source_mapping=source_mapping,
        ),
        "portfolio_snapshot": _optional_mapping(
            portfolio_snapshot or source_mapping.get("portfolio_snapshot")
        ),
        "max_new_trades": _optional_positive_int(
            max_new_trades,
            fallback=source_mapping.get("max_new_trades"),
        ),
        "max_candidates_per_symbol": _optional_positive_int(
            max_candidates_per_symbol,
            fallback=source_mapping.get("max_candidates_per_symbol"),
        ),
        "minimum_score": _float_or_default(
            source_mapping.get("minimum_score") if minimum_score is None else minimum_score,
            default=2.0,
        ),
        "metadata": _metadata(source_mapping.get("metadata"), override=metadata),
    }


def _extract_handoffs(source: Any) -> Any:
    if isinstance(source, list):
        return source

    if not isinstance(source, Mapping):
        return None

    for key in (
        "option_behavior_strategy_handoffs",
        "option_behavior_handoffs",
        "handoffs",
        "items",
    ):
        if key in source:
            return source.get(key)

    return None


def _resolve_context_arg(
    *,
    explicit: str | Mapping[str, Any] | None,
    source_mapping: Mapping[str, Any],
    keys: Sequence[str],
) -> str | Mapping[str, Any]:
    value = _context_value(explicit=explicit, source_mapping=source_mapping, keys=keys)
    if isinstance(value, Mapping):
        return dict(value)
    return _string_or_none(value) or ""


def _resolve_optional_context_arg(
    *,
    explicit: str | Mapping[str, Any] | None,
    source_mapping: Mapping[str, Any],
    keys: Sequence[str],
) -> str | Mapping[str, Any] | None:
    value = _context_value(explicit=explicit, source_mapping=source_mapping, keys=keys)
    if isinstance(value, Mapping):
        return dict(value)
    return _string_or_none(value)


def _context_value(
    *,
    explicit: Any,
    source_mapping: Mapping[str, Any],
    keys: Sequence[str],
) -> Any:
    if explicit is not None:
        return explicit

    for key in keys:
        value = source_mapping.get(key)
        if isinstance(value, Mapping) or _string_or_none(value):
            return value

    regime_result = source_mapping.get("regime_result")
    if isinstance(regime_result, Mapping):
        value = regime_result.get("regime")
        if _string_or_none(value):
            return value

    return None


def _resolve_underlying_positions(
    *,
    explicit: Sequence[str] | Mapping[str, Any] | None,
    source_mapping: Mapping[str, Any],
) -> Sequence[str] | Mapping[str, Any] | None:
    if explicit is not None:
        return explicit

    for key in ("has_underlying_positions", "underlying_positions"):
        value = source_mapping.get(key)
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return [item for item in value if isinstance(item, str)]

    portfolio_snapshot = source_mapping.get("portfolio_snapshot")
    if isinstance(portfolio_snapshot, Mapping):
        positions = portfolio_snapshot.get("positions")
        derived = _derive_underlying_positions_from_positions(positions)
        if derived:
            return derived

    return None


def _derive_underlying_positions_from_positions(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []

    symbols: list[str] = []
    for position in value:
        if not isinstance(position, Mapping):
            continue
        symbol = _string_or_none(position.get("symbol"))
        if not symbol:
            continue
        quantity = position.get("quantity")
        try:
            if float(quantity) != 0:
                symbols.append(symbol)
        except (TypeError, ValueError):
            symbols.append(symbol)

    return sorted(set(symbols))


def _optional_mapping(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(value)
    return value


def _metadata(value: Any, *, override: Mapping[str, Any] | None) -> Mapping[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(value, Mapping):
        merged.update(value)
    if isinstance(override, Mapping):
        merged.update(override)
    return merged


def _optional_positive_int(value: Any, *, fallback: Any) -> int | None:
    selected = value if value is not None else fallback
    if selected is None:
        return None

    try:
        return int(selected)
    except (TypeError, ValueError):
        return selected


def _float_or_default(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_file_summary(files: Mapping[str, Path]) -> dict[str, Any]:
    return {
        "file_count": len(files),
        "written_files": sorted(files.keys()),
        "missing_files": sorted(
            key for key, path in files.items() if not path.exists()
        ),
        "empty_files": sorted(
            key
            for key, path in files.items()
            if path.exists() and path.stat().st_size == 0
        ),
    }


def _build_source_summary(source_args: Mapping[str, Any]) -> dict[str, Any]:
    handoffs = source_args.get("option_behavior_strategy_handoffs")
    handoff_count = (
        len(handoffs)
        if isinstance(handoffs, Sequence) and not isinstance(handoffs, (str, bytes))
        else 0
    )

    return {
        "plan_date": _string_or_none(source_args.get("plan_date")),
        "handoff_count": handoff_count,
        "has_portfolio_snapshot": isinstance(
            source_args.get("portfolio_snapshot"), Mapping
        ),
        "market_regime_provided": bool(source_args.get("market_regime")),
        "setup_family_provided": bool(source_args.get("setup_family")),
        "max_new_trades": source_args.get("max_new_trades"),
        "max_candidates_per_symbol": source_args.get("max_candidates_per_symbol"),
        "minimum_score": source_args.get("minimum_score"),
    }


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None

