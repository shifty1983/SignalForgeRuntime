from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.quantconnect_export.operation import run_quantconnect_export_operation


ALGORITHM_TEMPLATE_SCHEMA_VERSION = "quantconnect_algorithm_template.v1"
OPERATION_TYPE = "quantconnect_algorithm_template"
DEFAULT_MAIN_PY_FILENAME = "main.py"


def build_quantconnect_algorithm_template(source: Any) -> dict[str, Any]:
    """Build a paste-ready QuantConnect main.py template.

    This generator does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, or slippage engines.
    It only embeds the local SignalForge export payload into a QuantConnect
    algorithm template that can be manually pasted into the QuantConnect Web IDE.
    """

    operation_result = run_quantconnect_export_operation(source)
    export = _as_mapping(operation_result.get("export"))
    generated_payloads = _as_mapping(export.get("generated_payloads"))

    payload = {
        "strategy_configs": _as_list(generated_payloads.get("strategy_configs")),
        "universe": _as_list(generated_payloads.get("universe")),
        "decision_rules": _as_list(generated_payloads.get("decision_rules")),
        "backtest_manifest": _as_mapping(generated_payloads.get("backtest_manifest")),
    }

    main_py = _render_main_py(payload)

    return {
        "schema_version": ALGORITHM_TEMPLATE_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": operation_result.get("status", "needs_review"),
        "summary": {
            "strategy_config_count": len(payload["strategy_configs"]),
            "universe_count": len(payload["universe"]),
            "decision_rule_count": len(payload["decision_rules"]),
            "manifest_strategy_count": _safe_int(
                payload["backtest_manifest"].get("strategy_count")
            ),
            "line_count": len(main_py.splitlines()),
        },
        "main_py": main_py,
        "operation_result": operation_result,
        "explicit_exclusions": list(operation_result.get("explicit_exclusions", [])),
    }


def write_quantconnect_algorithm_template(
    source: Any,
    *,
    output_path: str | PathLike[str],
) -> dict[str, Any]:
    """Write a paste-ready QuantConnect main.py template to disk."""

    result = build_quantconnect_algorithm_template(source)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result["main_py"], encoding="utf-8")

    return {
        "schema_version": ALGORITHM_TEMPLATE_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": result.get("status", "needs_review"),
        "output_path": str(path),
        "file_summary": {
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "line_count": result["summary"]["line_count"],
        },
        "template_result": result,
        "explicit_exclusions": list(result.get("explicit_exclusions", [])),
    }


def _render_main_py(payload: Mapping[str, Any]) -> str:
    payload_json = json.dumps(payload, indent=2, sort_keys=True)

    return f'''from AlgorithmImports import *
import json


SIGNALFORGE_EXPORT = json.loads(r"""
{payload_json}
""")


class SignalForgeExportSmokeAlgorithm(QCAlgorithm):

    def initialize(self):
        self.strategy_configs = SIGNALFORGE_EXPORT.get("strategy_configs", [])
        self.decision_rules = SIGNALFORGE_EXPORT.get("decision_rules", [])
        self.manifest = SIGNALFORGE_EXPORT.get("backtest_manifest", {{}})

        start_date = self.manifest.get("default_start_date") or "2023-01-01"
        end_date = self.manifest.get("default_end_date") or "2023-03-31"
        cash = self.manifest.get("default_cash") or 100000

        self._set_backtest_dates(start_date, end_date)
        self.set_cash(float(cash))

        self.symbols_by_strategy_id = {{}}
        self.indicators_by_strategy_id = {{}}
        self.last_signal_by_strategy_id = {{}}

        configs = self._valid_strategy_configs()
        self.strategy_weight = 1.0 / len(configs) if configs else 0

        for config in configs:
            strategy_id = config["strategy_id"]
            ticker = config["symbol"]
            resolution = self._resolution(config.get("resolution", "daily"))

            symbol = self.add_equity(ticker, resolution).symbol
            self.symbols_by_strategy_id[strategy_id] = symbol
            self.indicators_by_strategy_id[strategy_id] = {{
                "fast": self.sma(symbol, 10, resolution),
                "slow": self.sma(symbol, 30, resolution),
            }}

        self.set_warm_up(30, Resolution.DAILY)

        self.debug(
            "SIGNALFORGE_EXPORT_LOADED|"
            f"strategy_count={{len(configs)}}|"
            f"manifest_id={{self.manifest.get('manifest_id')}}"
        )

    def on_data(self, data):
        if self.is_warming_up:
            return

        for config in self._valid_strategy_configs():
            strategy_id = config["strategy_id"]
            symbol = self.symbols_by_strategy_id.get(strategy_id)
            indicators = self.indicators_by_strategy_id.get(strategy_id)

            if symbol is None or indicators is None:
                continue

            fast = indicators["fast"]
            slow = indicators["slow"]

            if not fast.is_ready or not slow.is_ready:
                continue

            is_risk_on = fast.current.value > slow.current.value
            signal = "risk_on" if is_risk_on else "risk_off"
            previous_signal = self.last_signal_by_strategy_id.get(strategy_id)

            if signal != previous_signal:
                self.debug(
                    "SIGNALFORGE_DECISION|"
                    f"time={{self.time}}|"
                    f"strategy_id={{strategy_id}}|"
                    f"symbol={{config['symbol']}}|"
                    f"signal={{signal}}|"
                    f"fast={{fast.current.value:.2f}}|"
                    f"slow={{slow.current.value:.2f}}"
                )
                self.last_signal_by_strategy_id[strategy_id] = signal

            if is_risk_on and not self.portfolio[symbol].invested:
                self.set_holdings(symbol, self.strategy_weight)

            elif not is_risk_on and self.portfolio[symbol].invested:
                self.liquidate(symbol)

    def _valid_strategy_configs(self):
        valid_configs = []

        for config in self.strategy_configs:
            if not isinstance(config, dict):
                continue

            strategy_id = config.get("strategy_id")
            symbol = config.get("symbol")
            asset_class = str(config.get("asset_class", "equity")).lower()

            if not strategy_id or not symbol:
                continue

            if asset_class != "equity":
                self.debug(
                    "SIGNALFORGE_SKIPPED_STRATEGY|"
                    f"strategy_id={{strategy_id}}|"
                    f"symbol={{symbol}}|"
                    f"reason=only_equity_smoke_test_supported"
                )
                continue

            valid_configs.append(config)

        return valid_configs

    def _set_backtest_dates(self, start_date, end_date):
        start_parts = [int(part) for part in str(start_date).split("-")]
        end_parts = [int(part) for part in str(end_date).split("-")]

        self.set_start_date(start_parts[0], start_parts[1], start_parts[2])
        self.set_end_date(end_parts[0], end_parts[1], end_parts[2])

    def _resolution(self, value):
        normalized = str(value).lower()

        if normalized == "minute":
            return Resolution.MINUTE
        if normalized == "hour":
            return Resolution.HOUR
        if normalized == "second":
            return Resolution.SECOND
        if normalized == "tick":
            return Resolution.TICK

        return Resolution.DAILY
'''


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
