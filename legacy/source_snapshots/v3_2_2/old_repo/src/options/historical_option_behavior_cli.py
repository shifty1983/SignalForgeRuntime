from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence, TextIO

try:
    from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS
except Exception:  # pragma: no cover - allows standalone smoke tests
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

SCHEMA_VERSION = "signalforge_historical_option_behavior.v1"
DEFAULT_SOURCE = (
    "artifacts/qc_replay_5y_behavior_inputs/"
    "signalforge_qc_replay_option_behavior_input.jsonl"
)


@dataclass
class OptionAgg:
    contract_count: int = 0
    iv_count: int = 0
    iv_sum: float = 0.0
    iv_min: float | None = None
    iv_max: float | None = None
    spread_count: int = 0
    spread_sum: float = 0.0
    oi_count: int = 0
    open_interest_sum: float = 0.0
    volume_count: int = 0
    volume_sum: float = 0.0
    delta_count: int = 0
    abs_delta_sum: float = 0.0
    theta_count: int = 0
    abs_theta_sum: float = 0.0
    max_abs_theta: float = 0.0
    vega_count: int = 0
    abs_vega_sum: float = 0.0
    gamma_count: int = 0
    abs_gamma_sum: float = 0.0
    gamma_by_strike: dict[str, float] = field(default_factory=dict)
    gamma_by_expiration: dict[str, float] = field(default_factory=dict)
    call_otm_iv_sum: float = 0.0
    call_otm_iv_count: int = 0
    put_otm_iv_sum: float = 0.0
    put_otm_iv_count: int = 0
    near_iv_sum: float = 0.0
    near_iv_count: int = 0
    far_iv_sum: float = 0.0
    far_iv_count: int = 0
    atm_iv_sum: float = 0.0
    atm_iv_count: int = 0
    min_dte: int | None = None
    max_dte: int | None = None

    def update(self, row: Mapping[str, Any]) -> None:
        self.contract_count += 1

        iv = _to_float(row.get("implied_volatility") or row.get("iv"))
        if iv is not None and iv > 0:
            self.iv_count += 1
            self.iv_sum += iv
            self.iv_min = iv if self.iv_min is None else min(self.iv_min, iv)
            self.iv_max = iv if self.iv_max is None else max(self.iv_max, iv)

        spread = _to_float(row.get("spread_pct"))
        if spread is None:
            bid = _to_float(row.get("bid"))
            ask = _to_float(row.get("ask"))
            mid = _to_float(row.get("mid_price"))
            if bid is not None and ask is not None and mid is not None and mid > 0:
                spread = (ask - bid) / mid
        if spread is not None and spread >= 0:
            self.spread_count += 1
            self.spread_sum += spread

        oi = _to_float(row.get("open_interest"))
        if oi is not None and oi >= 0:
            self.oi_count += 1
            self.open_interest_sum += oi

        volume = _to_float(row.get("volume"))
        if volume is not None and volume >= 0:
            self.volume_count += 1
            self.volume_sum += volume

        delta = _to_float(row.get("delta"))
        if delta is not None:
            self.delta_count += 1
            self.abs_delta_sum += abs(delta)

        theta = _to_float(row.get("theta"))
        if theta is not None:
            abs_theta = abs(theta)
            self.theta_count += 1
            self.abs_theta_sum += abs_theta
            self.max_abs_theta = max(self.max_abs_theta, abs_theta)

        vega = _to_float(row.get("vega"))
        if vega is not None:
            self.vega_count += 1
            self.abs_vega_sum += abs(vega)

        gamma = _to_float(row.get("gamma"))
        if gamma is not None:
            abs_gamma = abs(gamma)
            self.gamma_count += 1
            self.abs_gamma_sum += abs_gamma
            strike = _clean_text(row.get("strike"))
            if strike:
                self.gamma_by_strike[strike] = self.gamma_by_strike.get(strike, 0.0) + abs_gamma
            expiration = _clean_text(row.get("expiration"))
            if expiration:
                self.gamma_by_expiration[expiration[:10]] = self.gamma_by_expiration.get(expiration[:10], 0.0) + abs_gamma

        dte = _to_int(row.get("dte"))
        if dte is not None:
            self.min_dte = dte if self.min_dte is None else min(self.min_dte, dte)
            self.max_dte = dte if self.max_dte is None else max(self.max_dte, dte)

        right = (_clean_text(row.get("option_right")) or "").lower()
        moneyness = _to_float(row.get("moneyness"))
        if iv is not None and iv > 0 and moneyness is not None:
            if abs(moneyness - 1.0) <= 0.05:
                self.atm_iv_sum += iv
                self.atm_iv_count += 1
            if right == "call" and moneyness > 1.02:
                self.call_otm_iv_sum += iv
                self.call_otm_iv_count += 1
            elif right == "put" and moneyness < 0.98:
                self.put_otm_iv_sum += iv
                self.put_otm_iv_count += 1

        if iv is not None and iv > 0 and dte is not None:
            if dte <= 45:
                self.near_iv_sum += iv
                self.near_iv_count += 1
            elif dte >= 60:
                self.far_iv_sum += iv
                self.far_iv_count += 1

    def to_base_metrics(self) -> dict[str, Any]:
        avg_iv = self.iv_sum / self.iv_count if self.iv_count else None
        atm_iv = self.atm_iv_sum / self.atm_iv_count if self.atm_iv_count else avg_iv
        avg_spread = self.spread_sum / self.spread_count if self.spread_count else None
        avg_abs_delta = self.abs_delta_sum / self.delta_count if self.delta_count else None
        avg_abs_theta = self.abs_theta_sum / self.theta_count if self.theta_count else None
        avg_abs_vega = self.abs_vega_sum / self.vega_count if self.vega_count else None
        avg_abs_gamma = self.abs_gamma_sum / self.gamma_count if self.gamma_count else None
        near_iv = self.near_iv_sum / self.near_iv_count if self.near_iv_count else None
        far_iv = self.far_iv_sum / self.far_iv_count if self.far_iv_count else None
        put_otm_iv = self.put_otm_iv_sum / self.put_otm_iv_count if self.put_otm_iv_count else None
        call_otm_iv = self.call_otm_iv_sum / self.call_otm_iv_count if self.call_otm_iv_count else None
        skew_spread = (put_otm_iv - call_otm_iv) if put_otm_iv is not None and call_otm_iv is not None else None
        term_spread = (far_iv - near_iv) if far_iv is not None and near_iv is not None else None
        dominant_strike, strike_share = _dominant_share(self.gamma_by_strike, self.abs_gamma_sum)
        dominant_expiration, expiration_share = _dominant_share(self.gamma_by_expiration, self.abs_gamma_sum)

        return {
            "contract_count": self.contract_count,
            "iv_observation_count": self.iv_count,
            "current_implied_volatility": _round(avg_iv),
            "atm_implied_volatility": _round(atm_iv),
            "min_contract_iv": _round(self.iv_min),
            "max_contract_iv": _round(self.iv_max),
            "avg_spread_pct": _round(avg_spread),
            "spread_observation_count": self.spread_count,
            "total_open_interest": _round(self.open_interest_sum),
            "open_interest_observation_count": self.oi_count,
            "total_volume": _round(self.volume_sum),
            "volume_observation_count": self.volume_count,
            "avg_abs_delta": _round(avg_abs_delta),
            "delta_observation_count": self.delta_count,
            "avg_abs_theta": _round(avg_abs_theta),
            "max_abs_theta": _round(self.max_abs_theta if self.theta_count else None),
            "theta_observation_count": self.theta_count,
            "avg_abs_vega": _round(avg_abs_vega),
            "vega_observation_count": self.vega_count,
            "total_abs_gamma": _round(self.abs_gamma_sum),
            "avg_abs_gamma": _round(avg_abs_gamma),
            "gamma_observation_count": self.gamma_count,
            "dominant_gamma_strike": dominant_strike,
            "dominant_gamma_strike_share": _round(strike_share),
            "dominant_gamma_expiration": dominant_expiration,
            "dominant_gamma_expiration_share": _round(expiration_share),
            "near_term_avg_iv": _round(near_iv),
            "far_term_avg_iv": _round(far_iv),
            "term_structure_spread": _round(term_spread),
            "put_otm_avg_iv": _round(put_otm_iv),
            "call_otm_avg_iv": _round(call_otm_iv),
            "put_call_skew_spread": _round(skew_spread),
            "min_dte": self.min_dte,
            "max_dte": self.max_dte,
        }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build historical point-in-time options behavior rows from QuantConnect "
            "option behavior JSONL. This does not call brokers, route orders, submit orders, "
            "model fills, perform live execution, or create automatic strategy actions."
        )
    )
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="Path to QC option behavior JSONL, JSON, .gz, or .zip source.")
    parser.add_argument("--output-dir", default="artifacts/historical_option_behavior", help="Directory for output artifacts.")
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--symbols", default=None, help="Optional comma-separated underlying symbols.")
    parser.add_argument("--min-history-points", type=int, default=3)
    parser.add_argument("--max-rows", type=int, default=None, help="Optional smoke-test cap on source rows read.")
    parser.add_argument("--progress-every", type=int, default=500000, help="Print progress every N source rows; 0 disables progress.")
    args = parser.parse_args(argv)

    source_path = Path(args.source)
    if not source_path.exists():
        raise SystemExit(f"option behavior source does not exist: {source_path}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    selected_symbols = _parse_symbols(args.symbols)
    start_date = _parse_date(args.start_date)
    end_date = _parse_date(args.end_date)

    result = build_historical_option_behavior(
        source_path=source_path,
        selected_symbols=selected_symbols,
        start_date=start_date,
        end_date=end_date,
        min_history_points=args.min_history_points,
        max_rows=args.max_rows,
        progress_every=args.progress_every,
    )

    result_path = output_dir / "signalforge_historical_option_behavior.json"
    summary_path = output_dir / "signalforge_historical_option_behavior_summary.json"
    rows_path = output_dir / "signalforge_historical_option_behavior_rows.jsonl"
    csv_path = output_dir / "signalforge_historical_option_behavior_rows.csv"

    rows = result.pop("historical_option_behavior_rows")

    with rows_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")

    _write_csv(csv_path, rows)

    result["paths"] = {
        "result": str(result_path),
        "summary": str(summary_path),
        "rows_jsonl": str(rows_path),
        "rows_csv": str(csv_path),
    }
    result["historical_option_behavior_row_count"] = len(rows)

    summary = _summary_result(result, rows)

    result_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0 if result.get("status") != "blocked" else 1


def build_historical_option_behavior(
    *,
    source_path: Path,
    selected_symbols: set[str] | None,
    start_date: date | None,
    end_date: date | None,
    min_history_points: int,
    max_rows: int | None,
    progress_every: int,
) -> dict[str, Any]:
    aggs: dict[tuple[str, str], OptionAgg] = {}
    malformed_examples: list[dict[str, Any]] = []
    source_row_count = 0
    accepted_row_count = 0
    skipped_out_of_window_count = 0
    skipped_symbol_count = 0
    symbol_set: set[str] = set()
    quote_date_set: set[str] = set()
    min_quote_date: str | None = None
    max_quote_date: str | None = None

    for row_index, row in enumerate(_iter_source_rows(source_path)):
        if max_rows is not None and source_row_count >= max_rows:
            break
        source_row_count += 1
        if progress_every and source_row_count % progress_every == 0:
            print(f"processed option rows: {source_row_count}", file=sys.stderr)

        if not isinstance(row, Mapping):
            _append_malformed(malformed_examples, row_index, "row must be a mapping")
            continue

        symbol = _clean_symbol(row.get("underlying_symbol") or row.get("symbol") or row.get("ticker"))
        quote_date = _clean_date_text(row.get("quote_date") or row.get("date") or row.get("timestamp"))
        if not symbol:
            _append_malformed(malformed_examples, row_index, "missing underlying_symbol")
            continue
        if not quote_date:
            _append_malformed(malformed_examples, row_index, "missing quote_date", symbol=symbol)
            continue

        if selected_symbols is not None and symbol not in selected_symbols:
            skipped_symbol_count += 1
            continue

        parsed_date = _parse_date(quote_date)
        if parsed_date is None:
            _append_malformed(malformed_examples, row_index, "invalid quote_date", symbol=symbol, quote_date=quote_date)
            continue
        if start_date is not None and parsed_date < start_date:
            skipped_out_of_window_count += 1
            continue
        if end_date is not None and parsed_date > end_date:
            skipped_out_of_window_count += 1
            continue

        accepted_row_count += 1
        symbol_set.add(symbol)
        quote_date_set.add(quote_date)
        min_quote_date = quote_date if min_quote_date is None or quote_date < min_quote_date else min_quote_date
        max_quote_date = quote_date if max_quote_date is None or quote_date > max_quote_date else max_quote_date
        key = (symbol, quote_date)
        if key not in aggs:
            aggs[key] = OptionAgg()
        aggs[key].update(row)

    if not aggs:
        return {
            "artifact_type": "signalforge_historical_option_behavior",
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "is_ready": False,
            "blocker_items": [{"reason": "no usable option behavior rows were found"}],
            "historical_option_behavior_rows": [],
            "source_row_count": source_row_count,
            "accepted_row_count": accepted_row_count,
            "malformed_row_examples": malformed_examples,
            "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        }

    rows_by_symbol: dict[str, list[tuple[str, OptionAgg]]] = defaultdict(list)
    for (symbol, quote_date), agg in aggs.items():
        rows_by_symbol[symbol].append((quote_date, agg))

    output_rows: list[dict[str, Any]] = []
    for symbol in sorted(rows_by_symbol):
        iv_history: list[float] = []
        prior_iv: float | None = None
        for quote_date, agg in sorted(rows_by_symbol[symbol], key=lambda item: item[0]):
            metrics = agg.to_base_metrics()
            current_iv = _to_float(metrics.get("current_implied_volatility"))
            if current_iv is not None and current_iv > 0:
                iv_history.append(current_iv)

            row = _build_behavior_row(
                symbol=symbol,
                quote_date=quote_date,
                metrics=metrics,
                current_iv=current_iv,
                prior_iv=prior_iv,
                iv_history=iv_history,
                min_history_points=min_history_points,
            )
            output_rows.append(row)
            if current_iv is not None and current_iv > 0:
                prior_iv = current_iv

    state_counts = Counter(row["options_behavior_state"] for row in output_rows)
    coverage_counts = Counter(row["coverage_status"] for row in output_rows)
    return {
        "artifact_type": "signalforge_historical_option_behavior",
        "schema_version": SCHEMA_VERSION,
        "status": "ready" if coverage_counts.get("ready", 0) else "needs_review",
        "is_ready": coverage_counts.get("ready", 0) > 0,
        "requires_manual_approval": True,
        "contract": "historical_option_behavior",
        "adapter_type": "historical_option_behavior_builder",
        "source_path": str(source_path),
        "source_row_count": source_row_count,
        "accepted_row_count": accepted_row_count,
        "skipped_symbol_row_count": skipped_symbol_count,
        "skipped_out_of_window_row_count": skipped_out_of_window_count,
        "malformed_row_example_count": len(malformed_examples),
        "malformed_row_examples": malformed_examples,
        "selected_symbols": sorted(selected_symbols) if selected_symbols else None,
        "underlying_symbol_count": len(symbol_set),
        "quote_date_count": len(quote_date_set),
        "quote_date_min": min_quote_date,
        "quote_date_max": max_quote_date,
        "min_history_points": min_history_points,
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "options_behavior_state_counts": dict(sorted(state_counts.items())),
        "historical_option_behavior_rows": output_rows,
        "next_step": "historical_regime_asset_options_alignment",
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_behavior_row(
    *,
    symbol: str,
    quote_date: str,
    metrics: Mapping[str, Any],
    current_iv: float | None,
    prior_iv: float | None,
    iv_history: Sequence[float],
    min_history_points: int,
) -> dict[str, Any]:
    history_count = len(iv_history)
    min_iv = min(iv_history) if iv_history else None
    max_iv = max(iv_history) if iv_history else None
    iv_rank = None
    iv_percentile = None
    if current_iv is not None and min_iv is not None and max_iv is not None and max_iv > min_iv and history_count >= min_history_points:
        iv_rank = ((current_iv - min_iv) / (max_iv - min_iv)) * 100.0
        iv_percentile = sum(1 for value in iv_history if value <= current_iv) / history_count * 100.0

    iv_change = current_iv - prior_iv if current_iv is not None and prior_iv is not None else None
    iv_change_pct = iv_change / prior_iv if iv_change is not None and prior_iv and prior_iv > 0 else None

    iv_history_state = "ready" if history_count >= min_history_points and current_iv is not None else "needs_review"
    iv_rank_state = _rank_state(iv_rank)
    iv_percentile_state = _percentile_state(iv_percentile)
    iv_expansion_state = _iv_expansion_state(iv_change, iv_change_pct)
    spread_state = _spread_state(_to_float(metrics.get("avg_spread_pct")))
    liquidity_state = _liquidity_state(
        contract_count=_to_int(metrics.get("contract_count")) or 0,
        total_open_interest=_to_float(metrics.get("total_open_interest")) or 0.0,
        total_volume=_to_float(metrics.get("total_volume")) or 0.0,
        avg_spread_pct=_to_float(metrics.get("avg_spread_pct")),
    )
    gamma_state = _gamma_state(
        total_abs_gamma=_to_float(metrics.get("total_abs_gamma")) or 0.0,
        strike_share=_to_float(metrics.get("dominant_gamma_strike_share")),
        expiration_share=_to_float(metrics.get("dominant_gamma_expiration_share")),
    )
    theta_state = _theta_state(_to_float(metrics.get("avg_abs_theta")), _to_float(metrics.get("max_abs_theta")))
    vega_state = _vega_state(_to_float(metrics.get("avg_abs_vega")))
    delta_state = "usable_delta_available" if (_to_int(metrics.get("delta_observation_count")) or 0) > 0 else "missing_delta"
    skew_state = _skew_state(_to_float(metrics.get("put_call_skew_spread")))
    term_state = _term_structure_state(_to_float(metrics.get("term_structure_spread")))
    oi_state = _open_interest_state(_to_float(metrics.get("total_open_interest")) or 0.0)
    volume_state = _volume_state(_to_float(metrics.get("total_volume")) or 0.0)
    premium_bias = _premium_bias(iv_rank_state, iv_percentile_state, iv_expansion_state)
    strategy_family_bias = _strategy_family_bias(premium_bias, liquidity_state, spread_state)
    coverage_status, readiness_reasons = _coverage_status(
        iv_history_state=iv_history_state,
        spread_state=spread_state,
        liquidity_state=liquidity_state,
        delta_state=delta_state,
        vega_state=vega_state,
    )
    behavior_state, behavior_reasons = _options_behavior_state(
        coverage_status=coverage_status,
        premium_bias=premium_bias,
        iv_expansion_state=iv_expansion_state,
        gamma_state=gamma_state,
        theta_state=theta_state,
        liquidity_state=liquidity_state,
        spread_state=spread_state,
    )

    return {
        "artifact_type": "historical_options_behavior_item",
        "symbol": symbol,
        "quote_date": quote_date,
        "coverage_status": coverage_status,
        "readiness_reasons": readiness_reasons,
        "options_behavior_state": behavior_state,
        "options_behavior_reasons": behavior_reasons,
        "strategy_selection_handoff": "available" if coverage_status == "ready" else "review_required",
        "iv_history_state": iv_history_state,
        "history_count": history_count,
        "min_history_points": min_history_points,
        "current_implied_volatility": _round(current_iv),
        "prior_implied_volatility": _round(prior_iv),
        "iv_change": _round(iv_change),
        "iv_change_pct": _round(iv_change_pct),
        "min_implied_volatility": _round(min_iv),
        "max_implied_volatility": _round(max_iv),
        "iv_rank": _round(iv_rank),
        "iv_percentile": _round(iv_percentile),
        "iv_rank_state": iv_rank_state,
        "iv_percentile_state": iv_percentile_state,
        "iv_expansion_state": iv_expansion_state,
        "premium_bias": premium_bias,
        "strategy_family_bias": strategy_family_bias,
        "gamma_concentration_state": gamma_state,
        "theta_sensitivity_state": theta_state,
        "vega_sensitivity": vega_state,
        "delta_availability": delta_state,
        "liquidity_state": liquidity_state,
        "spread_state": spread_state,
        "open_interest_behavior": oi_state,
        "volume_behavior": volume_state,
        "skew_state": skew_state,
        "term_structure_state": term_state,
        **dict(metrics),
        "manual_review_required": coverage_status != "ready",
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _iter_source_rows(path: Path) -> Iterable[Any]:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            members = [name for name in archive.namelist() if not name.endswith("/")]
            if not members:
                return
            # Prefer JSONL members because the QC replay option input is line-delimited.
            members = sorted(members, key=lambda name: (not name.lower().endswith(".jsonl"), name))
            with archive.open(members[0]) as raw:
                for line in raw:
                    if line.strip():
                        yield json.loads(line.decode("utf-8-sig"))
        return
    if suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8-sig") as handle:
            yield from _iter_text_rows(handle, path)
        return
    with path.open("r", encoding="utf-8-sig") as handle:
        yield from _iter_text_rows(handle, path)


def _iter_text_rows(handle: TextIO, path: Path) -> Iterable[Any]:
    if path.suffix.lower() == ".jsonl":
        for line in handle:
            if line.strip():
                yield json.loads(line)
        return

    payload = json.load(handle)
    if isinstance(payload, Mapping):
        for key in ("option_rows", "options", "quantconnect_option_rows", "rows", "data"):
            value = payload.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                yield from value
                return
        return
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        yield from payload


def _summary_result(result: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    fields = [
        "coverage_status",
        "options_behavior_state",
        "iv_rank_state",
        "iv_percentile_state",
        "iv_expansion_state",
        "premium_bias",
        "gamma_concentration_state",
        "theta_sensitivity_state",
        "liquidity_state",
        "spread_state",
        "skew_state",
        "term_structure_state",
    ]
    counts = {f"{field}_counts": dict(sorted(Counter(row.get(field) for row in rows).items())) for field in fields}
    return {
        "artifact_type": result.get("artifact_type"),
        "schema_version": result.get("schema_version"),
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "source_path": result.get("source_path"),
        "source_row_count": result.get("source_row_count"),
        "accepted_row_count": result.get("accepted_row_count"),
        "underlying_symbol_count": result.get("underlying_symbol_count"),
        "quote_date_count": result.get("quote_date_count"),
        "quote_date_min": result.get("quote_date_min"),
        "quote_date_max": result.get("quote_date_max"),
        "historical_option_behavior_row_count": len(rows),
        "malformed_row_example_count": result.get("malformed_row_example_count"),
        "skipped_symbol_row_count": result.get("skipped_symbol_row_count"),
        "skipped_out_of_window_row_count": result.get("skipped_out_of_window_row_count"),
        "next_step": result.get("next_step"),
        "paths": result.get("paths"),
        **counts,
        "explicit_exclusions": list(result.get("explicit_exclusions") or []),
    }


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    preferred = [
        "symbol", "quote_date", "coverage_status", "options_behavior_state", "strategy_selection_handoff",
        "current_implied_volatility", "iv_rank", "iv_percentile", "iv_rank_state", "iv_percentile_state",
        "iv_expansion_state", "premium_bias", "liquidity_state", "spread_state", "gamma_concentration_state",
        "theta_sensitivity_state", "vega_sensitivity", "delta_availability", "skew_state", "term_structure_state",
        "contract_count", "avg_spread_pct", "total_open_interest", "total_volume",
    ]
    keys = list(dict.fromkeys([*preferred, *[key for row in rows for key in row.keys()]]))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _coverage_status(*, iv_history_state: str, spread_state: str, liquidity_state: str, delta_state: str, vega_state: str) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if iv_history_state != "ready":
        reasons.append("iv_history_not_ready")
    if spread_state in {"blocked_wide_spread", "missing_spread"}:
        reasons.append(spread_state)
    if liquidity_state in {"illiquid_options", "missing_liquidity"}:
        reasons.append(liquidity_state)
    if delta_state == "missing_delta":
        reasons.append("missing_delta")
    if vega_state == "missing_vega":
        reasons.append("missing_vega")
    return ("ready" if not reasons else "needs_review", reasons or ["options_behavior_source_ready"])


def _options_behavior_state(*, coverage_status: str, premium_bias: str, iv_expansion_state: str, gamma_state: str, theta_state: str, liquidity_state: str, spread_state: str) -> tuple[str, list[str]]:
    if coverage_status != "ready":
        return "needs_review", ["coverage_not_ready"]
    reasons: list[str] = []
    if premium_bias == "premium_selling_bias":
        reasons.append("rich_or_high_iv_supports_premium_selling")
    elif premium_bias == "premium_buying_bias":
        reasons.append("cheap_or_low_iv_supports_premium_buying")
    else:
        reasons.append("neutral_premium_context")
    if iv_expansion_state in {"iv_expansion", "iv_spike"}:
        reasons.append("iv_expanding")
    if gamma_state == "concentrated_gamma":
        reasons.append("gamma_concentration_requires_strike_awareness")
    if theta_state in {"high_theta_sensitivity", "elevated_theta_sensitivity"}:
        reasons.append("theta_sensitivity_material")
    if liquidity_state == "liquid_options" and spread_state == "acceptable_spread":
        reasons.append("liquidity_and_spread_supported")
    if premium_bias == "premium_selling_bias":
        return "premium_selling_supported", reasons
    if premium_bias == "premium_buying_bias":
        return "premium_buying_supported", reasons
    return "neutral_options_context", reasons


def _premium_bias(iv_rank_state: str, iv_percentile_state: str, iv_expansion_state: str) -> str:
    if iv_rank_state == "high_iv_rank" or iv_percentile_state == "high_iv_percentile" or iv_expansion_state in {"iv_expansion", "iv_spike"}:
        return "premium_selling_bias"
    if iv_rank_state == "low_iv_rank" or iv_percentile_state == "low_iv_percentile" or iv_expansion_state == "iv_contraction":
        return "premium_buying_bias"
    return "neutral_premium_bias"


def _strategy_family_bias(premium_bias: str, liquidity_state: str, spread_state: str) -> str:
    if liquidity_state in {"illiquid_options", "missing_liquidity"} or spread_state in {"blocked_wide_spread", "missing_spread"}:
        return "avoid_or_review_options"
    if premium_bias == "premium_selling_bias":
        return "credit_defined_risk_or_income_bias"
    if premium_bias == "premium_buying_bias":
        return "debit_or_long_convexity_bias"
    return "balanced_defined_risk_bias"


def _iv_expansion_state(change: float | None, change_pct: float | None) -> str:
    if change is None:
        return "insufficient_prior_iv"
    if change >= 0.05 or (change_pct is not None and change_pct >= 0.25):
        return "iv_spike"
    if change >= 0.02 or (change_pct is not None and change_pct >= 0.10):
        return "iv_expansion"
    if change <= -0.02 or (change_pct is not None and change_pct <= -0.10):
        return "iv_contraction"
    return "iv_stable"


def _rank_state(value: float | None) -> str:
    if value is None:
        return "unclassified"
    if value >= 70.0:
        return "high_iv_rank"
    if value <= 30.0:
        return "low_iv_rank"
    return "normal_iv_rank"


def _percentile_state(value: float | None) -> str:
    if value is None:
        return "unclassified"
    if value >= 70.0:
        return "high_iv_percentile"
    if value <= 30.0:
        return "low_iv_percentile"
    return "normal_iv_percentile"


def _spread_state(avg_spread_pct: float | None) -> str:
    if avg_spread_pct is None:
        return "missing_spread"
    if avg_spread_pct <= 0.15:
        return "acceptable_spread"
    if avg_spread_pct <= 0.30:
        return "wide_spread_review"
    return "blocked_wide_spread"


def _liquidity_state(*, contract_count: int, total_open_interest: float, total_volume: float, avg_spread_pct: float | None) -> str:
    if contract_count <= 0:
        return "missing_liquidity"
    if total_open_interest >= 1000 and total_volume >= 10 and (avg_spread_pct is None or avg_spread_pct <= 0.20):
        return "liquid_options"
    if total_open_interest >= 250 or total_volume >= 3:
        return "moderate_liquidity_review"
    return "illiquid_options"


def _gamma_state(*, total_abs_gamma: float, strike_share: float | None, expiration_share: float | None) -> str:
    if total_abs_gamma <= 0.01:
        return "low_gamma"
    if (strike_share is not None and strike_share >= 0.35) or (expiration_share is not None and expiration_share >= 0.50):
        return "concentrated_gamma"
    return "distributed_gamma"


def _theta_state(avg_abs_theta: float | None, max_abs_theta: float | None) -> str:
    if avg_abs_theta is None:
        return "missing_theta"
    if avg_abs_theta >= 0.07 or (max_abs_theta is not None and max_abs_theta >= 0.12):
        return "high_theta_sensitivity"
    if avg_abs_theta >= 0.03:
        return "elevated_theta_sensitivity"
    if avg_abs_theta >= 0.01:
        return "normal_theta_sensitivity"
    return "low_theta_sensitivity"


def _vega_state(avg_abs_vega: float | None) -> str:
    if avg_abs_vega is None:
        return "missing_vega"
    if avg_abs_vega >= 0.10:
        return "high_vega_sensitivity"
    if avg_abs_vega >= 0.03:
        return "normal_vega_sensitivity"
    return "low_vega_sensitivity"


def _skew_state(skew_spread: float | None) -> str:
    if skew_spread is None:
        return "skew_not_available"
    if skew_spread >= 0.03:
        return "put_skew_rich"
    if skew_spread <= -0.03:
        return "call_skew_rich"
    return "balanced_skew"


def _term_structure_state(term_spread: float | None) -> str:
    if term_spread is None:
        return "term_structure_not_available"
    if term_spread >= 0.03:
        return "contango_term_structure"
    if term_spread <= -0.03:
        return "backwardated_term_structure"
    return "flat_term_structure"


def _open_interest_state(value: float) -> str:
    if value >= 1000:
        return "high_open_interest"
    if value >= 250:
        return "moderate_open_interest"
    return "low_open_interest"


def _volume_state(value: float) -> str:
    if value >= 100:
        return "high_volume"
    if value >= 10:
        return "moderate_volume"
    return "low_volume"


def _dominant_share(values: Mapping[str, float], total: float) -> tuple[str | None, float | None]:
    if not values or total <= 0:
        return None, None
    key, value = max(values.items(), key=lambda item: item[1])
    return key, value / total if total > 0 else None


def _append_malformed(rows: list[dict[str, Any]], row_index: int, reason: str, **extra: Any) -> None:
    if len(rows) < 100:
        rows.append({"row_index": row_index, "reason": reason, **extra})


def _parse_symbols(value: str | None) -> set[str] | None:
    if not value:
        return None
    symbols = {_clean_symbol(part) for part in value.split(",")}
    return {symbol for symbol in symbols if symbol}


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _clean_date_text(value: Any) -> str | None:
    parsed = _parse_date(value)
    return parsed.isoformat() if parsed else None


def _clean_symbol(value: Any) -> str | None:
    text = _clean_text(value)
    return text.upper() if text else None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    return int(number) if number is not None else None


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(value, digits)


if __name__ == "__main__":
    raise SystemExit(main())
