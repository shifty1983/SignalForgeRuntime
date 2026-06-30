from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from signalforge.data.seed_bundle import resolve_seed_bundle_root


ASSET_BEHAVIOR_SOURCE_RELATIVE_PATH = (
    "artifacts/qc_replay_5y_asset_behavior_decision_export_fred_regime_asset_class_mapped/"
    "signalforge_asset_behavior_decision_export.json"
)

DEFAULT_OUTPUT = "data/runtime/asset_behavior/asset_behavior_latest_snapshot.json"


@dataclass(frozen=True)
class AssetBehaviorBootstrapSummary:
    seed_bundle_root: str | None
    source_path: str | None
    output_path: str
    is_ready: bool
    source_is_ready: bool | None
    status: str | None
    item_count: int
    symbol_count: int
    eligible_long_count: int
    eligible_short_count: int
    neutral_position_count: int
    review_required_count: int
    blocked_count: int
    macro_regime_label: str | None
    policy_regime_label: str | None
    weekly_planning_label: str | None
    blocker_count: int
    blockers: tuple[str, ...]


def _count(items: Iterable[dict[str, Any]], key: str, value: str) -> int:
    return sum(1 for item in items if item.get(key) == value)


def _counter(items: Iterable[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(item.get(key)) for item in items if item.get(key) is not None).items()))


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": item.get("symbol"),
        "asset_class": item.get("asset_class"),
        "directional_stance": item.get("directional_stance"),
        "final_decision": item.get("final_decision"),
        "final_gate": item.get("final_gate"),
        "manual_review_required": item.get("manual_review_required"),
        "option_behavior_handoff": item.get("option_behavior_handoff"),
        "tradability_gate": item.get("tradability_gate"),
        "tradability_state": item.get("tradability_state"),
        "stance_gate": item.get("stance_gate"),
        "direction_fit_score": item.get("direction_fit_score"),
        "final_decision_score": item.get("final_decision_score"),
        "relative_strength_score": item.get("relative_strength_score"),
        "relative_weakness_score": item.get("relative_weakness_score"),
        "tradability_score": item.get("tradability_score"),
        "decision_reasons": item.get("decision_reasons") or [],
        "conflict_reasons": item.get("conflict_reasons") or [],
        "tradability_blocked_reasons": item.get("tradability_blocked_reasons") or [],
        "tradability_review_reasons": item.get("tradability_review_reasons") or [],
        "source_item": item,
    }


