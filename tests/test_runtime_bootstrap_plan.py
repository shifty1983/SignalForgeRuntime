from __future__ import annotations

from pathlib import Path

from signalforge.contracts.runtime_source_map import RUNTIME_SOURCE_MAPPINGS
from signalforge.runtime.bootstrap_plan import build_runtime_bootstrap_plan, write_bootstrap_plan


def test_bootstrap_plan_blocks_when_seed_bundle_missing():
    plan = build_runtime_bootstrap_plan(Path("does_not_exist"))

    assert not plan.is_ready
    assert plan.blocker_count > 0
    assert plan.row_count == len(RUNTIME_SOURCE_MAPPINGS)


def test_bootstrap_plan_ready_with_minimal_seed_sources(tmp_path: Path):
    root = tmp_path / "seed"
    root.mkdir()

    for mapping in RUNTIME_SOURCE_MAPPINGS:
        if mapping.seed_source_relative_path:
            source_path = root / mapping.seed_source_relative_path
            source_path.mkdir(parents=True, exist_ok=True)
            (source_path / "sample.json").write_text("{}", encoding="utf-8")

    plan = build_runtime_bootstrap_plan(root)

    assert plan.is_ready
    assert plan.blocker_count == 0
    assert plan.row_count == len(RUNTIME_SOURCE_MAPPINGS)
    assert all(row.seed_file_count > 0 for row in plan.rows if row.seed_source_relative_path)


def test_write_bootstrap_plan(tmp_path: Path):
    root = tmp_path / "seed"
    root.mkdir()

    for mapping in RUNTIME_SOURCE_MAPPINGS:
        if mapping.seed_source_relative_path:
            source_path = root / mapping.seed_source_relative_path
            source_path.mkdir(parents=True, exist_ok=True)
            (source_path / "sample.json").write_text("{}", encoding="utf-8")

    plan = build_runtime_bootstrap_plan(root)
    output_path = write_bootstrap_plan(plan, tmp_path / "plan.json")

    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8")

