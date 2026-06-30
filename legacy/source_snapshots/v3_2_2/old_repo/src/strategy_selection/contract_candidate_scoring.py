from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


CONTRACT_CANDIDATE_SCORING_SCHEMA_VERSION = "signalforge_contract_candidate_scoring.v1"

COVERED_CAPABILITIES = [
    "contract_candidate_scoring",
    "contract_level_candidate_ranking",
    "contract_liquidity_spread_greek_scoring",
    "contract_candidate_review_handoff",
    "contract_scoring_not_contract_selection_or_execution",
]

DEPENDS_ON_CAPABILITIES = [
    "contract_selection_readiness",
]

READINESS_ITEM_KEYS = (
    "contract_readiness_queue",
    "ranked_contract_readiness_items",
    "contract_selection_readiness_items",
    "items",
    "data",
    "rows",
)

OPTION_ROW_KEYS = (
    "option_rows",
    "contract_rows",
    "contracts",
    "items",
    "data",
    "rows",
)

SCORE_READY = "ready_for_contract_candidate_review"
SCORE_CONSTRAINED = "constrained_for_contract_candidate_review"
SCORE_DATA_REVIEW = "data_review_required"
SCORE_BLOCKED = "blocked_from_contract_candidate_review"

ELIGIBLE_READINESS_STATUSES = {
    "ready_for_contract_selection_evaluation",
    "constrained_for_contract_selection_evaluation",
}


