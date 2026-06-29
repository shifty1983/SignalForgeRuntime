from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional


def _as_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        value = float(value)
        if math.isnan(value):
            return None
        return value
    except Exception:
        return None


def read_jsonl(path: str | Path) -> Iterable[Dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8-sig", errors="ignore") as handle:
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


def build_phase5_trade_scoring_qc_manifest(
    *,
    selected_strategy_outcome_rows_path: str | Path,
    selected_strategy_outcome_summary_path: str | Path,
    output_dir: str | Path,
) -> Dict[str, Any]:
    output_path = Path(output_dir)
    manifest_path = output_path / "signalforge_phase5_trade_scoring_qc_manifest.json"

    rows = list(read_jsonl(selected_strategy_outcome_rows_path))

    summary = {}
    summary_path = Path(selected_strategy_outcome_summary_path)
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))

    selection_state_counts = Counter()
    data_state_counts = Counter()
    outcome_state_counts = Counter()
    complete_strategy_counts = Counter()
    partial_reason_counts = Counter()

    selected_count = 0
    no_trade_count = 0
    complete_selected_count = 0
    partial_selected_count = 0

    selected_missing_strategy_count = 0
    selected_missing_score_state_count = 0

    complete_missing_realized_return_count = 0
    complete_not_reconstructable_count = 0
    complete_missing_outcome_date_count = 0

    partial_missing_exclusion_reason_count = 0
    partial_marked_reconstructable_count = 0
    partial_has_realized_return_count = 0

    no_trade_invalid_state_count = 0
    no_trade_marked_selected_count = 0

    for row in rows:
        selection_state = row.get("selection_state")
        data_state = row.get("data_state")
        outcome_state = row.get("outcome_state")

        selection_state_counts[str(selection_state or "missing")] += 1
        data_state_counts[str(data_state or "missing")] += 1
        outcome_state_counts[str(outcome_state or "missing")] += 1

        if selection_state == "selected":
            selected_count += 1

            if not row.get("selected_strategy"):
                selected_missing_strategy_count += 1

            if not row.get("selected_expectancy_state"):
                selected_missing_score_state_count += 1

            if data_state == "complete":
                complete_selected_count += 1
                complete_strategy_counts[str(row.get("selected_strategy") or "missing")] += 1

                if _as_float(row.get("realized_return")) is None:
                    complete_missing_realized_return_count += 1

                if row.get("is_portfolio_reconstructable") is not True:
                    complete_not_reconstructable_count += 1

                if not row.get("selected_outcome_availability_date"):
                    complete_missing_outcome_date_count += 1

            else:
                partial_selected_count += 1
                reason = str(row.get("portfolio_exclusion_reason") or data_state or outcome_state or "missing")
                partial_reason_counts[reason] += 1

                if not row.get("portfolio_exclusion_reason"):
                    partial_missing_exclusion_reason_count += 1

                if row.get("is_portfolio_reconstructable") is True:
                    partial_marked_reconstructable_count += 1

                if _as_float(row.get("realized_return")) is not None:
                    partial_has_realized_return_count += 1

        elif selection_state == "no_trade":
            no_trade_count += 1

            if data_state != "no_trade" or outcome_state != "no_trade":
                no_trade_invalid_state_count += 1

            if row.get("is_selected_trade") is True:
                no_trade_marked_selected_count += 1

    selected_trades_scored_consistently = (
        selected_count > 0
        and selected_missing_strategy_count == 0
        and selected_missing_score_state_count == 0
        and complete_missing_realized_return_count == 0
        and complete_not_reconstructable_count == 0
        and complete_missing_outcome_date_count == 0
    )

    # Passing condition:
    # - If there are no partial selected trades, the pipeline is cleaner and this
    #   criterion should pass.
    # - If partial selected trades exist, every partial must be explicitly marked
    #   non-reconstructable, have an exclusion reason, and have no realized return.
    invalid_or_unpriceable_trades_marked = (
        partial_selected_count == 0
        or (
            partial_missing_exclusion_reason_count == 0
            and partial_marked_reconstructable_count == 0
            and partial_has_realized_return_count == 0
        )
    )

    no_trade_rows_marked = (
        no_trade_invalid_state_count == 0
        and no_trade_marked_selected_count == 0
    )

    outcome_logic_documented = True

    blockers = []

    if not selected_trades_scored_consistently:
        blockers.append("selected_trades_not_scored_consistently")

    if not invalid_or_unpriceable_trades_marked:
        blockers.append("invalid_or_unpriceable_trades_not_marked")

    if not no_trade_rows_marked:
        blockers.append("no_trade_rows_not_marked_consistently")

    if not outcome_logic_documented:
        blockers.append("outcome_logic_not_documented")

    manifest = {
        "adapter_type": "phase5_trade_scoring_qc_manifest_builder",
        "artifact_type": "signalforge_phase5_trade_scoring_qc_manifest",
        "contract": "phase5_trade_scoring_qc_manifest",
        "phase": "Phase 5: Trade Scoring",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "input_selected_strategy_outcome_row_count": len(rows),
        "summary_counts": {
            "input_selection_row_count": summary.get("input_selection_row_count"),
            "selected_row_count": summary.get("selected_row_count"),
            "no_trade_row_count": summary.get("no_trade_row_count"),
            "complete_selected_trade_count": summary.get("complete_selected_trade_count"),
            "partial_selected_trade_count": summary.get("partial_selected_trade_count"),
            "portfolio_reconstructable_trade_count": summary.get("portfolio_reconstructable_trade_count"),
        },
        "selection_state_counts": dict(sorted(selection_state_counts.items())),
        "data_state_counts": dict(sorted(data_state_counts.items())),
        "outcome_state_counts": dict(sorted(outcome_state_counts.items())),
        "complete_selected_strategy_counts": dict(sorted(complete_strategy_counts.items())),
        "partial_reason_counts": dict(sorted(partial_reason_counts.items())),
        "phase5_completion_criteria": {
            "selected_trades_are_scored_consistently": selected_trades_scored_consistently,
            "invalid_or_unpriceable_trades_are_marked": invalid_or_unpriceable_trades_marked,
            "no_trade_rows_are_marked_consistently": no_trade_rows_marked,
            "outcome_logic_is_documented": outcome_logic_documented,
        },
        "outcome_logic_documentation": {
            "complete_selected_trade_rule": "selected_data_state == complete and realized_return is present; row is portfolio_reconstructable",
            "partial_selected_trade_rule": "if partial selected trades exist, selected trade with missing exit quote or missing risk capital is marked non-reconstructable with portfolio_exclusion_reason; zero partial selected trades is a pass condition",
            "no_trade_rule": "no-trade rows are retained with data_state and outcome_state set to no_trade",
            "portfolio_reconstruction_rule": "only rows with is_portfolio_reconstructable == true are eligible for Phase 6 return math",
        },
        "validation_counts": {
            "selected_missing_strategy_count": selected_missing_strategy_count,
            "selected_missing_score_state_count": selected_missing_score_state_count,
            "complete_missing_realized_return_count": complete_missing_realized_return_count,
            "complete_not_reconstructable_count": complete_not_reconstructable_count,
            "complete_missing_outcome_date_count": complete_missing_outcome_date_count,
            "partial_missing_exclusion_reason_count": partial_missing_exclusion_reason_count,
            "partial_marked_reconstructable_count": partial_marked_reconstructable_count,
            "partial_has_realized_return_count": partial_has_realized_return_count,
            "no_trade_invalid_state_count": no_trade_invalid_state_count,
            "no_trade_marked_selected_count": no_trade_marked_selected_count,
        },
        "paths": {
            "selected_strategy_outcome_rows_path": str(selected_strategy_outcome_rows_path),
            "selected_strategy_outcome_summary_path": str(selected_strategy_outcome_summary_path),
            "manifest_path": str(manifest_path),
        },
    }

    write_json(manifest_path, manifest)
    return manifest
