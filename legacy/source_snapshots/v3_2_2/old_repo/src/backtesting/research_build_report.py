from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


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

CONTRACT_OUTCOME_FILE = "signalforge_qc_contract_outcome_snapshots.json"

TOP_LEVEL_RECORD_KEYS = [
    "research_outputs",
    "responses",
    "results",
    "items",
    "records",
    "payloads",
    "contract_outcome_snapshots",
    "snapshots",
]

BATCH_PATTERNS = [
    "*research*batch*.jsonl",
    "*research*batch*.json",
    "*batch*.jsonl",
    "*batch*.json",
]

RESEARCH_OUTPUT_PATTERNS = [
    "*research*output*.jsonl",
    "*research*output*.json",
    "*research*result*.jsonl",
    "*research*result*.json",
    "*output*.jsonl",
    "*output*.json",
]


def build_research_build_report(
    replay_result_dir: str | Path,
    research_batch_path: str | Path | None = None,
    research_output_path: str | Path | None = None,
    target_max_batch_bytes: int = 10 * 1024 * 1024,
    object_store_size_kb: float | None = None,
) -> dict[str, Any]:
    """Build a deterministic research build report from replay + research artifacts."""

    replay_dir = Path(replay_result_dir)
    batch_path = _resolve_optional_path(research_batch_path)
    output_path = _resolve_optional_path(research_output_path)

    if batch_path is None and replay_dir.exists():
        batch_path = _infer_file(replay_dir, BATCH_PATTERNS)

    if output_path is None and replay_dir.exists():
        output_path = _infer_file(replay_dir, RESEARCH_OUTPUT_PATTERNS)

    blocked_reasons: list[str] = []
    warnings: list[str] = []
    findings: list[str] = []
    recommendations: list[str] = []

    if not replay_dir.exists():
        blocked_reasons.append("replay_result_dir_missing")

    batch_summary = _summarize_record_file(batch_path, target_max_batch_bytes)
    output_summary = _summarize_record_file(output_path, target_max_batch_bytes)
    object_store_summary = _summarize_object_store_size(
        object_store_size_kb=object_store_size_kb,
        target_max_batch_bytes=target_max_batch_bytes,
    )
    replay_summary = _summarize_replay_dir(replay_dir)

    if not batch_summary["exists"]:
        warnings.append("research_batch_not_built_yet")

    if not output_summary["exists"]:
        warnings.append("research_output_not_built_yet")

    if replay_summary["result_dir_exists"] and replay_summary["json_file_count"] == 0:
        blocked_reasons.append("replay_result_dir_has_no_json_artifacts")

    output_records = output_summary.get("record_count") or output_summary.get("non_empty_line_count") or 0
    batch_records = batch_summary.get("record_count") or batch_summary.get("non_empty_line_count") or 0
    replay_candidates = replay_summary.get("replay_candidate_count")

    if output_summary["exists"] and output_records <= 10:
        warnings.append("research_output_sparse")
        findings.append(
            f"Research output contains only {output_records} parsed records/non-empty lines."
        )

    if batch_summary["exists"]:
        utilization = batch_summary["target_utilization"]
        multiplier = batch_summary["estimated_safe_multiplier_to_target"]

        if utilization < 0.25:
            findings.append(
                f"Research batch is using {round(utilization * 100, 2)}% of the configured "
                f"{target_max_batch_bytes} byte target."
            )
            recommendations.append(
                f"Increase research batch size by up to about {multiplier}x before hitting the configured target."
            )

        if batch_records <= 10:
            recommendations.append(
                "Increase the number of replay candidates included in each research batch; current batch appears very small."
            )

    if object_store_summary["declared_size_bytes"] > 0:
        utilization = object_store_summary["target_utilization"]
        multiplier = object_store_summary["estimated_safe_multiplier_to_target"]

        findings.append(
            f"QuantConnect Object Store source footprint is {object_store_summary['declared_size_kb']} KB."
        )

        if utilization < 0.25:
            findings.append(
                f"Object Store source footprint is using {round(utilization * 100, 2)}% "
                f"of the configured {target_max_batch_bytes} byte research target."
            )
            recommendations.append(
                f"Increase replay/research source volume by up to about {multiplier}x "
                "before hitting the configured target."
            )

    if isinstance(replay_candidates, int) and replay_candidates > 0 and output_records > 0:
        coverage = output_records / replay_candidates
        replay_summary["research_output_to_replay_candidate_ratio"] = round(coverage, 6)

        if coverage < 0.25:
            warnings.append("research_output_low_candidate_coverage")
            recommendations.append(
                "Validate candidate-to-research selection logic; output covers a small share of replay candidates."
            )

    if replay_summary["blocked_reason_counts"]:
        findings.append(
            "Replay artifacts include blocked reasons that should be reviewed before expanding research volume."
        )

    status = _classify_status(blocked_reasons, warnings)

    report = {
        "artifact_type": "signalforge_research_build_report",
        "adapter_type": "research_build_report_builder",
        "contract": "research_build_report",
        "status": status,
        "is_ready": status == "ready",
        "live_readiness_state": status,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "source_paths": {
            "replay_result_dir": _stable_path(replay_dir),
            "research_batch_path": _stable_path(batch_path),
            "research_output_path": _stable_path(output_path),
        },
        "target_max_batch_bytes": target_max_batch_bytes,
        "file_summary": _summarize_files(replay_dir, batch_path, output_path),
        "batch_summary": batch_summary,
        "research_output_summary": output_summary,
        "object_store_summary": object_store_summary,
        "replay_summary": replay_summary,
        "build_findings": _dedupe_sorted(findings),
        "next_build_recommendations": _dedupe_sorted(recommendations),
        "warnings": _dedupe_sorted(warnings),
        "blocked_reasons": _dedupe_sorted(blocked_reasons),
    }

    return _json_round_trip(report)


