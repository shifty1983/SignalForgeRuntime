"""Portfolio deployment readiness / live translation review.

This builder is intentionally a deployment gate, not a performance scorer. It reads
existing historical replay, portfolio reconstruction, metrics, and stress validation
artifacts and checks whether the backtested decision flow can be translated into a
live or paper-trading workflow without future-only fields, manual-only dependencies,
unrealistic timing assumptions, or strategy execution gaps.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

ADAPTER_TYPE = "portfolio_deployment_readiness_live_translation_review_builder"
ARTIFACT_TYPE = "signalforge_portfolio_deployment_readiness_live_translation_review"
CONTRACT = "portfolio_deployment_readiness_live_translation_review"

OUTPUT_BASENAME = "signalforge_portfolio_deployment_readiness_live_translation_review"

LIVE_DECISION_STAGES = {"decision_rows", "strategy_selection_rows"}
EVIDENCE_ONLY_STAGES = {
    "selected_trade_sequence_summary",
    "position_sizing_summary",
    "equity_reconstruction_summary",
    "metrics_report",
    "stress_validation_summary",
    "stress_validation_scenarios",
}

# Fields with these terms are generally only known after the decision/trade. The
# classifier treats historical/prior/asof/rolling/trailing aggregates differently.
FUTURE_OR_OUTCOME_TERMS = (
    "future",
    "forward",
    "lookahead",
    "realized",
    "actual_return",
    "post_entry",
    "post_trade",
    "after_entry",
    "after_exit",
    "trade_outcome",
    "contract_outcome",
    "final_outcome",
    "exit_price",
    "exit_timestamp",
    "exit_date",
    "closed_at",
    "close_timestamp",
    "close_date",
    "trade_pnl",
    "total_pnl",
    "net_pnl",
    "gross_pnl",
    "profit_loss",
    "pnl",
    "profit",
    "loss",
    "winner",
    "loser",
    "is_win",
    "is_loss",
    "winning_trade",
    "losing_trade",
    "mfe",
    "mae",
    "max_favorable_excursion",
    "max_adverse_excursion",
)

# These prefixes/phrases usually mean the value is a prior-history aggregate rather
# than the specific future result of the current candidate trade.
ASOF_SAFE_PRIOR_TERMS = (
    "historical",
    "prior",
    "asof",
    "as_of",
    "rolling",
    "trailing",
    "lookback",
    "expectancy",
    "edge_score",
    "edge_state",
    "average_strategy_adjusted",
    "median_strategy_adjusted",
    "sample_count",
    "sample_limited",
    "win_rate_prior",
    "historical_win_rate",
)

# Guardrail flags are live-facing safety assertions. They should block only when
# any observed value indicates leakage; all-false flags prove the opposite.
LIVE_SAFETY_ASSERTION_FIELDS = (
    "selection_uses_future_rows",
    "selection_uses_realized_outcome",
    "selection_uses_current_row_outcome",
    "source_candidate.uses_future_rows",
)

# These fields are carried for validation/reporting and must not drive live
# selection. They are allowed in live-stage artifacts as diagnostics but should
# remain excluded from the live decision feature set.
BACKTEST_ONLY_DIAGNOSTIC_FIELDS = (
    "eligibility.eligible_for_contract_outcome_validation",
    "source_candidate.eligibility.eligible_for_contract_outcome_validation",
    "source_candidate.strategy_pnl",
    "source_candidate.trade_pnl",
    "source_candidate.realized_trade_return",
)

# Planned or rule-derived exit dates can be known at entry if produced from a
# fixed-horizon or explicit close rule. They still require execution-rule review,
# but they are not automatically future leakage.
RULE_DERIVED_SCHEDULE_TERMS = (
    "target_exit_date",
    "planned_exit_date",
    "scheduled_exit_date",
    "expiration_date",
    "expiry_date",
)

MANUAL_TERMS = (
    "manual",
    "copy_paste",
    "copy paste",
    "uploaded",
    "human",
    "review_required",
    "requires_review",
    "requires_manual_approval",
    "manual_approval",
)

LIVE_DATA_TERMS = (
    "regime",
    "asset_behavior",
    "option_behavior",
    "expectancy",
    "option_liquidity",
    "spread_width",
    "open_interest",
    "volume",
    "iv",
    "implied_volatility",
    "skew",
    "term_structure",
)

DATE_KEY_TERMS = (
    "date",
    "timestamp",
    "time",
    "asof",
    "as_of",
)

STRATEGY_FIELD_CANDIDATES = (
    "strategy",
    "strategy_name",
    "selected_strategy",
    "top_strategy",
    "candidate_strategy",
    "strategy_id",
)
SYMBOL_FIELD_CANDIDATES = ("symbol", "underlying", "ticker")
DECISION_DATE_FIELD_CANDIDATES = (
    "decision_date",
    "asof_date",
    "as_of_date",
    "date",
    "trade_date",
    "entry_signal_date",
)


@dataclass(frozen=True)
class InputPathSet:
    decision_rows: Optional[Path] = None
    decision_summary: Optional[Path] = None
    strategy_selection_rows: Optional[Path] = None
    strategy_selection_summary: Optional[Path] = None
    selected_trade_sequence_summary: Optional[Path] = None
    position_sizing_summary: Optional[Path] = None
    equity_reconstruction_summary: Optional[Path] = None
    metrics_report: Optional[Path] = None
    stress_validation_summary: Optional[Path] = None
    stress_validation_scenarios: Optional[Path] = None
    execution_rulebook_readiness_bridge: Optional[Path] = None


@dataclass
class BuildConfig:
    max_timing_audit_rows: int = 25000
    max_dependency_value_examples: int = 3
    decision_timestamp_assumption: str = "after_market_close"


@dataclass
class FieldProfile:
    stage: str
    source_artifact: str
    field: str
    count: int = 0
    value_types: Counter = field(default_factory=Counter)
    examples: List[Any] = field(default_factory=list)

    def add_value(self, value: Any, max_examples: int) -> None:
        self.count += 1
        self.value_types[type(value).__name__] += 1
        if len(self.examples) < max_examples and _safe_example(value) not in self.examples:
            self.examples.append(_safe_example(value))


@dataclass
class BuildResult:
    review: Dict[str, Any]
    summary: Dict[str, Any]
    blockers: List[Dict[str, Any]]
    dependency_matrix: List[Dict[str, Any]]
    timing_audit: List[Dict[str, Any]]
    execution_gap_audit: List[Dict[str, Any]]
    manual_dependency_audit: List[Dict[str, Any]]
    future_field_audit: List[Dict[str, Any]]


def build_portfolio_deployment_readiness_live_translation_review(
    inputs: InputPathSet,
    output_dir: Path,
    config: Optional[BuildConfig] = None,
) -> BuildResult:
    """Build deployment readiness artifacts and write them to output_dir."""

    config = config or BuildConfig()
    output_dir.mkdir(parents=True, exist_ok=True)

    input_status = _collect_input_status(inputs)
    summaries = _read_summary_inputs(inputs)
    execution_rulebook_bridge = _read_execution_rulebook_bridge(inputs.execution_rulebook_readiness_bridge)
    field_profiles = _profile_input_fields(inputs, config)

    dependency_matrix = _build_dependency_matrix(field_profiles)
    future_field_audit = [row for row in dependency_matrix if row.get("future_dependency")]
    manual_dependency_audit = [row for row in dependency_matrix if row.get("manual_dependency")]

    blockers: List[Dict[str, Any]] = []
    blockers.extend(_input_blockers(input_status))
    blockers.extend(_future_field_blockers(future_field_audit))

    timing_audit, timing_blockers = _build_timing_audit(inputs, dependency_matrix, config)
    blockers.extend(timing_blockers)

    execution_gap_audit, execution_blockers, execution_warnings = _build_execution_gap_audit(
        inputs=inputs,
        summaries=summaries,
        dependency_matrix=dependency_matrix,
        execution_rulebook_bridge=execution_rulebook_bridge,
    )
    blockers.extend(execution_blockers)

    warnings = _build_warnings(
        input_status=input_status,
        dependency_matrix=dependency_matrix,
        execution_warnings=execution_warnings,
    )

    blocker_count = sum(1 for b in blockers if b.get("severity") == "blocker")
    warning_count = len(warnings) + sum(1 for b in blockers if b.get("severity") == "warning")

    future_field_dependency_count = len(future_field_audit)
    manual_only_dependency_count = len(manual_dependency_audit)
    missing_live_data_source_count = _count_missing_live_data_sources(input_status, dependency_matrix)
    timing_violation_count = sum(1 for row in timing_audit if row.get("timing_violations"))
    execution_gap_count = sum(1 for row in execution_gap_audit if row.get("readiness_state") in {"manual_review_required", "blocked"})

    deployment_readiness_state = _deployment_readiness_state(
        blocker_count=blocker_count,
        manual_only_dependency_count=manual_only_dependency_count,
        missing_live_data_source_count=missing_live_data_source_count,
        timing_violation_count=timing_violation_count,
        execution_gap_count=execution_gap_count,
        warning_count=warning_count,
    )

    summary = {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": ARTIFACT_TYPE,
        "contract": CONTRACT,
        "is_ready": blocker_count == 0,
        "deployment_readiness_state": deployment_readiness_state,
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "future_field_dependency_count": future_field_dependency_count,
        "manual_only_dependency_count": manual_only_dependency_count,
        "missing_live_data_source_count": missing_live_data_source_count,
        "timing_violation_count": timing_violation_count,
        "execution_gap_count": execution_gap_count,
        "phase7_stress_validation_dependency": "evidence_only",
        "execution_rulebook_bridge_dependency": _execution_rulebook_bridge_dependency_state(execution_rulebook_bridge),
        "recommended_next_phase": "paper_trading_shadow_replay",
        "paths": _output_paths(output_dir),
        "input_status": input_status,
        "warnings": warnings,
    }

    review = {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": ARTIFACT_TYPE,
        "contract": CONTRACT,
        "summary": summary,
        "blockers": blockers,
        "warnings": warnings,
        "dependency_matrix": dependency_matrix,
        "timing_audit_sample_count": len(timing_audit),
        "execution_gap_audit": execution_gap_audit,
    }

    _write_json(output_dir / f"{OUTPUT_BASENAME}.json", review)
    _write_json(output_dir / f"{OUTPUT_BASENAME}_summary.json", summary)
    _write_jsonl(output_dir / f"{OUTPUT_BASENAME}_blockers.jsonl", blockers)
    _write_jsonl(output_dir / f"{OUTPUT_BASENAME}_dependency_matrix.jsonl", dependency_matrix)
    _write_jsonl(output_dir / f"{OUTPUT_BASENAME}_timing_audit.jsonl", timing_audit)
    _write_jsonl(output_dir / f"{OUTPUT_BASENAME}_execution_gap_audit.jsonl", execution_gap_audit)
    _write_jsonl(output_dir / f"{OUTPUT_BASENAME}_manual_dependency_audit.jsonl", manual_dependency_audit)
    _write_jsonl(output_dir / f"{OUTPUT_BASENAME}_future_field_audit.jsonl", future_field_audit)

    return BuildResult(
        review=review,
        summary=summary,
        blockers=blockers,
        dependency_matrix=dependency_matrix,
        timing_audit=timing_audit,
        execution_gap_audit=execution_gap_audit,
        manual_dependency_audit=manual_dependency_audit,
        future_field_audit=future_field_audit,
    )


def _collect_input_status(inputs: InputPathSet) -> Dict[str, Dict[str, Any]]:
    status: Dict[str, Dict[str, Any]] = {}
    for name, path in inputs.__dict__.items():
        if path is None:
            status[name] = {
                "provided": False,
                "exists": False,
                "path": None,
                "readiness_state": "not_provided",
            }
            continue
        exists = path.exists()
        status[name] = {
            "provided": True,
            "exists": exists,
            "path": str(path),
            "size_bytes": path.stat().st_size if exists else None,
            "readiness_state": "available" if exists else "missing",
            "manual_path_hint": _path_has_manual_hint(path),
        }
    return status


def _read_summary_inputs(inputs: InputPathSet) -> Dict[str, Any]:
    summaries: Dict[str, Any] = {}
    for name in (
        "decision_summary",
        "strategy_selection_summary",
        "selected_trade_sequence_summary",
        "position_sizing_summary",
        "equity_reconstruction_summary",
        "metrics_report",
        "stress_validation_summary",
    ):
        path = getattr(inputs, name)
        summaries[name] = _read_json(path) if path and path.exists() else {}
    return summaries


def _read_execution_rulebook_bridge(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists():
        return {}
    data = _read_json(path)
    return data if isinstance(data, Mapping) else {}


def _execution_rulebook_bridge_dependency_state(bridge: Mapping[str, Any]) -> str:
    if not bridge:
        return "not_provided"
    if bridge.get("execution_rulebook_available") is True:
        return "applied"
    return "provided_but_unrecognized"


def _profile_input_fields(inputs: InputPathSet, config: BuildConfig) -> Dict[Tuple[str, str], FieldProfile]:
    profiles: Dict[Tuple[str, str], FieldProfile] = {}

    stage_paths: List[Tuple[str, Optional[Path], str]] = [
        ("decision_rows", inputs.decision_rows, "historical_decision_rows"),
        ("decision_summary", inputs.decision_summary, "historical_decision_rows_summary"),
        ("strategy_selection_rows", inputs.strategy_selection_rows, "historical_strategy_selection_rows"),
        ("strategy_selection_summary", inputs.strategy_selection_summary, "historical_strategy_selection_rows_summary"),
        ("selected_trade_sequence_summary", inputs.selected_trade_sequence_summary, "portfolio_selected_trade_sequence_summary"),
        ("position_sizing_summary", inputs.position_sizing_summary, "portfolio_position_sizing_replay_summary"),
        ("equity_reconstruction_summary", inputs.equity_reconstruction_summary, "portfolio_equity_reconstruction_summary"),
        ("metrics_report", inputs.metrics_report, "portfolio_metrics_report"),
        ("stress_validation_summary", inputs.stress_validation_summary, "portfolio_robustness_stress_validation_summary"),
        ("stress_validation_scenarios", inputs.stress_validation_scenarios, "portfolio_robustness_stress_validation_scenarios"),
    ]

    for stage, path, source_artifact in stage_paths:
        if not path or not path.exists():
            continue
        records = _iter_records_from_path(path)
        for record in records:
            if not isinstance(record, Mapping):
                continue
            for field_name, value in _flatten_mapping(record).items():
                key = (stage, field_name)
                if key not in profiles:
                    profiles[key] = FieldProfile(stage=stage, source_artifact=source_artifact, field=field_name)
                profiles[key].add_value(value, config.max_dependency_value_examples)
    return profiles


def _build_dependency_matrix(field_profiles: Mapping[Tuple[str, str], FieldProfile]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for (_, _), profile in sorted(field_profiles.items(), key=lambda item: (item[1].stage, item[1].field)):
        classification = _classify_field(profile.stage, profile.field, profile.source_artifact, profile)
        rows.append(
            {
                "stage": profile.stage,
                "field": profile.field,
                "source_artifact": profile.source_artifact,
                "field_observation_count": profile.count,
                "value_types": dict(profile.value_types),
                "example_values": profile.examples,
                **classification,
            }
        )
    return rows


def _classify_field(stage: str, field_name: str, source_artifact: str, profile: Optional[FieldProfile] = None) -> Dict[str, Any]:
    field_l = field_name.lower()
    source_l = source_artifact.lower()
    live_decision_stage = stage in LIVE_DECISION_STAGES
    evidence_only_stage = stage in EVIDENCE_ONLY_STAGES or stage.endswith("summary") or stage == "metrics_report"

    manual_dependency = _contains_any(field_l, MANUAL_TERMS) or _contains_any(source_l, MANUAL_TERMS)
    future_like = _is_future_or_outcome_field(field_l)
    asof_safe_prior = _is_asof_safe_prior_field(field_l)

    future_dependency = False
    asof_safe = True
    live_availability = "live_ready"
    readiness_state = "live_ready"
    notes = "Field appears live-compatible based on naming heuristics."

    if manual_dependency:
        live_availability = "manual_only"
        readiness_state = "manual_review_required"
        notes = "Field or artifact name indicates a manual dependency or approval requirement."

    if live_decision_stage and _is_live_safety_assertion_field(field_l):
        if _is_false_only_boolean_profile(profile):
            return {
                "live_availability": "live_safety_assertion",
                "asof_safe": True,
                "manual_dependency": manual_dependency,
                "future_dependency": False,
                "readiness_state": "live_ready",
                "notes": "Guardrail flag is false for all observed rows; it validates that this selection stage did not use future/current-row outcome inputs.",
            }
        return {
            "live_availability": "backtest_only",
            "asof_safe": False,
            "manual_dependency": manual_dependency,
            "future_dependency": True,
            "readiness_state": "blocked",
            "notes": "Guardrail flag indicates possible future, realized, or current-row outcome use in a live decision stage.",
        }

    if live_decision_stage and _is_backtest_only_diagnostic_field(field_l):
        return {
            "live_availability": "backtest_only_diagnostic",
            "asof_safe": True,
            "manual_dependency": manual_dependency,
            "future_dependency": False,
            "readiness_state": "warning",
            "notes": "Backtest-only diagnostic is carried in the artifact but should remain excluded from live decision inputs.",
        }

    if live_decision_stage and _is_rule_derived_schedule_field(field_l):
        return {
            "live_availability": "rule_derived",
            "asof_safe": True,
            "manual_dependency": manual_dependency,
            "future_dependency": False,
            "readiness_state": "warning",
            "notes": "Planned schedule field can be known at entry if derived from an explicit live close rule; verify the rule mapping.",
        }

    if evidence_only_stage:
        # Portfolio results, stress scenarios, and metrics are evidence for deployment.
        # They should not feed back into live trade selection.
        if future_like:
            live_availability = "backtest_only"
            readiness_state = "paper_ready"
            future_dependency = False
            notes = "Outcome/performance field is allowed here because this stage is evidence-only, not live selection input."
        elif manual_dependency:
            live_availability = "manual_only"
            readiness_state = "manual_review_required"
        else:
            live_availability = "evidence_only"
            readiness_state = "paper_ready"
            notes = "Evidence-only field. It can support deployment review but must not drive live trade selection."
    elif future_like and asof_safe_prior:
        live_availability = "available_from_prior_history"
        readiness_state = "warning"
        asof_safe = True
        notes = "Field name contains outcome/performance terms but also indicates prior historical aggregation; verify as-of windowing."
    elif future_like and live_decision_stage:
        future_dependency = True
        asof_safe = False
        live_availability = "backtest_only"
        readiness_state = "blocked"
        notes = "Field appears to require future or post-trade information in a live decision stage."
    elif future_like:
        live_availability = "backtest_only"
        readiness_state = "warning"
        notes = "Field appears outcome/performance-related and should remain diagnostic only."
    elif _contains_any(field_l, LIVE_DATA_TERMS):
        live_availability = "unknown"
        readiness_state = "warning"
        notes = "Live data category detected; verify this input can be produced before the decision timestamp."

    return {
        "live_availability": live_availability,
        "asof_safe": asof_safe,
        "manual_dependency": manual_dependency,
        "future_dependency": future_dependency,
        "readiness_state": readiness_state,
        "notes": notes,
    }


def _input_blockers(input_status: Mapping[str, Mapping[str, Any]]) -> List[Dict[str, Any]]:
    blockers: List[Dict[str, Any]] = []
    required_inputs = (
        "decision_rows",
        "decision_summary",
        "strategy_selection_rows",
        "strategy_selection_summary",
        "selected_trade_sequence_summary",
        "position_sizing_summary",
        "equity_reconstruction_summary",
        "metrics_report",
        "stress_validation_summary",
    )
    for name in required_inputs:
        row = input_status.get(name, {})
        if row.get("provided") and not row.get("exists"):
            blockers.append(
                {
                    "blocker_type": "missing_input_artifact",
                    "severity": "blocker",
                    "field": name,
                    "affected_stage": name,
                    "reason": "Required deployment-readiness input path was provided but does not exist.",
                    "recommended_action": "Regenerate the upstream artifact or correct the input path.",
                }
            )
        elif not row.get("provided"):
            blockers.append(
                {
                    "blocker_type": "missing_input_artifact",
                    "severity": "blocker",
                    "field": name,
                    "affected_stage": name,
                    "reason": "Required deployment-readiness input path was not provided.",
                    "recommended_action": "Pass the upstream artifact into the readiness review CLI.",
                }
            )
    return blockers


def _future_field_blockers(future_field_audit: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    blockers: List[Dict[str, Any]] = []
    for row in future_field_audit:
        blockers.append(
            {
                "blocker_type": "future_field_dependency",
                "severity": "blocker",
                "field": row.get("field"),
                "affected_stage": row.get("stage"),
                "source_artifact": row.get("source_artifact"),
                "reason": "Field is only known after the decision/trade and cannot be used in live decision selection.",
                "recommended_action": "Remove from live decision features or mark as backtest-only diagnostic.",
            }
        )
    return blockers


def _build_timing_audit(
    inputs: InputPathSet,
    dependency_matrix: Sequence[Mapping[str, Any]],
    config: BuildConfig,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    blocked_fields_by_stage: Dict[str, set] = defaultdict(set)
    for row in dependency_matrix:
        if row.get("future_dependency"):
            blocked_fields_by_stage[str(row.get("stage"))].add(str(row.get("field")))

    audit_rows: List[Dict[str, Any]] = []
    blockers: List[Dict[str, Any]] = []

    sources = [
        ("decision_rows", inputs.decision_rows),
        ("strategy_selection_rows", inputs.strategy_selection_rows),
    ]

    seen_blockers: set = set()
    for stage, path in sources:
        if not path or not path.exists():
            continue
        for idx, record in enumerate(_iter_records_from_path(path)):
            if idx >= config.max_timing_audit_rows:
                break
            if not isinstance(record, Mapping):
                continue
            flat = _flatten_mapping(record)
            decision_date = _extract_first(flat, DECISION_DATE_FIELD_CANDIDATES)
            symbol = _extract_first(flat, SYMBOL_FIELD_CANDIDATES)
            strategy = _extract_first(flat, STRATEGY_FIELD_CANDIDATES)
            violations: List[str] = []

            for field_name in blocked_fields_by_stage.get(stage, set()):
                if field_name in flat:
                    violations.append(f"uses_future_or_post_trade_field:{field_name}")

            parsed_decision_date = _parse_date_like(decision_date)
            if parsed_decision_date:
                for key, value in flat.items():
                    key_l = key.lower()
                    if "asof" not in key_l and "as_of" not in key_l:
                        continue
                    if not _contains_any(key_l, DATE_KEY_TERMS):
                        continue
                    parsed_asof = _parse_date_like(value)
                    if parsed_asof and parsed_asof > parsed_decision_date:
                        violations.append(f"asof_after_decision:{key}")

            readiness_state = "live_ready" if not violations else "blocked"
            audit_row = {
                "stage": stage,
                "row_index": idx,
                "decision_date": _safe_example(decision_date),
                "symbol": _safe_example(symbol),
                "strategy": _safe_example(strategy),
                "decision_timestamp_assumption": config.decision_timestamp_assumption,
                "required_inputs_available_by_decision_time": not violations,
                "timing_violations": violations,
                "readiness_state": readiness_state,
            }
            audit_rows.append(audit_row)

            for violation in violations:
                blocker_key = (stage, violation)
                if blocker_key in seen_blockers:
                    continue
                seen_blockers.add(blocker_key)
                blockers.append(
                    {
                        "blocker_type": "unrealistic_timing_assumption",
                        "severity": "blocker",
                        "field": violation.split(":", 1)[-1],
                        "affected_stage": stage,
                        "reason": f"Timing audit detected violation: {violation}",
                        "recommended_action": "Rebuild the feature using only values available at or before the decision timestamp.",
                    }
                )

    return audit_rows, blockers


def _build_execution_gap_audit(
    inputs: InputPathSet,
    summaries: Mapping[str, Any],
    dependency_matrix: Sequence[Mapping[str, Any]],
    execution_rulebook_bridge: Mapping[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    strategies = _collect_strategy_names(inputs, summaries)
    if not strategies:
        strategies = ["unknown_strategy"]

    rulebook_resolutions = _normalize_rulebook_gap_resolutions(execution_rulebook_bridge)

    position_size_available = _position_sizing_available(summaries, dependency_matrix)
    close_rules_available = _close_rules_available(summaries, dependency_matrix)
    defense_rules_available = _defense_rules_available(summaries, dependency_matrix)

    audit: List[Dict[str, Any]] = []
    blockers: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    for strategy in sorted(strategies):
        mapping = _infer_strategy_execution_mapping(strategy)
        rulebook_resolution = rulebook_resolutions.get(_normalize_strategy_name(strategy), {})
        rulebook_gap_resolution_applied = bool(rulebook_resolution)
        effective_close_rules_available = close_rules_available or rulebook_resolution.get("close_rules_available") is True
        effective_defense_rules_available = defense_rules_available or rulebook_resolution.get("defense_rules_available") is True
        effective_paper_trade_supported = mapping["paper_trade_supported"] or rulebook_resolution.get("paper_trade_supported") is True
        gaps: List[str] = []
        severity = "none"

        if not mapping["order_intent_available"]:
            gaps.append("unmapped_order_intent")
            severity = "blocker"
        if not mapping["max_risk_defined"]:
            gaps.append("undefined_or_unbounded_strategy_risk")
            severity = "blocker"
        if not position_size_available:
            gaps.append("position_sizing_not_live_safe")
            severity = "blocker"
        if not effective_close_rules_available:
            gaps.append("unmapped_exit_logic")
            if severity != "blocker":
                severity = "warning"
        if not effective_defense_rules_available:
            gaps.append("unmapped_defense_logic")
            if severity != "blocker":
                severity = "warning"

        readiness_state = "live_ready"
        if severity == "blocker":
            readiness_state = "blocked"
        elif severity == "warning" or mapping.get("manual_approval_required"):
            readiness_state = "manual_review_required"

        row = {
            "strategy": strategy,
            **mapping,
            "position_size_available": position_size_available,
            "close_rules_available": effective_close_rules_available,
            "defense_rules_available": effective_defense_rules_available,
            "rulebook_gap_resolution_applied": rulebook_gap_resolution_applied,
            "execution_rulebook_strategy_state": rulebook_resolution.get("readiness_state"),
            "execution_gaps": gaps,
            "broker_execution_state": "paper_ready" if readiness_state != "blocked" and effective_paper_trade_supported else "blocked",
            "readiness_state": readiness_state,
        }
        audit.append(row)

        for gap in gaps:
            item = {
                "blocker_type": gap,
                "severity": "blocker" if severity == "blocker" and gap in {"unmapped_order_intent", "undefined_or_unbounded_strategy_risk", "position_sizing_not_live_safe"} else "warning",
                "field": strategy,
                "affected_stage": "execution_translation",
                "reason": f"Execution translation gap detected for strategy '{strategy}': {gap}.",
                "recommended_action": "Add a live order-intent, exit, defense, and broker translation rule for this strategy.",
            }
            if item["severity"] == "blocker":
                blockers.append(item)
            else:
                warnings.append(item)

    return audit, blockers, warnings


def _build_warnings(
    input_status: Mapping[str, Mapping[str, Any]],
    dependency_matrix: Sequence[Mapping[str, Any]],
    execution_warnings: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    warnings.extend(dict(w) for w in execution_warnings)

    for name, row in input_status.items():
        if row.get("manual_path_hint"):
            warnings.append(
                {
                    "blocker_type": "manual_only_dependency",
                    "severity": "warning",
                    "field": name,
                    "affected_stage": name,
                    "reason": "Input path suggests a manual source or manual import dependency.",
                    "recommended_action": "Replace with an automated live or scheduled import before live deployment.",
                }
            )

    live_data_unknowns = [
        row for row in dependency_matrix
        if row.get("readiness_state") == "warning" and row.get("live_availability") == "unknown"
    ]
    for row in live_data_unknowns[:50]:
        warnings.append(
            {
                "blocker_type": "missing_live_data_source",
                "severity": "warning",
                "field": row.get("field"),
                "affected_stage": row.get("stage"),
                "source_artifact": row.get("source_artifact"),
                "reason": "Live data category detected but the readiness review cannot prove the source is automated/live-available.",
                "recommended_action": "Document the live source and as-of timing for this field, or degrade the feature for paper trading.",
            }
        )

    prior_aggregate_warnings = [
        row for row in dependency_matrix
        if row.get("readiness_state") == "warning" and row.get("live_availability") == "available_from_prior_history"
    ]
    for row in prior_aggregate_warnings[:50]:
        warnings.append(
            {
                "blocker_type": "prior_history_asof_verification_required",
                "severity": "warning",
                "field": row.get("field"),
                "affected_stage": row.get("stage"),
                "source_artifact": row.get("source_artifact"),
                "reason": "Prior-history aggregate appears acceptable only if its lookback window ends before the decision timestamp.",
                "recommended_action": "Verify the feature builder uses as-of-safe windowing and excludes the current trade outcome.",
            }
        )

    return warnings


def _count_missing_live_data_sources(
    input_status: Mapping[str, Mapping[str, Any]],
    dependency_matrix: Sequence[Mapping[str, Any]],
) -> int:
    count = sum(1 for row in dependency_matrix if row.get("live_availability") == "unknown")
    count += sum(1 for row in input_status.values() if row.get("manual_path_hint"))
    return count


def _deployment_readiness_state(
    *,
    blocker_count: int,
    manual_only_dependency_count: int,
    missing_live_data_source_count: int,
    timing_violation_count: int,
    execution_gap_count: int,
    warning_count: int,
) -> str:
    if blocker_count > 0 or timing_violation_count > 0:
        return "blocked_for_live_translation"
    if manual_only_dependency_count > 0 or missing_live_data_source_count > 0 or execution_gap_count > 0:
        return "ready_for_paper_trading_with_manual_review"
    if warning_count > 0:
        return "ready_for_paper_trading_with_manual_review"
    return "ready_for_paper_trading"


def _collect_strategy_names(inputs: InputPathSet, summaries: Mapping[str, Any]) -> set:
    strategies: set = set()

    for summary in summaries.values():
        if isinstance(summary, Mapping):
            strategies.update(_extract_strategy_values_from_mapping(summary))

    for path in (inputs.strategy_selection_rows, inputs.decision_rows, inputs.stress_validation_scenarios):
        if not path or not path.exists():
            continue
        for idx, record in enumerate(_iter_records_from_path(path)):
            if idx > 50000:
                break
            if isinstance(record, Mapping):
                strategies.update(_extract_strategy_values_from_mapping(record))

    cleaned = {str(s).strip() for s in strategies if s is not None and str(s).strip()}
    cleaned = {s for s in cleaned if s.lower() not in {"none", "null", "nan", "unknown"}}
    return cleaned


def _extract_strategy_values_from_mapping(mapping: Mapping[str, Any]) -> set:
    values: set = set()
    flat = _flatten_mapping(mapping)
    for key, value in flat.items():
        key_l = key.lower().split(".")[-1]
        if key_l in STRATEGY_FIELD_CANDIDATES or key_l.endswith("strategy"):
            if isinstance(value, str):
                values.add(value)
    return values


def _normalize_rulebook_gap_resolutions(bridge: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    raw = bridge.get("readiness_review_execution_gap_resolution") if isinstance(bridge, Mapping) else None
    if not isinstance(raw, Mapping):
        return {}
    normalized: Dict[str, Dict[str, Any]] = {}
    for strategy, resolution in raw.items():
        if isinstance(resolution, Mapping):
            normalized[_normalize_strategy_name(str(strategy))] = dict(resolution)
    return normalized


def _normalize_strategy_name(strategy: str) -> str:
    return str(strategy).strip().lower().replace("-", "_").replace(" ", "_")


def _infer_strategy_execution_mapping(strategy: str) -> Dict[str, Any]:
    s = strategy.lower().replace("-", "_").replace(" ", "_")
    required_legs: Optional[int] = None
    max_risk_defined = True
    manual_approval_required = False
    order_intent_available = True
    entry_order_type = "limit_order"
    exit_order_type = "limit_order_or_rule_based_close"
    required_option_legs: List[str] = []

    if "iron_condor" in s:
        required_legs = 4
        required_option_legs = ["short_put", "long_put", "short_call", "long_call"]
    elif "butterfly" in s or "fly" in s:
        required_legs = 3
        required_option_legs = ["long_option", "short_options", "long_option"]
    elif "calendar" in s or "diagonal" in s:
        required_legs = 2
        required_option_legs = ["near_term_option", "far_term_option"]
    elif "spread" in s:
        required_legs = 2
        if "put" in s:
            required_option_legs = ["short_or_long_put", "hedge_put"]
        elif "call" in s:
            required_option_legs = ["short_or_long_call", "hedge_call"]
        else:
            required_option_legs = ["option_leg_1", "option_leg_2"]
    elif "covered_call" in s:
        required_legs = 2
        required_option_legs = ["long_underlying", "short_call"]
        manual_approval_required = True
    elif "cash_secured_put" in s:
        required_legs = 1
        required_option_legs = ["short_put"]
        manual_approval_required = True
    elif "long_call" in s or "buy_call" in s:
        required_legs = 1
        required_option_legs = ["long_call"]
    elif "long_put" in s or "buy_put" in s:
        required_legs = 1
        required_option_legs = ["long_put"]
    elif "short_call" in s or "naked_call" in s or "naked_short_call" in s:
        required_legs = 1
        required_option_legs = ["short_call"]
        max_risk_defined = False
    elif "short_put" in s or "naked_put" in s or "naked_short_put" in s:
        required_legs = 1
        required_option_legs = ["short_put"]
        max_risk_defined = False
    elif s in {"unknown_strategy", "unknown", "none"}:
        order_intent_available = False
        max_risk_defined = False
        required_legs = None
    else:
        order_intent_available = False
        required_legs = None
        manual_approval_required = True

    return {
        "order_intent_available": order_intent_available,
        "required_legs": required_legs,
        "required_option_legs": required_option_legs,
        "entry_order_type": entry_order_type if order_intent_available else None,
        "exit_order_type": exit_order_type if order_intent_available else None,
        "max_risk_defined": max_risk_defined,
        "manual_approval_required": manual_approval_required,
        "paper_trade_supported": order_intent_available and max_risk_defined,
        "live_trade_supported": False,
    }


def _position_sizing_available(summaries: Mapping[str, Any], dependency_matrix: Sequence[Mapping[str, Any]]) -> bool:
    summary = summaries.get("position_sizing_summary") or {}
    if isinstance(summary, Mapping):
        if summary.get("is_ready") is True:
            return True
        flat = _flatten_mapping(summary)
        if any("position_size" in key.lower() or "risk_budget" in key.lower() for key in flat):
            return True
    return any("position_size" in str(row.get("field", "")).lower() for row in dependency_matrix)


def _close_rules_available(summaries: Mapping[str, Any], dependency_matrix: Sequence[Mapping[str, Any]]) -> bool:
    keys = _all_summary_keys(summaries)
    if any(term in key for key in keys for term in ("close_rule", "exit_rule", "automatic_close_order", "portfolio_action")):
        return True
    return any(
        any(term in str(row.get("field", "")).lower() for term in ("close_rule", "exit_rule", "automatic_close_order", "portfolio_action"))
        for row in dependency_matrix
    )


def _defense_rules_available(summaries: Mapping[str, Any], dependency_matrix: Sequence[Mapping[str, Any]]) -> bool:
    keys = _all_summary_keys(summaries)
    if any(term in key for key in keys for term in ("defense", "maintenance", "roll_order", "risk_overlay")):
        return True
    return any(
        any(term in str(row.get("field", "")).lower() for term in ("defense", "maintenance", "roll_order", "risk_overlay"))
        for row in dependency_matrix
    )


def _all_summary_keys(summaries: Mapping[str, Any]) -> set:
    keys: set = set()
    for summary in summaries.values():
        if isinstance(summary, Mapping):
            keys.update(key.lower() for key in _flatten_mapping(summary).keys())
    return keys


def _output_paths(output_dir: Path) -> Dict[str, str]:
    return {
        "review_path": str(output_dir / f"{OUTPUT_BASENAME}.json"),
        "summary_path": str(output_dir / f"{OUTPUT_BASENAME}_summary.json"),
        "blockers_path": str(output_dir / f"{OUTPUT_BASENAME}_blockers.jsonl"),
        "dependency_matrix_path": str(output_dir / f"{OUTPUT_BASENAME}_dependency_matrix.jsonl"),
        "timing_audit_path": str(output_dir / f"{OUTPUT_BASENAME}_timing_audit.jsonl"),
        "execution_gap_audit_path": str(output_dir / f"{OUTPUT_BASENAME}_execution_gap_audit.jsonl"),
        "manual_dependency_audit_path": str(output_dir / f"{OUTPUT_BASENAME}_manual_dependency_audit.jsonl"),
        "future_field_audit_path": str(output_dir / f"{OUTPUT_BASENAME}_future_field_audit.jsonl"),
    }


def _iter_records_from_path(path: Path) -> Iterator[Any]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        yield from _iter_jsonl(path)
        return
    data = _read_json(path)
    if isinstance(data, list):
        yield from data
    elif isinstance(data, Mapping):
        # Some artifacts store rows under a named list key.
        row_list = _first_list_value(data)
        if row_list is not None and len(row_list) > 0 and all(isinstance(item, Mapping) for item in row_list[:10]):
            yield from row_list
        else:
            yield data
    else:
        yield data


def _first_list_value(data: Mapping[str, Any]) -> Optional[List[Any]]:
    preferred_terms = ("rows", "scenarios", "records", "snapshots", "items", "trades")
    for key, value in data.items():
        if isinstance(value, list) and any(term in key.lower() for term in preferred_terms):
            return value
    for value in data.values():
        if isinstance(value, list):
            return value
    return None


def _read_json(path: Optional[Path]) -> Any:
    if not path:
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _iter_jsonl(path: Path) -> Iterator[Any]:
    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                yield {
                    "_jsonl_parse_error": str(exc),
                    "_jsonl_line_number": line_number,
                    "_raw_line_preview": line[:250],
                }


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True, default=str)
        f.write("\n")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, default=str))
            f.write("\n")


def _flatten_mapping(mapping: Mapping[str, Any], prefix: str = "", max_depth: int = 5) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    if max_depth < 0:
        return result
    for key, value in mapping.items():
        key_s = str(key)
        full_key = f"{prefix}.{key_s}" if prefix else key_s
        if isinstance(value, Mapping):
            result.update(_flatten_mapping(value, full_key, max_depth - 1))
        elif isinstance(value, list):
            result[full_key] = value
            # Profile keys inside small lists of dicts without exploding rows.
            for idx, item in enumerate(value[:3]):
                if isinstance(item, Mapping):
                    result.update(_flatten_mapping(item, f"{full_key}[{idx}]", max_depth - 1))
        else:
            result[full_key] = value
    return result


def _extract_first(flat: Mapping[str, Any], candidates: Sequence[str]) -> Any:
    lowered = {key.lower(): value for key, value in flat.items()}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    for key, value in flat.items():
        key_tail = key.lower().split(".")[-1]
        if key_tail in candidates:
            return value
    return None


def _parse_date_like(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            pass
    # Best effort for ISO timestamps with timezone suffixes.
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _is_live_safety_assertion_field(field_l: str) -> bool:
    return field_l in LIVE_SAFETY_ASSERTION_FIELDS


def _is_backtest_only_diagnostic_field(field_l: str) -> bool:
    return field_l in BACKTEST_ONLY_DIAGNOSTIC_FIELDS


def _is_rule_derived_schedule_field(field_l: str) -> bool:
    normalized = field_l.replace(".", "_").replace("-", "_")
    return _contains_any(normalized, RULE_DERIVED_SCHEDULE_TERMS)


def _is_false_only_boolean_profile(profile: Optional[FieldProfile]) -> bool:
    if profile is None or profile.count <= 0:
        return False
    if set(profile.value_types.keys()) != {"bool"}:
        return False
    return set(profile.examples) <= {False}


def _is_future_or_outcome_field(field_l: str) -> bool:
    normalized = field_l.replace(".", "_").replace("-", "_")
    return _contains_any(normalized, FUTURE_OR_OUTCOME_TERMS)


def _is_asof_safe_prior_field(field_l: str) -> bool:
    normalized = field_l.replace(".", "_").replace("-", "_")
    return _contains_any(normalized, ASOF_SAFE_PRIOR_TERMS)


def _contains_any(text: str, terms: Sequence[str]) -> bool:
    return any(term in text for term in terms)


def _path_has_manual_hint(path: Path) -> bool:
    text = str(path).lower().replace("\\", "/")
    return any(term in text for term in ("/manual/", "manual_", "_manual", "copy_paste", "uploaded"))


def _safe_example(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return f"list[{len(value)}]"
    if isinstance(value, Mapping):
        return f"dict[{len(value)}]"
    return str(value)
