import importlib
import importlib.machinery
import importlib.util
import inspect
import json
import shutil
import sys
from pathlib import Path
from typing import Any


OUT_DIR = Path("docs/strategy_selection_engine")
BACKUP_PATH = OUT_DIR / "stage36j_backtesting_backups" / "historical_strategy_selection_rows_builder.py.before_stage36j"

ORIGINAL_OUTPUT_DIR = OUT_DIR / "stage36k_original_selection_replay_output"
CURRENT_OUTPUT_DIR = OUT_DIR / "stage36k_current_selection_replay_output"

CURRENT_MODULE_NAME = "signalforge.backtesting.historical_strategy_selection_rows_builder"
ARTIFACT_ROOT = Path("artifacts")


def load_module_from_any_suffix(module_name: str, path: Path):
    loader = importlib.machinery.SourceFileLoader(module_name, str(path))
    spec = importlib.util.spec_from_loader(module_name, loader)

    if spec is None:
        raise RuntimeError(f"Could not create loader spec for {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    loader.exec_module(module)
    return module


def newest_existing(paths: list[Path]) -> Path | None:
    existing = [p for p in paths if p.exists()]
    if not existing:
        return None
    return sorted(existing, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def find_candidate_file(patterns: list[str]) -> Path | None:
    candidates: list[Path] = []

    for pattern in patterns:
        candidates.extend(ARTIFACT_ROOT.glob(pattern))

    return newest_existing(candidates)


def resolve_arg(name: str, original_output_dir: Path, current_output_dir: Path | None = None) -> Any:
    lowered = name.lower()

    if "output" in lowered and "dir" in lowered:
        return original_output_dir

    if "candidate" in lowered and "path" in lowered:
        path = find_candidate_file([
            "historical_strategy_candidate_rows_*/signalforge_historical_strategy_candidate_rows.jsonl",
            "**/signalforge_historical_strategy_candidate_rows.jsonl",
        ])
        if path is None:
            raise FileNotFoundError("Could not locate historical strategy candidate rows artifact")
        return path

    if "expectancy" in lowered and "path" in lowered:
        path = find_candidate_file([
            "walk_forward_expectancy_*/signalforge_walk_forward_expectancy_rows.jsonl",
            "walk_forward_expectancy_*/signalforge_walk_forward_expectancy.jsonl",
            "**/signalforge_walk_forward_expectancy_rows.jsonl",
            "**/signalforge_walk_forward_expectancy.jsonl",
        ])
        if path is None:
            raise FileNotFoundError("Could not locate walk-forward expectancy rows artifact")
        return path

    if "start" in lowered and "date" in lowered:
        return None

    if "end" in lowered and "date" in lowered:
        return None

    raise RuntimeError(f"Unresolved required argument: {name}")


def build_call_args(func, output_dir: Path) -> tuple[list[Any], dict[str, Any], dict[str, str]]:
    sig = inspect.signature(func)
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    resolved: dict[str, str] = {}

    for name, param in sig.parameters.items():
        if param.kind in {param.VAR_POSITIONAL, param.VAR_KEYWORD}:
            continue

        if param.default is not param.empty:
            continue

        value = resolve_arg(name, output_dir)

        if value is None and param.default is not param.empty:
            continue

        resolved[name] = str(value)

        if param.kind == param.KEYWORD_ONLY:
            kwargs[name] = value
        else:
            args.append(value)

    return args, kwargs, resolved


def normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        normalized = {}

        for key, item in value.items():
            key_lower = str(key).lower()

            if key_lower in {
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
        text = value.replace(str(ORIGINAL_OUTPUT_DIR), "<OUTPUT_DIR>")
        text = text.replace(str(CURRENT_OUTPUT_DIR), "<OUTPUT_DIR>")
        text = text.replace(str(ORIGINAL_OUTPUT_DIR).replace("/", "\\"), "<OUTPUT_DIR>")
        text = text.replace(str(CURRENT_OUTPUT_DIR).replace("/", "\\"), "<OUTPUT_DIR>")
        return text

    return value


def canonical_json(value: Any) -> str:
    return json.dumps(normalize_value(value), sort_keys=True, default=str)


def read_json_or_jsonl(path: Path) -> Any:
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


def file_manifest(output_dir: Path) -> dict[str, Path]:
    manifest = {}

    if not output_dir.exists():
        return manifest

    for path in output_dir.rglob("*"):
        if path.is_file():
            manifest[str(path.relative_to(output_dir)).replace("\\", "/")] = path

    return manifest


def compare_outputs() -> tuple[list[dict[str, Any]], list[str]]:
    blockers = []
    rows = []

    original_files = file_manifest(ORIGINAL_OUTPUT_DIR)
    current_files = file_manifest(CURRENT_OUTPUT_DIR)

    all_names = sorted(set(original_files) | set(current_files))

    for name in all_names:
        original_path = original_files.get(name)
        current_path = current_files.get(name)

        if original_path is None:
            rows.append({
                "file": name,
                "exists_original": False,
                "exists_current": True,
                "same": False,
                "original_count": None,
                "current_count": None,
            })
            blockers.append(f"missing_original_output_file_{name}")
            continue

        if current_path is None:
            rows.append({
                "file": name,
                "exists_original": True,
                "exists_current": False,
                "same": False,
                "original_count": None,
                "current_count": None,
            })
            blockers.append(f"missing_current_output_file_{name}")
            continue

        original_value = read_json_or_jsonl(original_path)
        current_value = read_json_or_jsonl(current_path)

        original_canonical = canonical_json(original_value)
        current_canonical = canonical_json(current_value)

        same = original_canonical == current_canonical

        rows.append({
            "file": name,
            "exists_original": True,
            "exists_current": True,
            "same": same,
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

    if blockers:
        raise SystemExit("\n".join(blockers))

    shutil.rmtree(ORIGINAL_OUTPUT_DIR, ignore_errors=True)
    shutil.rmtree(CURRENT_OUTPUT_DIR, ignore_errors=True)
    ORIGINAL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CURRENT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    original_module = load_module_from_any_suffix(
        "stage36k_original_historical_strategy_selection_rows_builder",
        BACKUP_PATH,
    )

    sys.modules.pop(CURRENT_MODULE_NAME, None)
    current_module = importlib.import_module(CURRENT_MODULE_NAME)

    func_name = "build_historical_strategy_selection_rows_artifact"

    original_func = getattr(original_module, func_name)
    current_func = getattr(current_module, func_name)

    original_args, original_kwargs, original_resolved = build_call_args(original_func, ORIGINAL_OUTPUT_DIR)
    current_args, current_kwargs, current_resolved = build_call_args(current_func, CURRENT_OUTPUT_DIR)

    original_result = original_func(*original_args, **original_kwargs)
    current_result = current_func(*current_args, **current_kwargs)

    result_same = canonical_json(original_result) == canonical_json(current_result)

    if not result_same:
        blockers.append("builder_return_value_mismatch")

    output_rows, output_blockers = compare_outputs()
    blockers.extend(output_blockers)

    warnings.append("stage36k_runs_historical_selection_replay_only")
    warnings.append("historical_wrapper_remains_in_backtesting_engine_owns_selection_decision_helpers")

    summary = {
        "adapter_type": "historical_strategy_selection_replay_parity_builder",
        "artifact_type": "signalforge_historical_strategy_selection_replay_parity",
        "contract": "historical_strategy_selection_replay_parity",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "function": func_name,
        "backup_path": str(BACKUP_PATH),
        "current_module": CURRENT_MODULE_NAME,
        "original_output_dir": str(ORIGINAL_OUTPUT_DIR),
        "current_output_dir": str(CURRENT_OUTPUT_DIR),
        "original_resolved_args": original_resolved,
        "current_resolved_args": current_resolved,
        "result_same": result_same,
        "output_file_count": len(output_rows),
        "matching_output_file_count": sum(1 for row in output_rows if row["same"]),
        "output_rows": output_rows,
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": "stage36l_extract_selected_trade_sequence_decision_cluster_or_continue_candidate_filter_extraction",
    }

    summary_path = OUT_DIR / "signalforge_stage36k_historical_strategy_selection_replay_parity_summary.json"
    rows_path = OUT_DIR / "signalforge_stage36k_historical_strategy_selection_replay_parity_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage36k_historical_strategy_selection_replay_parity.md"

    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    with rows_path.open("w", encoding="utf-8") as f:
        for row in output_rows:
            f.write(json.dumps(row, default=str) + "\n")

    md = [
        "# Stage 36K Historical Strategy Selection Replay Parity",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- result_same: {summary['result_same']}",
        f"- output_file_count: {summary['output_file_count']}",
        f"- matching_output_file_count: {summary['matching_output_file_count']}",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
        "## Resolved Inputs",
        "",
        "### Original",
        "",
    ]

    for key, value in original_resolved.items():
        md.append(f"- {key}: `{value}`")

    md.extend(["", "### Current", ""])

    for key, value in current_resolved.items():
        md.append(f"- {key}: `{value}`")

    md.extend([
        "",
        "## Output Files",
        "",
        "| file | same | original count | current count |",
        "|---|---:|---:|---:|",
    ])

    for row in output_rows:
        md.append(
            f"| `{row['file']}` | {row['same']} | "
            f"{row['original_count']} | {row['current_count']} |"
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

    print("\n--- Stage 36K historical strategy selection replay parity compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "result_same",
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

    print("\n--- Stage 36K resolved inputs ---")
    print("original:")
    for key, value in original_resolved.items():
        print(f"{key}: {value}")
    print("current:")
    for key, value in current_resolved.items():
        print(f"{key}: {value}")

    print("\n--- Stage 36K output rows compact ---")
    print("file\tsame\toriginal_count\tcurrent_count")
    for row in output_rows:
        print(f"{row['file']}\t{row['same']}\t{row['original_count']}\t{row['current_count']}")

    if blockers:
        print("\n--- Stage 36K blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 36K warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
