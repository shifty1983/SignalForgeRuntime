from __future__ import annotations

import argparse
import bisect
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from signalforge.engines.regime.fred_weekly_pipeline import build_signalforge_fred_weekly_regime_pipeline


DEFAULT_REGIME_PATH = "artifacts/fred_regime_pipeline/signalforge_fred_regime_pipeline.json"
DEFAULT_CONTRACT_PATH = (
    "artifacts/qc_replay_5y_behavior_inputs/"
    "signalforge_qc_replay_contract_outcome_evidence.json"
)
DEFAULT_OUTPUT_DIR = "artifacts/qc_replay_5y_historical_regime_date_map"
DEFAULT_RESULT_FILE = "signalforge_historical_regime_date_map.json"
DEFAULT_SUMMARY_FILE = "signalforge_historical_regime_date_map_summary.json"

SCHEMA_VERSION = "signalforge_historical_regime_date_map.v2"
ITEM_SCHEMA_VERSION = "signalforge_historical_regime_date_map_item.v2"


EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
    "automatic_close_orders",
    "automatic_roll_orders",
    "automatic_defense_orders",
    "automatic_strategy_changes",
    "automatic_parameter_changes",
    "automatic_pause_actions",
]


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    regime_path = Path(args.regime_source)
    contract_path = Path(args.contract_source)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    regime = _read_json(regime_path)
    contracts = _read_json(contract_path)

    regime_rows = _regime_rows(regime)
    regime_dates = [_parse_date(row.get("date")) for row in regime_rows]

    outcomes = [
        row
        for row in contracts.get("contract_outcome_snapshots", [])
        if isinstance(row, Mapping)
    ]

    quote_dates = sorted(
        {
            parsed
            for row in outcomes
            if (parsed := _parse_date(row.get("quote_date"))) is not None
        }
    )

    map_items: list[dict[str, Any]] = []
    unmatched_dates: list[str] = []
    weekly_context_failures: list[dict[str, Any]] = []

    for quote_date in quote_dates:
        index = bisect.bisect_right(regime_dates, quote_date) - 1
        if index < 0:
            unmatched_dates.append(quote_date.isoformat())
            map_items.append(_missing_item(quote_date=quote_date))
            continue

        matched = regime_rows[index]
        regime_date = _parse_date(matched.get("date"))
        match_state = "exact_date_match" if regime_date == quote_date else "prior_date_match"

        weekly_context, weekly_failure = _build_weekly_context_asof(
            source_regime=regime,
            source_rows=regime_rows[: index + 1],
            quote_date=quote_date,
            matched_row=matched,
            max_macro_lookback_months=args.max_macro_lookback_months,
            periods=args.periods,
            weekly_lookback_days=args.weekly_lookback_days,
        )
        if weekly_failure:
            weekly_context_failures.append(weekly_failure)

        map_items.append(
            _mapped_item(
                quote_date=quote_date,
                regime_date=regime_date,
                regime_match_state=match_state,
                matched_row=matched,
                weekly_context=weekly_context,
            )
        )

    by_quote_date = {item["quote_date"]: item for item in map_items}
    enriched_preview, missing_contract_regime_count = _preview(outcomes, by_quote_date)

    match_counts = Counter(item["regime_match_state"] for item in map_items)
    regime_counts = Counter(item.get("regime_state") or "unknown" for item in map_items)
    macro_counts = Counter(item.get("macro_regime_label") or "unknown" for item in map_items)
    policy_counts = Counter(item.get("policy_regime_label") or "unknown" for item in map_items)
    weekly_planning_counts = Counter(
        item.get("weekly_planning_label") or "unknown" for item in map_items
    )
    weekly_context_status_counts = Counter(
        item.get("weekly_context_status") or "unknown" for item in map_items
    )

    status = "ready" if not unmatched_dates and not weekly_context_failures else "needs_review"

    result_path = output_dir / args.result_file
    summary_path = output_dir / args.summary_file

    explicit_exclusions = _dedupe(
        _as_list(contracts.get("explicit_exclusions"))
        or _as_list(regime.get("explicit_exclusions"))
        or EXPLICIT_EXCLUSIONS
    )

    result = {
        "artifact_type": "signalforge_historical_regime_date_map",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "is_ready": True,
        "requires_manual_approval": True,
        "mapping_mode": "quote_date_asof_latest_prior_fred_monthly_regime_with_weekly_policy_context",
        "regime_source_path": str(regime_path),
        "contract_source_path": str(contract_path),
        "source_artifacts": {
            "fred_regime_pipeline": regime.get("artifact_type"),
            "contract_outcome_evidence": contracts.get("artifact_type"),
            "fred_weekly_policy_builder": "signalforge_fred_weekly_regime_pipeline.v2",
        },
        "source_statuses": {
            "fred_regime_pipeline": regime.get("status"),
            "contract_outcome_evidence": contracts.get("status"),
        },
        "regime_row_count": len(regime_rows),
        "contract_outcome_count": len(outcomes),
        "quote_date_count": len(quote_dates),
        "mapped_quote_date_count": len(map_items) - len(unmatched_dates),
        "unmatched_quote_date_count": len(unmatched_dates),
        "unmatched_quote_dates": unmatched_dates,
        "weekly_context_failure_count": len(weekly_context_failures),
        "weekly_context_failures": weekly_context_failures[:50],
        "missing_contract_regime_count_in_preview": missing_contract_regime_count,
        "regime_match_state_counts": dict(sorted(match_counts.items())),
        "regime_state_counts": dict(sorted(regime_counts.items())),
        "macro_regime_label_counts": dict(sorted(macro_counts.items())),
        "policy_regime_label_counts": dict(sorted(policy_counts.items())),
        "weekly_planning_label_counts": dict(sorted(weekly_planning_counts.items())),
        "weekly_context_status_counts": dict(sorted(weekly_context_status_counts.items())),
        "date_map_items": map_items,
        "enriched_contract_preview": enriched_preview,
        "next_step": "build_matrix_enriched_contract_outcomes",
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": explicit_exclusions,
    }

    summary = {
        "artifact_type": result["artifact_type"],
        "schema_version": result["schema_version"],
        "status": result["status"],
        "is_ready": result["is_ready"],
        "mapping_mode": result["mapping_mode"],
        "source_artifacts": result["source_artifacts"],
        "source_statuses": result["source_statuses"],
        "regime_row_count": result["regime_row_count"],
        "contract_outcome_count": result["contract_outcome_count"],
        "quote_date_count": result["quote_date_count"],
        "mapped_quote_date_count": result["mapped_quote_date_count"],
        "unmatched_quote_date_count": result["unmatched_quote_date_count"],
        "unmatched_quote_dates": result["unmatched_quote_dates"][:25],
        "weekly_context_failure_count": result["weekly_context_failure_count"],
        "weekly_context_failures": result["weekly_context_failures"][:10],
        "regime_match_state_counts": result["regime_match_state_counts"],
        "regime_state_counts": result["regime_state_counts"],
        "macro_regime_label_counts": result["macro_regime_label_counts"],
        "policy_regime_label_counts": result["policy_regime_label_counts"],
        "weekly_planning_label_counts": result["weekly_planning_label_counts"],
        "weekly_context_status_counts": result["weekly_context_status_counts"],
        "first_map_item": map_items[0] if map_items else None,
        "last_map_item": map_items[-1] if map_items else None,
        "next_step": result["next_step"],
        "files": {
            "result": str(result_path),
            "summary": str(summary_path),
        },
        "explicit_exclusions": result["explicit_exclusions"],
    }

    _write_json(result_path, result)
    _write_json(summary_path, summary)

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Map each QC replay quote_date to the latest prior FRED monthly regime row "
            "and enrich the mapping with the FRED weekly/planning policy context fields."
        )
    )
    parser.add_argument("--regime-source", default=DEFAULT_REGIME_PATH)
    parser.add_argument("--contract-source", default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--result-file", default=DEFAULT_RESULT_FILE)
    parser.add_argument("--summary-file", default=DEFAULT_SUMMARY_FILE)
    parser.add_argument("--max-macro-lookback-months", type=int, default=18)
    parser.add_argument("--periods", type=int, default=1)
    parser.add_argument("--weekly-lookback-days", type=int, default=7)
    return parser.parse_args(argv)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")

    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise SystemExit(f"input JSON must be an object: {path}")

    return value


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _regime_rows(regime: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = [
        dict(row)
        for row in regime.get("regime_rows", [])
        if isinstance(row, Mapping) and _parse_date(row.get("date")) is not None
    ]
    return sorted(rows, key=lambda row: _parse_date(row.get("date")))


def _build_weekly_context_asof(
    *,
    source_regime: Mapping[str, Any],
    source_rows: Sequence[Mapping[str, Any]],
    quote_date: date,
    matched_row: Mapping[str, Any],
    max_macro_lookback_months: int,
    periods: int,
    weekly_lookback_days: int,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    source = {
        "artifact_type": source_regime.get("artifact_type"),
        "schema_version": source_regime.get("schema_version"),
        "status": source_regime.get("status"),
        "as_of_quote_date": quote_date.isoformat(),
        "latest_date": _date_text(matched_row.get("date")),
        "latest_ready_regime_row": dict(matched_row),
        "regime_rows": [dict(row) for row in source_rows],
        "explicit_exclusions": _as_list(source_regime.get("explicit_exclusions")),
    }

    try:
        result = build_signalforge_fred_weekly_regime_pipeline(
            source,
            max_macro_lookback_months=max_macro_lookback_months,
            periods=periods,
            weekly_lookback_days=weekly_lookback_days,
        )
    except Exception as error:  # pragma: no cover - defensive integration boundary
        fallback = _fallback_weekly_context(matched_row, reason=str(error))
        return fallback, {
            "quote_date": quote_date.isoformat(),
            "regime_date": _date_text(matched_row.get("date")),
            "reason": str(error),
            "failure_type": type(error).__name__,
        }

    if not isinstance(result, Mapping):
        fallback = _fallback_weekly_context(matched_row, reason="weekly builder returned non-mapping")
        return fallback, {
            "quote_date": quote_date.isoformat(),
            "regime_date": _date_text(matched_row.get("date")),
            "reason": "weekly builder returned non-mapping",
            "failure_type": "invalid_result",
        }

    output = dict(result)
    if output.get("status") == "blocked":
        return output, {
            "quote_date": quote_date.isoformat(),
            "regime_date": _date_text(matched_row.get("date")),
            "reason": "; ".join(str(x) for x in _as_list(output.get("blocked_reasons")))
            or "weekly context blocked",
            "failure_type": "blocked_weekly_context",
        }

    return output, None


def _fallback_weekly_context(row: Mapping[str, Any], *, reason: str) -> dict[str, Any]:
    resolution = _resolve_regime_state(row)
    regime_state = resolution["regime_state"]
    risk_environment = _clean_text(row.get("risk_environment")) or "unknown"
    return {
        "artifact_type": "signalforge_fred_weekly_regime_pipeline",
        "schema_version": "signalforge_fred_weekly_regime_pipeline.v2.fallback",
        "status": "needs_review",
        "is_ready": False,
        "as_of_date": _date_text(row.get("date")),
        "macro_regime_label": regime_state,
        "macro_regime": regime_state,
        "macro_regime_score": _float_or_none(row.get("macro_regime_score")),
        "macro_regime_confidence": _float_or_none(row.get("macro_regime_confidence")),
        "macro_regime_drivers": _clean_text(row.get("macro_regime_drivers")),
        "source_macro_regime_label": _clean_text(row.get("regime_label")) or regime_state,
        "macro_regime_source_date": _date_text(row.get("date")),
        "macro_base_selection_reason": f"fallback: {reason}",
        "policy_regime_label": _clean_text(row.get("policy_regime_label")) or regime_state,
        "weekly_planning_label": _clean_text(row.get("weekly_planning_label")) or regime_state,
        "weekly_risk_environment": risk_environment,
        "weekly_rates_regime": _clean_text(row.get("rates_regime")),
        "weekly_liquidity_regime": _clean_text(row.get("liquidity_regime")),
        "weekly_volatility_regime": _clean_text(row.get("volatility_regime")),
        "weekly_event_risk": bool(row.get("event_risk", False)),
        "warnings": [reason],
        "blocked_reasons": [],
    }


def _missing_item(*, quote_date: date) -> dict[str, Any]:
    return {
        "artifact_type": "historical_regime_date_map_item",
        "schema_version": ITEM_SCHEMA_VERSION,
        "quote_date": quote_date.isoformat(),
        "regime_match_state": "missing_prior_regime_row",
        "regime_date": None,
        "regime_state": "unknown",
        "macro_regime_label": "unknown",
        "macro_regime": "unknown",
        "macro_regime_score": None,
        "macro_regime_confidence": None,
        "macro_regime_drivers": None,
        "source_macro_regime_label": "unknown",
        "macro_regime_source_date": None,
        "macro_base_selection_reason": "missing_prior_regime_row",
        "policy_regime_label": "unknown",
        "weekly_planning_label": "unknown",
        "weekly_context_status": "missing_prior_regime_row",
        "weekly_context_is_ready": False,
        "weekly_overlay_date": None,
        "weekly_risk_environment": "unknown",
        "weekly_rates_regime": "unknown",
        "weekly_liquidity_regime": "unknown",
        "weekly_volatility_regime": "unknown",
        "weekly_event_risk": False,
        "risk_environment": "unknown",
        "regime_risk_bias": "unknown",
        "regime_resolution_method": "missing_prior_regime_row",
        "growth_regime": None,
        "inflation_regime": None,
        "liquidity_regime": None,
        "rates_regime": None,
        "volatility_regime": None,
        "yield_curve_regime": None,
        "latest_regime_options_policy": None,
        "latest_regime_asset_class_policy": None,
        "regime_row": None,
        "latest_weekly_overlay_row": None,
        "latest_macro_regime_row": None,
    }


def _mapped_item(
    *,
    quote_date: date,
    regime_date: date | None,
    regime_match_state: str,
    matched_row: Mapping[str, Any],
    weekly_context: Mapping[str, Any],
) -> dict[str, Any]:
    fallback_resolution = _resolve_regime_state(matched_row)
    fallback_state = fallback_resolution["regime_state"]

    macro_regime_label = (
        _clean_text(weekly_context.get("macro_regime_label"))
        or _clean_text(matched_row.get("macro_regime_label"))
        or _clean_text(matched_row.get("regime_label"))
        or fallback_state
    )
    policy_regime_label = (
        _clean_text(weekly_context.get("policy_regime_label"))
        or _clean_text(matched_row.get("policy_regime_label"))
        or macro_regime_label
    )
    weekly_planning_label = (
        _clean_text(weekly_context.get("weekly_planning_label"))
        or _clean_text(matched_row.get("weekly_planning_label"))
        or policy_regime_label
    )

    # Downstream historical matrix code has historically consumed regime_state. The
    # updated meaning is the policy label from the FRED weekly/planning layer because
    # that is the label intended to feed options and asset-class policy.
    regime_state = policy_regime_label or macro_regime_label or fallback_state

    risk_environment = (
        _clean_text(weekly_context.get("weekly_risk_environment"))
        or _clean_text(matched_row.get("risk_environment"))
        or "unknown"
    )

    return {
        "artifact_type": "historical_regime_date_map_item",
        "schema_version": ITEM_SCHEMA_VERSION,
        "quote_date": quote_date.isoformat(),
        "regime_match_state": regime_match_state,
        "regime_date": regime_date.isoformat() if regime_date else None,
        "regime_state": regime_state,
        "macro_regime_label": macro_regime_label,
        "macro_regime": weekly_context.get("macro_regime") or macro_regime_label,
        "macro_regime_score": _float_or_none(weekly_context.get("macro_regime_score")),
        "macro_regime_confidence": _float_or_none(
            weekly_context.get("macro_regime_confidence")
        ),
        "macro_regime_drivers": _clean_text(weekly_context.get("macro_regime_drivers")),
        "source_macro_regime_label": (
            _clean_text(weekly_context.get("source_macro_regime_label"))
            or _clean_text(matched_row.get("regime_label"))
            or macro_regime_label
        ),
        "macro_regime_source_date": (
            _clean_text(weekly_context.get("macro_regime_source_date"))
            or (regime_date.isoformat() if regime_date else None)
        ),
        "macro_base_selection_reason": _clean_text(
            weekly_context.get("macro_base_selection_reason")
        ),
        "policy_regime_label": policy_regime_label,
        "weekly_planning_label": weekly_planning_label,
        "weekly_context_status": _clean_text(weekly_context.get("status")) or "unknown",
        "weekly_context_is_ready": bool(weekly_context.get("is_ready", False)),
        "weekly_overlay_date": _clean_text(weekly_context.get("weekly_overlay_date"))
        or _clean_text(weekly_context.get("as_of_date"))
        or (regime_date.isoformat() if regime_date else None),
        "weekly_risk_environment": risk_environment,
        "weekly_rates_regime": _clean_text(weekly_context.get("weekly_rates_regime"))
        or _clean_text(matched_row.get("rates_regime")),
        "weekly_liquidity_regime": _clean_text(
            weekly_context.get("weekly_liquidity_regime")
        )
        or _clean_text(matched_row.get("liquidity_regime")),
        "weekly_volatility_regime": _clean_text(
            weekly_context.get("weekly_volatility_regime")
        )
        or _clean_text(matched_row.get("volatility_regime")),
        "weekly_event_risk": bool(weekly_context.get("weekly_event_risk", False)),
        "risk_environment": risk_environment,
        "regime_risk_bias": _clean_text(matched_row.get("regime_risk_bias")) or "unknown",
        "regime_resolution_method": (
            "fred_weekly_policy_context"
            if weekly_context.get("status") != "needs_review"
            else fallback_resolution["resolution_method"]
        ),
        "growth_regime": _clean_text(matched_row.get("growth_regime")),
        "inflation_regime": _clean_text(matched_row.get("inflation_regime")),
        "liquidity_regime": _clean_text(matched_row.get("liquidity_regime")),
        "rates_regime": _clean_text(matched_row.get("rates_regime")),
        "volatility_regime": _clean_text(matched_row.get("volatility_regime")),
        "yield_curve_regime": _clean_text(matched_row.get("yield_curve_regime")),
        "latest_regime_options_policy": weekly_context.get("latest_regime_options_policy"),
        "latest_regime_asset_class_policy": weekly_context.get(
            "latest_regime_asset_class_policy"
        ),
        "regime_row": dict(matched_row),
        "latest_weekly_overlay_row": weekly_context.get("latest_weekly_overlay_row"),
        "latest_macro_regime_row": weekly_context.get("latest_macro_regime_row"),
    }


def _preview(
    outcomes: Sequence[Mapping[str, Any]],
    by_quote_date: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    enriched_preview = []
    missing_contract_regime_count = 0

    for row in outcomes[:100]:
        quote_date = _date_text(row.get("quote_date"))
        match = by_quote_date.get(quote_date)
        if match is None or match.get("regime_state") == "unknown":
            missing_contract_regime_count += 1

        enriched_preview.append(
            {
                "symbol": row.get("symbol"),
                "quote_date": quote_date,
                "exit_date": row.get("exit_date"),
                "horizon_days": row.get("horizon_days"),
                "strategy_family": row.get("strategy_family"),
                "regime_state": match.get("regime_state") if match else "unknown",
                "macro_regime_label": match.get("macro_regime_label") if match else "unknown",
                "policy_regime_label": match.get("policy_regime_label") if match else "unknown",
                "weekly_planning_label": match.get("weekly_planning_label") if match else "unknown",
                "regime_date": match.get("regime_date") if match else None,
                "regime_match_state": match.get("regime_match_state")
                if match
                else "missing_date_map",
            }
        )

    return enriched_preview, missing_contract_regime_count


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _date_text(value: Any) -> str:
    parsed = _parse_date(value)
    return parsed.isoformat() if parsed else ""


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_regime_state(row: Mapping[str, Any]) -> dict[str, str]:
    direct = _first_non_unknown(
        row.get("policy_regime_label"),
        row.get("macro_regime_label"),
        row.get("regime_label"),
        row.get("macro_regime"),
    )
    if direct is not None:
        return {
            "regime_state": direct,
            "resolution_method": "direct_regime_label",
        }

    growth = _clean_text(row.get("growth_regime")) or ""
    inflation = _clean_text(row.get("inflation_regime")) or ""
    liquidity = _clean_text(row.get("liquidity_regime")) or ""
    rates = _clean_text(row.get("rates_regime")) or ""
    risk_environment = _clean_text(row.get("risk_environment")) or ""
    regime_risk_bias = _clean_text(row.get("regime_risk_bias")) or ""

    weak_growth = any(token in growth for token in ("slowdown", "contraction", "recession"))
    strong_growth = any(token in growth for token in ("expansion", "growth"))
    rising_inflation = any(token in inflation for token in ("rising", "hot", "high"))
    easing_inflation = any(token in inflation for token in ("falling", "cooling", "disinflation"))
    rising_rates = "rising" in rates
    tightening_liquidity = any(token in liquidity for token in ("tight", "contract", "drain"))

    if weak_growth:
        return {
            "regime_state": "deflationary_slowdown",
            "resolution_method": "component_regime_fallback",
        }

    if rising_inflation or rising_rates or tightening_liquidity:
        return {
            "regime_state": "overheating",
            "resolution_method": "component_regime_fallback",
        }

    if strong_growth and (easing_inflation or risk_environment == "risk_on"):
        return {
            "regime_state": "goldilocks",
            "resolution_method": "component_regime_fallback",
        }

    if risk_environment == "risk_off" or regime_risk_bias == "risk_off_bias":
        return {
            "regime_state": "deflationary_slowdown",
            "resolution_method": "risk_environment_fallback",
        }

    if risk_environment == "risk_on" or regime_risk_bias == "risk_on_bias":
        return {
            "regime_state": "goldilocks",
            "resolution_method": "risk_environment_fallback",
        }

    return {
        "regime_state": "goldilocks",
        "resolution_method": "default_non_unknown_fallback",
    }


def _first_non_unknown(*values: Any) -> str | None:
    for value in values:
        text = _clean_text(value)
        if text and text.lower() not in {"unknown", "none", "null", "nan"}:
            return text
    return None


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _dedupe(values: Sequence[Any]) -> list[Any]:
    seen: set[str] = set()
    output: list[Any] = []
    for value in values:
        key = str(value)
        if key and key not in seen:
            seen.add(key)
            output.append(value)
    return output


if __name__ == "__main__":
    raise SystemExit(main())

