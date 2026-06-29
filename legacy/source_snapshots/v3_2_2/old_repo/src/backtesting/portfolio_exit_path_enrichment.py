from __future__ import annotations

import json
import math
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class PortfolioExitPathEnrichmentResult:
    rows: list[dict[str, Any]]
    summary: dict[str, Any]


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", errors="ignore") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _get_by_path(payload: Mapping[str, Any] | None, path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def _coerce_float(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
    else:
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        had_percent = "%" in text
        text = text.replace("%", "")
        try:
            parsed = float(text)
        except ValueError:
            return None
        if had_percent:
            parsed /= 100.0
    if not math.isfinite(parsed):
        return None
    return parsed


def _coerce_int(value: Any) -> int | None:
    parsed = _coerce_float(value)
    if parsed is None:
        return None
    return int(parsed)


def _as_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = str(value).strip()
    if not text:
        return None
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    for fmt in ("%Y%m%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _date_diff_days(start: Any, end: Any) -> int | None:
    start_text = _as_date(start)
    end_text = _as_date(end)
    if not start_text or not end_text:
        return None
    try:
        return (datetime.strptime(end_text, "%Y-%m-%d") - datetime.strptime(start_text, "%Y-%m-%d")).days
    except ValueError:
        return None


def _round_return(value: Any) -> str:
    parsed = _coerce_float(value)
    if parsed is None:
        return ""
    return f"{parsed:.10f}"


def _normal_text(value: Any) -> str:
    return str(value or "").strip()


def _match_key(row: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        _as_date(_first_present(row.get("decision_date"), row.get("date"), row.get("entry_date"))) or "",
        _normal_text(_first_present(row.get("symbol"), row.get("underlying_symbol"))),
        _normal_text(_first_present(row.get("selected_strategy"), row.get("strategy"))),
        _round_return(_first_present(row.get("realized_return"), row.get("strategy_adjusted_return"), row.get("strategy_return"))),
        _as_date(_first_present(row.get("outcome_availability_date"), row.get("portfolio_realization_date"), row.get("selected_outcome_date"), row.get("outcome_date"))) or "",
    )


def _fallback_match_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        _as_date(_first_present(row.get("decision_date"), row.get("date"), row.get("entry_date"))) or "",
        _normal_text(_first_present(row.get("symbol"), row.get("underlying_symbol"))),
        _normal_text(_first_present(row.get("selected_strategy"), row.get("strategy"))),
    )


def _index_selected_rows(rows: list[dict[str, Any]]) -> tuple[dict[tuple[str, str, str, str, str], deque[dict[str, Any]]], dict[tuple[str, str, str], deque[dict[str, Any]]]]:
    full: dict[tuple[str, str, str, str, str], deque[dict[str, Any]]] = defaultdict(deque)
    fallback: dict[tuple[str, str, str], deque[dict[str, Any]]] = defaultdict(deque)
    for row in rows:
        if row.get("is_selected_trade") is False:
            continue
        if row.get("is_portfolio_reconstructable") is False and str(row.get("outcome_state") or "") != "complete":
            continue
        full[_match_key(row)].append(row)
        fallback[_fallback_match_key(row)].append(row)
    return full, fallback


def _pop_selected_match(
    position_row: Mapping[str, Any],
    full_index: dict[tuple[str, str, str, str, str], deque[dict[str, Any]]],
    fallback_index: dict[tuple[str, str, str], deque[dict[str, Any]]],
) -> dict[str, Any] | None:
    full_key = _match_key(position_row)
    bucket = full_index.get(full_key)
    if bucket:
        return bucket.popleft()
    fallback_key = _fallback_match_key(position_row)
    bucket = fallback_index.get(fallback_key)
    if bucket:
        return bucket.popleft()
    return None


