from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from signalforge.contracts.runtime_inputs import RUNTIME_INPUT_CONTRACTS
from signalforge.contracts.runtime_source_map import RUNTIME_SOURCE_MAPPINGS_BY_INPUT
from signalforge.rulebooks.spread_guardrail import SPREAD_GUARDRAIL_MAX


DEFAULT_PRE_TRADE_DECISIONS = "data/runtime/pre_trade_rules/v3_2_2_pre_trade_decisions.jsonl"
DEFAULT_OUTPUT = "artifacts/v3_2_2_runtime_readiness_audit_summary.json"


@dataclass(frozen=True)
class RuntimeReadinessAuditSummary:
    is_ready: bool
    readiness_state: str
    runtime_root: str
    required_contract_count: int
    required_contract_present_count: int
    missing_required_contract_count: int
    missing_required_contracts: tuple[str, ...]
    source_map_input_count: int
    source_map_missing_count: int
    source_map_missing_inputs: tuple[str, ...]
    pre_trade_decision_path: str
    pre_trade_decision_count: int
    accepted_count: int
    skipped_count: int
    spread_guardrail_max: float
    spread_guardrail_constant_ok: bool
    malformed_decision_count: int
    invalid_action_count: int
    spread_rule_mismatch_count: int
    prior_rule_mismatch_count: int
    blocker_count: int
    blockers: tuple[str, ...]
    warning_count: int
    warnings: tuple[str, ...]


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()

            if not line:
                continue

            value = json.loads(line)

            if isinstance(value, dict):
                yield value


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


def _contract_name(contract: Any) -> str:
    return str(getattr(contract, "name"))


def _contract_path(contract: Any) -> str:
    return str(getattr(contract, "path", getattr(contract, "relative_path", "")))


def _contract_required(contract: Any) -> bool:
    return bool(getattr(contract, "required", True))


def _mapping_inputs() -> set[str]:
    if isinstance(RUNTIME_SOURCE_MAPPINGS_BY_INPUT, dict):
        return {str(key) for key in RUNTIME_SOURCE_MAPPINGS_BY_INPUT.keys()}

    return set()


def _prior_stats_blocking(stats: Any) -> bool:
    if not isinstance(stats, dict):
        return False

    prior_count = _safe_int(stats.get("prior_count"))
    prior_net_pnl = _safe_float(stats.get("prior_net_pnl")) or 0.0
    prior_profit_factor = _safe_float(stats.get("prior_profit_factor"))

    if prior_profit_factor is None:
        prior_profit_factor = 0.0

    return prior_count >= 8 and prior_net_pnl <= 0 and prior_profit_factor <= 0.90


def _decision_malformed(row: dict[str, Any]) -> bool:
    required_fields = (
        "contract",
        "rulebook",
        "symbol",
        "paper_candidate_action",
        "skip_reasons",
        "spread_pct",
        "spread_guardrail_passed",
        "prior_symbol_regime_gate_passed",
    )

    for field in required_fields:
        if field not in row:
            return True

    if row.get("contract") != "v3_2_2_pre_trade_decision":
        return True

    if not isinstance(row.get("skip_reasons"), list):
        return True

    return False


def _spread_rule_mismatch(row: dict[str, Any]) -> bool:
    spread_pct = _safe_float(row.get("spread_pct"))
    action = row.get("paper_candidate_action")
    skip_reasons = set(str(reason) for reason in row.get("skip_reasons") or [])

    if spread_pct is None:
        return "spread_missing" not in skip_reasons or action != "skip"

    if spread_pct > SPREAD_GUARDRAIL_MAX:
        return "spread_gt_12_5pct" not in skip_reasons or action != "skip"

    return "spread_gt_12_5pct" in skip_reasons


def _prior_rule_mismatch(row: dict[str, Any]) -> bool:
    stats = row.get("prior_symbol_regime_stats")
    action = row.get("paper_candidate_action")
    skip_reasons = set(str(reason) for reason in row.get("skip_reasons") or [])
    blocking = _prior_stats_blocking(stats)

    if blocking:
        return "prior_symbol_regime_weak" not in skip_reasons or action != "skip"

    return "prior_symbol_regime_weak" in skip_reasons