def render_research_build_report_markdown(report: dict[str, Any]) -> str:
    batch = report.get("batch_summary", {})
    output = report.get("research_output_summary", {})
    obj = report.get("object_store_summary", {})
    replay = report.get("replay_summary", {})

    lines = [
        "# SignalForge Research Build Report",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Contract: `{report.get('contract')}`",
        f"- Replay result dir: `{report.get('source_paths', {}).get('replay_result_dir')}`",
        f"- Research batch: `{report.get('source_paths', {}).get('research_batch_path')}`",
        f"- Research output: `{report.get('source_paths', {}).get('research_output_path')}`",
        "",
        "## QuantConnect Object Store summary",
        "",
        f"- Declared size KB: `{obj.get('declared_size_kb')}`",
        f"- Declared size bytes: `{obj.get('declared_size_bytes')}`",
        f"- Target utilization: `{obj.get('target_utilization')}`",
        f"- Estimated safe multiplier to target: `{obj.get('estimated_safe_multiplier_to_target')}`",
        "",
        "## Batch summary",
        "",
        f"- Exists: `{batch.get('exists')}`",
        f"- Size bytes: `{batch.get('size_bytes')}`",
        f"- Size KB: `{batch.get('size_kb')}`",
        f"- Non-empty lines: `{batch.get('non_empty_line_count')}`",
        f"- Parsed records: `{batch.get('record_count')}`",
        f"- Target utilization: `{batch.get('target_utilization')}`",
        f"- Estimated safe multiplier to target: `{batch.get('estimated_safe_multiplier_to_target')}`",
        "",
        "## Research output summary",
        "",
        f"- Exists: `{output.get('exists')}`",
        f"- Size bytes: `{output.get('size_bytes')}`",
        f"- Non-empty lines: `{output.get('non_empty_line_count')}`",
        f"- Parsed records: `{output.get('record_count')}`",
        "",
        "## Replay summary",
        "",
        f"- JSON artifact count: `{replay.get('json_file_count')}`",
        f"- Contract outcome snapshot count: `{replay.get('contract_outcome_snapshot_count')}`",
        f"- Replay candidate count: `{replay.get('replay_candidate_count')}`",
        f"- Research output to replay candidate ratio: `{replay.get('research_output_to_replay_candidate_ratio')}`",
        f"- Readiness state counts: `{json.dumps(replay.get('readiness_state_counts', {}), sort_keys=True)}`",
        f"- Blocked reason counts: `{json.dumps(replay.get('blocked_reason_counts', {}), sort_keys=True)}`",
        f"- Edge score summary: `{json.dumps(replay.get('edge_score_summary', {}), sort_keys=True)}`",
        "",
        "## Findings",
        "",
    ]

    findings = report.get("build_findings") or []
    lines.extend([f"- {item}" for item in findings] or ["- None"])

    lines.extend(["", "## Next build recommendations", ""])
    recommendations = report.get("next_build_recommendations") or []
    lines.extend([f"- {item}" for item in recommendations] or ["- None"])

    lines.extend(["", "## Warnings", ""])
    warnings = report.get("warnings") or []
    lines.extend([f"- `{item}`" for item in warnings] or ["- None"])

    lines.extend(["", "## Blocked reasons", ""])
    blocked = report.get("blocked_reasons") or []
    lines.extend([f"- `{item}`" for item in blocked] or ["- None"])

    lines.extend(["", "## Explicitly excluded", ""])
    lines.extend([f"- `{item}`" for item in report.get("explicit_exclusions", [])])

    return "\n".join(lines) + "\n"


