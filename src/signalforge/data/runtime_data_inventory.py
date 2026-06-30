from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from signalforge.contracts.runtime_inputs import RUNTIME_INPUT_CONTRACTS, RuntimeInputContract


@dataclass(frozen=True)
class RuntimeInputStatus:
    name: str
    relative_path: str
    required: bool
    exists: bool
    is_fresh: bool | None
    size_bytes: int | None
    modified_at_utc: str | None
    age_days: float | None
    max_age_days: int | None
    blocker: str | None
    warning: str | None


@dataclass(frozen=True)
class RuntimeDataInventory:
    root: str
    is_ready: bool
    blocker_count: int
    warning_count: int
    input_count: int
    missing_required_count: int
    stale_required_count: int
    statuses: tuple[RuntimeInputStatus, ...]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _file_age_days(path: Path, now: datetime) -> float:
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return (now - modified).total_seconds() / 86400.0


def _modified_at_utc(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def build_runtime_input_status(
    *,
    root: Path,
    contract: RuntimeInputContract,
    now: datetime,
) -> RuntimeInputStatus:
    path = root / contract.relative_path

    if not path.exists():
        return RuntimeInputStatus(
            name=contract.name,
            relative_path=contract.relative_path,
            required=contract.required,
            exists=False,
            is_fresh=None,
            size_bytes=None,
            modified_at_utc=None,
            age_days=None,
            max_age_days=contract.max_age_days,
            blocker="missing_required_input" if contract.required else None,
            warning=None if contract.required else "missing_optional_input",
        )

    size_bytes = path.stat().st_size if path.is_file() else None
    age_days = _file_age_days(path, now)
    modified_at = _modified_at_utc(path)

    blocker = None
    warning = None

    if contract.max_age_days is None:
        is_fresh = True
    else:
        is_fresh = age_days <= contract.max_age_days
        if not is_fresh:
            if contract.required:
                blocker = "stale_required_input"
            else:
                warning = "stale_optional_input"

    if path.is_file() and size_bytes == 0:
        if contract.required:
            blocker = "empty_required_input"
        else:
            warning = "empty_optional_input"

    return RuntimeInputStatus(
        name=contract.name,
        relative_path=contract.relative_path,
        required=contract.required,
        exists=True,
        is_fresh=is_fresh,
        size_bytes=size_bytes,
        modified_at_utc=modified_at,
        age_days=age_days,
        max_age_days=contract.max_age_days,
        blocker=blocker,
        warning=warning,
    )


def build_runtime_data_inventory(
    root: str | Path = ".",
    *,
    now: datetime | None = None,
) -> RuntimeDataInventory:
    root_path = Path(root)
    effective_now = now or _utc_now()

    statuses = tuple(
        build_runtime_input_status(
            root=root_path,
            contract=contract,
            now=effective_now,
        )
        for contract in RUNTIME_INPUT_CONTRACTS
    )

    blocker_count = sum(1 for status in statuses if status.blocker)
    warning_count = sum(1 for status in statuses if status.warning)
    missing_required_count = sum(
        1 for status in statuses
        if status.required and not status.exists
    )
    stale_required_count = sum(
        1 for status in statuses
        if status.required and status.exists and status.is_fresh is False
    )

    return RuntimeDataInventory(
        root=str(root_path),
        is_ready=blocker_count == 0,
        blocker_count=blocker_count,
        warning_count=warning_count,
        input_count=len(statuses),
        missing_required_count=missing_required_count,
        stale_required_count=stale_required_count,
        statuses=statuses,
    )


def inventory_to_dict(inventory: RuntimeDataInventory) -> dict:
    return asdict(inventory)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit SignalForge runtime data readiness.")
    parser.add_argument("--root", default=".", help="Runtime repo root.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    inventory = build_runtime_data_inventory(args.root)
    payload = inventory_to_dict(inventory)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"root: {inventory.root}")
        print(f"is_ready: {inventory.is_ready}")
        print(f"blocker_count: {inventory.blocker_count}")
        print(f"warning_count: {inventory.warning_count}")
        print(f"missing_required_count: {inventory.missing_required_count}")
        print(f"stale_required_count: {inventory.stale_required_count}")

    return 0 if inventory.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())

