from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from signalforge.rulebooks.prior_symbol_regime_state import (
    PriorSymbolRegimeStats,
    passes_prior_symbol_regime_gate,
)
from signalforge.rulebooks.spread_guardrail import (
    SPREAD_GUARDRAIL_MAX,
    passes_spread_guardrail,
)


DEFAULT_PORTFOLIO_CONSTRUCTION_SNAPSHOT = (
    "data/runtime/portfolio_construction/portfolio_construction_latest_snapshot.json"
)

DEFAULT_PRIOR_STATE = (
    "data/runtime/rule_state/v3_2_2_prior_symbol_regime_state.json"
)

DEFAULT_OPTION_QUOTE_SNAPSHOT = (
    "data/runtime/option_quotes/option_quote_snapshot.jsonl"
)

DEFAULT_OUTPUT = (
    "data/runtime/pre_trade_rules/v3_2_2_pre_trade_decisions.jsonl"
)


@dataclass(frozen=True)
class PreTradeDecisionBootstrapSummary:
    output_path: str
    is_ready: bool
    portfolio_candidate_count: int
    quote_snapshot_row_count: int
    prior_state_row_count: int
    decision_count: int
    accepted_count: int
    skipped_count: int
    spread_guardrail_skip_count: int
    prior_gate_skip_count: int
    missing_prior_state_count: int
    blocker_count: int
    blockers: tuple[str, ...]


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))

    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")

    return value


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()

            if not line:
                continue

            value = json.loads(line)

            if isinstance(value, dict):
                yield value


def _count_jsonl(path: Path) -> int:
    if not path.is_file():
        return 0

    with path.open("rb") as handle:
        return sum(1 for _ in handle)


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int:
    if value is None or value == "":
        return 0

    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _capital_label_from_starting_capital(value: Any) -> str | None:
    number = _safe_float(value)

    if number is None:
        return None

    if number >= 1000 and number % 1000 == 0:
        return f"{int(number // 1000)}k"

    return str(int(number))


def _infer_capital_label(row: dict[str, Any], snapshot: dict[str, Any]) -> str | None:
    row_label = row.get("capital_label")

    if row_label:
        return str(row_label)

    allocator_payload = row.get("allocator_payload")

    if isinstance(allocator_payload, dict):
        label = _capital_label_from_starting_capital(allocator_payload.get("starting_capital"))

        if label:
            return label

    recommended = snapshot.get("allocator_recommended_candidate")

    if isinstance(recommended, dict):
        label = _capital_label_from_starting_capital(recommended.get("starting_capital"))

        if label:
            return label

    return "30k"


def _iter_prior_records(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item

        return

    if not isinstance(payload, dict):
        return

    container_names = (
        "state_rows",
        "prior_symbol_regime_state_rows",
        "rows",
        "states",
        "items",
        "latest_rows",
    )

    for name in container_names:
        value = payload.get(name)

        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield item

    mapping_names = (
        "state_by_key",
        "latest_state_by_key",
        "prior_symbol_regime_state_by_key",
    )

    for name in mapping_names:
        value = payload.get(name)

        if isinstance(value, dict):
            for item in value.values():
                if isinstance(item, dict):
                    yield item


def _prior_record_to_stats(record: dict[str, Any]) -> PriorSymbolRegimeStats:
    profit_factor = (
        _safe_float(record.get("prior_profit_factor"))
        if record.get("prior_profit_factor") is not None
        else _safe_float(record.get("prior_pf"))
    )

    if profit_factor is None:
        profit_factor = _safe_float(record.get("profit_factor"))

    return PriorSymbolRegimeStats(
        prior_count=_safe_int(
            record.get("prior_count")
            if record.get("prior_count") is not None
            else record.get("sample_count")
        ),
        prior_net_pnl=_safe_float(
            record.get("prior_net_pnl")
            if record.get("prior_net_pnl") is not None
            else record.get("net_pnl")
        )
        or 0.0,
        prior_profit_factor=profit_factor,
    )


def _prior_record_key(record: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    capital_label = (
        record.get("capital_label")
        or record.get("capital")
        or record.get("capital_scenario")
        or record.get("starting_capital_label")
    )

    symbol = record.get("symbol")
    regime = record.get("regime_state") or record.get("regime")

    return (
        str(capital_label) if capital_label is not None else None,
        str(symbol) if symbol is not None else None,
        str(regime) if regime is not None else None,
    )


def _load_prior_state_by_key(path: Path) -> tuple[dict[tuple[str | None, str | None, str | None], PriorSymbolRegimeStats], int]:
    payload = _load_json(path)
    records = list(_iter_prior_records(payload))

    by_key: dict[tuple[str | None, str | None, str | None], PriorSymbolRegimeStats] = {}

    for record in records:
        key = _prior_record_key(record)

        if key[1] is None or key[2] is None:
            continue

        by_key[key] = _prior_record_to_stats(record)

    return by_key, len(records)


def _lookup_prior_stats(
    *,
    by_key: dict[tuple[str | None, str | None, str | None], PriorSymbolRegimeStats],
    capital_label: str | None,
    symbol: str | None,
    regime_state: str | None,
) -> PriorSymbolRegimeStats | None:
    if not symbol or not regime_state:
        return None

    exact_key = (capital_label, symbol, regime_state)

    if exact_key in by_key:
        return by_key[exact_key]

    fallback_keys = (
        ("30k", symbol, regime_state),
        ("40k", symbol, regime_state),
        (None, symbol, regime_state),
    )

    for key in fallback_keys:
        if key in by_key:
            return by_key[key]

    for (candidate_capital, candidate_symbol, candidate_regime), stats in by_key.items():
        if candidate_symbol == symbol and candidate_regime == regime_state:
            return stats

    return None


def _candidate_spread_pct(row: dict[str, Any]) -> float | None:
    for key in ("spread_pct", "entry_spread_pct", "option_spread_pct", "bid_ask_spread_pct"):
        value = _safe_float(row.get(key))

        if value is not None:
            return value

    leg_spreads: list[float] = []

    for leg_key in ("selected_entry_legs", "entry_legs", "selected_legs"):
        legs = row.get(leg_key)

        if not isinstance(legs, list):
            continue

        for leg in legs:
            if not isinstance(leg, dict):
                continue

            spread = _safe_float(leg.get("spread_pct"))

            if spread is not None:
                leg_spreads.append(spread)

    if leg_spreads:
        return max(leg_spreads)

    return None


def _portfolio_candidates(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    latest_rows = snapshot.get("latest_rows")

    if isinstance(latest_rows, list):
        return [row for row in latest_rows if isinstance(row, dict)]

    latest_by_symbol = snapshot.get("latest_rows_by_symbol")

    if isinstance(latest_by_symbol, dict):
        return [row for row in latest_by_symbol.values() if isinstance(row, dict)]

    return []


def _build_decision(
    *,
    row: dict[str, Any],
    snapshot: dict[str, Any],
    prior_state_by_key: dict[tuple[str | None, str | None, str | None], PriorSymbolRegimeStats],
) -> dict[str, Any]:
    capital_label = _infer_capital_label(row, snapshot)
    symbol = row.get("symbol")
    regime_state = row.get("regime_state")
    selected_strategy = row.get("selected_strategy")
    spread_pct = _candidate_spread_pct(row)

    prior_stats = _lookup_prior_stats(
        by_key=prior_state_by_key,
        capital_label=capital_label,
        symbol=str(symbol) if symbol is not None else None,
        regime_state=str(regime_state) if regime_state is not None else None,
    )

    spread_pass = passes_spread_guardrail(spread_pct)
    prior_pass = passes_prior_symbol_regime_gate(prior_stats)

    skip_reasons: list[str] = []

    if row.get("selection_state") not in (None, "selected"):
        skip_reasons.append("not_selected")

    if row.get("sizing_state") not in (None, "sized"):
        skip_reasons.append("not_sized")

    if spread_pct is None:
        skip_reasons.append("spread_missing")
    elif not spread_pass:
        skip_reasons.append("spread_gt_12_5pct")

    if prior_stats is None:
        prior_payload = None
    else:
        prior_payload = asdict(prior_stats)

    if prior_stats is not None and not prior_pass:
        skip_reasons.append("prior_symbol_regime_weak")

    final_action = "accept" if not skip_reasons else "skip"

    return {
        "contract": "v3_2_2_pre_trade_decision",
        "rulebook": "signalforge_v3_2_2",
        "decision_date": row.get("decision_date"),
        "portfolio_realization_date": row.get("portfolio_realization_date"),
        "symbol": symbol,
        "capital_label": capital_label,
        "regime_state": regime_state,
        "selected_strategy": selected_strategy,
        "sequence_id": row.get("sequence_id"),
        "trade_key": row.get("trade_key"),
        "selection_state": row.get("selection_state"),
        "sizing_state": row.get("sizing_state"),
        "spread_pct": spread_pct,
        "spread_guardrail_max": SPREAD_GUARDRAIL_MAX,
        "spread_guardrail_passed": spread_pass,
        "prior_state_found": prior_stats is not None,
        "prior_symbol_regime_stats": prior_payload,
        "prior_symbol_regime_gate_passed": prior_pass,
        "v3_2_1_action": "normal" if spread_pass else "skip_spread_gt_12_5pct",
        "v3_2_2_action": "normal" if prior_pass else "skip_prior_symbol_regime_weak",
        "paper_candidate_action": final_action,
        "skip_reasons": skip_reasons,
        "source_portfolio_row": row,
    }


def build_v3_2_2_pre_trade_decisions_bootstrap(
    *,
    portfolio_construction_snapshot_path: str | Path = DEFAULT_PORTFOLIO_CONSTRUCTION_SNAPSHOT,
    prior_state_path: str | Path = DEFAULT_PRIOR_STATE,
    option_quote_snapshot_path: str | Path = DEFAULT_OPTION_QUOTE_SNAPSHOT,
    output_path: str | Path = DEFAULT_OUTPUT,
) -> PreTradeDecisionBootstrapSummary:
    portfolio_path = Path(portfolio_construction_snapshot_path)
    prior_path = Path(prior_state_path)
    quote_path = Path(option_quote_snapshot_path)
    output = Path(output_path)

    blockers: list[str] = []

    if not portfolio_path.is_file():
        blockers.append("portfolio_construction_snapshot_missing")

    if not prior_path.is_file():
        blockers.append("prior_symbol_regime_state_missing")

    if not quote_path.is_file():
        blockers.append("option_quote_snapshot_missing")

    if blockers:
        return PreTradeDecisionBootstrapSummary(
            output_path=str(output),
            is_ready=False,
            portfolio_candidate_count=0,
            quote_snapshot_row_count=0,
            prior_state_row_count=0,
            decision_count=0,
            accepted_count=0,
            skipped_count=0,
            spread_guardrail_skip_count=0,
            prior_gate_skip_count=0,
            missing_prior_state_count=0,
            blocker_count=len(blockers),
            blockers=tuple(blockers),
        )

    snapshot = _load_json(portfolio_path)
    candidates = _portfolio_candidates(snapshot)
    prior_state_by_key, prior_state_row_count = _load_prior_state_by_key(prior_path)
    quote_snapshot_row_count = _count_jsonl(quote_path)

    if not candidates:
        blockers.append("no_portfolio_candidates")

    decisions = [
        _build_decision(
            row=row,
            snapshot=snapshot,
            prior_state_by_key=prior_state_by_key,
        )
        for row in candidates
    ]

    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", encoding="utf-8") as handle:
        for decision in decisions:
            handle.write(json.dumps(decision, sort_keys=True) + "\n")

    action_counts = Counter(decision["paper_candidate_action"] for decision in decisions)
    skip_reason_counts = Counter(
        reason
        for decision in decisions
        for reason in decision.get("skip_reasons", [])
    )

    return PreTradeDecisionBootstrapSummary(
        output_path=str(output),
        is_ready=not blockers,
        portfolio_candidate_count=len(candidates),
        quote_snapshot_row_count=quote_snapshot_row_count,
        prior_state_row_count=prior_state_row_count,
        decision_count=len(decisions),
        accepted_count=int(action_counts.get("accept", 0)),
        skipped_count=int(action_counts.get("skip", 0)),
        spread_guardrail_skip_count=int(skip_reason_counts.get("spread_gt_12_5pct", 0)),
        prior_gate_skip_count=int(skip_reason_counts.get("prior_symbol_regime_weak", 0)),
        missing_prior_state_count=sum(1 for decision in decisions if not decision.get("prior_state_found")),
        blocker_count=len(blockers),
        blockers=tuple(blockers),
    )


def summary_to_dict(summary: PreTradeDecisionBootstrapSummary) -> dict[str, Any]:
    return asdict(summary)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap V3.2.2 pre-trade decisions.")
    parser.add_argument("--portfolio-construction-snapshot", default=DEFAULT_PORTFOLIO_CONSTRUCTION_SNAPSHOT)
    parser.add_argument("--prior-state", default=DEFAULT_PRIOR_STATE)
    parser.add_argument("--option-quote-snapshot", default=DEFAULT_OPTION_QUOTE_SNAPSHOT)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-output", default="artifacts/v3_2_2_pre_trade_decisions_bootstrap_summary.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = build_v3_2_2_pre_trade_decisions_bootstrap(
        portfolio_construction_snapshot_path=args.portfolio_construction_snapshot,
        prior_state_path=args.prior_state,
        option_quote_snapshot_path=args.option_quote_snapshot,
        output_path=args.output,
    )

    summary_path = Path(args.summary_output)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True), encoding="utf-8")

    if args.json:
        print(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True))
    else:
        print(f"is_ready: {summary.is_ready}")
        print(f"portfolio_candidate_count: {summary.portfolio_candidate_count}")
        print(f"decision_count: {summary.decision_count}")
        print(f"accepted_count: {summary.accepted_count}")
        print(f"skipped_count: {summary.skipped_count}")
        print(f"spread_guardrail_skip_count: {summary.spread_guardrail_skip_count}")
        print(f"prior_gate_skip_count: {summary.prior_gate_skip_count}")
        print(f"missing_prior_state_count: {summary.missing_prior_state_count}")
        print(f"blocker_count: {summary.blocker_count}")

    return 0 if summary.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())


