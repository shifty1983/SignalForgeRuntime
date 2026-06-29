from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping


def read_jsonl(path: str | Path) -> Iterable[Dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8", errors="ignore") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc
            if isinstance(payload, dict):
                yield payload


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _present(value: Any) -> bool:
    return value not in (None, "", [], {})


def build_phase4_strategy_selection_replay_qc_manifest(
    *,
    strategy_selection_rows_path: str | Path,
    strategy_selection_summary_path: str | Path,
    output_dir: str | Path,
) -> Dict[str, Any]:
    output_path = Path(output_dir)
    manifest_path = output_path / "signalforge_phase4_strategy_selection_replay_qc_manifest.json"

    rows = list(read_jsonl(strategy_selection_rows_path))

    summary = {}
    summary_path = Path(strategy_selection_summary_path)
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))

    selection_state_counts = Counter()
    selected_strategy_counts = Counter()
    no_trade_reason_counts = Counter()

    invalid_selection_state_count = 0
    selected_missing_strategy_count = 0
    selected_missing_regime_count = 0
    selected_missing_asset_behavior_count = 0
    selected_missing_option_behavior_count = 0
    selected_missing_expectancy_count = 0
    selected_expectancy_not_positive_count = 0
    selected_sample_below_minimum_count = 0

    rows_missing_candidate_count = 0
    rows_missing_rejected_candidate_count = 0
    rows_missing_rejected_strategy_counts = 0
    rows_missing_rejected_expectancy_state_counts = 0
    rows_missing_blocked_reason_counts = 0

    no_trade_missing_reason_count = 0
    no_trade_with_selected_strategy_count = 0

    rows_using_realized_outcome = 0
    rows_using_current_row_outcome = 0
    rows_using_future_rows = 0

    for row in rows:
        state = row.get("selection_state")
        selection_state_counts[str(state or "missing")] += 1

        if state not in ("selected", "no_trade"):
            invalid_selection_state_count += 1

        if "candidate_count" not in row:
            rows_missing_candidate_count += 1

        if "rejected_candidate_count" not in row:
            rows_missing_rejected_candidate_count += 1

        if "rejected_strategy_counts" not in row:
            rows_missing_rejected_strategy_counts += 1

        if "rejected_expectancy_state_counts" not in row:
            rows_missing_rejected_expectancy_state_counts += 1

        if "blocked_reason_counts" not in row:
            rows_missing_blocked_reason_counts += 1

        if row.get("selection_uses_realized_outcome") is True:
            rows_using_realized_outcome += 1

        if row.get("selection_uses_current_row_outcome") is True:
            rows_using_current_row_outcome += 1

        if row.get("selection_uses_future_rows") is True:
            rows_using_future_rows += 1

        if state == "selected":
            selected_strategy_counts[str(row.get("selected_strategy") or "missing")] += 1

            if not _present(row.get("selected_strategy")):
                selected_missing_strategy_count += 1

            if not _present(row.get("regime_state")):
                selected_missing_regime_count += 1

            if not _present(row.get("asset_behavior_state")):
                selected_missing_asset_behavior_count += 1

            if not _present(row.get("option_behavior_state")):
                selected_missing_option_behavior_count += 1

            if (
                not _present(row.get("selected_expectancy_state"))
                or not _present(row.get("selected_expectancy_average_return"))
                or not _present(row.get("selected_expectancy_sample_count"))
                or not _present(row.get("selected_expectancy_scope"))
            ):
                selected_missing_expectancy_count += 1

            if row.get("selected_expectancy_state") != "positive_expectancy_candidate":
                selected_expectancy_not_positive_count += 1

            sample_count = row.get("selected_expectancy_sample_count")
            minimum_sample_count = row.get("minimum_sample_count") or 20
            try:
                if int(sample_count) < int(minimum_sample_count):
                    selected_sample_below_minimum_count += 1
            except Exception:
                selected_sample_below_minimum_count += 1

        if state == "no_trade":
            no_trade_reason_counts[str(row.get("selection_reason") or "missing")] += 1

            if not _present(row.get("selection_reason")):
                no_trade_missing_reason_count += 1

            if _present(row.get("selected_strategy")):
                no_trade_with_selected_strategy_count += 1

    selected_row_count = selection_state_counts.get("selected", 0)
    no_trade_row_count = selection_state_counts.get("no_trade", 0)

    each_decision_row_has_terminal_state = (
        len(rows) > 0
        and invalid_selection_state_count == 0
        and selected_row_count + no_trade_row_count == len(rows)
    )

    rejected_strategies_recorded = (
        rows_missing_rejected_candidate_count == 0
        and rows_missing_rejected_strategy_counts == 0
        and rows_missing_rejected_expectancy_state_counts == 0
        and rows_missing_blocked_reason_counts == 0
    )

    selection_uses_required_context = (
        selected_row_count > 0
        and selected_missing_regime_count == 0
        and selected_missing_asset_behavior_count == 0
        and selected_missing_option_behavior_count == 0
        and selected_missing_expectancy_count == 0
    )

    no_future_leakage = (
        rows_using_realized_outcome == 0
        and rows_using_current_row_outcome == 0
        and rows_using_future_rows == 0
    )

    blockers = []

    if not each_decision_row_has_terminal_state:
        blockers.append("not_every_decision_row_has_selected_or_no_trade_state")

    if not rejected_strategies_recorded:
        blockers.append("rejected_strategy_details_missing")

    if not selection_uses_required_context:
        blockers.append("selection_missing_regime_asset_option_or_expectancy_context")

    if selected_missing_strategy_count:
        blockers.append("selected_rows_missing_strategy")

    if selected_expectancy_not_positive_count:
        blockers.append("selected_rows_not_positive_expectancy")

    if selected_sample_below_minimum_count:
        blockers.append("selected_rows_below_minimum_expectancy_sample")

    if no_trade_missing_reason_count or no_trade_with_selected_strategy_count:
        blockers.append("no_trade_rows_invalid")

    if not no_future_leakage:
        blockers.append("selection_leakage_detected")

    manifest = {
        "adapter_type": "phase4_strategy_selection_replay_qc_manifest_builder",
        "artifact_type": "signalforge_phase4_strategy_selection_replay_qc_manifest",
        "contract": "phase4_strategy_selection_replay_qc_manifest",
        "phase": "Phase 4: Strategy Selection Replay",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "input_selection_row_count": len(rows),
        "summary_counts": {
            "decision_group_count": summary.get("decision_group_count"),
            "selected_row_count": summary.get("selected_row_count"),
            "no_trade_row_count": summary.get("no_trade_row_count"),
            "selection_rate": summary.get("selection_rate"),
        },
        "selection_state_counts": dict(sorted(selection_state_counts.items())),
        "selected_strategy_counts": dict(sorted(selected_strategy_counts.items())),
        "no_trade_reason_counts": dict(sorted(no_trade_reason_counts.items())),
        "phase4_completion_criteria": {
            "each_decision_row_produces_selected_or_no_trade_state": each_decision_row_has_terminal_state,
            "rejected_strategies_are_recorded": rejected_strategies_recorded,
            "selection_uses_regime_asset_behavior_option_behavior_and_expectancy": selection_uses_required_context,
            "selection_does_not_use_realized_outcome_or_future_rows": no_future_leakage,
        },
        "validation_counts": {
            "invalid_selection_state_count": invalid_selection_state_count,
            "selected_missing_strategy_count": selected_missing_strategy_count,
            "selected_missing_regime_count": selected_missing_regime_count,
            "selected_missing_asset_behavior_count": selected_missing_asset_behavior_count,
            "selected_missing_option_behavior_count": selected_missing_option_behavior_count,
            "selected_missing_expectancy_count": selected_missing_expectancy_count,
            "selected_expectancy_not_positive_count": selected_expectancy_not_positive_count,
            "selected_sample_below_minimum_count": selected_sample_below_minimum_count,
            "rows_missing_candidate_count": rows_missing_candidate_count,
            "rows_missing_rejected_candidate_count": rows_missing_rejected_candidate_count,
            "rows_missing_rejected_strategy_counts": rows_missing_rejected_strategy_counts,
            "rows_missing_rejected_expectancy_state_counts": rows_missing_rejected_expectancy_state_counts,
            "rows_missing_blocked_reason_counts": rows_missing_blocked_reason_counts,
            "no_trade_missing_reason_count": no_trade_missing_reason_count,
            "no_trade_with_selected_strategy_count": no_trade_with_selected_strategy_count,
            "rows_using_realized_outcome": rows_using_realized_outcome,
            "rows_using_current_row_outcome": rows_using_current_row_outcome,
            "rows_using_future_rows": rows_using_future_rows,
        },
        "paths": {
            "strategy_selection_rows_path": str(strategy_selection_rows_path),
            "strategy_selection_summary_path": str(strategy_selection_summary_path),
            "manifest_path": str(manifest_path),
        },
    }

    write_json(manifest_path, manifest)
    return manifest