def build_signalforge_contract_candidate_scoring(
    contract_readiness_source: Mapping[str, Any] | Sequence[Any] | None,
    option_source: Mapping[str, Any] | Sequence[Any] | None = None,
    *,
    max_spread_pct: float = 0.15,
    min_open_interest: int = 100,
    min_volume: int = 1,
    min_contract_score: float = 0.50,
    max_candidates_per_symbol: int = 5,
) -> dict[str, Any]:
    """Score contract candidates after final-review contract readiness.

    This artifact ranks contract rows for human review. It does not select a
    contract for trading, call broker APIs, route orders, submit orders, model
    fills/slippage, or authorize automatic strategy/parameter changes.
    """

    source_artifacts = {
        "contract_readiness_source": _source_artifact_type(contract_readiness_source),
        "option_source": _source_artifact_type(option_source),
    }
    readiness_items = _extract_items(contract_readiness_source, READINESS_ITEM_KEYS)
    if not readiness_items:
        return _blocked_result(["missing_contract_readiness_items"], source_artifacts=source_artifacts)

    option_rows = _extract_items(option_source, OPTION_ROW_KEYS)
    indexed_option_rows = _index_option_rows(option_rows)

    scoring_items = [
        _build_symbol_scoring_item(
            item,
            indexed_option_rows.get(_clean_symbol(_first_value(item, ("symbol", "underlying_symbol", "ticker"))) or "", []),
            max_spread_pct=float(max_spread_pct),
            min_open_interest=int(min_open_interest),
            min_volume=int(min_volume),
            min_contract_score=float(min_contract_score),
            max_candidates_per_symbol=max(1, int(max_candidates_per_symbol)),
        )
        for item in readiness_items
        if isinstance(item, Mapping)
    ]

    ranked_contract_candidates = _rank_contract_candidates(scoring_items)
    for index, candidate in enumerate(ranked_contract_candidates, start=1):
        candidate["contract_candidate_rank"] = index

    summary = _summary(
        readiness_items=readiness_items,
        scoring_items=scoring_items,
        ranked_contract_candidates=ranked_contract_candidates,
        option_rows=option_rows,
    )

    status = (
        "ready"
        if summary["ranked_contract_candidate_count"] > 0
        and summary["data_review_symbol_count"] == 0
        and summary["blocked_symbol_count"] == 0
        else "needs_review"
    )

    return {
        "artifact_type": "signalforge_contract_candidate_scoring",
        "schema_version": CONTRACT_CANDIDATE_SCORING_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "contract_candidate_scoring",
        "adapter_type": "contract_candidate_scoring_builder",
        "review_scope": "ranked_contract_candidate_review_not_contract_selection_or_execution",
        "source_artifacts": source_artifacts,
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "next_build_recommendations": [
            {
                "capability": "contract_candidate_review_export",
                "priority": "medium",
                "recommendation": "Export ranked contract candidates for human review only after contract candidate scoring is ready.",
            }
        ],
        "contract_candidate_scoring_items": scoring_items,
        "contract_candidate_score_queue": ranked_contract_candidates,
        "ranked_contract_candidate_items": ranked_contract_candidates,
        "contract_candidate_scoring_summary": summary,
        "thresholds": {
            "max_spread_pct": float(max_spread_pct),
            "min_open_interest": int(min_open_interest),
            "min_volume": int(min_volume),
            "min_contract_score": float(min_contract_score),
            "max_candidates_per_symbol": max(1, int(max_candidates_per_symbol)),
        },
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "blocked_reasons": [],
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_symbol_scoring_item(
    readiness_item: Mapping[str, Any],
    source_option_rows: Sequence[Mapping[str, Any]],
    *,
    max_spread_pct: float,
    min_open_interest: int,
    min_volume: int,
    min_contract_score: float,
    max_candidates_per_symbol: int,
) -> dict[str, Any]:
    symbol = _clean_symbol(_first_value(readiness_item, ("symbol", "underlying_symbol", "ticker"))) or "UNKNOWN"
    readiness_status = _clean_text(
        _first_value(readiness_item, ("contract_selection_readiness_status", "coverage_status"))
    ) or SCORE_DATA_REVIEW
    eligible = (
        readiness_item.get("eligible_for_contract_selection_evaluation") is True
        or readiness_status in ELIGIBLE_READINESS_STATUSES
    )

    raw_rows: Sequence[Any]
    if source_option_rows:
        raw_rows = source_option_rows
    else:
        raw_rows = _extract_nested_contract_rows(readiness_item)

    normalized_rows = [_normalize_contract_row(row) for row in raw_rows if isinstance(row, Mapping)]
    valid_rows = [row for row in normalized_rows if row["is_valid_contract_row"]]
    scored_rows = [
        _score_contract_row(
            row,
            readiness_item=readiness_item,
            max_spread_pct=max_spread_pct,
            min_open_interest=min_open_interest,
            min_volume=min_volume,
        )
        for row in valid_rows
    ]
    reviewable_rows = [row for row in scored_rows if row["contract_score"] >= min_contract_score and row["is_reviewable_contract_candidate"]]
    ranked_symbol_candidates = sorted(
        reviewable_rows,
        key=lambda row: (
            row["contract_score"],
            row["liquidity_score"],
            -row["spread_pct"] if row["spread_pct"] is not None else -999.0,
            str(row.get("contract_symbol") or ""),
        ),
        reverse=True,
    )[:max_candidates_per_symbol]

    data_review_reasons = list(readiness_item.get("data_review_reasons") or [])
    hard_block_reasons = list(readiness_item.get("hard_block_reasons") or [])
    risk_flags = list(readiness_item.get("risk_flags") or [])
    constraint_flags = list(readiness_item.get("constraint_flags") or [])
    scoring_notes: list[str] = []

    if not eligible:
        data_review_reasons.append("not_ready_for_contract_selection_evaluation")
    if eligible and not normalized_rows:
        data_review_reasons.append("missing_contract_rows_for_scoring")
    if eligible and normalized_rows and not valid_rows:
        data_review_reasons.append("no_valid_contract_rows_for_scoring")
    if eligible and valid_rows and not ranked_symbol_candidates:
        data_review_reasons.append("no_contract_candidates_pass_score_threshold")

    if hard_block_reasons:
        coverage_status = SCORE_BLOCKED
    elif data_review_reasons:
        coverage_status = SCORE_DATA_REVIEW
    elif risk_flags or constraint_flags or readiness_status == "constrained_for_contract_selection_evaluation":
        coverage_status = SCORE_CONSTRAINED
    else:
        coverage_status = SCORE_READY

    eligible_for_contract_candidate_review = coverage_status in {SCORE_READY, SCORE_CONSTRAINED}
    if eligible_for_contract_candidate_review:
        scoring_notes.append("contract_candidates_ranked_for_human_review")
    else:
        scoring_notes.append("contract_candidates_not_ready_for_human_review")

    top_candidate = ranked_symbol_candidates[0] if ranked_symbol_candidates else None

    return {
        "artifact_type": "contract_candidate_scoring_item",
        "symbol": symbol,
        "coverage_status": coverage_status,
        "contract_candidate_scoring_status": coverage_status,
        "eligible_for_contract_candidate_review": eligible_for_contract_candidate_review,
        "manual_review_required": True,
        "selected_strategy_family": readiness_item.get("selected_strategy_family"),
        "selected_expected_value_score": readiness_item.get("selected_expected_value_score"),
        "selected_expected_value_state": readiness_item.get("selected_expected_value_state"),
        "source_contract_readiness_rank": readiness_item.get("contract_readiness_rank"),
        "source_contract_readiness_status": readiness_status,
        "source_final_review_rank": readiness_item.get("source_final_review_rank"),
        "contract_row_count": len(normalized_rows),
        "valid_contract_row_count": len(valid_rows),
        "scored_contract_row_count": len(scored_rows),
        "reviewable_contract_candidate_count": len(reviewable_rows),
        "ranked_contract_candidate_count": len(ranked_symbol_candidates),
        "top_contract_candidate_score": top_candidate.get("contract_score") if top_candidate else None,
        "top_contract_symbol": top_candidate.get("contract_symbol") if top_candidate else None,
        "ranked_contract_candidates": ranked_symbol_candidates,
        "risk_flags": sorted(set(risk_flags)),
        "constraint_flags": sorted(set(constraint_flags)),
        "data_review_reasons": sorted(set(data_review_reasons)),
        "hard_block_reasons": sorted(set(hard_block_reasons)),
        "needs_review_reasons": sorted(set(data_review_reasons + hard_block_reasons + risk_flags + constraint_flags)),
        "scoring_notes": scoring_notes,
        "macro_regime": readiness_item.get("macro_regime"),
        "weekly_planning_label": readiness_item.get("weekly_planning_label"),
        "asset_behavior_state": readiness_item.get("asset_behavior_state"),
        "options_behavior_state": readiness_item.get("options_behavior_state"),
        "premium_bias": readiness_item.get("premium_bias"),
        "strategy_environment_bias": readiness_item.get("strategy_environment_bias"),
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _score_contract_row(
    row: Mapping[str, Any],
    *,
    readiness_item: Mapping[str, Any],
    max_spread_pct: float,
    min_open_interest: int,
    min_volume: int,
) -> dict[str, Any]:
    spread_pct = row.get("spread_pct")
    open_interest = row.get("open_interest")
    volume = row.get("volume")
    delta = row.get("delta")
    dte = row.get("dte")
    moneyness = row.get("moneyness")
    gamma = row.get("gamma")

    spread_score = _bounded_score(1.0 - ((spread_pct or max_spread_pct) / max_spread_pct)) if max_spread_pct > 0 else 0.0
    liquidity_score = _liquidity_score(open_interest=open_interest, volume=volume, min_open_interest=min_open_interest, min_volume=min_volume)
    delta_score = _delta_score(delta=delta, strategy_family=_clean_text(readiness_item.get("selected_strategy_family")))
    dte_score = _dte_score(dte)
    moneyness_score = _moneyness_score(moneyness)
    greek_score = _greek_score(gamma=gamma, theta=row.get("theta"), vega=row.get("vega"))

    contract_score = round(
        0.25 * spread_score
        + 0.25 * liquidity_score
        + 0.20 * delta_score
        + 0.15 * dte_score
        + 0.10 * moneyness_score
        + 0.05 * greek_score,
        4,
    )

    review_reasons: list[str] = []
    if spread_pct is None:
        review_reasons.append("missing_spread_pct")
    elif spread_pct > max_spread_pct:
        review_reasons.append("spread_above_threshold")
    if open_interest is not None and open_interest < min_open_interest:
        review_reasons.append("open_interest_below_threshold")
    if volume is not None and volume < min_volume:
        review_reasons.append("volume_below_threshold")
    if delta is None:
        review_reasons.append("missing_delta")

    is_reviewable = not review_reasons

    return {
        "artifact_type": "contract_candidate_score",
        "symbol": row.get("symbol"),
        "contract_symbol": row.get("contract_symbol"),
        "expiration": row.get("expiration"),
        "quote_date": row.get("quote_date"),
        "dte": dte,
        "strike": row.get("strike"),
        "option_right": row.get("option_right"),
        "bid": row.get("bid"),
        "ask": row.get("ask"),
        "mid": row.get("mid"),
        "spread_pct": spread_pct,
        "open_interest": open_interest,
        "volume": volume,
        "implied_volatility": row.get("implied_volatility"),
        "delta": delta,
        "gamma": gamma,
        "theta": row.get("theta"),
        "vega": row.get("vega"),
        "moneyness": moneyness,
        "selected_strategy_family": readiness_item.get("selected_strategy_family"),
        "source_contract_readiness_rank": readiness_item.get("contract_readiness_rank"),
        "contract_score": contract_score,
        "spread_score": round(spread_score, 4),
        "liquidity_score": round(liquidity_score, 4),
        "delta_score": round(delta_score, 4),
        "dte_score": round(dte_score, 4),
        "moneyness_score": round(moneyness_score, 4),
        "greek_score": round(greek_score, 4),
        "is_reviewable_contract_candidate": is_reviewable,
        "review_reasons": review_reasons,
        "manual_review_required": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _normalize_contract_row(row: Mapping[str, Any]) -> dict[str, Any]:
    bid = _safe_float(_first_value(row, ("bid", "bid_price")))
    ask = _safe_float(_first_value(row, ("ask", "ask_price")))
    mid = _safe_float(_first_value(row, ("mid", "mid_price", "mark", "mark_price")))
    if mid is None and bid is not None and ask is not None and ask >= bid:
        mid = (bid + ask) / 2.0
    spread = None if bid is None or ask is None or ask < bid else ask - bid
    spread_pct = None if spread is None or not mid or mid <= 0 else spread / mid

    strike = _safe_float(row.get("strike"))
    expiration = _clean_text(_first_value(row, ("expiration", "expiry", "expiration_date")))
    quote_date = _clean_text(_first_value(row, ("quote_date", "date", "as_of_date")))
    option_right = _clean_text(_first_value(row, ("option_right", "right", "option_type", "type")))
    underlying_price = _safe_float(_first_value(row, ("underlying_price", "spot_price")))
    moneyness = _safe_float(row.get("moneyness"))
    if moneyness is None and strike is not None and underlying_price and underlying_price > 0:
        moneyness = strike / underlying_price

    is_valid_contract_row = bool(strike is not None and expiration and (bid is not None or ask is not None or mid is not None))

    return {
        "symbol": _clean_symbol(_first_value(row, ("underlying_symbol", "symbol", "ticker", "underlying"))),
        "contract_symbol": _clean_text(_first_value(row, ("contract_symbol", "option_symbol", "symbol"))),
        "expiration": expiration,
        "quote_date": quote_date,
        "dte": _safe_int(row.get("dte")),
        "strike": strike,
        "option_right": option_right,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread_pct": spread_pct,
        "open_interest": _safe_int(_first_value(row, ("open_interest", "oi"))),
        "volume": _safe_int(row.get("volume")),
        "implied_volatility": _safe_float(_first_value(row, ("implied_volatility", "iv"))),
        "delta": _safe_float(row.get("delta")),
        "gamma": _safe_float(row.get("gamma")),
        "theta": _safe_float(row.get("theta")),
        "vega": _safe_float(row.get("vega")),
        "moneyness": moneyness,
        "is_valid_contract_row": is_valid_contract_row,
    }


def _rank_contract_candidates(scoring_items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for item in scoring_items:
        if item.get("eligible_for_contract_candidate_review") is not True:
            continue
        symbol = item.get("symbol")
        for candidate in item.get("ranked_contract_candidates", []):
            if not isinstance(candidate, Mapping):
                continue
            candidate_copy = dict(candidate)
            candidate_copy["symbol"] = symbol or candidate_copy.get("symbol")
            candidate_copy["symbol_contract_candidate_rank"] = len(ranked) + 1
            candidate_copy["source_contract_candidate_scoring_status"] = item.get("coverage_status")
            candidate_copy["risk_flags"] = list(item.get("risk_flags", []))
            candidate_copy["constraint_flags"] = list(item.get("constraint_flags", []))
            ranked.append(candidate_copy)
    return sorted(
        ranked,
        key=lambda candidate: (
            _safe_float(candidate.get("contract_score")) or -999.0,
            _safe_float(candidate.get("liquidity_score")) or -999.0,
            -(_safe_float(candidate.get("spread_pct")) or 999.0),
            str(candidate.get("symbol") or ""),
            str(candidate.get("contract_symbol") or ""),
        ),
        reverse=True,
    )


def _summary(
    *,
    readiness_items: Sequence[Any],
    scoring_items: Sequence[Mapping[str, Any]],
    ranked_contract_candidates: Sequence[Mapping[str, Any]],
    option_rows: Sequence[Any],
) -> dict[str, Any]:
    coverage_counts = Counter(str(item.get("coverage_status") or "unknown") for item in scoring_items)
    readiness_status_counts = Counter(
        str(_first_value(item, ("contract_selection_readiness_status", "coverage_status")) or "unknown")
        for item in readiness_items
        if isinstance(item, Mapping)
    )
    strategy_family_counts = Counter(
        str(item.get("selected_strategy_family"))
        for item in scoring_items
        if item.get("selected_strategy_family")
    )
    ranked_strategy_family_counts = Counter(
        str(item.get("selected_strategy_family"))
        for item in ranked_contract_candidates
        if item.get("selected_strategy_family")
    )
    risk_flag_counts = Counter(flag for item in scoring_items for flag in item.get("risk_flags", []))
    constraint_counts = Counter(flag for item in scoring_items for flag in item.get("constraint_flags", []))
    data_reason_counts = Counter(reason for item in scoring_items for reason in item.get("data_review_reasons", []))
    hard_block_counts = Counter(reason for item in scoring_items for reason in item.get("hard_block_reasons", []))

    ready_count = coverage_counts.get(SCORE_READY, 0)
    constrained_count = coverage_counts.get(SCORE_CONSTRAINED, 0)
    data_review_count = coverage_counts.get(SCORE_DATA_REVIEW, 0)
    blocked_count = coverage_counts.get(SCORE_BLOCKED, 0)

    return {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "symbol_count": len(scoring_items),
        "contract_readiness_symbol_count": len(readiness_items),
        "scoreable_symbol_count": ready_count + constrained_count,
        "ready_contract_candidate_symbol_count": ready_count,
        "constrained_contract_candidate_symbol_count": constrained_count,
        "data_review_symbol_count": data_review_count,
        "blocked_symbol_count": blocked_count,
        "needs_review_symbol_count": data_review_count + blocked_count,
        "manual_review_symbol_count": len(scoring_items),
        "contract_candidate_symbol_count": ready_count + constrained_count,
        "contract_candidate_count": sum(int(item.get("reviewable_contract_candidate_count") or 0) for item in scoring_items),
        "ranked_contract_candidate_count": len(ranked_contract_candidates),
        "option_row_count": len(option_rows),
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "source_contract_readiness_status_counts": dict(sorted(readiness_status_counts.items())),
        "strategy_family_counts": dict(sorted(strategy_family_counts.items())),
        "ranked_contract_candidate_strategy_family_counts": dict(sorted(ranked_strategy_family_counts.items())),
        "risk_flag_counts": dict(sorted(risk_flag_counts.items())),
        "constraint_flag_counts": dict(sorted(constraint_counts.items())),
        "data_review_reason_counts": dict(sorted(data_reason_counts.items())),
        "hard_block_reason_counts": dict(sorted(hard_block_counts.items())),
    }


def _extract_nested_contract_rows(readiness_item: Mapping[str, Any]) -> list[Any]:
    value = readiness_item.get("candidate_contract_rows")
    if _looks_like_items(value):
        return list(value)
    return []


def _index_option_rows(option_rows: Sequence[Any]) -> dict[str, list[Mapping[str, Any]]]:
    indexed: dict[str, list[Mapping[str, Any]]] = {}
    for row in option_rows:
        if not isinstance(row, Mapping):
            continue
        symbol = _clean_symbol(_first_value(row, ("underlying_symbol", "root_symbol", "ticker", "underlying", "symbol")))
        if not symbol:
            continue
        indexed.setdefault(symbol, []).append(row)
    return indexed


def _extract_items(source: Mapping[str, Any] | Sequence[Any] | None, keys: Sequence[str]) -> list[Any]:
    if source is None:
        return []
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return list(source)
    if not isinstance(source, Mapping):
        return []
    for key in keys:
        value = source.get(key)
        if _looks_like_items(value):
            return list(value)
    for parent_key in ("result", "payload", "data", "import_result"):
        parent = source.get(parent_key)
        if isinstance(parent, Mapping):
            for key in keys:
                value = parent.get(key)
                if _looks_like_items(value):
                    return list(value)
    return []


def _looks_like_items(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _source_artifact_type(source: Any) -> str:
    if isinstance(source, Mapping):
        return _clean_text(source.get("artifact_type")) or "mapping"
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return "sequence"
    if source is None:
        return "missing"
    return type(source).__name__


def _liquidity_score(*, open_interest: int | None, volume: int | None, min_open_interest: int, min_volume: int) -> float:
    oi_score = 0.5 if open_interest is None else min(1.0, open_interest / max(min_open_interest * 5.0, 1.0))
    volume_score = 0.5 if volume is None else min(1.0, volume / max(min_volume * 25.0, 1.0))
    return _bounded_score(0.65 * oi_score + 0.35 * volume_score)


def _delta_score(*, delta: float | None, strategy_family: str | None) -> float:
    if delta is None:
        return 0.0
    abs_delta = abs(delta)
    if strategy_family in {"defined_risk_short_premium", "credit_spread", "defined_risk_only"}:
        target = 0.35
    else:
        target = 0.50
    return _bounded_score(1.0 - abs(abs_delta - target) / 0.50)


def _dte_score(dte: int | None) -> float:
    if dte is None:
        return 0.65
    if 21 <= dte <= 60:
        return 1.0
    if 7 <= dte < 21:
        return 0.75
    if 60 < dte <= 90:
        return 0.80
    return 0.35


def _moneyness_score(moneyness: float | None) -> float:
    if moneyness is None:
        return 0.65
    return _bounded_score(1.0 - abs(moneyness - 1.0) / 0.25)


def _greek_score(*, gamma: float | None, theta: float | None, vega: float | None) -> float:
    gamma_score = 0.75 if gamma is None else _bounded_score(1.0 - max(0.0, gamma - 0.03) / 0.08)
    theta_score = 0.75 if theta is None else _bounded_score(1.0 - max(0.0, abs(theta) - 0.04) / 0.12)
    vega_score = 0.75 if vega is None else _bounded_score(1.0 - max(0.0, vega - 0.12) / 0.30)
    return _bounded_score((gamma_score + theta_score + vega_score) / 3.0)


def _bounded_score(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _first_value(item: Mapping[str, Any] | None, keys: Sequence[str]) -> Any:
    if item is None:
        return None
    for key in keys:
        if key in item:
            value = item.get(key)
            if value is not None:
                return value
    return None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_symbol(value: Any) -> str | None:
    text = _clean_text(value)
    return text.upper() if text else None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _blocked_result(blocked_reasons: Sequence[str], *, source_artifacts: Mapping[str, Any]) -> dict[str, Any]:
    summary = {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "symbol_count": 0,
        "contract_readiness_symbol_count": 0,
        "scoreable_symbol_count": 0,
        "ready_contract_candidate_symbol_count": 0,
        "constrained_contract_candidate_symbol_count": 0,
        "data_review_symbol_count": 0,
        "blocked_symbol_count": 0,
        "needs_review_symbol_count": 0,
        "manual_review_symbol_count": 0,
        "contract_candidate_symbol_count": 0,
        "contract_candidate_count": 0,
        "ranked_contract_candidate_count": 0,
        "option_row_count": 0,
        "coverage_status_counts": {},
        "source_contract_readiness_status_counts": {},
        "strategy_family_counts": {},
        "ranked_contract_candidate_strategy_family_counts": {},
        "risk_flag_counts": {},
        "constraint_flag_counts": {},
        "data_review_reason_counts": {},
        "hard_block_reason_counts": {},
    }
    return {
        "artifact_type": "signalforge_contract_candidate_scoring",
        "schema_version": CONTRACT_CANDIDATE_SCORING_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "contract_candidate_scoring",
        "adapter_type": "contract_candidate_scoring_builder",
        "review_scope": "ranked_contract_candidate_review_not_contract_selection_or_execution",
        "source_artifacts": dict(source_artifacts),
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "blocked_reasons": list(blocked_reasons),
        "contract_candidate_scoring_items": [],
        "contract_candidate_score_queue": [],
        "ranked_contract_candidate_items": [],
        "contract_candidate_scoring_summary": summary,
        "thresholds": {},
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
