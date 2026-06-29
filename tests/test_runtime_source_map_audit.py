from __future__ import annotations

from pathlib import Path

from signalforge.contracts.runtime_inputs import RUNTIME_INPUT_CONTRACTS
from signalforge.contracts.runtime_source_map import RUNTIME_SOURCE_MAPPINGS
from signalforge.data.runtime_source_map_audit import build_runtime_source_map_audit


def test_every_source_mapping_targets_existing_runtime_contract():
    contract_names = {contract.name for contract in RUNTIME_INPUT_CONTRACTS}
    mapping_names = {mapping.runtime_input_name for mapping in RUNTIME_SOURCE_MAPPINGS}

    assert mapping_names == contract_names


def test_source_map_reports_missing_seed_sources_when_no_bundle():
    audit = build_runtime_source_map_audit(seed_bundle=Path("does_not_exist"))

    assert not audit.is_ready
    assert audit.blocker_count > 0

    blockers = {status.blocker for status in audit.statuses if status.blocker}
    assert "required_seed_source_missing" in blockers


def test_source_map_ready_with_minimal_seed_sources(tmp_path: Path):
    root = tmp_path / "seed"
    root.mkdir()

    for mapping in RUNTIME_SOURCE_MAPPINGS:
        if mapping.seed_source_relative_path:
            source_path = root / mapping.seed_source_relative_path
            source_path.mkdir(parents=True, exist_ok=True)

    audit = build_runtime_source_map_audit(seed_bundle=root)

    assert audit.is_ready
    assert audit.blocker_count == 0
    assert audit.mapping_count == len(RUNTIME_SOURCE_MAPPINGS)