def build_v3_2_2_runtime_readiness_audit(
    *,
    runtime_root: str | Path = ".",
    pre_trade_decisions_path: str | Path = DEFAULT_PRE_TRADE_DECISIONS,
) -> RuntimeReadinessAuditSummary:
    root = Path(runtime_root)
    pre_trade_path = root / pre_trade_decisions_path

    blockers: list[str] = []
    warnings: list[str] = []

    required_contracts = [
        contract
        for contract in RUNTIME_INPUT_CONTRACTS
        if _contract_required(contract)
    ]

    missing_required_contracts: list[str] = []

    for contract in required_contracts:
        path = root / _contract_path(contract)

        if not path.is_file() or path.stat().st_size <= 0:
            missing_required_contracts.append(_contract_name(contract))

    if missing_required_contracts:
        blockers.append("missing_required_runtime_contracts")

    mapping_inputs = _mapping_inputs()
    source_map_missing_inputs = [
        _contract_name(contract)
        for contract in required_contracts
        if _contract_name(contract) not in mapping_inputs
    ]

    if source_map_missing_inputs:
        blockers.append("source_map_missing_required_inputs")

    spread_guardrail_constant_ok = abs(float(SPREAD_GUARDRAIL_MAX) - 0.125) < 0.0000001

    if not spread_guardrail_constant_ok:
        blockers.append("spread_guardrail_constant_not_12_5pct")

    if not pre_trade_path.is_file() or pre_trade_path.stat().st_size <= 0:
        blockers.append("pre_trade_decisions_missing")

        return RuntimeReadinessAuditSummary(
            is_ready=False,
            readiness_state="blocked",
            runtime_root=str(root),
            required_contract_count=len(required_contracts),
            required_contract_present_count=len(required_contracts) - len(missing_required_contracts),
            missing_required_contract_count=len(missing_required_contracts),
            missing_required_contracts=tuple(missing_required_contracts),
            source_map_input_count=len(mapping_inputs),
            source_map_missing_count=len(source_map_missing_inputs),
            source_map_missing_inputs=tuple(source_map_missing_inputs),
            pre_trade_decision_path=str(pre_trade_path),
            pre_trade_decision_count=0,
            accepted_count=0,
            skipped_count=0,
            spread_guardrail_max=float(SPREAD_GUARDRAIL_MAX),
            spread_guardrail_constant_ok=spread_guardrail_constant_ok,
            malformed_decision_count=0,
            invalid_action_count=0,
            spread_rule_mismatch_count=0,
            prior_rule_mismatch_count=0,
            blocker_count=len(blockers),
            blockers=tuple(blockers),
            warning_count=len(warnings),
            warnings=tuple(warnings),
        )

    decisions = list(_read_jsonl(pre_trade_path))

    if not decisions:
        blockers.append("pre_trade_decisions_empty")

    action_counts = Counter(str(row.get("paper_candidate_action")) for row in decisions)
    invalid_action_count = sum(
        1
        for row in decisions
        if row.get("paper_candidate_action") not in {"accept", "skip"}
    )
    malformed_decision_count = sum(1 for row in decisions if _decision_malformed(row))
    spread_rule_mismatch_count = sum(1 for row in decisions if _spread_rule_mismatch(row))
    prior_rule_mismatch_count = sum(1 for row in decisions if _prior_rule_mismatch(row))

    if malformed_decision_count:
        blockers.append("malformed_pre_trade_decisions")

    if invalid_action_count:
        blockers.append("invalid_pre_trade_actions")

    if spread_rule_mismatch_count:
        blockers.append("spread_rule_mismatches")

    if prior_rule_mismatch_count:
        blockers.append("prior_rule_mismatches")

    accepted_count = int(action_counts.get("accept", 0))
    skipped_count = int(action_counts.get("skip", 0))

    if accepted_count == 0:
        warnings.append("no_accepted_pre_trade_decisions")

    if skipped_count == 0:
        warnings.append("no_skipped_pre_trade_decisions")

    readiness_state = "ready" if not blockers else "blocked"

    return RuntimeReadinessAuditSummary(
        is_ready=not blockers,
        readiness_state=readiness_state,
        runtime_root=str(root),
        required_contract_count=len(required_contracts),
        required_contract_present_count=len(required_contracts) - len(missing_required_contracts),
        missing_required_contract_count=len(missing_required_contracts),
        missing_required_contracts=tuple(missing_required_contracts),
        source_map_input_count=len(mapping_inputs),
        source_map_missing_count=len(source_map_missing_inputs),
        source_map_missing_inputs=tuple(source_map_missing_inputs),
        pre_trade_decision_path=str(pre_trade_path),
        pre_trade_decision_count=len(decisions),
        accepted_count=accepted_count,
        skipped_count=skipped_count,
        spread_guardrail_max=float(SPREAD_GUARDRAIL_MAX),
        spread_guardrail_constant_ok=spread_guardrail_constant_ok,
        malformed_decision_count=malformed_decision_count,
        invalid_action_count=invalid_action_count,
        spread_rule_mismatch_count=spread_rule_mismatch_count,
        prior_rule_mismatch_count=prior_rule_mismatch_count,
        blocker_count=len(blockers),
        blockers=tuple(blockers),
        warning_count=len(warnings),
        warnings=tuple(warnings),
    )


def summary_to_dict(summary: RuntimeReadinessAuditSummary) -> dict[str, Any]:
    return asdict(summary)


def write_summary(summary: RuntimeReadinessAuditSummary, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True), encoding="utf-8")
    return path


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit SignalForge V3.2.2 runtime readiness.")
    parser.add_argument("--runtime-root", default=".")
    parser.add_argument("--pre-trade-decisions", default=DEFAULT_PRE_TRADE_DECISIONS)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = build_v3_2_2_runtime_readiness_audit(
        runtime_root=args.runtime_root,
        pre_trade_decisions_path=args.pre_trade_decisions,
    )
    write_summary(summary, args.output)

    if args.json:
        print(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True))
    else:
        print(f"is_ready: {summary.is_ready}")
        print(f"readiness_state: {summary.readiness_state}")
        print(f"required_contract_present_count: {summary.required_contract_present_count}/{summary.required_contract_count}")
        print(f"source_map_missing_count: {summary.source_map_missing_count}")
        print(f"pre_trade_decision_count: {summary.pre_trade_decision_count}")
        print(f"accepted_count: {summary.accepted_count}")
        print(f"skipped_count: {summary.skipped_count}")
        print(f"spread_rule_mismatch_count: {summary.spread_rule_mismatch_count}")
        print(f"prior_rule_mismatch_count: {summary.prior_rule_mismatch_count}")
        print(f"blocker_count: {summary.blocker_count}")
        print(f"warning_count: {summary.warning_count}")

    return 0 if summary.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())