def _source_candidate(selected_row: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not selected_row:
        return {}
    source = selected_row.get("source_candidate")
    if isinstance(source, Mapping):
        return source
    return {}


def _list_or_empty(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _leg_mid(leg: Mapping[str, Any], *, prefix: str = "") -> float | None:
    keys = (
        f"{prefix}_mid_price" if prefix else "mid_price",
        f"{prefix}_mid" if prefix else "mid",
        "mid_price",
        "mid",
        "entry_mid",
        "exit_mid",
        "exit_mid_price",
    )
    for key in keys:
        value = _coerce_float(leg.get(key))
        if value is not None:
            return value
    return None


def _leg_quantity(leg: Mapping[str, Any]) -> int:
    return _coerce_int(_first_present(leg.get("quantity"), leg.get("contract_count"), leg.get("contract_quantity"))) or 1


def _leg_action(leg: Mapping[str, Any]) -> str | None:
    action = str(_first_present(leg.get("action"), leg.get("side"), leg.get("direction"), "") or "").lower()
    if action in {"buy", "bought", "long", "debit"}:
        return "buy"
    if action in {"sell", "sold", "short", "credit"}:
        return "sell"
    return None


def _leg_value(leg: Mapping[str, Any], *, prefix: str = "") -> float | None:
    direct_keys = (
        f"{prefix}_leg_value" if prefix else "leg_value",
        "exit_leg_value" if prefix == "exit" else "entry_leg_value",
    )
    for key in direct_keys:
        direct = _coerce_float(leg.get(key))
        if direct is not None:
            return direct
    mid = _leg_mid(leg, prefix=prefix)
    if mid is None:
        return None
    quantity = _leg_quantity(leg)
    action = _leg_action(leg)
    if action == "buy":
        return mid * quantity
    if action == "sell":
        return -mid * quantity
    return None


def _net_leg_value(legs: list[Any], *, prefix: str = "") -> float | None:
    values: list[float] = []
    for leg in legs:
        if not isinstance(leg, Mapping):
            continue
        value = _leg_value(leg, prefix=prefix)
        if value is None:
            return None
        values.append(value)
    if not values:
        return None
    return sum(values)


def _first_leg_expiration_or_dte(*leg_lists: Any) -> tuple[str | None, int | None]:
    expiration: str | None = None
    dte: int | None = None
    for legs in leg_lists:
        for leg in _list_or_empty(legs):
            if not isinstance(leg, Mapping):
                continue
            expiration = expiration or _as_date(_first_present(leg.get("expiration"), leg.get("expiry"), leg.get("expiration_date")))
            dte = dte if dte is not None else _coerce_int(_first_present(leg.get("dte"), leg.get("days_to_expiration"), leg.get("entry_dte"), leg.get("exit_dte")))
            if expiration and dte is not None:
                return expiration, dte
    return expiration, dte


def _has_nonempty(row: Mapping[str, Any], keys: tuple[str, ...]) -> bool:
    return any(row.get(key) not in (None, "", [], {}) for key in keys)


def _extract_exit_path_row(
    *,
    position_row: Mapping[str, Any],
    selected_row: Mapping[str, Any] | None,
    row_index: int,
) -> dict[str, Any]:
    source = _source_candidate(selected_row)

    entry_date = _as_date(
        _first_present(
            position_row.get("decision_date"),
            position_row.get("entry_date"),
            selected_row.get("decision_date") if selected_row else None,
            selected_row.get("date") if selected_row else None,
            source.get("decision_date"),
            source.get("date"),
        )
    )
    final_exit_date = _as_date(
        _first_present(
            position_row.get("portfolio_realization_date"),
            position_row.get("outcome_availability_date"),
            position_row.get("selected_outcome_date"),
            position_row.get("outcome_date"),
            selected_row.get("selected_outcome_date") if selected_row else None,
            selected_row.get("selected_outcome_availability_date") if selected_row else None,
            selected_row.get("outcome_date") if selected_row else None,
            source.get("outcome_date"),
            source.get("outcome_availability_date"),
        )
    )
    target_exit_date = _as_date(
        _first_present(
            position_row.get("target_exit_date"),
            selected_row.get("selected_target_exit_date") if selected_row else None,
            selected_row.get("target_exit_date") if selected_row else None,
            source.get("target_exit_date"),
        )
    )

    entry_legs = _list_or_empty(
        _first_present(
            position_row.get("entry_legs"),
            position_row.get("selected_entry_legs"),
            position_row.get("selected_legs"),
            selected_row.get("entry_legs") if selected_row else None,
            selected_row.get("selected_entry_legs") if selected_row else None,
            selected_row.get("selected_legs") if selected_row else None,
            source.get("selected_legs"),
            source.get("entry_legs"),
        )
    )
    exit_legs = _list_or_empty(
        _first_present(
            position_row.get("exit_legs"),
            position_row.get("selected_exit_legs"),
            selected_row.get("exit_legs") if selected_row else None,
            selected_row.get("selected_exit_legs") if selected_row else None,
            source.get("exit_legs"),
        )
    )

    entry_strategy_value = _coerce_float(
        _first_present(
            position_row.get("entry_net_mid_debit"),
            selected_row.get("selected_entry_net_mid_debit") if selected_row else None,
            selected_row.get("entry_net_mid_debit") if selected_row else None,
            source.get("entry_net_mid_debit"),
        )
    )
    if entry_strategy_value is None:
        entry_strategy_value = _net_leg_value(entry_legs, prefix="entry")

    exit_strategy_value = _coerce_float(
        _first_present(
            position_row.get("exit_strategy_value"),
            selected_row.get("selected_exit_strategy_value") if selected_row else None,
            selected_row.get("exit_strategy_value") if selected_row else None,
            source.get("exit_strategy_value"),
        )
    )
    if exit_strategy_value is None:
        exit_strategy_value = _net_leg_value(exit_legs, prefix="exit")

    realized_return = _coerce_float(
        _first_present(
            position_row.get("realized_return"),
            selected_row.get("realized_return") if selected_row else None,
            source.get("strategy_adjusted_return"),
            source.get("strategy_return"),
        )
    )
    realized_pnl = _coerce_float(
        _first_present(
            position_row.get("realized_pnl_dollars"),
            selected_row.get("selected_strategy_pnl") if selected_row else None,
            source.get("strategy_pnl"),
        )
    )
    risk_capital = _coerce_float(
        _first_present(
            position_row.get("position_risk_dollars"),
            selected_row.get("selected_risk_capital") if selected_row else None,
            source.get("risk_capital"),
        )
    )

    expiration, dte = _first_leg_expiration_or_dte(entry_legs, exit_legs)
    holding_period_days = _coerce_int(
        _first_present(
            position_row.get("holding_period_days"),
            selected_row.get("holding_period_days") if selected_row else None,
            source.get("holding_period_days"),
        )
    )
    if holding_period_days is None:
        holding_period_days = _date_diff_days(entry_date, final_exit_date)

    quote_path = _first_present(
        position_row.get("quote_path"),
        position_row.get("daily_quote_path"),
        position_row.get("holding_period_quote_path"),
        selected_row.get("quote_path") if selected_row else None,
        selected_row.get("daily_quote_path") if selected_row else None,
        source.get("quote_path"),
        source.get("daily_quote_path"),
    )
    greek_path = _first_present(
        position_row.get("greek_path"),
        position_row.get("daily_greek_path"),
        selected_row.get("greek_path") if selected_row else None,
        source.get("greek_path"),
    )
    behavior_path = _first_present(
        position_row.get("behavior_path"),
        selected_row.get("behavior_path") if selected_row else None,
        source.get("behavior_path"),
    )
    mae = _coerce_float(_first_present(position_row.get("mae"), position_row.get("max_adverse_excursion"), selected_row.get("mae") if selected_row else None, source.get("mae"), source.get("max_adverse_excursion")))
    mfe = _coerce_float(_first_present(position_row.get("mfe"), position_row.get("max_favorable_excursion"), selected_row.get("mfe") if selected_row else None, source.get("mfe"), source.get("max_favorable_excursion")))

    missing_components: list[str] = []
    if not entry_date:
        missing_components.append("missing_entry_date")
    if not final_exit_date:
        missing_components.append("missing_final_exit_date")
    if not entry_legs:
        missing_components.append("missing_entry_legs")
    if not exit_legs:
        missing_components.append("missing_exit_legs")
    if realized_return is None and realized_pnl is None:
        missing_components.append("missing_final_return_or_pnl")
    if quote_path in (None, "", [], {}):
        missing_components.append("missing_daily_or_intraperiod_quote_path")
    if mae is None or mfe is None:
        missing_components.append("missing_mae_mfe")
    if greek_path in (None, "", [], {}):
        missing_components.append("missing_greek_path")
    if behavior_path in (None, "", [], {}):
        missing_components.append("missing_behavior_path")

    has_final_outcome_path = bool(entry_date and final_exit_date and entry_legs and exit_legs and (realized_return is not None or realized_pnl is not None))
    has_quote_path = quote_path not in (None, "", [], {})
    has_mae_mfe = mae is not None and mfe is not None

    if has_quote_path:
        path_state = "path_ready"
    elif has_mae_mfe:
        path_state = "mae_mfe_ready"
    elif has_final_outcome_path:
        path_state = "final_outcome_path_enriched"
    else:
        path_state = "partial_path_enrichment"

    path_points = []
    if entry_date:
        path_points.append(
            {
                "path_point_type": "entry",
                "date": entry_date,
                "strategy_value": entry_strategy_value,
                "legs": entry_legs,
                "source": "entry_leg_snapshot",
            }
        )
    if final_exit_date:
        path_points.append(
            {
                "path_point_type": "final_exit",
                "date": final_exit_date,
                "target_exit_date": target_exit_date,
                "strategy_value": exit_strategy_value,
                "realized_return": realized_return,
                "realized_pnl_dollars": realized_pnl,
                "legs": exit_legs,
                "source": "final_exit_leg_snapshot",
            }
        )

    selected_outcome_id = selected_row.get("selected_strategy_outcome_id") if selected_row else None
    source_candidate_id = _first_present(
        selected_row.get("selected_candidate_id") if selected_row else None,
        source.get("quote_outcome_id"),
        source.get("leg_selection_id"),
    )

    return {
        "adapter_type": "portfolio_exit_path_enrichment_builder",
        "artifact_type": "signalforge_portfolio_exit_path_enrichment_row",
        "contract": "portfolio_exit_path_enrichment",
        "exit_path_enrichment_id": f"portfolio_exit_path_enrichment_{row_index:08d}",
        "position_sizing_id": position_row.get("position_sizing_id"),
        "sequence_id": position_row.get("sequence_id"),
        "sequence_index": position_row.get("sequence_index"),
        "trade_key": position_row.get("trade_key"),
        "selected_strategy_outcome_id": selected_outcome_id,
        "source_candidate_id": source_candidate_id,
        "sizing_state": position_row.get("sizing_state"),
        "path_enrichment_state": path_state,
        "has_final_outcome_path": has_final_outcome_path,
        "has_mae_mfe": has_mae_mfe,
        "has_daily_or_intraperiod_quote_path": has_quote_path,
        "has_greek_path": greek_path not in (None, "", [], {}),
        "has_behavior_path": behavior_path not in (None, "", [], {}),
        "can_support_final_outcome_exit_approximations": has_final_outcome_path,
        "can_support_mae_mfe_profit_target_loss_stop_approximations": has_mae_mfe,
        "can_support_true_path_dependent_exits": has_quote_path,
        "entry_date": entry_date,
        "target_exit_date": target_exit_date,
        "final_exit_date": final_exit_date,
        "portfolio_realization_date": _as_date(position_row.get("portfolio_realization_date")),
        "holding_period_days": holding_period_days,
        "expiration": expiration,
        "dte": dte,
        "symbol": position_row.get("symbol"),
        "selected_strategy": position_row.get("selected_strategy"),
        "construction_quality": _first_present(position_row.get("selected_construction_quality"), position_row.get("construction_quality"), selected_row.get("selected_construction_quality") if selected_row else None),
        "selected_expectancy_state": position_row.get("selected_expectancy_state"),
        "selected_expectancy_score": position_row.get("selected_expectancy_score"),
        "selected_expectancy_sample_count": position_row.get("selected_expectancy_sample_count"),
        "entry_strategy_value": entry_strategy_value,
        "exit_strategy_value": exit_strategy_value,
        "realized_return": realized_return,
        "realized_pnl_dollars": realized_pnl,
        "risk_capital_or_position_risk_dollars": risk_capital,
        "position_risk_dollars": position_row.get("position_risk_dollars"),
        "entry_legs": entry_legs,
        "exit_legs": exit_legs,
        "path_points": path_points,
        "mae": mae,
        "mfe": mfe,
        "quote_path": quote_path if has_quote_path else None,
        "greek_path": greek_path if greek_path not in (None, "", [], {}) else None,
        "behavior_path": behavior_path if behavior_path not in (None, "", [], {}) else None,
        "missing_path_components": missing_components,
        "path_evidence_policy": {
            "version": "portfolio_exit_path_enrichment_v1",
            "description": "Creates a final-outcome path scaffold from entry legs and final exit legs. It does not synthesize daily quote paths, MAE/MFE, Greeks, or behavior paths when source evidence is absent.",
            "realized_outcome_based_exit_optimization_allowed": False,
        },
    }


def _coverage(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    denominator = len(rows)
    if denominator == 0:
        return {
            "entry_date_coverage": None,
            "final_exit_date_coverage": None,
            "entry_leg_coverage": None,
            "exit_leg_coverage": None,
            "final_return_or_pnl_coverage": None,
            "final_outcome_path_coverage": None,
            "mae_mfe_coverage": None,
            "daily_or_intraperiod_quote_path_coverage": None,
            "greek_path_coverage": None,
            "behavior_path_coverage": None,
            "dte_or_expiration_coverage": None,
        }

    def pct(predicate: Any) -> float:
        return sum(1 for row in rows if predicate(row)) / denominator

    return {
        "entry_date_coverage": pct(lambda row: row.get("entry_date") not in (None, "")),
        "final_exit_date_coverage": pct(lambda row: row.get("final_exit_date") not in (None, "")),
        "entry_leg_coverage": pct(lambda row: row.get("entry_legs") not in (None, "", [], {})),
        "exit_leg_coverage": pct(lambda row: row.get("exit_legs") not in (None, "", [], {})),
        "final_return_or_pnl_coverage": pct(lambda row: row.get("realized_return") is not None or row.get("realized_pnl_dollars") is not None),
        "final_outcome_path_coverage": pct(lambda row: bool(row.get("has_final_outcome_path"))),
        "mae_mfe_coverage": pct(lambda row: bool(row.get("has_mae_mfe"))),
        "daily_or_intraperiod_quote_path_coverage": pct(lambda row: bool(row.get("has_daily_or_intraperiod_quote_path"))),
        "greek_path_coverage": pct(lambda row: bool(row.get("has_greek_path"))),
        "behavior_path_coverage": pct(lambda row: bool(row.get("has_behavior_path"))),
        "dte_or_expiration_coverage": pct(lambda row: row.get("dte") is not None or row.get("expiration") not in (None, "")),
    }


def _capabilities(coverage: Mapping[str, Any]) -> dict[str, bool]:
    final_ready = (coverage.get("final_outcome_path_coverage") or 0.0) >= 0.95
    mae_ready = (coverage.get("mae_mfe_coverage") or 0.0) >= 0.95
    quote_path_ready = (coverage.get("daily_or_intraperiod_quote_path_coverage") or 0.0) >= 0.95
    dte_ready = (coverage.get("dte_or_expiration_coverage") or 0.0) >= 0.95
    greek_ready = (coverage.get("greek_path_coverage") or 0.0) >= 0.95
    behavior_ready = (coverage.get("behavior_path_coverage") or 0.0) >= 0.95

    return {
        "can_test_fixed_horizon_or_close_on_outcome_date": final_ready,
        "can_test_final_outcome_exit_approximations": final_ready,
        "can_test_quote_native_exit_costs": final_ready,
        "can_test_dte_exit_rules": dte_ready,
        "can_test_mae_mfe_profit_target_loss_stop_approximations": mae_ready,
        "can_test_true_path_dependent_exits": quote_path_ready,
        "can_test_greek_triggered_exits": quote_path_ready and greek_ready,
        "can_test_behavior_triggered_exits": quote_path_ready and behavior_ready,
    }


def build_portfolio_exit_path_enrichment(
    *,
    position_sizing_rows: list[dict[str, Any]],
    selected_strategy_outcome_rows: list[dict[str, Any]] | None = None,
    output_dir: str | Path,
    scope: str = "sized",
    minimum_final_outcome_path_coverage: float = 0.95,
) -> PortfolioExitPathEnrichmentResult:
    output_dir = Path(output_dir)
    selected_strategy_outcome_rows = selected_strategy_outcome_rows or []

    if scope not in {"sized", "all"}:
        raise ValueError("scope must be 'sized' or 'all'")

    full_index, fallback_index = _index_selected_rows(selected_strategy_outcome_rows)

    if scope == "sized":
        scoped_position_rows = [row for row in position_sizing_rows if row.get("sizing_state") == "sized"]
    else:
        scoped_position_rows = list(position_sizing_rows)

    enriched_rows: list[dict[str, Any]] = []
    selected_match_count = 0

    for row_index, position_row in enumerate(scoped_position_rows, start=1):
        selected_match = _pop_selected_match(position_row, full_index, fallback_index)
        if selected_match is not None:
            selected_match_count += 1
        enriched_rows.append(
            _extract_exit_path_row(
                position_row=position_row,
                selected_row=selected_match,
                row_index=row_index,
            )
        )

    coverage = _coverage(enriched_rows)
    capabilities = _capabilities(coverage)
    state_counts = Counter(str(row.get("path_enrichment_state") or "missing") for row in enriched_rows)
    missing_component_counts: Counter[str] = Counter()
    strategy_counts: Counter[str] = Counter(str(row.get("selected_strategy") or "UNKNOWN") for row in enriched_rows)
    symbol_counts: Counter[str] = Counter(str(row.get("symbol") or "UNKNOWN") for row in enriched_rows)

    for row in enriched_rows:
        missing_component_counts.update(row.get("missing_path_components") or [])

    blockers: list[str] = []
    warnings: list[str] = []

    if not position_sizing_rows:
        blockers.append("no_position_sizing_rows")
    if not scoped_position_rows:
        blockers.append("no_scoped_position_sizing_rows")
    if not enriched_rows:
        blockers.append("no_exit_path_enrichment_rows")

    final_path_coverage = coverage.get("final_outcome_path_coverage")
    if final_path_coverage is None or final_path_coverage < minimum_final_outcome_path_coverage:
        blockers.append("final_outcome_path_coverage_below_minimum")

    if (coverage.get("daily_or_intraperiod_quote_path_coverage") or 0.0) < 0.95:
        warnings.append("daily_or_intraperiod_quote_path_not_available_for_true_path_dependent_exits")
    if (coverage.get("mae_mfe_coverage") or 0.0) < 0.95:
        warnings.append("mae_mfe_not_available_for_profit_target_stop_loss_approximations")
    if selected_strategy_outcome_rows and selected_match_count < len(scoped_position_rows):
        warnings.append("some_position_rows_could_not_be_matched_to_selected_strategy_outcome_rows")

    if capabilities["can_test_true_path_dependent_exits"]:
        exit_policy_readiness_state = "path_ready"
    elif capabilities["can_test_mae_mfe_profit_target_loss_stop_approximations"]:
        exit_policy_readiness_state = "mae_mfe_ready"
    elif capabilities["can_test_final_outcome_exit_approximations"]:
        exit_policy_readiness_state = "final_outcome_only"
    else:
        exit_policy_readiness_state = "needs_enrichment"

    summary = {
        "adapter_type": "portfolio_exit_path_enrichment_builder",
        "artifact_type": "signalforge_portfolio_exit_path_enrichment",
        "contract": "portfolio_exit_path_enrichment",
        "is_ready": len(blockers) == 0,
        "readiness_state": "pass" if len(blockers) == 0 else "blocked",
        "exit_policy_readiness_state": exit_policy_readiness_state,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "scope": scope,
        "input_position_sizing_row_count": len(position_sizing_rows),
        "scoped_position_sizing_row_count": len(scoped_position_rows),
        "input_selected_strategy_outcome_row_count": len(selected_strategy_outcome_rows),
        "selected_strategy_outcome_match_count": selected_match_count,
        "selected_strategy_outcome_match_rate": selected_match_count / len(scoped_position_rows) if scoped_position_rows else None,
        "enriched_row_count": len(enriched_rows),
        "path_enrichment_state_counts": dict(sorted(state_counts.items())),
        "coverage": coverage,
        "exit_policy_capabilities": capabilities,
        "missing_path_component_counts": dict(sorted(missing_component_counts.items())),
        "top_strategy_counts": dict(strategy_counts.most_common(20)),
        "top_symbol_counts": dict(symbol_counts.most_common(20)),
        "minimum_final_outcome_path_coverage": minimum_final_outcome_path_coverage,
        "explicit_exclusions": [
            "strategy_reselection",
            "expectancy_rebuild",
            "entry_rule_optimization",
            "exit_rule_optimization",
            "defensive_adjustment_simulation",
            "synthetic_daily_quote_path_generation",
            "synthetic_mae_mfe_generation",
            "broker_order_routing",
            "full_margin_model",
            "portfolio_margin",
            "intraday_order_book_queue_modeling",
        ],
        "next_build_recommendations": _next_build_recommendations(exit_policy_readiness_state),
        "paths": {
            "rows_path": str(output_dir / "signalforge_portfolio_exit_path_enrichment_rows.jsonl"),
            "summary_path": str(output_dir / "signalforge_portfolio_exit_path_enrichment_summary.json"),
            "gap_report_path": str(output_dir / "signalforge_portfolio_exit_path_enrichment_gap_report.json"),
        },
    }

    gap_report = {
        "adapter_type": "portfolio_exit_path_enrichment_builder",
        "artifact_type": "signalforge_portfolio_exit_path_enrichment_gap_report",
        "contract": "portfolio_exit_path_enrichment_gap_report",
        "exit_policy_readiness_state": exit_policy_readiness_state,
        "coverage": coverage,
        "missing_path_component_counts": dict(sorted(missing_component_counts.items())),
        "required_for_true_exit_policy_sensitivity": {
            "daily_or_intraperiod_quote_path": "required for true profit targets, stop losses, trailing exits, and defensive adjustment timing",
            "mae_mfe": "required for non-path profit-target/stop-loss approximations",
            "greek_path": "required for delta/theta/vega triggered exits",
            "behavior_path": "required for regime, asset behavior, or option behavior triggered exits",
        },
        "safe_next_tests_without_more_data": [
            "fixed_horizon_or_close_on_outcome_date",
            "final_outcome_grouping_by_dte_strategy_symbol_regime",
            "quote_native_final_exit_cost_stress",
        ] if capabilities["can_test_final_outcome_exit_approximations"] else [],
        "unsafe_next_tests_until_more_data": [
            "real_profit_target_exit_optimization",
            "real_stop_loss_exit_optimization",
            "delta_triggered_exit_optimization",
            "theta_decay_exit_optimization",
            "vega_or_iv_exit_optimization",
            "behavior_or_regime_flip_defensive_exit_optimization",
        ],
    }

    write_jsonl(output_dir / "signalforge_portfolio_exit_path_enrichment_rows.jsonl", enriched_rows)
    write_json(output_dir / "signalforge_portfolio_exit_path_enrichment_summary.json", summary)
    write_json(output_dir / "signalforge_portfolio_exit_path_enrichment_gap_report.json", gap_report)

    return PortfolioExitPathEnrichmentResult(rows=enriched_rows, summary=summary)


def _next_build_recommendations(exit_policy_readiness_state: str) -> list[str]:
    if exit_policy_readiness_state == "path_ready":
        return [
            "Build portfolio_exit_policy_sensitivity with true path-dependent profit target, stop loss, DTE, and defensive exit rules.",
            "Keep all exit policy tests decision-time/path-time safe; do not rank exits using final realized outcomes.",
        ]
    if exit_policy_readiness_state == "mae_mfe_ready":
        return [
            "Build MAE/MFE-labeled exit approximation sensitivity for profit targets and stop losses.",
            "Do not label MAE/MFE scenarios as true path-dependent exits without daily quote timestamps.",
        ]
    if exit_policy_readiness_state == "final_outcome_only":
        return [
            "Use this artifact as the fixed-horizon exit evidence layer for deployment profile documentation.",
            "Build daily holding-period quote path extraction before optimizing real profit targets, stop losses, or defensive exits.",
        ]
    return [
        "Patch upstream handoff until entry legs, final exit legs, final exit date, and final return/PnL are available for almost all sized trades.",
    ]


def build_portfolio_exit_path_enrichment_artifact(
    *,
    position_sizing_rows_path: str | Path,
    selected_strategy_outcome_rows_path: str | Path | None,
    output_dir: str | Path,
    scope: str = "sized",
    minimum_final_outcome_path_coverage: float = 0.95,
) -> dict[str, Any]:
    position_rows = read_jsonl(position_sizing_rows_path)
    selected_rows = read_jsonl(selected_strategy_outcome_rows_path) if selected_strategy_outcome_rows_path else []
    result = build_portfolio_exit_path_enrichment(
        position_sizing_rows=position_rows,
        selected_strategy_outcome_rows=selected_rows,
        output_dir=output_dir,
        scope=scope,
        minimum_final_outcome_path_coverage=minimum_final_outcome_path_coverage,
    )
    return result.summary
