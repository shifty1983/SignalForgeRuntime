from __future__ import annotations

from signalforge.backtesting.migrated_workflow_dry_run_inputs import (
    build_dry_run_input_availability_manifest,
)


def test_dry_run_input_scanner_builds_manifest():
    manifest = build_dry_run_input_availability_manifest()

    assert manifest["adapter_type"] == "migrated_workflow_strict_dry_run_input_availability_scanner"
    assert "categories" in manifest
    assert "blockers" in manifest
    assert "candidate_roots" in manifest
    assert "excluded_name_fragments" in manifest
