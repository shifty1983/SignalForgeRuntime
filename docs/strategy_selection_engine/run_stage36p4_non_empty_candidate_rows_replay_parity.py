import importlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any


OUT_DIR = Path("docs/strategy_selection_engine")
BACKUP_PATH = OUT_DIR / "stage36o_backtesting_backups" / "historical_strategy_candidate_rows_builder.py.before_stage36o.py"

DECISION_ROWS_PATH = Path(
    "artifacts/historical_strategy_family_eligibility_enrichment_local_rebuild_20210601_20260531/"
    "signalforge_historical_strategy_family_eligibility_enriched_decision_rows.jsonl"
)

EXPECTED_ROW_COUNT = 54456

ORIGINAL_OUTPUT_DIR = OUT_DIR / "stage36p4_original_candidate_rows_output"
CURRENT_OUTPUT_DIR = OUT_DIR / "stage36p4_current_candidate_rows_output"

CURRENT_MODULE_NAME = "signalforge.backtesting.historical_strategy_candidate_rows_builder"
FUNC_NAME = "build_historical_strategy_candidate_rows_artifact"


def load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        normalized = {}
        for key, item in value.items():
            key_l = str(key).lower()
            if key_l in {
                "path",
                "paths",
                "rows_path",
                "summary_path",
                "output_dir",
                "output_path",
                "created_at",
                "generated_at",
                "run_id",
            }:
                normalized[key] = "<normalized>"
            else:
                normalized[key] = normalize_value(item)
        return normalized

    if isinstance(value, list):
        return [normalize_value(item) for item in value]

    if isinstance(value, str):
        text = value
        for p in [ORIGINAL_OUTPUT_DIR, CURRENT_OUTPUT_DIR]:
            text = text.replace(str(p), "<OUTPUT_DIR>")
            text = text.replace(str(p).replace("/", "\\"), "<OUTPUT_DIR>")
        text = text.replace(str(DECISION_ROWS_PATH), "<DECISION_ROWS_PATH>")
        text = text.replace(str(DECISION_ROWS_PATH).replace("/", "\\"), "<DECISION_ROWS_PATH>")
        return text

    return value


def canonical(value: Any) -> str:
    return json.dumps(normalize_value(value), sort_keys=True, default=str)


def read_output(path: Path) -> Any:
    if path.suffix.lower() == ".jsonl":
        rows = []
        with path.open("r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8-sig"))

    return path.read_text(encoding="utf-8-sig", errors="replace")


def manifest(output_dir: Path) -> dict[str, Path]:
    files = {}
    if not output_dir.exists():
        return files
    for path in output_dir.rglob("*"):
        if path.is_file():
            files[str(path.relative_to(output_dir)).replace("\\", "/")] = path
    return files


def compare_outputs() -> tuple[list[dict[str, Any]], list[str]]:
    blockers = []
    rows = []

    original_files = manifest(ORIGINAL_OUTPUT_DIR)
    current_files = manifest(CURRENT_OUTPUT_DIR)

    for name in sorted(set(original_files) | set(current_files)):
        original_path = original_files.get(name)
        current_path = current_files.get(name)

        if original_path is None:
            rows.append({"file": name, "same": False, "exists_original": False, "exists_current": True})
            blockers.append(f"missing_original_output_file_{name}")
            continue

        if current_path is None:
            rows.append({"file": name, "same": False, "exists_original": True, "exists_current": False})
            blockers.append(f"missing_current_output_file_{name}")
            continue

        original_value = read_output(original_path)
        current_value = read_output(current_path)

        same = canonical(original_value) == canonical(current_value)

        rows.append({
            "file": name,
            "same": same,
            "exists_original": True,
            "exists_current": True,
            "original_count": len(original_value) if isinstance(original_value, list) else None,
            "current_count": len(current_value) if isinstance(current_value, list) else None,
        })

        if not same:
            blockers.append(f"output_mismatch_{name}")

    return rows, blockers


