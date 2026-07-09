import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from signalforge.engines.paper_trading.canonical_paper_review_bundle_reader import (
    build_canonical_paper_review_bundle_reader,
)


CANONICAL_ROOT = Path("data/canonical/signalforge_pipeline")

CONTRACT = "canonical_portfolio_construction_reader"
ARTIFACT_TYPE = "signalforge_canonical_portfolio_construction_reader"

STAGE_ROLES = {
    "position_sizing": "position_sizing_manifest",
    "equity_reconstruction": "equity_reconstruction_manifest",
    "allocated_equity_reconstruction": "allocated_equity_reconstruction_manifest",
}


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _count_jsonl(path: Path) -> Optional[int]:
    if not path.exists() or path.suffix.lower() != ".jsonl":
        return None

    count = 0
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def _is_canonical(path_text: str) -> bool:
    try:
        Path(path_text).resolve().relative_to(CANONICAL_ROOT.resolve())
        return True
    except Exception:
        return False


def _stage_dir_from_manifest(path: Path) -> Path:
    return path.parent


def _discover_stage_files(stage_dir: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    if not stage_dir.exists():
        return rows

    for path in sorted(stage_dir.glob("*"), key=lambda p: str(p).lower()):
        if not path.is_file():
            continue

        role = "other"
        lower_name = path.name.lower()

        if "summary" in lower_name:
            role = "summary"
        elif "manifest" in lower_name:
            role = "manifest"
        elif path.suffix.lower() == ".jsonl":
            role = "rows"
        elif path.suffix.lower() == ".json":
            role = "json"

        rows.append({
            "stage_dir": str(stage_dir),
            "file_role": role,
            "path": str(path),
            "exists": path.exists(),
            "canonical": _is_canonical(str(path)),
            "suffix": path.suffix.lower(),
            "size_bytes": path.stat().st_size if path.exists() else None,
            "jsonl_row_count": _count_jsonl(path),
        })

    return rows


def build_canonical_portfolio_construction_reader(
    handoff_contract_path: str | Path = "configs/paper_live_engine/signalforge_v21_paper_live_engine_handoff_contract.json",
) -> Dict[str, Any]:
    blockers: List[str] = []
    warnings: List[str] = [
        "canonical_portfolio_construction_reader_does_not_run_optimization",
        "canonical_portfolio_construction_reader_does_not_create_orders",
        "paper_runtime_consumes_promoted_canonical_stage_24_25_25a_outputs",
    ]

    bundle_artifact = build_canonical_paper_review_bundle_reader(handoff_contract_path)

    if bundle_artifact.get("is_ready") is not True:
        blockers.append("paper_review_bundle_reader_not_ready")

    paper_review_bundle = bundle_artifact.get("paper_review_bundle", {})
    artifact_paths = paper_review_bundle.get("artifact_paths", {}) if isinstance(paper_review_bundle, Mapping) else {}

    manifest_rows: List[Dict[str, Any]] = []
    stage_file_rows: List[Dict[str, Any]] = []

    for stage_role, artifact_role in STAGE_ROLES.items():
        path_text = artifact_paths.get(artifact_role)

        if not isinstance(path_text, str):
            blockers.append(f"missing_bundle_artifact_path_{artifact_role}")
            continue

        path = Path(path_text)

        row: Dict[str, Any] = {
            "stage_role": stage_role,
            "artifact_role": artifact_role,
            "manifest_path": path_text,
            "exists": path.exists(),
            "canonical": _is_canonical(path_text),
            "is_ready": None,
            "artifact_type": None,
            "contract": None,
            "read_error": None,
        }

        if not path.exists():
            blockers.append(f"missing_canonical_manifest_{stage_role}_{path}")

        if not _is_canonical(path_text):
            blockers.append(f"non_canonical_manifest_{stage_role}_{path}")

        if path.exists():
            try:
                data = _read_json(path)
                row.update({
                    "is_ready": data.get("is_ready") if isinstance(data, dict) else None,
                    "artifact_type": data.get("artifact_type") if isinstance(data, dict) else None,
                    "contract": data.get("contract") if isinstance(data, dict) else None,
                    "top_level_keys": sorted(list(data.keys())) if isinstance(data, dict) else [],
                })
            except Exception as exc:
                row["read_error"] = str(exc)
                blockers.append(f"manifest_read_error_{stage_role}_{exc}")

            stage_file_rows.extend(_discover_stage_files(_stage_dir_from_manifest(path)))

        manifest_rows.append(row)

    for row in stage_file_rows:
        if row["canonical"] is not True:
            blockers.append(f"non_canonical_stage_file_{row['path']}")

    checks = [
        {
            "check": "paper_review_bundle_ready",
            "passed": bundle_artifact.get("is_ready") is True,
        },
        {
            "check": "position_sizing_manifest_present",
            "passed": any(row["stage_role"] == "position_sizing" and row["exists"] for row in manifest_rows),
        },
        {
            "check": "equity_reconstruction_manifest_present",
            "passed": any(row["stage_role"] == "equity_reconstruction" and row["exists"] for row in manifest_rows),
        },
        {
            "check": "allocated_equity_reconstruction_manifest_present",
            "passed": any(row["stage_role"] == "allocated_equity_reconstruction" and row["exists"] for row in manifest_rows),
        },
        {
            "check": "all_manifest_paths_canonical",
            "passed": all(row["canonical"] for row in manifest_rows),
        },
        {
            "check": "all_discovered_stage_files_canonical",
            "passed": all(row["canonical"] for row in stage_file_rows),
        },
        {
            "check": "does_not_authorize_trades",
            "passed": True,
        },
    ]

    failed_checks = [row["check"] for row in checks if row["passed"] is not True]
    if failed_checks:
        blockers.append(f"failed_portfolio_construction_reader_checks_{failed_checks}")

    return {
        "adapter_type": "canonical_portfolio_construction_reader_builder",
        "artifact_type": ARTIFACT_TYPE,
        "contract": CONTRACT,
        "is_ready": len(blockers) == 0,
        "readiness_state": "ready_for_paper_portfolio_review" if not blockers else "blocked",
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "canonical_root": str(CANONICAL_ROOT),
        "manifest_count": len(manifest_rows),
        "stage_file_count": len(stage_file_rows),
        "manifest_rows": manifest_rows,
        "stage_file_rows": stage_file_rows,
        "checks": checks,
        "portfolio_construction_policy": "consume_canonical_stage_24_25_25a_outputs_only",
        "optimizer_policy": "do_not_run_optimizer_in_paper_runtime",
        "trade_authorization": "not_authorized_by_canonical_portfolio_construction_reader",
        "requires_manual_approval": True,
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
    }
