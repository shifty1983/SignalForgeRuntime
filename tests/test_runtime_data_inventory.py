from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from signalforge.contracts.runtime_inputs import RUNTIME_INPUT_CONTRACTS
from signalforge.data.runtime_data_inventory import build_runtime_data_inventory


def write_required_runtime_files(root: Path, *, content: str = "{}\n") -> None:
    for contract in RUNTIME_INPUT_CONTRACTS:
        path = root / contract.relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def test_empty_runtime_data_reports_missing_required_inputs(tmp_path: Path):
    inventory = build_runtime_data_inventory(tmp_path)

    assert not inventory.is_ready
    assert inventory.input_count == len(RUNTIME_INPUT_CONTRACTS)
    assert inventory.missing_required_count == len(RUNTIME_INPUT_CONTRACTS)
    assert inventory.blocker_count == len(RUNTIME_INPUT_CONTRACTS)

    blockers = {status.blocker for status in inventory.statuses}
    assert blockers == {"missing_required_input"}


def test_complete_runtime_data_reports_ready(tmp_path: Path):
    write_required_runtime_files(tmp_path)

    inventory = build_runtime_data_inventory(tmp_path)

    assert inventory.is_ready
    assert inventory.blocker_count == 0
    assert inventory.missing_required_count == 0
    assert inventory.stale_required_count == 0


def test_empty_required_file_blocks_runtime(tmp_path: Path):
    write_required_runtime_files(tmp_path)

    first_contract = RUNTIME_INPUT_CONTRACTS[0]
    empty_path = tmp_path / first_contract.relative_path
    empty_path.write_text("", encoding="utf-8")

    inventory = build_runtime_data_inventory(tmp_path)

    assert not inventory.is_ready
    assert inventory.blocker_count == 1

    blocked = [status for status in inventory.statuses if status.blocker]
    assert blocked[0].name == first_contract.name
    assert blocked[0].blocker == "empty_required_input"


def test_stale_required_file_blocks_runtime(tmp_path: Path):
    write_required_runtime_files(tmp_path)

    now = datetime(2026, 6, 28, tzinfo=timezone.utc)
    stale_contract = next(
        contract for contract in RUNTIME_INPUT_CONTRACTS
        if contract.max_age_days is not None
    )

    stale_path = tmp_path / stale_contract.relative_path
    stale_mtime = (now - timedelta(days=stale_contract.max_age_days + 2)).timestamp()
    os.utime(stale_path, (stale_mtime, stale_mtime))

    inventory = build_runtime_data_inventory(tmp_path, now=now)

    assert not inventory.is_ready
    assert inventory.stale_required_count == 1

    blocked = [status for status in inventory.statuses if status.blocker]
    assert blocked[0].name == stale_contract.name
    assert blocked[0].blocker == "stale_required_input"


def test_closed_trade_outcomes_has_no_freshness_limit(tmp_path: Path):
    write_required_runtime_files(tmp_path)

    now = datetime(2026, 6, 28, tzinfo=timezone.utc)
    outcome_contract = next(
        contract for contract in RUNTIME_INPUT_CONTRACTS
        if contract.name == "closed_trade_outcomes"
    )

    outcome_path = tmp_path / outcome_contract.relative_path
    old_mtime = (now - timedelta(days=3650)).timestamp()
    os.utime(outcome_path, (old_mtime, old_mtime))

    inventory = build_runtime_data_inventory(tmp_path, now=now)

    status_by_name = {status.name: status for status in inventory.statuses}
    outcome_status = status_by_name["closed_trade_outcomes"]

    assert outcome_status.exists
    assert outcome_status.is_fresh is True
    assert outcome_status.blocker is None

