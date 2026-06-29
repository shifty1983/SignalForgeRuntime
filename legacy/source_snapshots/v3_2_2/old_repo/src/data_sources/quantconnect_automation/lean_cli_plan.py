from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DATA_PULL_ARTIFACT_TYPE = "signalforge_quantconnect_lean_rest_data_pull_plan"
DATA_PULL_SCHEMA_VERSION = "signalforge_quantconnect_lean_rest_data_pull_plan.v1"

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


@dataclass(frozen=True)
class LeanCommand:
    """A shell-safe representation of a LEAN CLI command."""

    purpose: str
    args: tuple[str, ...]
    requires_paid_data_confirmation: bool = True

    def as_args(self) -> list[str]:
        return list(self.args)

    def as_powershell(self) -> str:
        return command_to_powershell(self.args)


def _clean_symbol(symbol: Any) -> str:
    text = str(symbol or "").strip().upper()
    if not text:
        raise ValueError("symbols must not contain blank values")
    return text


def _as_list(value: Any, *, default: Sequence[Any] | None = None) -> list[Any]:
    if value is None:
        return list(default or [])
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _compact_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("start and end dates are required")
    if len(text) == 8 and text.isdigit():
        return text
    try:
        return datetime.strptime(text, "%Y-%m-%d").strftime("%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"date must be YYYY-MM-DD or YYYYMMDD: {text!r}") from exc


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _command(*parts: str, purpose: str) -> LeanCommand:
    return LeanCommand(purpose=purpose, args=tuple(parts))


def command_to_powershell(args: Iterable[str]) -> str:
    quoted: list[str] = []
    for arg in args:
        # PowerShell single-quoted strings escape embedded single quotes by doubling them.
        text = str(arg)
        if text.replace("-", "").replace("_", "").replace(".", "").replace("/", "").isalnum():
            quoted.append(text)
        else:
            quoted.append("'" + text.replace("'", "''") + "'")
    return " ".join(quoted)


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    with manifest_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("QuantConnect automation manifest must be a JSON object")
    return data


def _symbols_from_manifest(manifest: Mapping[str, Any]) -> list[str]:
    return sorted({_clean_symbol(symbol) for symbol in _as_list(manifest.get("symbols"))})


def _security_master_command() -> LeanCommand:
    return _command(
        "lean",
        "data",
        "download",
        "--dataset",
        "US Equity Security Master",
        purpose="download_us_equity_security_master",
    )


def _option_universe_bulk_command(start: str, end: str, *, overwrite: bool = False, yes: bool = False) -> LeanCommand:
    args = [
        "lean",
        "data",
        "download",
        "--dataset",
        "US Equity Option Universe",
        "--data-type",
        "bulk",
        "--start",
        start,
        "--end",
        end,
    ]
    if overwrite:
        args.append("--overwrite")
    if yes:
        args.append("--yes")
    return LeanCommand(purpose="download_us_equity_option_universe_bulk", args=tuple(args))


def _equity_price_ticker_commands(
    symbols: Sequence[str],
    start: str,
    end: str,
    price_config: Mapping[str, Any],
    *,
    overwrite: bool = False,
    yes: bool = False,
) -> list[LeanCommand]:
    resolution = str(price_config.get("resolution", "Daily"))
    data_types = [str(item) for item in _as_list(price_config.get("data_types"), default=["Trade"])]
    commands: list[LeanCommand] = []
    for symbol in symbols:
        for data_type in data_types:
            args = [
                "lean",
                "data",
                "download",
                "--dataset",
                "US Equities",
                "--data-type",
                data_type,
                "--ticker",
                symbol,
                "--resolution",
                resolution,
                "--start",
                start,
                "--end",
                end,
            ]
            if overwrite:
                args.append("--overwrite")
            if yes:
                args.append("--yes")
            commands.append(
                LeanCommand(
                    purpose=f"download_us_equity_{data_type.lower()}_{resolution.lower()}_{symbol}",
                    args=tuple(args),
                )
            )
    return commands


def _equity_options_bulk_command(
    start: str,
    end: str,
    options_config: Mapping[str, Any],
    *,
    overwrite: bool = False,
    yes: bool = False,
) -> LeanCommand:
    resolution = str(options_config.get("resolution", "Daily"))
    option_style = str(options_config.get("option_style", "American"))
    data_type = str(options_config.get("data_type", "Bulk"))
    args = [
        "lean",
        "data",
        "download",
        "--dataset",
        "US Equity Options",
        "--data-type",
        data_type,
        "--option-style",
        option_style,
        "--resolution",
        resolution,
        "--start",
        start,
        "--end",
        end,
    ]
    if overwrite:
        args.append("--overwrite")
    if yes:
        args.append("--yes")
    return LeanCommand(purpose="download_us_equity_options_bulk", args=tuple(args))


def build_download_plan(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic LEAN CLI download plan from a SignalForge manifest.

    The function only plans commands. Execution is handled by the CLI module and
    requires explicit flags because QuantConnect data downloads can incur QCC or
    subscription charges.
    """

    symbols = _symbols_from_manifest(manifest)
    start = _compact_date(manifest.get("start"))
    end = _compact_date(manifest.get("end"))
    overwrite = _bool(manifest.get("overwrite"), False)
    yes = _bool(manifest.get("yes"), False)

    commands: list[LeanCommand] = []
    warnings: list[str] = []

    dependencies = manifest.get("dependencies") or {}
    if not isinstance(dependencies, Mapping):
        raise ValueError("dependencies must be a JSON object when provided")

    if _bool(dependencies.get("security_master"), True):
        commands.append(_security_master_command())

    price_config = manifest.get("price") or {}
    if not isinstance(price_config, Mapping):
        raise ValueError("price must be a JSON object when provided")
    if _bool(price_config.get("enabled"), True):
        commands.extend(
            _equity_price_ticker_commands(
                symbols=symbols,
                start=start,
                end=end,
                price_config=price_config,
                overwrite=overwrite,
                yes=yes,
            )
        )

    option_universe_config = manifest.get("option_universe") or {}
    if not isinstance(option_universe_config, Mapping):
        raise ValueError("option_universe must be a JSON object when provided")
    if _bool(option_universe_config.get("enabled"), True):
        commands.append(_option_universe_bulk_command(start=start, end=end, overwrite=overwrite, yes=yes))

    options_config = manifest.get("options") or {}
    if not isinstance(options_config, Mapping):
        raise ValueError("options must be a JSON object when provided")
    if _bool(options_config.get("enabled"), False):
        mode = str(options_config.get("mode", "bulk")).lower()
        if mode != "bulk":
            warnings.append(
                "options.mode is not 'bulk'; use extra_lean_commands from the QuantConnect CLI command generator for targeted option-contract downloads."
            )
        else:
            commands.append(_equity_options_bulk_command(start=start, end=end, options_config=options_config, overwrite=overwrite, yes=yes))
            warnings.append(
                "US Equity Options bulk data can be very large; keep CLI execution behind manual confirmation and prefer Daily/Hour before Minute."
            )

    extra_commands = manifest.get("extra_lean_commands") or []
    if not isinstance(extra_commands, list):
        raise ValueError("extra_lean_commands must be a list when provided")
    for index, command in enumerate(extra_commands, start=1):
        if isinstance(command, str):
            args = tuple(shlex.split(command, posix=False))
        elif isinstance(command, list):
            args = tuple(str(part) for part in command)
        else:
            raise ValueError("extra_lean_commands entries must be strings or string lists")
        commands.append(LeanCommand(purpose=f"extra_lean_command_{index:03d}", args=args))

    command_rows = [
        {
            "index": index,
            "purpose": command.purpose,
            "args": command.as_args(),
            "powershell": command.as_powershell(),
            "requires_paid_data_confirmation": command.requires_paid_data_confirmation,
        }
        for index, command in enumerate(commands, start=1)
    ]

    status = "ready" if command_rows and symbols else "blocked"
    blockers: list[str] = []
    if not symbols:
        blockers.append("symbols_missing")
    if not command_rows:
        blockers.append("no_download_commands_built")

    return {
        "artifact_type": DATA_PULL_ARTIFACT_TYPE,
        "schema_version": DATA_PULL_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "source_kind": "quantconnect_lean_cli_and_rest",
        "contract": "historical_market_price_and_options_data_pull",
        "operation_type": "quantconnect_lean_rest_data_pull_plan",
        "start": start,
        "end": end,
        "symbol_count": len(symbols),
        "symbols": symbols,
        "command_count": len(command_rows),
        "commands": command_rows,
        "warning_count": len(warnings),
        "warnings": warnings,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "requires_manual_approval": True,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "broker_order_id": None,
        "order_intent": None,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }
