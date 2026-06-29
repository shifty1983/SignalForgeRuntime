from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable


DEFAULT_INPUT = "data/runtime/trade_outcomes/closed_trade_outcomes.jsonl"
DEFAULT_OUTPUT = "data/runtime/rule_state/v3_2_2_prior_symbol_regime_state.json"

V3_2_2_MIN_PRIOR_COUNT = 8
V3_2_2_MAX_PRIOR_NET_PNL = 0.0
V3_2_2_MAX_PRIOR_PROFIT_FACTOR = 0.90


@dataclass(frozen=True)
class PriorSymbolRegimeStateRow:
    capital_label: str
    symbol: str
    regime_state: str
    prior_count: int
    prior_net_pnl: float
    prior_profit_factor: float | None
    prior_win_rate: float
    winning_trade_count: int
    losing_trade_count: int
    gross_profit: float
    gross_loss_abs: float
    first_close_date: str | None
    last_close_date: str | None
    v3_2_2_gate_blocks: bool


@dataclass(frozen=True)
class PriorSymbolRegimeStateSummary:
    input_path: str
    output_path: str
    is_ready: bool
    input_row_count: int
    state_row_count: int
    blocking_state_count: int
    capital_labels: tuple[str, ...]
    blocker_count: int
    blockers: tuple[str, ...]


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue

            value = json.loads(line)
            if isinstance(value, dict):
                yield value


def _profit_factor(gross_profit: float, gross_loss_abs: float) -> float | None:
    if gross_loss_abs == 0:
        if gross_profit > 0:
            return None
        return 0.0
    return gross_profit / gross_loss_abs


def _gate_blocks(*, prior_count: int, prior_net_pnl: float, prior_profit_factor: float | None) -> bool:
    pf = 0.0 if prior_profit_factor is None else prior_profit_factor

    return (
        prior_count >= V3_2_2_MIN_PRIOR_COUNT
        and prior_net_pnl <= V3_2_2_MAX_PRIOR_NET_PNL
        and pf <= V3_2_2_MAX_PRIOR_PROFIT_FACTOR
    )


def build_state_rows(closed_rows: Iterable[dict[str, Any]]) -> tuple[PriorSymbolRegimeStateRow, int]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    input_row_count = 0

    for row in closed_rows:
        input_row_count += 1

        capital_label = str(row["capital_label"])
        symbol = str(row["symbol"])
        regime_state = str(row["regime_state"])

        groups.setdefault((capital_label, symbol, regime_state), []).append(row)

    state_rows: list[PriorSymbolRegimeStateRow] = []

    for (capital_label, symbol, regime_state), rows in sorted(groups.items()):
        pnls = [float(row.get("pnl") or 0.0) for row in rows]
        close_dates = sorted(
            close_date
            for close_date in (_parse_date(row.get("close_date")) for row in rows)
            if close_date is not None
        )

        gross_profit = sum(pnl for pnl in pnls if pnl > 0)
        gross_loss_abs = abs(sum(pnl for pnl in pnls if pnl < 0))
        prior_net_pnl = sum(pnls)
        prior_count = len(rows)
        winning_trade_count = sum(1 for pnl in pnls if pnl > 0)
        losing_trade_count = sum(1 for pnl in pnls if pnl < 0)
        prior_profit_factor = _profit_factor(gross_profit, gross_loss_abs)
        prior_win_rate = winning_trade_count / prior_count if prior_count else 0.0

        state_rows.append(
            PriorSymbolRegimeStateRow(
                capital_label=capital_label,
                symbol=symbol,
                regime_state=regime_state,
                prior_count=prior_count,
                prior_net_pnl=round(prior_net_pnl, 6),
                prior_profit_factor=None if prior_profit_factor is None else round(prior_profit_factor, 6),
                prior_win_rate=round(prior_win_rate, 6),
                winning_trade_count=winning_trade_count,
                losing_trade_count=losing_trade_count,
                gross_profit=round(gross_profit, 6),
                gross_loss_abs=round(gross_loss_abs, 6),
                first_close_date=close_dates[0].isoformat() if close_dates else None,
                last_close_date=close_dates[-1].isoformat() if close_dates else None,
                v3_2_2_gate_blocks=_gate_blocks(
                    prior_count=prior_count,
                    prior_net_pnl=prior_net_pnl,
                    prior_profit_factor=prior_profit_factor,
                ),
            )
        )

    return tuple(state_rows), input_row_count


def build_prior_symbol_regime_state(
    *,
    input_path: str | Path = DEFAULT_INPUT,
    output_path: str | Path = DEFAULT_OUTPUT,
) -> PriorSymbolRegimeStateSummary:
    input_file = Path(input_path)
    output_file = Path(output_path)

    blockers: list[str] = []

    if not input_file.is_file():
        blockers.append("closed_outcomes_input_missing")
        return PriorSymbolRegimeStateSummary(
            input_path=str(input_file),
            output_path=str(output_file),
            is_ready=False,
            input_row_count=0,
            state_row_count=0,
            blocking_state_count=0,
            capital_labels=tuple(),
            blocker_count=len(blockers),
            blockers=tuple(blockers),
        )

    state_rows, input_row_count = build_state_rows(_read_jsonl(input_file))

    if input_row_count == 0:
        blockers.append("closed_outcomes_input_empty")

    if not state_rows:
        blockers.append("no_prior_state_rows_built")

    payload = {
        "contract": "v3_2_2_prior_symbol_regime_state",
        "rule": {
            "scope": "capital_label + symbol + regime_state",
            "min_prior_count": V3_2_2_MIN_PRIOR_COUNT,
            "max_prior_net_pnl": V3_2_2_MAX_PRIOR_NET_PNL,
            "max_prior_profit_factor": V3_2_2_MAX_PRIOR_PROFIT_FACTOR,
            "action_when_blocked": "skip_trade",
        },
        "state_rows": [asdict(row) for row in state_rows],
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    blocking_state_count = sum(1 for row in state_rows if row.v3_2_2_gate_blocks)
    capital_labels = tuple(sorted({row.capital_label for row in state_rows}))

    return PriorSymbolRegimeStateSummary(
        input_path=str(input_file),
        output_path=str(output_file),
        is_ready=not blockers,
        input_row_count=input_row_count,
        state_row_count=len(state_rows),
        blocking_state_count=blocking_state_count,
        capital_labels=capital_labels,
        blocker_count=len(blockers),
        blockers=tuple(blockers),
    )


def summary_to_dict(summary: PriorSymbolRegimeStateSummary) -> dict[str, Any]:
    return asdict(summary)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build V3.2.2 prior symbol/regime state.")
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = build_prior_symbol_regime_state(
        input_path=args.input,
        output_path=args.output,
    )

    if args.json:
        print(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True))
    else:
        print(f"is_ready: {summary.is_ready}")
        print(f"input_row_count: {summary.input_row_count}")
        print(f"state_row_count: {summary.state_row_count}")
        print(f"blocking_state_count: {summary.blocking_state_count}")
        print(f"output_path: {summary.output_path}")

    return 0 if summary.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
