# Auto-promoted by Stage 40C6B.
# Core engine for Stage 21 cohort-risk / pruned strategy selection.
# Backtesting should call this module instead of owning post-expectancy pruning logic.

from __future__ import annotations

import argparse
import copy
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


SYMBOL_ASSET_TYPE_MAP: dict[str, str] = {}


@dataclass
class PerfStats:
    count: int = 0
    wins: int = 0
    losses: int = 0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    total_return: float = 0.0

    def update(self, realized_return: float) -> None:
        self.count += 1
        self.total_return += realized_return

        if realized_return > 0:
            self.wins += 1
            self.gross_profit += realized_return
        elif realized_return < 0:
            self.losses += 1
            self.gross_loss += abs(realized_return)

    def profit_factor(self) -> float | None:
        if self.count <= 0:
            return None
        if self.gross_loss > 0:
            return self.gross_profit / self.gross_loss
        if self.gross_profit > 0:
            return 99.0
        return None

    def win_rate(self) -> float | None:
        if self.count <= 0:
            return None
        return self.wins / self.count

    def average_return(self) -> float | None:
        if self.count <= 0:
            return None
        return self.total_return / self.count


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None

    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def as_float(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default

    try:
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


def as_int(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default

    try:
        return int(float(value))
    except Exception:
        return default


def get_nested(row: dict[str, Any], *keys: str) -> Any:
    current: Any = row

    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)

    return current


def first_value(row: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def get_strategy(row: dict[str, Any]) -> str:
    value = first_value(
        row,
        [
            "selected_strategy",
            "strategy",
            "strategy_id",
            "candidate_strategy",
            "strategy_name",
        ],
    )

    return str(value or "")


def get_symbol(row: dict[str, Any]) -> str:
    return str(row.get("symbol") or "")


def get_regime_state(row: dict[str, Any]) -> str:
    value = first_value(row, ["regime_state", "regime"])
    return str(value or "unknown_regime")


def get_asset_type(row: dict[str, Any]) -> str:
    symbol = str(row.get("symbol") or "").upper()
    if symbol and symbol in SYMBOL_ASSET_TYPE_MAP:
        return SYMBOL_ASSET_TYPE_MAP[symbol]

    candidates = [
        row.get("asset_type"),
        row.get("asset_class"),
        row.get("underlying_asset_type"),
        row.get("symbol_asset_type"),
        get_nested(row, "research_context", "asset_behavior", "asset_type"),
        get_nested(row, "research_context", "asset_behavior", "asset_class"),
        get_nested(row, "research_context", "asset_behavior", "instrument_type"),
        get_nested(row, "asset_behavior", "asset_type"),
        get_nested(row, "asset_behavior", "asset_class"),
    ]

    for value in candidates:
        if value not in (None, ""):
            return str(value)

    return "unknown_asset_type"


def get_asset_behavior_state(row: dict[str, Any]) -> str:
    candidates = [
        row.get("asset_behavior_state"),
        row.get("asset_state"),
        row.get("behavior_state"),
        get_nested(row, "research_context", "asset_behavior", "asset_behavior_state"),
        get_nested(row, "research_context", "asset_behavior", "behavior_state"),
        get_nested(row, "research_context", "asset_behavior", "state"),
        get_nested(row, "research_context", "asset_behavior", "trend_state"),
        get_nested(row, "research_context", "asset_behavior", "momentum_state"),
        get_nested(row, "asset_behavior", "asset_behavior_state"),
        get_nested(row, "asset_behavior", "behavior_state"),
        get_nested(row, "asset_behavior", "state"),
    ]

    for value in candidates:
        if value not in (None, ""):
            return str(value)

    return "unknown_asset_behavior"


def get_option_behavior_state(row: dict[str, Any]) -> str:
    candidates = [
        row.get("options_behavior_state"),
        row.get("option_behavior_state"),
        get_nested(row, "research_context", "option_behavior", "options_behavior_state"),
        get_nested(row, "research_context", "option_behavior", "option_behavior_state"),
        get_nested(row, "research_context", "option_behavior", "state"),
        get_nested(row, "option_behavior", "options_behavior_state"),
        get_nested(row, "option_behavior", "option_behavior_state"),
    ]

    for value in candidates:
        if value not in (None, ""):
            return str(value)

    return "unknown_option_behavior"


def get_expectancy_score(row: dict[str, Any]) -> float:
    for key in [
        "selected_expectancy_score",
        "expectancy_score",
        "historical_edge_score",
        "risk_adjusted_edge_score",
    ]:
        value = as_float(row.get(key))
        if value is not None:
            return value

    return 0.0


def get_expectancy_sample_count(row: dict[str, Any]) -> int:
    for key in [
        "selected_expectancy_sample_count",
        "expectancy_sample_count",
        "sample_count",
        "training_sample_count",
    ]:
        value = as_int(row.get(key), -1)
        if value >= 0:
            return value

    return 0


def get_expectancy_state(row: dict[str, Any]) -> str:
    for key in [
        "selected_expectancy_state",
        "expectancy_state",
        "historical_edge_state",
    ]:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)

    return ""


def is_positive_expectancy(row: dict[str, Any]) -> bool:
    state = get_expectancy_state(row)

    if state == "positive_expectancy_candidate":
        return True

    if state in {"positive", "positive_edge_candidate"}:
        return True

    return get_expectancy_score(row) > 0


def get_realized_return(row: dict[str, Any]) -> float | None:
    for key in [
        "strategy_adjusted_return",
        "selected_strategy_adjusted_return",
        "realized_return",
        "return",
    ]:
        value = as_float(row.get(key))
        if value is not None:
            return value

    return None


def get_outcome_availability_date(row: dict[str, Any]) -> date | None:
    for key in [
        "outcome_availability_date",
        "portfolio_realization_date",
        "realization_date",
        "exit_date",
        "expiration_date",
    ]:
        parsed = parse_date(row.get(key))
        if parsed is not None:
            return parsed

    return None


def get_decision_date(row: dict[str, Any]) -> date | None:
    return parse_date(row.get("decision_date"))


def cohort_keys(row: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    asset_type = get_asset_type(row)
    asset_behavior_state = get_asset_behavior_state(row)
    strategy = get_strategy(row)
    regime = get_regime_state(row)
    option_state = get_option_behavior_state(row)

    return {
        "primary": (asset_type, asset_behavior_state, strategy, regime, option_state),
        "asset_behavior_strategy_regime": (asset_type, asset_behavior_state, strategy, regime),
        "asset_strategy_regime": (asset_type, strategy, regime),
        "asset_behavior_strategy_option": (asset_type, asset_behavior_state, strategy, option_state),
        "asset_strategy_option": (asset_type, strategy, option_state),
        "asset_behavior_strategy": (asset_type, asset_behavior_state, strategy),
        "asset_strategy": (asset_type, strategy),
        "strategy": (strategy,),
    }


def stats_payload(stats: PerfStats) -> dict[str, Any]:
    return {
        "sample_count": stats.count,
        "profit_factor": stats.profit_factor(),
        "win_rate": stats.win_rate(),
        "average_return": stats.average_return(),
        "gross_profit": stats.gross_profit,
        "gross_loss": stats.gross_loss,
    }


def pf_score(stats: PerfStats, min_sample: int, weight: float) -> float:
    if stats.count < min_sample:
        return 0.0

    pf = stats.profit_factor()
    if pf is None:
        return 0.0

    capped = max(0.10, min(10.0, pf))
    return weight * max(-2.0, min(2.0, math.log(capped)))


def classify_cohort(
    row: dict[str, Any],
    stats_by_key: dict[tuple[str, ...], PerfStats],
    args: argparse.Namespace,
) -> dict[str, Any]:
    keys = cohort_keys(row)

    primary = stats_by_key[keys["primary"]]
    asset_behavior_strategy_regime = stats_by_key[keys["asset_behavior_strategy_regime"]]
    asset_strategy_regime = stats_by_key[keys["asset_strategy_regime"]]
    asset_behavior_strategy_option = stats_by_key[keys["asset_behavior_strategy_option"]]
    asset_strategy_option = stats_by_key[keys["asset_strategy_option"]]
    asset_behavior_strategy = stats_by_key[keys["asset_behavior_strategy"]]
    asset_strategy = stats_by_key[keys["asset_strategy"]]
    strategy_stats = stats_by_key[keys["strategy"]]

    state = "normal"
    multiplier = 1.0
    reasons: list[str] = []

    strategy = get_strategy(row)
    asset_behavior_state = get_asset_behavior_state(row)
    regime = get_regime_state(row)
    option_state = get_option_behavior_state(row)
    sample_count = get_expectancy_sample_count(row)

    # Expectancy sample quality is available as of the decision date.
    if sample_count < args.min_expectancy_sample:
        state = "blocked"
        multiplier = 0.0
        reasons.append("expectancy_sample_below_minimum")

    # Primary cohort block/reduce rules.
    primary_pf = primary.profit_factor()
    if primary.count >= args.min_primary_sample and primary_pf is not None:
        if primary_pf < args.block_primary_pf_below:
            state = "blocked"
            multiplier = 0.0
            reasons.append("primary_cohort_pf_below_block_threshold")
        elif primary_pf < args.reduce_primary_pf_below and state != "blocked":
            state = "reduced"
            multiplier = min(multiplier, 0.5)
            reasons.append("primary_cohort_pf_below_reduce_threshold")

    # Asset-behavior/strategy/regime fallback rules.
    behavior_regime_pf = asset_behavior_strategy_regime.profit_factor()
    if asset_behavior_strategy_regime.count >= args.min_secondary_sample and behavior_regime_pf is not None:
        if behavior_regime_pf < args.block_secondary_pf_below:
            state = "blocked"
            multiplier = 0.0
            reasons.append("asset_behavior_strategy_regime_pf_below_block_threshold")
        elif behavior_regime_pf < args.reduce_secondary_pf_below and state not in {"blocked"}:
            state = "reduced"
            multiplier = min(multiplier, 0.5)
            reasons.append("asset_behavior_strategy_regime_pf_below_reduce_threshold")

    # Broader asset/strategy/regime fallback rules.
    regime_pf = asset_strategy_regime.profit_factor()
    if asset_strategy_regime.count >= args.min_secondary_sample and regime_pf is not None:
        if regime_pf < args.block_secondary_pf_below and state not in {"blocked"}:
            state = "blocked"
            multiplier = 0.0
            reasons.append("asset_strategy_regime_pf_below_block_threshold")
        elif regime_pf < args.reduce_secondary_pf_below and state not in {"blocked"}:
            state = "reduced"
            multiplier = min(multiplier, 0.5)
            reasons.append("asset_strategy_regime_pf_below_reduce_threshold")

    # Strategy fallback reduction, not hard block, unless evidence is poor and mature.
    strategy_pf = strategy_stats.profit_factor()
    if strategy_stats.count >= args.min_strategy_sample and strategy_pf is not None:
        if strategy_pf < args.reduce_strategy_pf_below and state not in {"blocked"}:
            state = "reduced"
            multiplier = min(multiplier, 0.5)
            reasons.append("strategy_pf_below_reduce_threshold")

    # Policy-level long-premium risk control.
    # This uses only current as-of regime/strategy labels, not future returns.
    if strategy in {"long_call", "long_put"}:
        if regime in {"deflationary_slowdown", "late_cycle_overheating"} and state not in {"blocked"}:
            state = "reduced"
            multiplier = min(multiplier, 0.5)
            reasons.append("long_premium_in_policy_reduced_regime")

        if strategy == "long_put" and regime == "goldilocks" and state not in {"blocked"}:
            state = "reduced"
            multiplier = min(multiplier, 0.5)
            reasons.append("long_put_goldilocks_policy_reduction")

    # Preferred rule requires enough current as-of evidence.
    if state == "normal":
        preferred = False

        if primary.count >= args.min_primary_sample:
            pf = primary.profit_factor()
            wr = primary.win_rate()
            if pf is not None and wr is not None and pf >= args.preferred_primary_pf and wr >= args.preferred_win_rate:
                preferred = True
                reasons.append("primary_cohort_preferred")

        if not preferred and asset_behavior_strategy_regime.count >= args.min_secondary_sample:
            pf = asset_behavior_strategy_regime.profit_factor()
            wr = asset_behavior_strategy_regime.win_rate()
            if pf is not None and wr is not None and pf >= args.preferred_secondary_pf and wr >= args.preferred_win_rate:
                preferred = True
                reasons.append("asset_behavior_strategy_regime_preferred")

        if not preferred and asset_strategy_regime.count >= args.min_secondary_sample:
            pf = asset_strategy_regime.profit_factor()
            wr = asset_strategy_regime.win_rate()
            if pf is not None and wr is not None and pf >= args.preferred_secondary_pf and wr >= args.preferred_win_rate:
                preferred = True
                reasons.append("asset_strategy_regime_preferred")

        if preferred:
            state = "preferred"
            multiplier = 1.25

    if (
        state == "normal"
        and primary.count < args.min_primary_sample
        and asset_behavior_strategy_regime.count < args.min_secondary_sample
        and asset_strategy_regime.count < args.min_secondary_sample
    ):
        state = "insufficient_history"
        multiplier = 0.75
        reasons.append("cohort_history_below_primary_and_secondary_minimum")

    selection_score = get_expectancy_score(row)
    selection_score += pf_score(primary, args.min_primary_sample, 0.35)
    selection_score += pf_score(asset_behavior_strategy_regime, args.min_secondary_sample, 0.30)
    selection_score += pf_score(asset_strategy_regime, args.min_secondary_sample, 0.20)
    selection_score += pf_score(asset_behavior_strategy, args.min_strategy_sample, 0.15)
    selection_score += pf_score(asset_strategy, args.min_strategy_sample, 0.10)

    if state == "preferred":
        selection_score += 0.20
    elif state == "normal":
        selection_score += 0.0
    elif state == "insufficient_history":
        selection_score -= 0.05
    elif state == "reduced":
        selection_score -= 0.25
    elif state == "blocked":
        selection_score = -999.0

    return {
        "cohort_risk_state": state,
        "cohort_risk_multiplier": multiplier,
        "cohort_risk_reasons": reasons,
        "asset_type": get_asset_type(row),
        "asset_behavior_state": asset_behavior_state,
        "strategy": strategy,
        "regime_state": regime,
        "option_behavior_state": option_state,
        "cohort_keys": {
            name: "|".join(value) for name, value in keys.items()
        },
        "asof_stats": {
            "primary": stats_payload(primary),
            "asset_behavior_strategy_regime": stats_payload(asset_behavior_strategy_regime),
            "asset_strategy_regime": stats_payload(asset_strategy_regime),
            "asset_behavior_strategy_option": stats_payload(asset_behavior_strategy_option),
            "asset_strategy_option": stats_payload(asset_strategy_option),
            "asset_behavior_strategy": stats_payload(asset_behavior_strategy),
            "asset_strategy": stats_payload(asset_strategy),
            "strategy": stats_payload(strategy_stats),
        },
        "cohort_adjusted_selection_score": selection_score,
        "leakage_controls": {
            "uses_current_trade_realized_return": False,
            "uses_future_rows": False,
            "uses_prior_available_outcomes_only": True,
            "asset_type_included_in_cohort_identity": True,
            "asset_behavior_included_in_cohort_identity": True,
        },
    }


def make_no_trade_row(group_rows: list[dict[str, Any]], reason: str) -> dict[str, Any]:
    template = group_rows[0] if group_rows else {}

    return {
        "decision_date": template.get("decision_date"),
        "symbol": template.get("symbol"),
        "selection_state": "no_trade",
        "selected_strategy": None,
        "selected_expectancy_state": None,
        "selected_expectancy_score": None,
        "selected_expectancy_sample_count": None,
        "selected_cohort_risk_state": None,
        "selected_cohort_risk_multiplier": None,
        "selection_skip_reasons": [reason],
        "candidate_count": len(group_rows),
        "contract": "historical_strategy_selection_rows",
    }


def make_selected_row(row: dict[str, Any], group_candidate_count: int) -> dict[str, Any]:
    out = copy.deepcopy(row)
    cohort = out.get("cohort_risk") or {}

    strategy = get_strategy(out)
    score = get_expectancy_score(out)
    sample_count = get_expectancy_sample_count(out)
    expectancy_state = get_expectancy_state(out)

    out["selection_state"] = "selected"
    out["selected_strategy"] = strategy
    out["selected_expectancy_score"] = score
    out["selected_expectancy_sample_count"] = sample_count
    out["selected_expectancy_state"] = expectancy_state or "positive_expectancy_candidate"

    realized_return = get_realized_return(out)
    if realized_return is not None:
        out["selected_strategy_adjusted_return"] = realized_return
        out["realized_return"] = realized_return

    out["selected_data_state"] = out.get("selected_data_state") or out.get("data_state")
    out["selected_outcome_state"] = out.get("selected_outcome_state") or out.get("outcome_state") or out.get("data_state")
    out["selected_cohort_risk_state"] = cohort.get("cohort_risk_state")
    out["selected_cohort_risk_multiplier"] = cohort.get("cohort_risk_multiplier")
    out["selected_cohort_adjusted_selection_score"] = cohort.get("cohort_adjusted_selection_score")
    out["selected_asset_type"] = cohort.get("asset_type")
    out["selected_asset_behavior_state"] = cohort.get("asset_behavior_state")
    out["candidate_count"] = group_candidate_count
    out["contract"] = "historical_strategy_selection_rows"

    return out


def run(args: argparse.Namespace) -> dict[str, Any]:
    input_path = Path(args.expectancy_rows)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = read_jsonl(input_path)

    rows_with_dates: list[tuple[int, date, dict[str, Any]]] = []
    missing_date_rows: list[tuple[int, dict[str, Any]]] = []

    for idx, row in enumerate(rows):
        decision_date = get_decision_date(row)
        if decision_date is None:
            missing_date_rows.append((idx, row))
        else:
            rows_with_dates.append((idx, decision_date, row))

    rows_with_dates.sort(key=lambda item: (item[1], item[0]))

    by_decision_date: dict[date, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    pending_outcomes: list[tuple[date, dict[str, Any]]] = []

    for idx, decision_date, row in rows_with_dates:
        by_decision_date[decision_date].append((idx, row))

        realized_return = get_realized_return(row)
        availability_date = get_outcome_availability_date(row)

        if realized_return is not None and availability_date is not None:
            pending_outcomes.append((availability_date, row))

    pending_outcomes.sort(key=lambda item: item[0])

    stats_by_key: dict[tuple[str, ...], PerfStats] = defaultdict(PerfStats)
    outcome_cursor = 0

    enriched_by_idx: dict[int, dict[str, Any]] = {}

    for current_date in sorted(by_decision_date):
        # Strictly before current_date to avoid same-day/current-row leakage.
        while outcome_cursor < len(pending_outcomes) and pending_outcomes[outcome_cursor][0] < current_date:
            _, outcome_row = pending_outcomes[outcome_cursor]
            realized_return = get_realized_return(outcome_row)

            if realized_return is not None:
                for key in cohort_keys(outcome_row).values():
                    stats_by_key[key].update(realized_return)

            outcome_cursor += 1

        for idx, row in by_decision_date[current_date]:
            out = copy.deepcopy(row)
            out["cohort_risk"] = classify_cohort(out, stats_by_key, args)
            enriched_by_idx[idx] = out

    for idx, row in missing_date_rows:
        out = copy.deepcopy(row)
        out["cohort_risk"] = {
            "cohort_risk_state": "blocked",
            "cohort_risk_multiplier": 0.0,
            "cohort_risk_reasons": ["missing_decision_date"],
            "asset_type": get_asset_type(out),
            "asset_behavior_state": get_asset_behavior_state(out),
            "strategy": get_strategy(out),
            "regime_state": get_regime_state(out),
            "option_behavior_state": get_option_behavior_state(out),
            "leakage_controls": {
                "uses_current_trade_realized_return": False,
                "uses_future_rows": False,
                "uses_prior_available_outcomes_only": True,
                "asset_type_included_in_cohort_identity": True,
            "asset_behavior_included_in_cohort_identity": True,
            },
        }
        enriched_by_idx[idx] = out

    enriched_rows = [enriched_by_idx[idx] for idx in sorted(enriched_by_idx)]

    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for row in enriched_rows:
        decision = str(row.get("decision_date") or "")
        symbol = str(row.get("symbol") or "")
        groups[(decision, symbol)].append(row)

    selection_rows: list[dict[str, Any]] = []
    selection_state_counts = Counter()
    selected_strategy_counts = Counter()
    cohort_state_counts = Counter()

    for _, group_rows in sorted(groups.items(), key=lambda item: item[0]):
        eligible: list[dict[str, Any]] = []

        for row in group_rows:
            cohort = row.get("cohort_risk") or {}
            state = cohort.get("cohort_risk_state")
            cohort_state_counts[state] += 1

            if not is_positive_expectancy(row):
                continue

            if state == "blocked":
                continue

            if not get_strategy(row):
                continue

            eligible.append(row)

        if not eligible:
            no_trade = make_no_trade_row(group_rows, "no_positive_expectancy_candidate_after_cohort_risk")
            selection_rows.append(no_trade)
            selection_state_counts["no_trade"] += 1
            continue

        eligible.sort(
            key=lambda row: (
                as_float((row.get("cohort_risk") or {}).get("cohort_adjusted_selection_score"), -999.0) or -999.0,
                get_expectancy_score(row),
                get_expectancy_sample_count(row),
            ),
            reverse=True,
        )

        winner = make_selected_row(eligible[0], len(group_rows))
        selection_rows.append(winner)
        selection_state_counts["selected"] += 1
        selected_strategy_counts[get_strategy(winner)] += 1

    enriched_path = output_dir / "signalforge_historical_strategy_cohort_risk_enriched_expectancy_rows.jsonl"
    selection_path = output_dir / "signalforge_historical_strategy_selection_cohort_risk_rows.jsonl"
    summary_path = output_dir / "signalforge_historical_strategy_selection_cohort_risk_summary.json"

    summary = {
        "adapter_type": "historical_strategy_selection_cohort_risk_builder",
        "artifact_type": "signalforge_historical_strategy_selection_cohort_risk",
        "contract": "historical_strategy_selection_cohort_risk",
        "is_ready": True,
        "blocker_count": 0,
        "blockers": [],
        "input_expectancy_rows": str(input_path),
        "input_row_count": len(rows),
        "enriched_row_count": len(enriched_rows),
        "decision_group_count": len(groups),
        "selection_row_count": len(selection_rows),
        "selected_row_count": selection_state_counts["selected"],
        "no_trade_row_count": selection_state_counts["no_trade"],
        "selection_state_counts": dict(selection_state_counts),
        "selected_strategy_counts": dict(selected_strategy_counts),
        "cohort_risk_state_counts": dict(cohort_state_counts),
        "cohort_definition": {
            "primary": "asset_type|asset_behavior_state|strategy|regime_state|option_behavior_state",
            "secondary": "asset_type|asset_behavior_state|strategy|regime_state",
            "fallback": "asset_type|strategy and strategy",
            "asset_type_included": True,
            "asset_behavior_included": True,
        },
        "leakage_controls": {
            "uses_current_trade_realized_return_for_classification": False,
            "uses_future_rows_for_classification": False,
            "uses_prior_available_outcomes_only": True,
            "current_trade_outcome_carried_only_for_downstream_replay": True,
            "asset_type_included_in_cohort_identity": True,
            "asset_behavior_included_in_cohort_identity": True,
        },
        "parameters": vars(args),
        "paths": {
            "enriched_expectancy_rows": str(enriched_path),
            "selection_rows": str(selection_path),
            "summary": str(summary_path),
        },
    }

    write_jsonl(enriched_path, enriched_rows)
    write_jsonl(selection_path, selection_rows)
    write_json(summary_path, summary)

    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build cohort-risk-aware strategy selection rows from walk-forward expectancy rows."
    )

    parser.add_argument("--expectancy-rows", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--symbol-asset-type-map", default=None)

    parser.add_argument("--min-expectancy-sample", type=int, default=20)
    parser.add_argument("--min-primary-sample", type=int, default=30)
    parser.add_argument("--min-secondary-sample", type=int, default=30)
    parser.add_argument("--min-strategy-sample", type=int, default=50)

    parser.add_argument("--block-primary-pf-below", type=float, default=0.80)
    parser.add_argument("--reduce-primary-pf-below", type=float, default=1.10)
    parser.add_argument("--block-secondary-pf-below", type=float, default=0.75)
    parser.add_argument("--reduce-secondary-pf-below", type=float, default=1.05)
    parser.add_argument("--reduce-strategy-pf-below", type=float, default=1.00)

    parser.add_argument("--preferred-primary-pf", type=float, default=2.00)
    parser.add_argument("--preferred-secondary-pf", type=float, default=1.75)
    parser.add_argument("--preferred-win-rate", type=float, default=0.55)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    global SYMBOL_ASSET_TYPE_MAP
    if args.symbol_asset_type_map:
        map_path = Path(args.symbol_asset_type_map)
        if map_path.exists():
            SYMBOL_ASSET_TYPE_MAP = {
                str(k).upper(): str(v)
                for k, v in json.loads(map_path.read_text(encoding="utf-8")).items()
            }

    summary = run(args)

    print(json.dumps(
        {
            "is_ready": summary["is_ready"],
            "blocker_count": summary["blocker_count"],
            "input_row_count": summary["input_row_count"],
            "enriched_row_count": summary["enriched_row_count"],
            "decision_group_count": summary["decision_group_count"],
            "selected_row_count": summary["selected_row_count"],
            "no_trade_row_count": summary["no_trade_row_count"],
            "selected_strategy_counts": summary["selected_strategy_counts"],
            "cohort_risk_state_counts": summary["cohort_risk_state_counts"],
            "leakage_controls": summary["leakage_controls"],
            "paths": summary["paths"],
        },
        indent=2,
        sort_keys=True,
    ))


if __name__ == "__main__":
    main()