def write_research_build_report(
    report: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "signalforge_research_build_report.json"
    md_path = out_dir / "signalforge_research_build_report.md"

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_research_build_report_markdown(report), encoding="utf-8")

    return {
        "json": str(json_path),
        "markdown": str(md_path),
    }


def _summarize_record_file(path: Path | None, target_max_batch_bytes: int) -> dict[str, Any]:
    if path is None:
        return {
            "exists": False,
            "path": None,
            "size_bytes": 0,
            "size_kb": 0.0,
            "non_empty_line_count": 0,
            "record_count": 0,
            "sha256": None,
            "target_utilization": 0.0,
            "estimated_safe_multiplier_to_target": 0,
            "parse_error": None,
        }

    if not path.exists():
        return {
            "exists": False,
            "path": _stable_path(path),
            "size_bytes": 0,
            "size_kb": 0.0,
            "non_empty_line_count": 0,
            "record_count": 0,
            "sha256": None,
            "target_utilization": 0.0,
            "estimated_safe_multiplier_to_target": 0,
            "parse_error": None,
        }

    size = path.stat().st_size
    non_empty_lines = _count_non_empty_lines(path)
    record_count, parse_error = _count_records(path)

    utilization = size / target_max_batch_bytes if target_max_batch_bytes > 0 else 0.0
    multiplier = int(target_max_batch_bytes // size) if size > 0 else 0

    return {
        "exists": True,
        "path": _stable_path(path),
        "size_bytes": size,
        "size_kb": round(size / 1024, 3),
        "non_empty_line_count": non_empty_lines,
        "record_count": record_count,
        "sha256": _sha256(path),
        "target_utilization": round(utilization, 6),
        "estimated_safe_multiplier_to_target": max(multiplier, 1) if size > 0 else 0,
        "parse_error": parse_error,
    }


def _summarize_object_store_size(
    object_store_size_kb: float | None,
    target_max_batch_bytes: int,
) -> dict[str, Any]:
    if object_store_size_kb is None:
        return {
            "declared_size_kb": None,
            "declared_size_bytes": 0,
            "target_utilization": 0.0,
            "estimated_safe_multiplier_to_target": 0,
        }

    size_bytes = int(object_store_size_kb * 1024)
    utilization = size_bytes / target_max_batch_bytes if target_max_batch_bytes > 0 else 0.0
    multiplier = int(target_max_batch_bytes // size_bytes) if size_bytes > 0 else 0

    return {
        "declared_size_kb": object_store_size_kb,
        "declared_size_bytes": size_bytes,
        "target_utilization": round(utilization, 6),
        "estimated_safe_multiplier_to_target": max(multiplier, 1) if size_bytes > 0 else 0,
    }


def _summarize_replay_dir(replay_dir: Path) -> dict[str, Any]:
    if not replay_dir.exists():
        return {
            "result_dir_exists": False,
            "json_file_count": 0,
            "json_files": [],
            "contract_outcome_snapshot_count": 0,
            "replay_candidate_count": None,
            "readiness_state_counts": {},
            "blocked_reason_counts": {},
            "edge_score_summary": {},
        }

    json_files = sorted(path for path in replay_dir.rglob("*.json") if path.is_file())
    loaded_payloads: list[Any] = []

    for path in json_files:
        payload, _error = _try_load_json(path)
        if payload is not None:
            loaded_payloads.append(payload)

    contract_snapshots = _load_contract_snapshots(replay_dir)
    scan_roots = contract_snapshots if contract_snapshots else loaded_payloads

    replay_candidate_count = _max_int_field(loaded_payloads, "replay_candidate_count")
    readiness_counts = _counter_for_fields(
        scan_roots,
        ["live_readiness_state", "historical_edge_state", "status"],
    )
    blocked_reason_counts = _blocked_reason_counts(scan_roots)
    edge_score_summary = _score_summary(
        scan_roots,
        ["risk_adjusted_edge_score", "historical_edge_score"],
    )

    return {
        "result_dir_exists": True,
        "json_file_count": len(json_files),
        "json_files": [_stable_path(path.relative_to(replay_dir)) for path in json_files],
        "contract_outcome_snapshot_count": len(contract_snapshots),
        "replay_candidate_count": replay_candidate_count,
        "readiness_state_counts": dict(sorted(readiness_counts.items())),
        "blocked_reason_counts": dict(sorted(blocked_reason_counts.items())),
        "edge_score_summary": edge_score_summary,
    }


def _summarize_files(
    replay_dir: Path,
    batch_path: Path | None,
    output_path: Path | None,
) -> dict[str, Any]:
    paths: list[Path] = []

    if replay_dir.exists():
        paths.extend(sorted(path for path in replay_dir.rglob("*") if path.is_file()))

    for path in [batch_path, output_path]:
        if path is not None and path.exists() and path not in paths:
            paths.append(path)

    file_sizes = {
        _stable_path(path): path.stat().st_size
        for path in sorted(paths, key=lambda item: _stable_path(item))
    }

    return {
        "file_count": len(file_sizes),
        "file_sizes": file_sizes,
        "total_size_bytes": sum(file_sizes.values()),
    }


def _load_contract_snapshots(replay_dir: Path) -> list[dict[str, Any]]:
    path = replay_dir / CONTRACT_OUTCOME_FILE
    payload, _error = _try_load_json(path)

    if not isinstance(payload, dict):
        return []

    snapshots = payload.get("contract_outcome_snapshots")

    if not isinstance(snapshots, list):
        return []

    return [item for item in snapshots if isinstance(item, dict)]


def _count_records(path: Path) -> tuple[int, str | None]:
    if path.suffix.lower() == ".jsonl":
        return _count_jsonl_records(path)

    payload, error = _try_load_json(path)

    if error:
        return 0, error

    if isinstance(payload, list):
        return len(payload), None

    if isinstance(payload, dict):
        for key in TOP_LEVEL_RECORD_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                return len(value), None

        return 1, None

    return 0, "json_payload_is_not_list_or_object"


def _count_jsonl_records(path: Path) -> tuple[int, str | None]:
    count = 0
    first_error: str | None = None

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw = line.strip()

            if not raw:
                continue

            try:
                json.loads(raw)
                count += 1
            except json.JSONDecodeError as exc:
                if first_error is None:
                    first_error = f"line_{line_number}: {exc.msg}"

    return count, first_error


def _count_non_empty_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _try_load_json(path: Path) -> tuple[Any | None, str | None]:
    if not path.exists():
        return None, "file_missing"

    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as exc:
        return None, exc.msg


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _resolve_optional_path(value: str | Path | None) -> Path | None:
    if value is None:
        return None

    text = str(value).strip()

    return Path(text) if text else None


def _infer_file(root: Path, patterns: list[str]) -> Path | None:
    matches: list[Path] = []

    for pattern in patterns:
        matches.extend(path for path in root.rglob(pattern) if path.is_file())

    if not matches:
        return None

    return sorted(set(matches), key=lambda path: (-path.stat().st_size, str(path)))[0]


def _counter_for_fields(roots: Any, field_names: list[str]) -> Counter[str]:
    counter: Counter[str] = Counter()

    for item in _walk(roots):
        if not isinstance(item, dict):
            continue

        for field_name in field_names:
            value = item.get(field_name)

            if isinstance(value, str) and value.strip():
                counter[value.strip()] += 1

    return counter


def _blocked_reason_counts(roots: Any) -> Counter[str]:
    counter: Counter[str] = Counter()

    for item in _walk(roots):
        if not isinstance(item, dict):
            continue

        reasons = item.get("blocked_reasons")

        if isinstance(reasons, list):
            for reason in reasons:
                if isinstance(reason, str) and reason.strip():
                    counter[reason.strip()] += 1

        reason = item.get("blocked_reason")

        if isinstance(reason, str) and reason.strip():
            counter[reason.strip()] += 1

    return counter


def _score_summary(roots: Any, field_names: list[str]) -> dict[str, Any]:
    values: list[float] = []

    for item in _walk(roots):
        if not isinstance(item, dict):
            continue

        for field_name in field_names:
            value = item.get(field_name)

            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values.append(float(value))

    if not values:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "average": None,
        }

    return {
        "count": len(values),
        "min": round(min(values), 6),
        "max": round(max(values), 6),
        "average": round(mean(values), 6),
    }


def _max_int_field(roots: Any, field_name: str) -> int | None:
    values: list[int] = []

    for item in _walk(roots):
        if not isinstance(item, dict):
            continue

        value = item.get(field_name)

        if isinstance(value, int) and not isinstance(value, bool):
            values.append(value)

    return max(values) if values else None


def _walk(value: Any) -> Iterable[Any]:
    yield value

    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)

    if isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _classify_status(blocked_reasons: list[str], warnings: list[str]) -> str:
    if blocked_reasons:
        return "blocked"

    if warnings:
        return "needs_review"

    return "ready"


def _dedupe_sorted(values: list[str]) -> list[str]:
    return sorted(set(values))


def _stable_path(path: Path | None) -> str | None:
    if path is None:
        return None

    return str(path).replace("\\", "/")


def _json_round_trip(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, sort_keys=True))
