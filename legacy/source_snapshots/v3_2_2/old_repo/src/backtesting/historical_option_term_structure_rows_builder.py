from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


def _as_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _as_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def _as_date(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value)
    if len(text) >= 10:
        return text[:10]
    return None


def _median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return float(statistics.median(values))


def _term_shape(spread: float, flat_threshold: float) -> str:
    if abs(spread) <= flat_threshold:
        return "flat"
    if spread > 0:
        return "contango"
    return "backwardation"


def iter_jsonl(path: str | Path) -> Iterable[Dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def build_historical_option_term_structure_rows(
    *,
    option_rows: Iterable[Mapping[str, Any]],
    min_dte: int = 7,
    max_dte: int = 90,
    max_abs_moneyness_diff: float = 0.15,
    min_contracts_per_expiration: int = 1,
    min_expiration_gap_days: int = 7,
    flat_threshold: float = 0.02,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    source_row_count = 0
    eligible_row_count = 0
    atm_filtered_row_count = 0
    rejected_counts: Counter[str] = Counter()

    expiration_groups: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    for row in option_rows:
        source_row_count += 1

        symbol = row.get("underlying_symbol")
        quote_date = _as_date(row.get("quote_date"))
        expiration = _as_date(row.get("expiration"))
        iv = _as_float(row.get("implied_volatility"))
        dte = _as_int(row.get("dte"))
        moneyness = _as_float(row.get("moneyness"))

        if not symbol:
            rejected_counts["missing_underlying_symbol"] += 1
            continue
        if not quote_date:
            rejected_counts["missing_quote_date"] += 1
            continue
        if not expiration:
            rejected_counts["missing_expiration"] += 1
            continue
        if iv is None or iv <= 0:
            rejected_counts["missing_or_invalid_implied_volatility"] += 1
            continue
        if dte is None:
            rejected_counts["missing_dte"] += 1
            continue
        if dte < min_dte or dte > max_dte:
            rejected_counts["dte_outside_range"] += 1
            continue

        eligible_row_count += 1

        if moneyness is not None and abs(moneyness - 1.0) > max_abs_moneyness_diff:
            rejected_counts["outside_atm_moneyness_band"] += 1
            continue

        atm_filtered_row_count += 1

        key = (str(symbol).upper(), quote_date, expiration)

        if key not in expiration_groups:
            expiration_groups[key] = {
                "symbol": str(symbol).upper(),
                "date": quote_date,
                "expiration": expiration,
                "dte_values": [],
                "iv_values": [],
                "contract_count": 0,
            }

        expiration_groups[key]["dte_values"].append(dte)
        expiration_groups[key]["iv_values"].append(iv)
        expiration_groups[key]["contract_count"] += 1

    symbol_date_expirations: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)

    for group in expiration_groups.values():
        if group["contract_count"] < min_contracts_per_expiration:
            continue

        expiration_iv = _median(group["iv_values"])
        expiration_dte = _median([float(value) for value in group["dte_values"]])

        if expiration_iv is None or expiration_dte is None:
            continue

        symbol_date_expirations[(group["symbol"], group["date"])].append(
            {
                "expiration": group["expiration"],
                "dte": int(round(expiration_dte)),
                "expiration_iv": expiration_iv,
                "contract_count": group["contract_count"],
            }
        )

    output_rows: List[Dict[str, Any]] = []
    shape_counts: Counter[str] = Counter()
    expiration_count_distribution: Counter[str] = Counter()
    skipped_symbol_date_counts: Counter[str] = Counter()

    for (symbol, date), expirations in symbol_date_expirations.items():
        expirations = sorted(expirations, key=lambda item: (item["dte"], item["expiration"]))
        expiration_count_distribution[str(len(expirations))] += 1

        if len(expirations) < 2:
            skipped_symbol_date_counts["less_than_two_expirations"] += 1
            continue

        selected_front = None
        selected_back = None

        for front_index, front in enumerate(expirations):
            for back in expirations[front_index + 1:]:
                if back["dte"] - front["dte"] >= min_expiration_gap_days:
                    selected_front = front
                    selected_back = back
                    break
            if selected_front and selected_back:
                break

        if not selected_front or not selected_back:
            skipped_symbol_date_counts["no_expiration_pair_with_required_gap"] += 1
            continue

        front_iv = selected_front["expiration_iv"]
        back_iv = selected_back["expiration_iv"]
        spread = back_iv - front_iv
        spread_pct = spread / front_iv if front_iv else None
        shape = _term_shape(spread, flat_threshold)
        shape_counts[shape] += 1

        output_rows.append(
            {
                "adapter_type": "historical_option_term_structure_rows_builder",
                "artifact_type": "signalforge_historical_option_term_structure_row",
                "contract": "historical_option_term_structure_rows",
                "symbol": symbol,
                "date": date,
                "term_structure_state": "available",
                "term_structure_shape": shape,
                "front_expiration": selected_front["expiration"],
                "back_expiration": selected_back["expiration"],
                "front_dte": selected_front["dte"],
                "back_dte": selected_back["dte"],
                "front_iv": front_iv,
                "back_iv": back_iv,
                "front_back_iv_spread": spread,
                "front_back_iv_spread_pct": spread_pct,
                "front_contract_count": selected_front["contract_count"],
                "back_contract_count": selected_back["contract_count"],
                "expiration_count": len(expirations),
                "data_state": "complete",
            }
        )

    output_rows.sort(key=lambda item: (item["date"], item["symbol"]))

    blockers: List[str] = []
    if not output_rows:
        blockers.append("no_complete_term_structure_rows_created")

    summary: Dict[str, Any] = {
        "adapter_type": "historical_option_term_structure_rows_builder",
        "artifact_type": "signalforge_historical_option_term_structure_rows",
        "contract": "historical_option_term_structure_rows",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "source_row_count": source_row_count,
        "eligible_row_count": eligible_row_count,
        "atm_filtered_row_count": atm_filtered_row_count,
        "expiration_group_count": len(expiration_groups),
        "symbol_date_count": len(symbol_date_expirations),
        "output_row_count": len(output_rows),
        "unique_symbols": len({row["symbol"] for row in output_rows}),
        "unique_dates": len({row["date"] for row in output_rows}),
        "term_structure_shape_counts": dict(sorted(shape_counts.items())),
        "expiration_count_distribution": dict(sorted(expiration_count_distribution.items())),
        "skipped_symbol_date_counts": dict(sorted(skipped_symbol_date_counts.items())),
        "rejected_source_row_counts": dict(sorted(rejected_counts.items())),
        "parameters": {
            "min_dte": min_dte,
            "max_dte": max_dte,
            "max_abs_moneyness_diff": max_abs_moneyness_diff,
            "min_contracts_per_expiration": min_contracts_per_expiration,
            "min_expiration_gap_days": min_expiration_gap_days,
            "flat_threshold": flat_threshold,
        },
        "paths": {},
    }

    return output_rows, summary


def build_historical_option_term_structure_rows_artifact(
    *,
    option_rows_path: str | Path,
    output_dir: str | Path,
    min_dte: int = 7,
    max_dte: int = 90,
    max_abs_moneyness_diff: float = 0.15,
    min_contracts_per_expiration: int = 1,
    min_expiration_gap_days: int = 7,
    flat_threshold: float = 0.02,
) -> Dict[str, Any]:
    output_path = Path(output_dir)

    rows_path = output_path / "signalforge_historical_option_term_structure_rows.jsonl"
    summary_path = output_path / "signalforge_historical_option_term_structure_rows_summary.json"

    rows, summary = build_historical_option_term_structure_rows(
        option_rows=iter_jsonl(option_rows_path),
        min_dte=min_dte,
        max_dte=max_dte,
        max_abs_moneyness_diff=max_abs_moneyness_diff,
        min_contracts_per_expiration=min_contracts_per_expiration,
        min_expiration_gap_days=min_expiration_gap_days,
        flat_threshold=flat_threshold,
    )

    summary["paths"] = {
        "option_rows_path": str(option_rows_path),
        "rows_path": str(rows_path),
        "summary_path": str(summary_path),
    }

    write_jsonl(rows_path, rows)
    write_json(summary_path, summary)

    return summary
