from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from statistics import mean, median
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


ARTIFACT_TYPE = "signalforge_partitioned_option_behavior_classifier"
SCHEMA_VERSION = "signalforge_partitioned_option_behavior_classifier.v1"

COMBINED_FILE = "signalforge_partitioned_option_behavior_classifier.json"
SUMMARY_FILE = "signalforge_partitioned_option_behavior_classifier_summary.json"

OPTION_FILE = "signalforge_qc_filtered_option_rows.json"
MANIFEST_FILE = "signalforge_qc_replay_manifest.json"


def build_signalforge_partitioned_option_behavior_classifier(
    *,
    asset_behavior_decision_export: Mapping[str, Any] | None,
    option_source_symbol_readiness: Mapping[str, Any] | None,
    inventory_source: Mapping[str, Any] | None,
    output_dir: str | Path,
    batch_limit: int | None = None,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    blocker_items: list[dict[str, Any]] = []
    warning_items: list[dict[str, Any]] = []

    if not isinstance(asset_behavior_decision_export, Mapping):
        asset_behavior_decision_export = {}
        blocker_items.append({"reason": "asset_behavior_decision_export_must_be_mapping"})

    if not isinstance(option_source_symbol_readiness, Mapping):
        option_source_symbol_readiness = {}
        blocker_items.append({"reason": "option_source_symbol_readiness_must_be_mapping"})

    if not isinstance(inventory_source, Mapping):
        inventory_source = {}
        blocker_items.append({"reason": "inventory_source_must_be_mapping"})

    decision_by_symbol = _asset_decision_by_symbol(asset_behavior_decision_export)
    readiness_by_symbol = _readiness_by_symbol(option_source_symbol_readiness)

    result_dirs = _extract_result_dirs(inventory_source)
    if batch_limit is not None:
        result_dirs = result_dirs[: max(0, int(batch_limit))]

    if not result_dirs:
        blocker_items.append({"reason": "missing_inventory_result_dirs"})

    partition_items: list[dict[str, Any]] = []
    partition_symbol_items: list[dict[str, Any]] = []
    total_option_rows = 0

    for partition_index, result_dir_text in enumerate(result_dirs):
        result_dir = Path(str(result_dir_text))
        partition_id = _partition_id(result_dir, partition_index)

        if not result_dir.exists():
            warning_items.append(
                {
                    "reason": "partition_result_dir_does_not_exist",
                    "partition_id": partition_id,
                    "result_dir": str(result_dir),
                }
            )
            continue

        try:
            manifest = _read_json(result_dir / MANIFEST_FILE)
            option_source = _read_json(result_dir / OPTION_FILE)
        except FileNotFoundError as exc:
            warning_items.append(
                {
                    "reason": "partition_missing_required_file",
                    "partition_id": partition_id,
                    "error": str(exc),
                }
            )
            continue
        except json.JSONDecodeError as exc:
            warning_items.append(
                {
                    "reason": "partition_invalid_json",
                    "partition_id": partition_id,
                    "error": str(exc),
                }
            )
            continue

        option_rows = _extract_option_rows(option_source)
        total_option_rows += len(option_rows)

        grouped_rows = _group_rows_by_underlying(option_rows)

        symbol_items: list[dict[str, Any]] = []
        for symbol, rows in sorted(grouped_rows.items()):
            decision = decision_by_symbol.get(symbol, {})
            readiness = readiness_by_symbol.get(symbol, {})
            item = _build_partition_symbol_item(
                symbol=symbol,
                rows=rows,
                partition_id=partition_id,
                partition_index=partition_index,
                request_id=manifest.get("request_id"),
                decision=decision,
                readiness=readiness,
            )
            symbol_items.append(item)
            partition_symbol_items.append(item)

        partition_status = "ready"
        partition_gate_counts = Counter(item["option_behavior_gate"] for item in symbol_items)

        if partition_gate_counts.get("blocked", 0) and not (
            partition_gate_counts.get("ready", 0) or partition_gate_counts.get("review_required", 0)
        ):
            partition_status = "blocked"
        elif partition_gate_counts.get("review_required", 0) or partition_gate_counts.get("blocked", 0):
            partition_status = "needs_review"

        partition_file = output_path / f"{partition_id}_option_behavior_classifier.json"
        partition_result = {
            "artifact_type": "signalforge_option_behavior_classifier_partition",
            "schema_version": f"{SCHEMA_VERSION}.partition",
            "status": partition_status,
            "is_ready": partition_status in {"ready", "needs_review"},
            "partition_id": partition_id,
            "partition_index": partition_index,
            "request_id": manifest.get("request_id"),
            "result_dir": str(result_dir),
            "option_row_count": len(option_rows),
            "symbol_count": len(symbol_items),
            "option_behavior_gate_counts": dict(sorted(partition_gate_counts.items())),
            "option_behavior_items": symbol_items,
            "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        }

        partition_file.write_text(
            json.dumps(partition_result, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )

        partition_items.append(
            {
                "artifact_type": "partitioned_option_behavior_classifier_partition_item",
                "partition_id": partition_id,
                "partition_index": partition_index,
                "request_id": manifest.get("request_id"),
                "result_dir": str(result_dir),
                "partition_status": partition_status,
                "partition_is_ready": partition_status in {"ready", "needs_review"},
                "option_row_count": len(option_rows),
                "symbol_count": len(symbol_items),
                "option_behavior_gate_counts": dict(sorted(partition_gate_counts.items())),
                "output_file": str(partition_file),
            }
        )

    if not partition_items:
        blocker_items.append({"reason": "no_partition_classifier_items_produced"})

    symbol_summary_items = _symbol_summary_items(
        partition_symbol_items,
        readiness_by_symbol=readiness_by_symbol,
        decision_by_symbol=decision_by_symbol,
    )

    option_behavior_gate_counts = Counter(
        item["option_behavior_gate"] for item in partition_symbol_items
    )
    symbol_global_gate_counts = Counter(
        item["global_option_behavior_gate"] for item in symbol_summary_items
    )
    iv_level_counts = Counter(
        item["dominant_iv_level"] for item in symbol_summary_items
    )
    liquidity_counts = Counter(
        item["dominant_liquidity_state"] for item in symbol_summary_items
    )

    status = "blocked" if blocker_items else "needs_review" if warning_items else "ready"

    combined = {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "partitioned_option_behavior_classifier",
        "adapter_type": "partitioned_option_behavior_classifier_builder",
        "source_artifacts": {
            "asset_behavior_decision_export": asset_behavior_decision_export.get("artifact_type"),
            "option_source_symbol_readiness": option_source_symbol_readiness.get("artifact_type"),
            "inventory": inventory_source.get("artifact_type"),
        },
        "source_statuses": {
            "asset_behavior_decision_export": asset_behavior_decision_export.get("status"),
            "option_source_symbol_readiness": option_source_symbol_readiness.get("status"),
            "inventory": inventory_source.get("status"),
        },
        "macro_regime_label": asset_behavior_decision_export.get("macro_regime_label")
        or option_source_symbol_readiness.get("macro_regime_label"),
        "policy_regime_label": asset_behavior_decision_export.get("policy_regime_label")
        or option_source_symbol_readiness.get("policy_regime_label"),
        "weekly_planning_label": asset_behavior_decision_export.get("weekly_planning_label")
        or option_source_symbol_readiness.get("weekly_planning_label"),
        "market_confirmation": asset_behavior_decision_export.get("market_confirmation"),
        "partition_count": len(partition_items),
        "requested_partition_count": len(result_dirs),
        "total_option_row_count": total_option_rows,
        "partition_symbol_item_count": len(partition_symbol_items),
        "symbol_count": len(symbol_summary_items),
        "option_behavior_gate_counts": dict(sorted(option_behavior_gate_counts.items())),
        "symbol_global_gate_counts": dict(sorted(symbol_global_gate_counts.items())),
        "iv_level_counts": dict(sorted(iv_level_counts.items())),
        "liquidity_state_counts": dict(sorted(liquidity_counts.items())),
        "ready_symbols": [
            item["symbol"]
            for item in symbol_summary_items
            if item["global_option_behavior_gate"] == "ready"
        ],
        "review_required_symbols": [
            item["symbol"]
            for item in symbol_summary_items
            if item["global_option_behavior_gate"] == "review_required"
        ],
        "blocked_symbols": [
            item["symbol"]
            for item in symbol_summary_items
            if item["global_option_behavior_gate"] == "blocked"
        ],
        "symbol_behavior_items": symbol_summary_items,
        "partition_items": partition_items,
        "blocker_items": blocker_items,
        "warning_items": warning_items,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }

    combined_path = output_path / COMBINED_FILE
    summary_path = output_path / SUMMARY_FILE

    combined_path.write_text(
        json.dumps(combined, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    summary = {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": f"{SCHEMA_VERSION}.summary",
        "status": status,
        "is_ready": status == "ready",
        "source_artifacts": combined["source_artifacts"],
        "source_statuses": combined["source_statuses"],
        "macro_regime_label": combined["macro_regime_label"],
        "policy_regime_label": combined["policy_regime_label"],
        "weekly_planning_label": combined["weekly_planning_label"],
        "partition_count": combined["partition_count"],
        "requested_partition_count": combined["requested_partition_count"],
        "total_option_row_count": total_option_rows,
        "partition_symbol_item_count": len(partition_symbol_items),
        "symbol_count": len(symbol_summary_items),
        "option_behavior_gate_counts": dict(sorted(option_behavior_gate_counts.items())),
        "symbol_global_gate_counts": dict(sorted(symbol_global_gate_counts.items())),
        "iv_level_counts": dict(sorted(iv_level_counts.items())),
        "liquidity_state_counts": dict(sorted(liquidity_counts.items())),
        "ready_symbol_count": len(combined["ready_symbols"]),
        "review_required_symbol_count": len(combined["review_required_symbols"]),
        "blocked_symbol_count": len(combined["blocked_symbols"]),
        "blocked_symbols": combined["blocked_symbols"],
        "blocker_count": len(blocker_items),
        "warning_count": len(warning_items),
        "files": {
            "combined": str(combined_path),
            "summary": str(summary_path),
        },
        "next_step": "join_regime_asset_option_behavior_to_contract_outcomes",
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }

    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    return summary


def _build_partition_symbol_item(
    *,
    symbol: str,
    rows: Sequence[Mapping[str, Any]],
    partition_id: str,
    partition_index: int,
    request_id: Any,
    decision: Mapping[str, Any],
    readiness: Mapping[str, Any],
) -> dict[str, Any]:
    metrics = _option_metrics(rows)

    readiness_gate = str(readiness.get("downstream_gate") or "review_required")
    asset_final_decision = str(decision.get("final_decision") or "unknown")
    asset_final_gate = str(decision.get("final_gate") or "unknown")
    asset_option_handoff = str(decision.get("option_behavior_handoff") or "unknown")

    gate, state, reasons = _option_behavior_gate(
        readiness_gate=readiness_gate,
        asset_option_handoff=asset_option_handoff,
        metrics=metrics,
    )

    return {
        "artifact_type": "partition_option_behavior_item",
        "symbol": symbol,
        "partition_id": partition_id,
        "partition_index": partition_index,
        "request_id": request_id,
        "asset_class": decision.get("asset_class") or "unknown",
        "asset_directional_stance": decision.get("directional_stance"),
        "asset_final_decision": asset_final_decision,
        "asset_final_gate": asset_final_gate,
        "asset_option_behavior_handoff": asset_option_handoff,
        "source_readiness_gate": readiness_gate,
        "option_behavior_gate": gate,
        "option_behavior_state": state,
        "option_behavior_reasons": reasons,
        "option_behavior_features": metrics,
    }


def _option_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ivs = _float_values(rows, ["implied_volatility", "implied_vol", "iv", "impliedVolatility"])
    deltas = _float_values(rows, ["delta"])
    gammas = _float_values(rows, ["gamma"])
    thetas = _float_values(rows, ["theta"])
    vegas = _float_values(rows, ["vega"])

    bids = _float_values(rows, ["bid", "bid_price", "bidPrice"])
    asks = _float_values(rows, ["ask", "ask_price", "askPrice"])
    volumes = _float_values(rows, ["volume", "option_volume"])
    open_interests = _float_values(rows, ["open_interest", "openInterest", "oi"])

    rights = [_option_right(row) for row in rows]
    call_count = sum(1 for right in rights if right == "call")
    put_count = sum(1 for right in rights if right == "put")

    expirations = sorted(
        {
            str(_first_present(row, ["expiration", "expiry", "expiry_date", "expiration_date"]))
            for row in rows
            if _first_present(row, ["expiration", "expiry", "expiry_date", "expiration_date"]) is not None
        }
    )
    strikes = {
        value
        for value in (_float_or_none(_first_present(row, ["strike", "strike_price"])) for row in rows)
        if value is not None
    }

    spreads: list[float] = []
    relative_spreads: list[float] = []
    for row in rows:
        bid = _float_or_none(_first_present(row, ["bid", "bid_price", "bidPrice"]))
        ask = _float_or_none(_first_present(row, ["ask", "ask_price", "askPrice"]))
        if bid is None or ask is None or ask < bid:
            continue

        spread = ask - bid
        spreads.append(spread)

        midpoint = (ask + bid) / 2
        if midpoint > 0:
            relative_spreads.append(spread / midpoint)

    call_ivs = [
        _float_or_none(_first_present(row, ["implied_volatility", "implied_vol", "iv", "impliedVolatility"]))
        for row in rows
        if _option_right(row) == "call"
    ]
    put_ivs = [
        _float_or_none(_first_present(row, ["implied_volatility", "implied_vol", "iv", "impliedVolatility"]))
        for row in rows
        if _option_right(row) == "put"
    ]
    call_ivs = [value for value in call_ivs if value is not None]
    put_ivs = [value for value in put_ivs if value is not None]

    avg_iv = mean(ivs) if ivs else None
    avg_relative_spread = mean(relative_spreads) if relative_spreads else None

    skew_value = None
    if call_ivs and put_ivs:
        skew_value = mean(put_ivs) - mean(call_ivs)

    return {
        "row_count": len(rows),
        "expiration_count": len(expirations),
        "strike_count": len(strikes),
        "call_count": call_count,
        "put_count": put_count,
        "implied_volatility_count": len(ivs),
        "average_implied_volatility": avg_iv,
        "median_implied_volatility": median(ivs) if ivs else None,
        "iv_level": _iv_level(avg_iv),
        "delta_count": len(deltas),
        "gamma_count": len(gammas),
        "theta_count": len(thetas),
        "vega_count": len(vegas),
        "greeks_coverage_state": _greeks_coverage_state(
            row_count=len(rows),
            delta_count=len(deltas),
            gamma_count=len(gammas),
            theta_count=len(thetas),
            vega_count=len(vegas),
        ),
        "bid_count": len(bids),
        "ask_count": len(asks),
        "spread_count": len(spreads),
        "average_spread": mean(spreads) if spreads else None,
        "median_spread": median(spreads) if spreads else None,
        "average_relative_spread": avg_relative_spread,
        "median_relative_spread": median(relative_spreads) if relative_spreads else None,
        "volume_count": len(volumes),
        "average_volume": mean(volumes) if volumes else None,
        "open_interest_count": len(open_interests),
        "average_open_interest": mean(open_interests) if open_interests else None,
        "liquidity_state": _liquidity_state(
            avg_relative_spread=avg_relative_spread,
            volumes=volumes,
            open_interests=open_interests,
            row_count=len(rows),
        ),
        "skew_value": skew_value,
        "skew_state": _skew_state(skew_value),
        "expiration_samples": expirations[:10],
    }


def _option_behavior_gate(
    *,
    readiness_gate: str,
    asset_option_handoff: str,
    metrics: Mapping[str, Any],
) -> tuple[str, str, list[str]]:
    reasons: list[str] = []

    if readiness_gate == "blocked":
        reasons.append("symbol_source_readiness_blocked")
        return "blocked", "option_behavior_blocked", reasons

    if metrics.get("row_count", 0) <= 0:
        reasons.append("missing_option_rows")
        return "blocked", "option_behavior_blocked", reasons

    if metrics.get("implied_volatility_count", 0) <= 0:
        reasons.append("missing_implied_volatility")

    if metrics.get("greeks_coverage_state") != "greeks_complete":
        reasons.append("greeks_incomplete")

    if metrics.get("liquidity_state") in {"liquidity_unknown", "illiquid"}:
        reasons.append(metrics.get("liquidity_state"))

    if readiness_gate == "review_required":
        reasons.append("symbol_source_readiness_review_required")

    if asset_option_handoff == "review_required":
        reasons.append("asset_option_behavior_handoff_review_required")

    if reasons:
        return "review_required", "option_behavior_needs_review", reasons

    return "ready", "option_behavior_ready", ["option_behavior_features_ready"]


def _symbol_summary_items(
    partition_symbol_items: Sequence[Mapping[str, Any]],
    *,
    readiness_by_symbol: Mapping[str, Mapping[str, Any]],
    decision_by_symbol: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for item in partition_symbol_items:
        grouped.setdefault(str(item.get("symbol") or "").upper(), []).append(item)

    items: list[dict[str, Any]] = []
    for symbol in sorted(set(grouped) | set(readiness_by_symbol)):
        partition_items = grouped.get(symbol, [])
        readiness = readiness_by_symbol.get(symbol, {})
        decision = decision_by_symbol.get(symbol, {})

        gate_counts = Counter(str(item.get("option_behavior_gate")) for item in partition_items)
        iv_levels = Counter(
            str((item.get("option_behavior_features") or {}).get("iv_level") or "unknown")
            for item in partition_items
        )
        liquidity_states = Counter(
            str((item.get("option_behavior_features") or {}).get("liquidity_state") or "unknown")
            for item in partition_items
        )

        if readiness.get("downstream_gate") == "blocked":
            global_gate = "blocked"
        elif gate_counts.get("ready", 0) > 0:
            global_gate = "ready"
        elif gate_counts.get("review_required", 0) > 0 or readiness.get("downstream_gate") == "review_required":
            global_gate = "review_required"
        else:
            global_gate = "blocked"

        row_count = sum(
            int((item.get("option_behavior_features") or {}).get("row_count") or 0)
            for item in partition_items
        )

        items.append(
            {
                "artifact_type": "option_behavior_symbol_summary_item",
                "symbol": symbol,
                "asset_class": decision.get("asset_class") or "unknown",
                "asset_directional_stance": decision.get("directional_stance"),
                "asset_final_decision": decision.get("final_decision"),
                "asset_option_behavior_handoff": decision.get("option_behavior_handoff"),
                "source_readiness_global_state": readiness.get("global_state"),
                "source_readiness_downstream_gate": readiness.get("downstream_gate"),
                "global_option_behavior_gate": global_gate,
                "partition_count_with_rows": len(partition_items),
                "total_option_row_count": row_count,
                "partition_gate_counts": dict(sorted(gate_counts.items())),
                "dominant_iv_level": _most_common(iv_levels, "unknown"),
                "dominant_liquidity_state": _most_common(liquidity_states, "unknown"),
            }
        )

    return items


def _asset_decision_by_symbol(source: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    items = source.get("asset_behavior_decision_items") or []
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes, bytearray)):
        return {}
    return {
        str(item.get("symbol") or "").upper(): item
        for item in items
        if isinstance(item, Mapping) and item.get("symbol")
    }


def _readiness_by_symbol(source: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    items = source.get("symbol_items") or []
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes, bytearray)):
        return {}
    return {
        str(item.get("symbol") or "").upper(): item
        for item in items
        if isinstance(item, Mapping) and item.get("symbol")
    }


def _extract_result_dirs(inventory_source: Mapping[str, Any]) -> list[str]:
    rows = inventory_source.get("results") or inventory_source.get("batches") or []
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        return []

    result_dirs: list[str] = []
    for row in rows:
        if isinstance(row, Mapping):
            value = row.get("result_dir") or row.get("decoded_result_dir") or row.get("source_dir")
            if value:
                result_dirs.append(str(value))

    return sorted(dict.fromkeys(result_dirs))


def _extract_option_rows(option_source: Mapping[str, Any]) -> list[Any]:
    for key in ("filtered_option_rows", "option_rows", "rows", "data"):
        value = option_source.get(key)
        if isinstance(value, list):
            return value
    return []


def _group_rows_by_underlying(rows: Sequence[Any]) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        symbol = _underlying_symbol(row)
        if symbol is None:
            continue
        grouped.setdefault(symbol, []).append(row)
    return grouped


def _underlying_symbol(row: Mapping[str, Any]) -> str | None:
    for key in (
        "underlying_symbol",
        "underlying",
        "underlying_ticker",
        "canonical_symbol",
        "root_symbol",
        "ticker",
    ):
        value = row.get(key)
        if value:
            text = str(value).strip().upper()
            if text:
                return text

    contract = row.get("contract")
    if isinstance(contract, Mapping):
        for key in ("underlying_symbol", "underlying", "root_symbol", "ticker"):
            value = contract.get(key)
            if value:
                text = str(value).strip().upper()
                if text:
                    return text

    symbol = str(row.get("symbol") or "").strip().upper()
    if not symbol:
        return None

    for separator in (" ", "_", "-"):
        if separator in symbol:
            root = symbol.split(separator, 1)[0].strip().upper()
            if root:
                return root

    if len(symbol) <= 6:
        return symbol

    return None


def _float_values(rows: Sequence[Mapping[str, Any]], keys: Sequence[str]) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = _float_or_none(_first_present(row, keys))
        if value is not None:
            values.append(value)
    return values


def _first_present(row: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key)
    return None


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _option_right(row: Mapping[str, Any]) -> str:
    value = str(
        _first_present(row, ["right", "option_right", "type", "option_type"]) or ""
    ).strip().lower()

    if value in {"c", "call", "calls"}:
        return "call"

    if value in {"p", "put", "puts"}:
        return "put"

    return "unknown"


def _iv_level(avg_iv: float | None) -> str:
    if avg_iv is None:
        return "iv_unknown"
    if avg_iv < 0.25:
        return "iv_low"
    if avg_iv < 0.60:
        return "iv_moderate"
    return "iv_high"


def _greeks_coverage_state(
    *,
    row_count: int,
    delta_count: int,
    gamma_count: int,
    theta_count: int,
    vega_count: int,
) -> str:
    if row_count <= 0:
        return "greeks_missing"

    required_counts = [delta_count, gamma_count, theta_count, vega_count]
    if all(count == row_count for count in required_counts):
        return "greeks_complete"

    if any(count > 0 for count in required_counts):
        return "greeks_partial"

    return "greeks_missing"


def _liquidity_state(
    *,
    avg_relative_spread: float | None,
    volumes: Sequence[float],
    open_interests: Sequence[float],
    row_count: int,
) -> str:
    if row_count <= 0:
        return "liquidity_unknown"

    has_activity = bool(volumes) or bool(open_interests)

    if avg_relative_spread is None:
        return "liquidity_unknown"

    if avg_relative_spread <= 0.10 and has_activity:
        return "liquid"

    if avg_relative_spread <= 0.25:
        return "moderate_liquidity"

    return "illiquid"


def _skew_state(skew_value: float | None) -> str:
    if skew_value is None:
        return "skew_unknown"

    if skew_value > 0.05:
        return "put_skew"

    if skew_value < -0.05:
        return "call_skew"

    return "balanced_skew"


def _most_common(counter: Counter[str], default: str) -> str:
    if not counter:
        return default
    return counter.most_common(1)[0][0]


def _partition_id(result_dir: Path, batch_index: int) -> str:
    batch_name = result_dir.name.replace(" ", "_")
    parent_name = result_dir.parent.name.replace(" ", "_")
    return f"{batch_index + 1:04d}_{parent_name}_{batch_name}"


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(str(path))
    return json.loads(path.read_text(encoding="utf-8-sig"))
