from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from signalforge.data.seed_bundle import resolve_seed_bundle_root


CLASSIFIER_SOURCE_RELATIVE_PATH = (
    "artifacts/qc_replay_5y_partitioned_option_behavior_classifier/"
    "signalforge_partitioned_option_behavior_classifier.json"
)

SOURCE_READINESS_RELATIVE_PATH = (
    "artifacts/qc_replay_5y_partitioned_option_behavior_source_readiness/"
    "signalforge_partitioned_option_behavior_source_readiness.json"
)

SYMBOL_READINESS_RELATIVE_PATH = (
    "artifacts/qc_replay_5y_option_source_symbol_readiness_consolidation/"
    "signalforge_option_source_symbol_readiness_consolidation.json"
)

DEFAULT_OUTPUT = "data/runtime/option_behavior/option_behavior_latest_snapshot.json"


@dataclass(frozen=True)
class OptionBehaviorBootstrapSummary:
    seed_bundle_root: str | None
    classifier_source_path: str | None
    source_readiness_path: str | None
    symbol_readiness_path: str | None
    output_path: str
    is_ready: bool
    classifier_is_ready: bool | None
    source_readiness_is_ready: bool | None
    symbol_readiness_is_ready: bool | None
    classifier_status: str | None
    source_readiness_status: str | None
    symbol_readiness_status: str | None
    symbol_count: int
    usable_symbol_count: int
    ready_symbol_count: int
    review_required_symbol_count: int
    blocked_symbol_count: int
    classifier_symbol_behavior_count: int
    total_option_row_count: int
    macro_regime_label: str | None
    policy_regime_label: str | None
    weekly_planning_label: str | None
    blocker_count: int
    blockers: tuple[str, ...]


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object JSON: {path}")
    return value


def _counter(items: Iterable[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(item.get(key)) for item in items if item.get(key) is not None).items()))


def _as_symbol_set(payload: dict[str, Any], key: str) -> set[str]:
    values = payload.get(key) or []
    if not isinstance(values, list):
        return set()
    return {str(value) for value in values if value is not None}