def build_asset_behavior_bootstrap(
    *,
    seed_bundle: str | Path | None = None,
    output_path: str | Path = DEFAULT_OUTPUT,
) -> AssetBehaviorBootstrapSummary:
    seed_root = resolve_seed_bundle_root(seed_bundle)
    output = Path(output_path)

    if seed_root is None:
        return AssetBehaviorBootstrapSummary(
            seed_bundle_root=None,
            source_path=None,
            output_path=str(output),
            is_ready=False,
            source_is_ready=None,
            status=None,
            item_count=0,
            symbol_count=0,
            eligible_long_count=0,
            eligible_short_count=0,
            neutral_position_count=0,
            review_required_count=0,
            blocked_count=0,
            macro_regime_label=None,
            policy_regime_label=None,
            weekly_planning_label=None,
            blocker_count=1,
            blockers=("seed_bundle_missing",),
        )

    source = seed_root / ASSET_BEHAVIOR_SOURCE_RELATIVE_PATH

    if not source.is_file():
        return AssetBehaviorBootstrapSummary(
            seed_bundle_root=str(seed_root),
            source_path=str(source),
            output_path=str(output),
            is_ready=False,
            source_is_ready=None,
            status=None,
            item_count=0,
            symbol_count=0,
            eligible_long_count=0,
            eligible_short_count=0,
            neutral_position_count=0,
            review_required_count=0,
            blocked_count=0,
            macro_regime_label=None,
            policy_regime_label=None,
            weekly_planning_label=None,
            blocker_count=1,
            blockers=("asset_behavior_source_missing",),
        )

    payload = json.loads(source.read_text(encoding="utf-8-sig"))
    items = payload.get("asset_behavior_decision_items") or []

    blockers: list[str] = []

    if not payload.get("is_ready"):
        blockers.append("source_not_ready")

    if payload.get("status") != "ready":
        blockers.append("source_status_not_ready")

    if not isinstance(items, list) or not items:
        blockers.append("no_asset_behavior_items")

    normalized_items = [_normalize_item(item) for item in items if isinstance(item, dict)]
    symbols = sorted({str(item["symbol"]) for item in normalized_items if item.get("symbol")})

    if len(symbols) != len(normalized_items):
        blockers.append("one_or_more_items_missing_symbol")

    snapshot = {
        "contract": "asset_behavior_latest_snapshot",
        "source": ASSET_BEHAVIOR_SOURCE_RELATIVE_PATH,
        "source_artifact_type": payload.get("artifact_type"),
        "source_schema_version": payload.get("schema_version"),
        "source_status": payload.get("status"),
        "source_is_ready": payload.get("is_ready"),
        "macro_regime_label": payload.get("macro_regime_label"),
        "policy_regime_label": payload.get("policy_regime_label"),
        "weekly_planning_label": payload.get("weekly_planning_label"),
        "aggregate_market_bias": payload.get("aggregate_market_bias"),
        "market_confirmation": payload.get("market_confirmation"),
        "item_count": len(normalized_items),
        "symbol_count": len(symbols),
        "final_decision_counts": _counter(normalized_items, "final_decision"),
        "final_gate_counts": _counter(normalized_items, "final_gate"),
        "asset_class_counts": _counter(normalized_items, "asset_class"),
        "tradability_state_counts": _counter(normalized_items, "tradability_state"),
        "option_behavior_handoff_counts": _counter(normalized_items, "option_behavior_handoff"),
        "symbols": symbols,
        "items": normalized_items,
        "items_by_symbol": {
            str(item["symbol"]): item
            for item in normalized_items
            if item.get("symbol")
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")

    eligible_long_count = _count(normalized_items, "final_decision", "eligible_long")
    eligible_short_count = _count(normalized_items, "final_decision", "eligible_short")
    neutral_position_count = _count(normalized_items, "final_decision", "neutral_position")
    review_required_count = _count(normalized_items, "final_gate", "review_required")
    blocked_count = _count(normalized_items, "final_gate", "blocked")

    return AssetBehaviorBootstrapSummary(
        seed_bundle_root=str(seed_root),
        source_path=str(source),
        output_path=str(output),
        is_ready=not blockers,
        source_is_ready=bool(payload.get("is_ready")),
        status=payload.get("status"),
        item_count=len(normalized_items),
        symbol_count=len(symbols),
        eligible_long_count=eligible_long_count,
        eligible_short_count=eligible_short_count,
        neutral_position_count=neutral_position_count,
        review_required_count=review_required_count,
        blocked_count=blocked_count,
        macro_regime_label=payload.get("macro_regime_label"),
        policy_regime_label=payload.get("policy_regime_label"),
        weekly_planning_label=payload.get("weekly_planning_label"),
        blocker_count=len(blockers),
        blockers=tuple(blockers),
    )


def summary_to_dict(summary: AssetBehaviorBootstrapSummary) -> dict[str, Any]:
    return asdict(summary)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap runtime asset behavior snapshot.")
    parser.add_argument("--seed-bundle", default=None)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-output", default="artifacts/asset_behavior_bootstrap_summary.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = build_asset_behavior_bootstrap(seed_bundle=args.seed_bundle, output_path=args.output)

    summary_path = Path(args.summary_output)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True), encoding="utf-8")

    if args.json:
        print(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True))
    else:
        print(f"is_ready: {summary.is_ready}")
        print(f"item_count: {summary.item_count}")
        print(f"symbol_count: {summary.symbol_count}")
        print(f"eligible_long_count: {summary.eligible_long_count}")
        print(f"eligible_short_count: {summary.eligible_short_count}")
        print(f"neutral_position_count: {summary.neutral_position_count}")
        print(f"review_required_count: {summary.review_required_count}")
        print(f"blocked_count: {summary.blocked_count}")
        print(f"blocker_count: {summary.blocker_count}")

    return 0 if summary.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())