def main() -> None:
    blockers: list[str] = []
    warnings: list[str] = []

    if not BACKUP_PATH.exists():
        blockers.append(f"missing_backup_path_{BACKUP_PATH}")

    if not DECISION_ROWS_PATH.exists():
        blockers.append(f"missing_decision_rows_path_{DECISION_ROWS_PATH}")

    shutil.rmtree(ORIGINAL_OUTPUT_DIR, ignore_errors=True)
    shutil.rmtree(CURRENT_OUTPUT_DIR, ignore_errors=True)
    ORIGINAL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CURRENT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    original_result = None
    current_result = None
    output_rows = []

    if not blockers:
        original_module = load_module(
            "stage36p4_original_historical_strategy_candidate_rows_builder",
            BACKUP_PATH,
        )

        sys.modules.pop(CURRENT_MODULE_NAME, None)
        current_module = importlib.import_module(CURRENT_MODULE_NAME)

        original_func = getattr(original_module, FUNC_NAME)
        current_func = getattr(current_module, FUNC_NAME)

        original_result = original_func(
            decision_rows_path=DECISION_ROWS_PATH,
            output_dir=ORIGINAL_OUTPUT_DIR,
            strategy_policy_path=None,
        )

        current_result = current_func(
            decision_rows_path=DECISION_ROWS_PATH,
            output_dir=CURRENT_OUTPUT_DIR,
            strategy_policy_path=None,
        )

        result_same = canonical(original_result) == canonical(current_result)

        if not result_same:
            blockers.append("builder_return_value_mismatch")

        output_rows, output_blockers = compare_outputs()
        blockers.extend(output_blockers)

        candidate_row_outputs = [
            row for row in output_rows
            if row["file"] == "signalforge_historical_strategy_candidate_rows.jsonl"
        ]

        if not candidate_row_outputs:
            blockers.append("missing_candidate_rows_output_comparison")
        else:
            row = candidate_row_outputs[0]
            if row.get("original_count") != EXPECTED_ROW_COUNT:
                blockers.append(
                    f"original_candidate_row_count_unexpected_{row.get('original_count')}_expected_{EXPECTED_ROW_COUNT}"
                )
            if row.get("current_count") != EXPECTED_ROW_COUNT:
                blockers.append(
                    f"current_candidate_row_count_unexpected_{row.get('current_count')}_expected_{EXPECTED_ROW_COUNT}"
                )

    warnings.append("stage36p4_runs_non_empty_historical_candidate_rows_replay")
    warnings.append("historical_candidate_row_builder_remains_in_backtesting_engine_owns_candidate_filter_helpers")

    result_same = canonical(original_result) == canonical(current_result) if original_result is not None else False

    summary = {
        "adapter_type": "non_empty_historical_candidate_rows_replay_parity_builder",
        "artifact_type": "signalforge_non_empty_historical_candidate_rows_replay_parity",
        "contract": "non_empty_historical_candidate_rows_replay_parity",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "function": FUNC_NAME,
        "backup_path": str(BACKUP_PATH),
        "current_module": CURRENT_MODULE_NAME,
        "decision_rows_path": str(DECISION_ROWS_PATH),
        "strategy_policy_path": None,
        "expected_candidate_row_count": EXPECTED_ROW_COUNT,
        "original_output_dir": str(ORIGINAL_OUTPUT_DIR),
        "current_output_dir": str(CURRENT_OUTPUT_DIR),
        "result_same": result_same,
        "output_file_count": len(output_rows),
        "matching_output_file_count": sum(1 for row in output_rows if row.get("same") is True),
        "output_rows": output_rows,
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": "commit_stage36o_p4_or_classify_walk_forward_expectancy_logic",
    }

    summary_path = OUT_DIR / "signalforge_stage36p4_non_empty_candidate_rows_replay_parity_summary.json"
    rows_path = OUT_DIR / "signalforge_stage36p4_non_empty_candidate_rows_replay_parity_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage36p4_non_empty_candidate_rows_replay_parity.md"

    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    with rows_path.open("w", encoding="utf-8") as f:
        for row in output_rows:
            f.write(json.dumps(row, default=str) + "\n")

    md = [
        "# Stage 36P4 Non-Empty Historical Candidate Rows Replay Parity",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- result_same: {summary['result_same']}",
        f"- expected_candidate_row_count: {summary['expected_candidate_row_count']}",
        f"- output_file_count: {summary['output_file_count']}",
        f"- matching_output_file_count: {summary['matching_output_file_count']}",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
        "## Inputs",
        "",
        f"- decision_rows_path: `{summary['decision_rows_path']}`",
        f"- strategy_policy_path: `{summary['strategy_policy_path']}`",
        "",
        "## Output Files",
        "",
        "| file | same | original count | current count |",
        "|---|---:|---:|---:|",
    ]

    for row in output_rows:
        md.append(
            f"| `{row['file']}` | {row.get('same')} | "
            f"{row.get('original_count')} | {row.get('current_count')} |"
        )

    if blockers:
        md.extend(["", "## Blockers", ""])
        for blocker in blockers:
            md.append(f"- {blocker}")

    if warnings:
        md.extend(["", "## Warnings", ""])
        for warning in warnings:
            md.append(f"- {warning}")

    md_path.write_text("\n".join(md), encoding="utf-8")

    print("\n--- Stage 36P4 non-empty historical candidate rows replay parity compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "result_same",
        "expected_candidate_row_count",
        "output_file_count",
        "matching_output_file_count",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"summary_path: {summary_path}")
    print(f"rows_path: {rows_path}")
    print(f"md_path: {md_path}")
    print(f"original_output_dir: {ORIGINAL_OUTPUT_DIR}")
    print(f"current_output_dir: {CURRENT_OUTPUT_DIR}")

    print("\n--- Stage 36P4 inputs ---")
    print(f"decision_rows_path: {DECISION_ROWS_PATH}")
    print("strategy_policy_path: None")

    print("\n--- Stage 36P4 output rows compact ---")
    print("file\tsame\toriginal_count\tcurrent_count")
    for row in output_rows:
        print(f"{row['file']}\t{row.get('same')}\t{row.get('original_count')}\t{row.get('current_count')}")

    if blockers:
        print("\n--- Stage 36P4 blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 36P4 warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