def _items_by_symbol(items: list[Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}

    for item in items:
        if not isinstance(item, dict):
            continue

        symbol = item.get("symbol")
        if not symbol:
            continue

        output[str(symbol)] = item

    return output


def _membership_gate(symbol: str, *, ready: set[str], review: set[str], blocked: set[str]) -> str:
    if symbol in blocked:
        return "blocked"
    if symbol in ready:
        return "ready"
    if symbol in review:
        return "review_required"
    return "unknown"


def _normalize_symbol_item(
    *,
    symbol: str,
    symbol_readiness_item: dict[str, Any] | None,
    classifier_item: dict[str, Any] | None,
    ready_symbols: set[str],
    review_required_symbols: set[str],
    blocked_symbols: set[str],
    usable_symbols: set[str],
) -> dict[str, Any]:
    symbol_readiness_item = symbol_readiness_item or {}
    classifier_item = classifier_item or {}

    downstream_gate = symbol_readiness_item.get("downstream_gate")
    global_state = symbol_readiness_item.get("global_state")
    classifier_gate = (
        classifier_item.get("option_behavior_gate")
        or classifier_item.get("global_gate")
        or classifier_item.get("symbol_global_gate")
        or classifier_item.get("downstream_gate")
    )

    membership_gate = _membership_gate(
        symbol,
        ready=ready_symbols,
        review=review_required_symbols,
        blocked=blocked_symbols,
    )

    return {
        "symbol": symbol,
        "downstream_gate": downstream_gate or membership_gate,
        "global_state": global_state,
        "classifier_gate": classifier_gate,
        "membership_gate": membership_gate,
        "is_usable": symbol in usable_symbols or membership_gate == "ready",
        "ready_partition_count": symbol_readiness_item.get("ready_partition_count"),
        "review_required_partition_count": symbol_readiness_item.get("review_required_partition_count"),
        "blocked_partition_count": symbol_readiness_item.get("blocked_partition_count"),
        "total_state_record_count": symbol_readiness_item.get("total_state_record_count"),
        "iv_level": classifier_item.get("iv_level"),
        "liquidity_state": classifier_item.get("liquidity_state"),
        "option_behavior_state": classifier_item.get("option_behavior_state"),
        "source_readiness_item": symbol_readiness_item,
        "classifier_item": classifier_item,
    }


def build_option_behavior_bootstrap(
    *,
    seed_bundle: str | Path | None = None,
    output_path: str | Path = DEFAULT_OUTPUT,
) -> OptionBehaviorBootstrapSummary:
    seed_root = resolve_seed_bundle_root(seed_bundle)
    output = Path(output_path)

    if seed_root is None:
        return OptionBehaviorBootstrapSummary(
            seed_bundle_root=None,
            classifier_source_path=None,
            source_readiness_path=None,
            symbol_readiness_path=None,
            output_path=str(output),
            is_ready=False,
            classifier_is_ready=None,
            source_readiness_is_ready=None,
            symbol_readiness_is_ready=None,
            classifier_status=None,
            source_readiness_status=None,
            symbol_readiness_status=None,
            symbol_count=0,
            usable_symbol_count=0,
            ready_symbol_count=0,
            review_required_symbol_count=0,
            blocked_symbol_count=0,
            classifier_symbol_behavior_count=0,
            total_option_row_count=0,
            macro_regime_label=None,
            policy_regime_label=None,
            weekly_planning_label=None,
            blocker_count=1,
            blockers=("seed_bundle_missing",),
        )

    classifier_path = seed_root / CLASSIFIER_SOURCE_RELATIVE_PATH
    source_readiness_path = seed_root / SOURCE_READINESS_RELATIVE_PATH
    symbol_readiness_path = seed_root / SYMBOL_READINESS_RELATIVE_PATH

    blockers: list[str] = []

    if not classifier_path.is_file():
        blockers.append("classifier_source_missing")

    if not source_readiness_path.is_file():
        blockers.append("source_readiness_missing")

    if not symbol_readiness_path.is_file():
        blockers.append("symbol_readiness_missing")

    if blockers:
        return OptionBehaviorBootstrapSummary(
            seed_bundle_root=str(seed_root),
            classifier_source_path=str(classifier_path),
            source_readiness_path=str(source_readiness_path),
            symbol_readiness_path=str(symbol_readiness_path),
            output_path=str(output),
            is_ready=False,
            classifier_is_ready=None,
            source_readiness_is_ready=None,
            symbol_readiness_is_ready=None,
            classifier_status=None,
            source_readiness_status=None,
            symbol_readiness_status=None,
            symbol_count=0,
            usable_symbol_count=0,
            ready_symbol_count=0,
            review_required_symbol_count=0,
            blocked_symbol_count=0,
            classifier_symbol_behavior_count=0,
            total_option_row_count=0,
            macro_regime_label=None,
            policy_regime_label=None,
            weekly_planning_label=None,
            blocker_count=len(blockers),
            blockers=tuple(blockers),
        )

    classifier = _load_json(classifier_path)
    source_readiness = _load_json(source_readiness_path)
    symbol_readiness = _load_json(symbol_readiness_path)

    if not classifier.get("is_ready"):
        blockers.append("classifier_not_ready")

    if classifier.get("status") != "ready":
        blockers.append("classifier_status_not_ready")

    if not source_readiness.get("is_ready"):
        blockers.append("source_readiness_not_ready")

    if source_readiness.get("status") != "ready":
        blockers.append("source_readiness_status_not_ready")

    if not symbol_readiness.get("is_ready"):
        blockers.append("symbol_readiness_not_ready")

    if symbol_readiness.get("status") != "ready":
        blockers.append("symbol_readiness_status_not_ready")

    symbol_items = symbol_readiness.get("symbol_items") or []
    classifier_symbol_items = classifier.get("symbol_behavior_items") or []

    symbol_readiness_by_symbol = _items_by_symbol(symbol_items)
    classifier_by_symbol = _items_by_symbol(classifier_symbol_items)

    usable_symbols = _as_symbol_set(symbol_readiness, "usable_symbols")
    ready_symbols = _as_symbol_set(classifier, "ready_symbols") or _as_symbol_set(source_readiness, "combined_ready_symbols")
    review_required_symbols = _as_symbol_set(classifier, "review_required_symbols") or _as_symbol_set(symbol_readiness, "review_required_symbols")
    blocked_symbols = _as_symbol_set(classifier, "blocked_symbols") or _as_symbol_set(symbol_readiness, "blocked_symbols")

    all_symbols = sorted(
        set(symbol_readiness_by_symbol)
        | set(classifier_by_symbol)
        | usable_symbols
        | ready_symbols
        | review_required_symbols
        | blocked_symbols
    )

    if not all_symbols:
        blockers.append("no_option_behavior_symbols")

    normalized_items = [
        _normalize_symbol_item(
            symbol=symbol,
            symbol_readiness_item=symbol_readiness_by_symbol.get(symbol),
            classifier_item=classifier_by_symbol.get(symbol),
            ready_symbols=ready_symbols,
            review_required_symbols=review_required_symbols,
            blocked_symbols=blocked_symbols,
            usable_symbols=usable_symbols,
        )
        for symbol in all_symbols
    ]

    snapshot = {
        "contract": "option_behavior_latest_snapshot",
        "classifier_source": CLASSIFIER_SOURCE_RELATIVE_PATH,
        "source_readiness_source": SOURCE_READINESS_RELATIVE_PATH,
        "symbol_readiness_source": SYMBOL_READINESS_RELATIVE_PATH,
        "classifier_artifact_type": classifier.get("artifact_type"),
        "classifier_schema_version": classifier.get("schema_version"),
        "source_readiness_artifact_type": source_readiness.get("artifact_type"),
        "source_readiness_schema_version": source_readiness.get("schema_version"),
        "symbol_readiness_artifact_type": symbol_readiness.get("artifact_type"),
        "symbol_readiness_schema_version": symbol_readiness.get("schema_version"),
        "classifier_status": classifier.get("status"),
        "classifier_is_ready": classifier.get("is_ready"),
        "source_readiness_status": source_readiness.get("status"),
        "source_readiness_is_ready": source_readiness.get("is_ready"),
        "symbol_readiness_status": symbol_readiness.get("status"),
        "symbol_readiness_is_ready": symbol_readiness.get("is_ready"),
        "macro_regime_label": symbol_readiness.get("macro_regime_label") or classifier.get("macro_regime_label"),
        "policy_regime_label": symbol_readiness.get("policy_regime_label") or classifier.get("policy_regime_label"),
        "weekly_planning_label": symbol_readiness.get("weekly_planning_label") or classifier.get("weekly_planning_label"),
        "symbol_count": len(all_symbols),
        "usable_symbol_count": len(usable_symbols),
        "ready_symbol_count": len(ready_symbols),
        "review_required_symbol_count": len(review_required_symbols),
        "blocked_symbol_count": len(blocked_symbols),
        "classifier_symbol_behavior_count": len(classifier_by_symbol),
        "total_option_row_count": int(classifier.get("total_option_row_count") or 0),
        "iv_level_counts": classifier.get("iv_level_counts") or {},
        "liquidity_state_counts": classifier.get("liquidity_state_counts") or {},
        "option_behavior_gate_counts": classifier.get("option_behavior_gate_counts") or {},
        "symbol_global_gate_counts": classifier.get("symbol_global_gate_counts") or {},
        "downstream_gate_counts": symbol_readiness.get("downstream_gate_counts") or {},
        "global_state_counts": symbol_readiness.get("global_state_counts") or {},
        "item_downstream_gate_counts": _counter(normalized_items, "downstream_gate"),
        "item_membership_gate_counts": _counter(normalized_items, "membership_gate"),
        "symbols": all_symbols,
        "usable_symbols": sorted(usable_symbols),
        "ready_symbols": sorted(ready_symbols),
        "review_required_symbols": sorted(review_required_symbols),
        "blocked_symbols": sorted(blocked_symbols),
        "items": normalized_items,
        "items_by_symbol": {
            item["symbol"]: item
            for item in normalized_items
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")

    return OptionBehaviorBootstrapSummary(
        seed_bundle_root=str(seed_root),
        classifier_source_path=str(classifier_path),
        source_readiness_path=str(source_readiness_path),
        symbol_readiness_path=str(symbol_readiness_path),
        output_path=str(output),
        is_ready=not blockers,
        classifier_is_ready=bool(classifier.get("is_ready")),
        source_readiness_is_ready=bool(source_readiness.get("is_ready")),
        symbol_readiness_is_ready=bool(symbol_readiness.get("is_ready")),
        classifier_status=classifier.get("status"),
        source_readiness_status=source_readiness.get("status"),
        symbol_readiness_status=symbol_readiness.get("status"),
        symbol_count=len(all_symbols),
        usable_symbol_count=len(usable_symbols),
        ready_symbol_count=len(ready_symbols),
        review_required_symbol_count=len(review_required_symbols),
        blocked_symbol_count=len(blocked_symbols),
        classifier_symbol_behavior_count=len(classifier_by_symbol),
        total_option_row_count=int(classifier.get("total_option_row_count") or 0),
        macro_regime_label=snapshot["macro_regime_label"],
        policy_regime_label=snapshot["policy_regime_label"],
        weekly_planning_label=snapshot["weekly_planning_label"],
        blocker_count=len(blockers),
        blockers=tuple(blockers),
    )


def summary_to_dict(summary: OptionBehaviorBootstrapSummary) -> dict[str, Any]:
    return asdict(summary)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap runtime option behavior snapshot.")
    parser.add_argument("--seed-bundle", default=None)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-output", default="artifacts/option_behavior_bootstrap_summary.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = build_option_behavior_bootstrap(seed_bundle=args.seed_bundle, output_path=args.output)

    summary_path = Path(args.summary_output)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True), encoding="utf-8")

    if args.json:
        print(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True))
    else:
        print(f"is_ready: {summary.is_ready}")
        print(f"symbol_count: {summary.symbol_count}")
        print(f"usable_symbol_count: {summary.usable_symbol_count}")
        print(f"ready_symbol_count: {summary.ready_symbol_count}")
        print(f"review_required_symbol_count: {summary.review_required_symbol_count}")
        print(f"blocked_symbol_count: {summary.blocked_symbol_count}")
        print(f"classifier_symbol_behavior_count: {summary.classifier_symbol_behavior_count}")
        print(f"total_option_row_count: {summary.total_option_row_count}")
        print(f"blocker_count: {summary.blocker_count}")

    return 0 if summary.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
