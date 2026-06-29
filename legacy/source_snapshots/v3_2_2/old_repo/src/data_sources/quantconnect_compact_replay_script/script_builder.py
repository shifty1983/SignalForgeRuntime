from __future__ import annotations

import json
import base64
import gzip
import re
import textwrap
from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


QUANTCONNECT_COMPACT_REPLAY_SCRIPT_SCHEMA_VERSION = "signalforge_quantconnect_compact_replay_script.v1"
DEFAULT_SCRIPT_FILENAME = "SignalForgeCompactReplayAlgorithm.py"
DEFAULT_CLASS_NAME = "SignalForgeCompactReplayAlgorithm"
DEFAULT_MANIFEST_OBJECT_STORE_KEY = "signalforge/historical_replay/quantconnect_replay_request_manifest.json"
DEFAULT_MANIFEST_MODULE_FILENAME = "signalforge_replay_manifest.py"

COVERED_CAPABILITIES = [
    "quantconnect_compact_replay_script",
    "quantconnect_object_store_compact_result_writer",
    "historical_market_option_replay_script",
    "signalforge_replay_manifest_reader",
    "quantconnect_compact_replay_not_order_intent_or_execution",
]

DEPENDS_ON_CAPABILITIES = [
    "quantconnect_historical_replay_handoff",
    "quantconnect_replay_result_import_validator",
    "position_maintenance_policy",
    "portfolio_construction_optimizer",
    "position_sizing_recommendation",
]

DEFAULT_RESULT_FILES = [
    "signalforge_qc_replay_manifest.json",
    "signalforge_qc_market_price_snapshots.json",
    "signalforge_qc_filtered_option_rows.json",
    "signalforge_qc_contract_outcome_snapshots.json",
    "signalforge_qc_maintenance_trigger_snapshots.json",
    "signalforge_qc_portfolio_replay_snapshots.json",
]

FORBIDDEN_EXECUTION_PATTERNS = [
    r"\bMarketOrder\s*\(",
    r"\bLimitOrder\s*\(",
    r"\bStopMarketOrder\s*\(",
    r"\bStopLimitOrder\s*\(",
    r"\bOptionExercise\s*\(",
    r"\bBuy\s*\(",
    r"\bSell\s*\(",
    r"\bLiquidate\s*\(",
    r"\bSetBrokerageModel\s*\(",
    r"SubmitOrderRequest",
]


def build_signalforge_quantconnect_compact_replay_script(
    handoff_source: Mapping[str, Any] | None,
    *,
    class_name: str = DEFAULT_CLASS_NAME,
    script_filename: str = DEFAULT_SCRIPT_FILENAME,
    manifest_object_store_key: str = DEFAULT_MANIFEST_OBJECT_STORE_KEY,
    embed_manifest: bool = True,
    external_manifest_module: bool = False,
    compressed_inline_manifest: bool = False,
    manifest_module_filename: str = DEFAULT_MANIFEST_MODULE_FILENAME,
) -> dict[str, Any]:
    """Build a copy/paste QuantConnect Lean Python script for compact replay.

    The generated script is designed for a QuantConnect research/backtest project.
    It reads the SignalForge replay request manifest, collects compact historical
    market/option replay rows, and writes the six JSON result files expected by
    the SignalForge import validator. It does not submit orders, route orders,
    model fills/slippage, or perform live execution.
    """

    blocked_reasons: list[str] = []
    if not isinstance(handoff_source, Mapping):
        blocked_reasons.append("missing_quantconnect_historical_replay_handoff_source")
        replay_manifest: dict[str, Any] = {}
    else:
        replay_manifest = _extract_replay_manifest(handoff_source)

    if not replay_manifest:
        blocked_reasons.append("missing_quantconnect_replay_request_manifest")
    if not replay_manifest.get("request_id"):
        blocked_reasons.append("missing_replay_request_id")
    if not replay_manifest.get("symbols"):
        blocked_reasons.append("missing_replay_symbols")
    if not replay_manifest.get("start"):
        blocked_reasons.append("missing_replay_start")
    if not replay_manifest.get("end"):
        blocked_reasons.append("missing_replay_end")

    safe_class_name = _safe_class_name(class_name)
    if safe_class_name != class_name:
        blocked_reasons.append("invalid_quantconnect_class_name")

    result_files = _expected_result_files(handoff_source)
    script_text = _build_script_text(
        replay_manifest=replay_manifest,
        class_name=safe_class_name or DEFAULT_CLASS_NAME,
        manifest_object_store_key=str(manifest_object_store_key or DEFAULT_MANIFEST_OBJECT_STORE_KEY),
        result_files=result_files,
        embed_manifest=embed_manifest,
        external_manifest_module=external_manifest_module,
        compressed_inline_manifest=compressed_inline_manifest,
    )
    manifest_module_text = (
        _build_manifest_module_text(replay_manifest)
        if embed_manifest and external_manifest_module and not compressed_inline_manifest
        else ""
    )

    if compressed_inline_manifest:
        script_text = _force_compressed_inline_manifest(script_text, replay_manifest)
    elif manifest_module_text:
        script_text = _force_external_manifest_import(script_text)

    forbidden_calls = _forbidden_calls(script_text)
    if forbidden_calls:
        blocked_reasons.append("generated_script_contains_execution_calls")

    summary = _summary(
        handoff_source=handoff_source,
        replay_manifest=replay_manifest,
        script_text=script_text,
        script_filename=script_filename,
        class_name=safe_class_name or DEFAULT_CLASS_NAME,
        result_files=result_files,
        forbidden_calls=forbidden_calls,
        blocked_reasons=blocked_reasons,
        manifest_object_store_key=manifest_object_store_key,
        embed_manifest=embed_manifest,
        external_manifest_module=external_manifest_module,
        compressed_inline_manifest=compressed_inline_manifest,
        manifest_module_filename=manifest_module_filename,
        manifest_module_text=manifest_module_text,
    )
    status = "ready" if not blocked_reasons else "blocked"

    return {
        "artifact_type": "signalforge_quantconnect_compact_replay_script",
        "schema_version": QUANTCONNECT_COMPACT_REPLAY_SCRIPT_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "quantconnect_compact_replay_script",
        "adapter_type": "quantconnect_compact_replay_script_builder",
        "review_scope": "quantconnect_compact_replay_script_not_order_intent_or_execution",
        "source_artifacts": {
            "quantconnect_historical_replay_handoff_source": _source_artifact_type(handoff_source),
        },
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "next_build_recommendations": [
            {
                "capability": "run_quantconnect_compact_replay_and_import_results",
                "priority": "high",
                "recommendation": "Copy the generated Lean Python script and replay manifest into QuantConnect, run the replay, then validate the six compact result files in SignalForge.",
            }
        ],
        "request_id": replay_manifest.get("request_id"),
        "symbols": list(replay_manifest.get("symbols") or []),
        "symbol_count": len(replay_manifest.get("symbols") or []),
        "replay_start": replay_manifest.get("start"),
        "replay_end": replay_manifest.get("end"),
        "benchmark_symbol": replay_manifest.get("benchmark_symbol"),
        "manifest_object_store_key": manifest_object_store_key,
        "embed_manifest": bool(embed_manifest),
        "external_manifest_module": bool(external_manifest_module),
        "compressed_inline_manifest": bool(compressed_inline_manifest),
        "manifest_module_filename": manifest_module_filename,
        "manifest_module_size_bytes": len(manifest_module_text.encode("utf-8")) if manifest_module_text else 0,
        "script_filename": script_filename,
        "class_name": safe_class_name or DEFAULT_CLASS_NAME,
        "expected_result_files": result_files,
        "expected_result_file_count": len(result_files),
        "quantconnect_compact_replay_script": script_text,
        "signalforge_replay_manifest_module": manifest_module_text,
        "supplemental_project_files": [
            {
                "filename": manifest_module_filename,
                "content_key": "signalforge_replay_manifest_module",
                "purpose": "external_replay_manifest_module",
            }
        ] if manifest_module_text else [],
        "quantconnect_compact_replay_script_summary": summary,
        "blocked_reasons": list(dict.fromkeys(blocked_reasons)),
        "execution_policy": {
            "submit_orders": False,
            "route_orders": False,
            "model_fills": False,
            "model_slippage": False,
            "live_execution": False,
            "produce_compact_replay_results_only": True,
        },
        "portfolio_action": None,
        "position_size": None,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "automatic_close_order": None,
        "automatic_roll_order": None,
        "automatic_defense_order": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_script_text(
    *,
    replay_manifest: Mapping[str, Any],
    class_name: str,
    manifest_object_store_key: str,
    result_files: Sequence[str],
    embed_manifest: bool,
    external_manifest_module: bool = False,
    compressed_inline_manifest: bool = False,
) -> str:
    manifest_json = json.dumps(dict(replay_manifest), indent=2, sort_keys=True, default=str)
    expected_files_json = json.dumps(list(result_files), indent=2, sort_keys=True)
    embedded_manifest = "json.loads(" + repr(manifest_json) + ")" if embed_manifest else "{}"
    template = r"""
# SignalForge QuantConnect compact replay script.
# Paste this file into a QuantConnect Lean Python project.
# It writes compact replay result JSON files only; it does not place trades.

from AlgorithmImports import *
from datetime import datetime, timedelta
import json
import math
import base64
import gzip


SIGNALFORGE_MANIFEST_OBJECT_STORE_KEY = __MANIFEST_OBJECT_STORE_KEY__
SIGNALFORGE_EXPECTED_RESULT_FILES = __EXPECTED_RESULT_FILES__
SIGNALFORGE_INLINE_REPLAY_MANIFEST = __EMBEDDED_MANIFEST__


class __CLASS_NAME__(QCAlgorithm):
    def Initialize(self):
        self.replay_manifest = self._load_replay_manifest()
        self.request_id = str(self.replay_manifest.get("request_id") or "")
        self.symbols = [str(symbol).upper() for symbol in self.replay_manifest.get("symbols", [])]
        self.candidates = list(self.replay_manifest.get("candidates", []))
        if not self.candidates:
            candidate_ids = [str(value) for value in self.replay_manifest.get("candidate_ids", [])]
            self.candidates = []
            for index, ticker in enumerate(self.symbols):
                candidate_id = candidate_ids[index] if index < len(candidate_ids) else ticker + "_historical_replay_candidate"
                self.candidates.append(dict(
                    symbol=ticker,
                    candidate_id=candidate_id,
                    strategy_family="unknown_strategy_family",
                    top_contract_symbol="",
                    top_contract_delta=0.0,
                    top_contract_gamma=0.0,
                    top_contract_theta=0.0,
                    top_contract_vega=0.0,
                ))
        self.option_slice_policy = dict(self.replay_manifest.get("option_slice_policy", {}))
        self.maintenance_policy = dict(self.replay_manifest.get("maintenance_evaluation_policy", {}))
        self.outcome_horizons = [int(value) for value in self.replay_manifest.get("outcome_horizons", [1, 5, 10, 21, 45])]
        self.object_store_prefix = str(self.replay_manifest.get("object_store_prefix") or "signalforge/historical_replay").rstrip("/")
        self.max_option_rows_per_symbol_per_day = int(self.replay_manifest.get("max_option_rows_per_symbol_per_day") or 100)

        start = self._parse_date(str(self.replay_manifest.get("start") or "2000-01-01"))
        end = self._parse_date(str(self.replay_manifest.get("end") or "2000-01-02"))
        self.SetStartDate(start.year, start.month, start.day)
        self.SetEndDate(end.year, end.month, end.day)
        self.SetCash(100000)

        self.market_price_snapshots = []
        self.filtered_option_rows = []
        self.contract_outcome_snapshots = []
        self.maintenance_trigger_snapshots = []
        self.portfolio_replay_snapshots = []
        self.latest_market_close_by_symbol = {}
        self.object_store_cleanup_summary = {
            "attempted": False,
            "performed": False,
            "deleted_count": 0,
            "deleted_keys": [],
            "warnings": [],
            "blocked_reasons": [],
        }

        resolution = self._resolution(str(self.replay_manifest.get("resolution") or "Daily"))
        benchmark_symbol = str(self.replay_manifest.get("benchmark_symbol") or "SPY").upper()
        all_symbols = sorted(set(self.symbols + [benchmark_symbol]))
        for ticker in all_symbols:
            equity = self.AddEquity(ticker, resolution)
            equity.SetDataNormalizationMode(DataNormalizationMode.Raw)

        for ticker in self.symbols:
            option = self.AddOption(ticker, resolution)
            min_dte = int(self.option_slice_policy.get("min_dte") or 7)
            max_dte = int(self.option_slice_policy.get("max_dte") or 90)
            option.SetFilter(lambda universe, min_dte=min_dte, max_dte=max_dte: universe.IncludeWeeklys().Expiration(timedelta(days=min_dte), timedelta(days=max_dte)))

    def OnData(self, data):
        current_date = self.Time.date().isoformat()
        for ticker in self.symbols:
            symbol = self.Symbol(ticker)
            if data.Bars.ContainsKey(symbol):
                bar = data.Bars[symbol]
                row = {
                    "symbol": ticker,
                    "date": current_date,
                    "open": float(bar.Open),
                    "high": float(bar.High),
                    "low": float(bar.Low),
                    "close": float(bar.Close),
                    "volume": int(bar.Volume),
                }
                self.market_price_snapshots.append(row)
                self.latest_market_close_by_symbol[ticker] = float(bar.Close)

        if data.OptionChains is not None:
            for chain in data.OptionChains.Values:
                underlying_symbol = str(chain.Underlying.Symbol.Value).upper()
                if underlying_symbol not in self.symbols:
                    continue
                underlying_price = self._underlying_price(underlying_symbol)
                option_rows = []
                for contract in chain:
                    row = self._option_contract_to_row(contract, underlying_symbol, underlying_price, current_date)
                    if row is not None:
                        option_rows.append(row)
                selected_option_rows = self._select_replay_option_rows(underlying_symbol, option_rows)
                self.filtered_option_rows.extend(selected_option_rows)

        self._append_portfolio_snapshot(current_date)

    def OnEndOfAlgorithm(self):
        self._build_contract_outcomes()
        self._build_maintenance_triggers()
        result_payloads = {
            "signalforge_qc_replay_manifest.json": {
                "artifact_type": "signalforge_qc_replay_manifest",
                "schema_version": "signalforge_qc_replay_manifest.v1",
                "request_id": self.request_id,
                "as_of_run_time": self.Time.isoformat(),
                "symbol_count": len(self.symbols),
                "candidate_count": len(self.candidates),
                "status": "ready",
            },
            "signalforge_qc_market_price_snapshots.json": {"market_price_snapshots": self.market_price_snapshots},
            "signalforge_qc_filtered_option_rows.json": {"filtered_option_rows": self.filtered_option_rows},
            "signalforge_qc_contract_outcome_snapshots.json": {"contract_outcome_snapshots": self.contract_outcome_snapshots},
            "signalforge_qc_maintenance_trigger_snapshots.json": {"maintenance_trigger_snapshots": self.maintenance_trigger_snapshots},
            "signalforge_qc_portfolio_replay_snapshots.json": {"portfolio_replay_snapshots": self.portfolio_replay_snapshots},
        }
        self.object_store_cleanup_summary = self._cleanup_existing_object_store_result_files()
        for filename in SIGNALFORGE_EXPECTED_RESULT_FILES:
            payload = result_payloads.get(filename, {})
            key = self.object_store_prefix + "/" + filename
            self.ObjectStore.Save(key, json.dumps(payload, sort_keys=True))
            self.Debug("SignalForge compact replay wrote " + key)

        self._emit_signalforge_runtime_transport(result_payloads)
        self._emit_signalforge_chart_transport_smoke()

    def _cleanup_existing_object_store_result_files(self):
        prefix = str(self.object_store_prefix or "").strip().rstrip("/")
        summary = {
            "artifact_type": "signalforge_quantconnect_object_store_cleanup",
            "schema_version": "signalforge_quantconnect_object_store_cleanup.v1",
            "request_id": self.request_id,
            "object_store_prefix": prefix,
            "attempted": True,
            "performed": False,
            "deleted_count": 0,
            "deleted_keys": [],
            "warnings": [],
            "blocked_reasons": [],
        }

        if not prefix or not prefix.startswith("signalforge/"):
            summary["blocked_reasons"].append("unsafe_object_store_prefix")
            self.Debug("SignalForge object store cleanup skipped " + json.dumps(summary, sort_keys=True))
            return summary

        for filename in SIGNALFORGE_EXPECTED_RESULT_FILES:
            key = prefix + "/" + filename
            try:
                if self.ObjectStore.ContainsKey(key):
                    self.ObjectStore.Delete(key)
                    summary["deleted_count"] = int(summary["deleted_count"]) + 1
                    summary["deleted_keys"].append(key)
            except Exception as exc:
                summary["warnings"].append("delete_failed:" + key + ":" + str(exc))

        summary["performed"] = True
        self.Debug("SignalForge object store cleanup " + json.dumps(summary, sort_keys=True))
        return summary


    def _emit_signalforge_chart_transport_smoke(self):
        try:
            self.Plot("SignalForgeTransportSmoke", "Smoke", 1)
            self.Debug("SignalForge chart transport smoke emitted")
        except Exception as exc:
            self.Debug("SignalForge chart transport smoke failed: " + str(exc))

    def _emit_signalforge_runtime_transport(self, result_payloads):
        chunk_size = int(self.replay_manifest.get("runtime_stat_transport_chunk_size") or 750)
        max_chunks = int(self.replay_manifest.get("runtime_stat_transport_max_chunks") or 250)

        if chunk_size <= 0:
            chunk_size = 750
        if max_chunks <= 0:
            max_chunks = 250

        file_payloads = {}
        file_summaries = {}

        for filename in SIGNALFORGE_EXPECTED_RESULT_FILES:
            payload = result_payloads.get(filename, {})
            payload_text = json.dumps(payload, sort_keys=True)
            file_payloads[filename] = payload_text
            file_summaries[filename] = {
                "char_count": len(payload_text),
                "object_store_key": self.object_store_prefix + "/" + filename,
            }

        transport_payload = {
            "artifact_type": "signalforge_quantconnect_backtest_result_transport_payload",
            "schema_version": "signalforge_quantconnect_backtest_result_transport_payload.v1",
            "request_id": self.request_id,
            "object_store_prefix": self.object_store_prefix,
            "expected_result_files": list(SIGNALFORGE_EXPECTED_RESULT_FILES),
            "file_summaries": file_summaries,
            "files": file_payloads,
            "object_store_delete_performed": bool(self.object_store_cleanup_summary.get("performed")),
            "object_store_cleanup_summary": dict(self.object_store_cleanup_summary),
        }

        payload_json = json.dumps(transport_payload, separators=(",", ":"), sort_keys=True)
        compressed = gzip.compress(payload_json.encode("utf-8"))
        encoded = base64.b64encode(compressed).decode("ascii")
        chunks = [encoded[index:index + chunk_size] for index in range(0, len(encoded), chunk_size)]

        self._set_signalforge_runtime_stat("SignalForgeTransportState", "ready" if len(chunks) <= max_chunks else "too_large")
        self._set_signalforge_runtime_stat("SignalForgeTransportRequestId", self.request_id)
        self._set_signalforge_runtime_stat("SignalForgeTransportObjectStorePrefix", self.object_store_prefix)
        self._set_signalforge_runtime_stat("SignalForgeTransportChunkSize", str(chunk_size))
        self._set_signalforge_runtime_stat("SignalForgeTransportMaxChunks", str(max_chunks))
        self._set_signalforge_runtime_stat("SignalForgeTransportChunkCount", str(len(chunks)))
        self._set_signalforge_runtime_stat("SignalForgeTransportEncodedCharCount", str(len(encoded)))
        self._set_signalforge_runtime_stat("SignalForgeTransportCompressedBytes", str(len(compressed)))
        self._set_signalforge_runtime_stat("SignalForgeTransportRawBytes", str(len(payload_json.encode("utf-8"))))

        if len(chunks) > max_chunks:
            self.Debug("SignalForge runtime transport too large: chunks=" + str(len(chunks)) + " max_chunks=" + str(max_chunks))
            return

        for index, chunk in enumerate(chunks, start=1):
            self._set_signalforge_runtime_stat("SignalForgeTransportChunk" + str(index).zfill(6), chunk)

        self.Debug("SignalForge runtime transport emitted chunks=" + str(len(chunks)))

    def _set_signalforge_runtime_stat(self, key, value):
        value_text = str(value)

        try:
            self.SetRuntimeStatistic(str(key), value_text)
            return
        except Exception:
            pass

        try:
            self.RuntimeStatistics[str(key)] = value_text
            return
        except Exception:
            pass

        self.Debug(str(key) + "=" + value_text)

    def _load_replay_manifest(self):
        if self.ObjectStore.ContainsKey(SIGNALFORGE_MANIFEST_OBJECT_STORE_KEY):
            return json.loads(self.ObjectStore.Read(SIGNALFORGE_MANIFEST_OBJECT_STORE_KEY))
        return dict(SIGNALFORGE_INLINE_REPLAY_MANIFEST)

    def _option_contract_to_row(self, contract, underlying_symbol, underlying_price, quote_date):
        if underlying_price is None or underlying_price <= 0:
            return None
        bid = float(contract.BidPrice) if contract.BidPrice is not None else 0.0
        ask = float(contract.AskPrice) if contract.AskPrice is not None else 0.0
        if ask <= 0 or bid < 0 or ask < bid:
            return None
        mid = (bid + ask) / 2.0
        spread_pct = (ask - bid) / mid if mid > 0 else 999.0
        if spread_pct > float(self.option_slice_policy.get("max_spread_pct") or 0.15):
            return None
        dte = int((contract.Expiry.date() - self.Time.date()).days)
        if dte < int(self.option_slice_policy.get("min_dte") or 7):
            return None
        if dte > int(self.option_slice_policy.get("max_dte") or 90):
            return None
        moneyness = float(contract.Strike) / float(underlying_price)
        if moneyness < float(self.option_slice_policy.get("moneyness_lower_bound") or 0.80):
            return None
        if moneyness > float(self.option_slice_policy.get("moneyness_upper_bound") or 1.20):
            return None
        open_interest = int(contract.OpenInterest) if contract.OpenInterest is not None else 0
        if open_interest < int(self.option_slice_policy.get("min_open_interest") or 100):
            return None
        volume = int(contract.Volume) if contract.Volume is not None else 0
        if volume < int(self.option_slice_policy.get("min_volume") or 1):
            return None
        greeks = contract.Greeks
        return {
            "underlying_symbol": underlying_symbol,
            "quote_date": quote_date,
            "expiration": contract.Expiry.date().isoformat(),
            "strike": float(contract.Strike),
            "option_right": str(contract.Right).lower(),
            "bid": bid,
            "ask": ask,
            "implied_volatility": self._safe_float(contract.ImpliedVolatility),
            "delta": self._safe_float(greeks.Delta if greeks is not None else None),
            "gamma": self._safe_float(greeks.Gamma if greeks is not None else None),
            "theta": self._safe_float(greeks.Theta if greeks is not None else None),
            "vega": self._safe_float(greeks.Vega if greeks is not None else None),
            "open_interest": open_interest,
            "volume": volume,
            "underlying_price": float(underlying_price),
            "option_symbol": str(contract.Symbol),
            "mid_price": mid,
            "spread_pct": spread_pct,
            "dte": dte,
            "moneyness": moneyness,
        }

    def _build_contract_outcomes(self):
        rows_by_symbol = {}
        for row in self.market_price_snapshots:
            rows_by_symbol.setdefault(row["symbol"], []).append(row)
        for symbol, rows in rows_by_symbol.items():
            rows.sort(key=lambda item: item["date"])

        option_rows_by_symbol_date = self._option_rows_by_symbol_date()
        for candidate in self.candidates:
            symbol = self._candidate_symbol(candidate)
            candidate_id = self._candidate_id(candidate, symbol)
            market_rows = rows_by_symbol.get(symbol, [])
            if len(market_rows) < 2:
                continue
            entry_option = self._select_entry_option_row(candidate, symbol, option_rows_by_symbol_date)
            if entry_option is None:
                continue
            entry_date = str(entry_option.get("quote_date") or market_rows[0]["date"])
            entry_index = self._market_index_on_or_after(market_rows, entry_date)
            entry_market = market_rows[entry_index]
            entry_close = float(entry_market.get("close") or 0.0)
            entry_mark = self._row_mid_price(entry_option)
            if entry_close <= 0 or entry_mark <= 0:
                continue

            for horizon in self.outcome_horizons:
                exit_index = min(entry_index + int(horizon), len(market_rows) - 1)
                exit_market = market_rows[exit_index]
                exit_close = float(exit_market.get("close") or 0.0)
                exit_date = str(exit_market.get("date") or entry_date)
                underlying_forward_return = (exit_close - entry_close) / entry_close if entry_close else 0.0
                exit_option = self._find_matching_option_row(entry_option, option_rows_by_symbol_date.get((symbol, exit_date), []))
                if exit_option is not None and self._row_mid_price(exit_option) > 0:
                    exit_mark = self._row_mid_price(exit_option)
                    pricing_method = "matched_option_mark"
                else:
                    exit_mark = self._estimate_option_mark(entry_option, entry_close, exit_close, max(exit_index - entry_index, 1))
                    pricing_method = "estimated_option_mark"
                contract_mark_return = (exit_mark - entry_mark) / entry_mark if entry_mark else 0.0
                path_returns = self._contract_path_returns(
                    entry_option=entry_option,
                    entry_mark=entry_mark,
                    entry_close=entry_close,
                    market_rows=market_rows[entry_index : exit_index + 1],
                    option_rows_by_symbol_date=option_rows_by_symbol_date,
                    symbol=symbol,
                )
                candidate_symbol = symbol
                candidate_id = self._candidate_id(candidate, candidate_symbol)
                strategy_family = str(candidate.get("strategy_family") or "")
                self.contract_outcome_snapshots.append({
                    "symbol": candidate_symbol,
                    "candidate_id": candidate_id,
                    "strategy_family": strategy_family,
                    "quote_date": entry_date,
                    "horizon_days": int(horizon),
                    "underlying_forward_return": underlying_forward_return,
                    "contract_mark_return": contract_mark_return,
                    "max_adverse_excursion": min(path_returns) if path_returns else contract_mark_return,
                    "max_favorable_excursion": max(path_returns) if path_returns else contract_mark_return,
                    "option_symbol": str(entry_option.get("option_symbol") or ""),
                    "expiration": str(entry_option.get("expiration") or ""),
                    "strike": self._safe_float(entry_option.get("strike")),
                    "option_right": str(entry_option.get("option_right") or ""),
                    "entry_mark": entry_mark,
                    "exit_mark": exit_mark,
                    "exit_date": exit_date,
                    "pricing_method": pricing_method,
                    "entry_delta": self._safe_float(entry_option.get("delta")),
                    "entry_gamma": self._safe_float(entry_option.get("gamma")),
                    "entry_theta": self._safe_float(entry_option.get("theta")),
                    "entry_vega": self._safe_float(entry_option.get("vega")),
                    "entry_implied_volatility": self._safe_float(entry_option.get("implied_volatility")),
                })

    def _build_maintenance_triggers(self):
        outcome_rows_by_candidate = {}
        for row in self.contract_outcome_snapshots:
            outcome_rows_by_candidate.setdefault(str(row.get("candidate_id") or ""), []).append(row)
        take_profit_threshold = float(self.maintenance_policy.get("take_profit_capture_pct") or 0.50)
        risk_cut_threshold = -abs(float(self.maintenance_policy.get("risk_cut_pct_of_budget") or 0.50))
        for candidate in self.candidates:
            symbol = self._candidate_symbol(candidate)
            candidate_id = self._candidate_id(candidate, symbol)
            rows = outcome_rows_by_candidate.get(candidate_id, [])
            if not rows:
                continue
            best = max(rows, key=lambda row: float(row.get("contract_mark_return") or 0.0))
            worst = min(rows, key=lambda row: float(row.get("contract_mark_return") or 0.0))
            if float(best.get("contract_mark_return") or 0.0) >= take_profit_threshold:
                trigger_type = "take_profit_review"
                trigger_state = "triggered"
                trigger_value = float(best.get("contract_mark_return") or 0.0)
                trigger_date = str(best.get("exit_date") or best.get("quote_date") or "")
            elif float(worst.get("contract_mark_return") or 0.0) <= risk_cut_threshold:
                trigger_type = "risk_cut_review"
                trigger_state = "triggered"
                trigger_value = float(worst.get("contract_mark_return") or 0.0)
                trigger_date = str(worst.get("exit_date") or worst.get("quote_date") or "")
            else:
                trigger_type = "hold_review"
                trigger_state = "not_triggered"
                trigger_value = float(best.get("contract_mark_return") or 0.0)
                trigger_date = str(best.get("exit_date") or best.get("quote_date") or "")
            self.maintenance_trigger_snapshots.append({
                "symbol": symbol,
                "candidate_id": candidate_id,
                "date": trigger_date,
                "trigger_type": trigger_type,
                "trigger_state": trigger_state,
                "trigger_value": trigger_value,
            })

    def _append_portfolio_snapshot(self, current_date):
        exposure_rows = []
        rows_by_symbol_date = self._option_rows_by_symbol_date()

        for candidate in self.candidates:
            symbol = self._candidate_symbol(candidate)
            row = self._select_option_row_for_date(candidate, symbol, current_date, rows_by_symbol_date)

            if row is not None:
                exposure_rows.append({
                    "delta": self._safe_float(row.get("delta")),
                    "gamma": self._safe_float(row.get("gamma")),
                    "theta": self._safe_float(row.get("theta")),
                    "vega": self._safe_float(row.get("vega")),
                })
            else:
                exposure_rows.append({
                    "delta": self._safe_float(candidate.get("top_contract_delta")),
                    "gamma": self._safe_float(candidate.get("top_contract_gamma")),
                    "theta": self._safe_float(candidate.get("top_contract_theta")),
                    "vega": self._safe_float(candidate.get("top_contract_vega")),
                })

        net_delta = sum(row["delta"] for row in exposure_rows)
        net_theta = sum(row["theta"] for row in exposure_rows)

        gross_abs_delta = sum(abs(row["delta"]) for row in exposure_rows)
        gross_abs_gamma = sum(abs(row["gamma"]) for row in exposure_rows)
        gross_abs_vega = sum(abs(row["vega"]) for row in exposure_rows)

        self.portfolio_replay_snapshots.append({
            "date": current_date,
            "candidate_count": len(self.candidates),
            "gross_abs_delta": round(gross_abs_delta, 6),
            "gross_abs_gamma": round(gross_abs_gamma, 6),
            "gross_abs_vega": round(gross_abs_vega, 6),
            "net_delta": round(net_delta, 6),
            "net_theta": round(net_theta, 6),
        })
        
    def _option_rows_by_symbol_date(self):
        grouped = {}
        for row in self.filtered_option_rows:
            symbol = str(row.get("underlying_symbol") or row.get("symbol") or "").upper()
            quote_date = str(row.get("quote_date") or "")
            if symbol and quote_date:
                grouped.setdefault((symbol, quote_date), []).append(row)
        return grouped

    def _select_entry_option_row(self, candidate, symbol, option_rows_by_symbol_date):
        candidate_option_symbol = str(candidate.get("top_contract_symbol") or candidate.get("option_symbol") or "")
        all_rows = []
        for (row_symbol, _date), rows in option_rows_by_symbol_date.items():
            if row_symbol == symbol:
                all_rows.extend(rows)
        if not all_rows:
            return None
        all_rows.sort(key=lambda row: str(row.get("quote_date") or ""))
        first_date = str(all_rows[0].get("quote_date") or "")
        first_date_rows = [row for row in all_rows if str(row.get("quote_date") or "") == first_date]
        if candidate_option_symbol:
            exact_rows = [row for row in first_date_rows if str(row.get("option_symbol") or "") == candidate_option_symbol]
            if exact_rows:
                return exact_rows[0]
        return self._best_option_row_for_candidate(candidate, first_date_rows)

    def _select_option_row_for_date(self, candidate, symbol, quote_date, option_rows_by_symbol_date):
        rows = option_rows_by_symbol_date.get((symbol, quote_date), [])
        if not rows:
            return None
        return self._best_option_row_for_candidate(candidate, rows)

    def _best_option_row_for_candidate(self, candidate, rows):
        if not rows:
            return None
        target_delta = self._candidate_target_delta(candidate)
        candidate_option_symbol = str(candidate.get("top_contract_symbol") or candidate.get("option_symbol") or "")
        exact_rows = [row for row in rows if candidate_option_symbol and str(row.get("option_symbol") or "") == candidate_option_symbol]
        if exact_rows:
            return exact_rows[0]

        directional_rows = [row for row in rows if self._candidate_row_matches_delta_direction(row, target_delta)]
        if not directional_rows:
            return None

        return sorted(directional_rows, key=lambda row: self._candidate_option_rank(row, target_delta), reverse=True)[0]

    def _find_matching_option_row(self, entry_option, rows):
        if not rows:
            return None
        entry_symbol = str(entry_option.get("option_symbol") or "")
        if entry_symbol:
            for row in rows:
                if str(row.get("option_symbol") or "") == entry_symbol:
                    return row
        entry_expiration = str(entry_option.get("expiration") or "")
        entry_right = str(entry_option.get("option_right") or "")
        entry_strike = self._safe_float(entry_option.get("strike"))
        for row in rows:
            if str(row.get("expiration") or "") != entry_expiration:
                continue
            if str(row.get("option_right") or "") != entry_right:
                continue
            if abs(self._safe_float(row.get("strike")) - entry_strike) < 0.0001:
                return row
        return None

    def _contract_path_returns(self, entry_option, entry_mark, entry_close, market_rows, option_rows_by_symbol_date, symbol):
        values = []
        for index, market_row in enumerate(market_rows):
            quote_date = str(market_row.get("date") or "")
            matched_option = self._find_matching_option_row(entry_option, option_rows_by_symbol_date.get((symbol, quote_date), []))
            if matched_option is not None and self._row_mid_price(matched_option) > 0:
                mark = self._row_mid_price(matched_option)
            else:
                mark = self._estimate_option_mark(entry_option, entry_close, float(market_row.get("close") or 0.0), max(index, 1))
            values.append((mark - entry_mark) / entry_mark if entry_mark else 0.0)
        return values or [0.0]

    def _estimate_option_mark(self, entry_option, entry_close, exit_close, days_elapsed):
        entry_mark = self._row_mid_price(entry_option)
        move = float(exit_close or 0.0) - float(entry_close or 0.0)
        delta = self._safe_float(entry_option.get("delta"))
        gamma = self._safe_float(entry_option.get("gamma"))
        theta = self._safe_float(entry_option.get("theta"))
        estimated = entry_mark + (delta * move) + (0.5 * gamma * move * move) + (theta * float(days_elapsed or 0))
        return max(0.01, estimated)

    def _candidate_option_rank(self, row, target_delta):
        delta = self._safe_float(row.get("delta"))
        delta_distance = abs(delta - target_delta)
        delta_score = 1.0 - min(delta_distance, 1.0)
        liquidity_score = min(float(row.get("open_interest") or 0.0) / 1000.0, 2.0) + min(float(row.get("volume") or 0.0) / 100.0, 2.0)
        spread_penalty = min(float(row.get("spread_pct") or 0.0), 1.0)
        direction_bonus = 1.0 if self._candidate_row_matches_delta_direction(row, target_delta) else -10.0
        return direction_bonus + (3.0 * delta_score) + (0.1 * liquidity_score) - spread_penalty

    def _candidate_row_matches_delta_direction(self, row, target_delta):
        option_right = self._normalized_option_right(row.get("option_right"))
        delta = self._safe_float(row.get("delta"))

        if target_delta < 0:
            return option_right == "put" or delta < 0
        if target_delta > 0:
            return option_right == "call" or delta > 0
        return True

    def _normalized_option_right(self, value):
        text = str(value or "").lower()
        if "put" in text:
            return "put"
        if "call" in text:
            return "call"
        return text

    def _option_row_rank(self, row):
        delta = abs(self._safe_float(row.get("delta")))
        liquidity = min(float(row.get("open_interest") or 0.0) / 1000.0, 2.0) + min(float(row.get("volume") or 0.0) / 100.0, 2.0)
        spread = min(float(row.get("spread_pct") or 0.0), 1.0)
        return delta + (0.1 * liquidity) - spread

    def _select_replay_option_rows(self, underlying_symbol, option_rows):
        if not option_rows:
            return []

        selected = []
        seen = set()

        def add_rows(rows):
            for row in rows:
                key = str(row.get("option_symbol") or "")
                if key and key not in seen:
                    selected.append(row)
                    seen.add(key)

        # Keep the best general rows for diagnostics and broad replay coverage.
        general_rows = sorted(option_rows, key=lambda item: self._option_row_rank(item), reverse=True)
        add_rows(general_rows[: self.max_option_rows_per_symbol_per_day])

        # Also force-keep candidate-direction rows so a -0.35 target cannot lose all puts
        # before contract selection runs.
        for candidate in self.candidates:
            candidate_symbol = self._candidate_symbol(candidate)
            if candidate_symbol != underlying_symbol:
                continue

            target_delta = self._candidate_target_delta(candidate)
            directional_rows = [
                row for row in option_rows
                if self._candidate_row_matches_delta_direction(row, target_delta)
            ]
            directional_rows.sort(key=lambda row: self._candidate_option_rank(row, target_delta), reverse=True)
            add_rows(directional_rows[: self.max_option_rows_per_symbol_per_day])

        return selected


    def _candidate_symbol(self, candidate):
        return str(candidate.get("symbol") or candidate.get("underlying_symbol") or "").upper()

    def _candidate_id(self, candidate, symbol):
        return str(candidate.get("candidate_id") or symbol + "_historical_replay_candidate")

    def _candidate_target_delta(self, candidate):
        for key in ["target_delta", "top_contract_delta", "delta"]:
            if candidate.get(key) is not None:
                value = self._safe_float(candidate.get(key))
                if value != 0:
                    return value
        return 0.35

    def _market_index_on_or_after(self, rows, target_date):
        for index, row in enumerate(rows):
            if str(row.get("date") or "") >= str(target_date or ""):
                return index
        return 0

    def _row_mid_price(self, row):
        mid_price = self._safe_float(row.get("mid_price"))
        if mid_price > 0:
            return mid_price
        bid = self._safe_float(row.get("bid"))
        ask = self._safe_float(row.get("ask"))
        return (bid + ask) / 2.0 if bid >= 0 and ask > 0 else 0.0

    def _underlying_price(self, ticker):
        if ticker in self.latest_market_close_by_symbol:
            return self.latest_market_close_by_symbol[ticker]
        security = self.Securities[self.Symbol(ticker)] if self.Securities.ContainsKey(self.Symbol(ticker)) else None
        return float(security.Price) if security is not None and security.Price is not None else None

    def _resolution(self, value):
        normalized = str(value or "Daily").lower()
        if normalized == "minute":
            return Resolution.Minute
        if normalized == "hour":
            return Resolution.Hour
        return Resolution.Daily

    def _parse_date(self, value):
        return datetime.strptime(value[:10], "%Y-%m-%d")

    def _safe_float(self, value):
        try:
            numeric = float(value)
            if math.isnan(numeric) or math.isinf(numeric):
                return 0.0
            return numeric
        except Exception:
            return 0.0
"""
    return (
        textwrap.dedent(template)
        .replace("__MANIFEST_OBJECT_STORE_KEY__", json.dumps(str(manifest_object_store_key)))
        .replace("__EXPECTED_RESULT_FILES__", expected_files_json)
        .replace("__EMBEDDED_MANIFEST__", embedded_manifest)
        .replace("__CLASS_NAME__", class_name)
        .strip()
        + "\n"
    )


def _inline_manifest_expression(
    *,
    replay_manifest: Mapping[str, Any],
    embed_manifest: bool,
    external_manifest_module: bool,
    compressed_inline_manifest: bool = False,
) -> str:
    if not embed_manifest:
        return "{}"

    if compressed_inline_manifest:
        payload_json = json.dumps(dict(replay_manifest), separators=(",", ":"), sort_keys=True)
        encoded = base64.b64encode(gzip.compress(payload_json.encode("utf-8"))).decode("ascii")
        return (
            "json.loads(gzip.decompress(base64.b64decode("
            + json.dumps(encoded)
            + ")).decode(\"utf-8\"))"
        )

    if external_manifest_module:
        return (
            "{}\\n"
            "try:\\n"
            "    from signalforge_replay_manifest import "
            "SIGNALFORGE_INLINE_REPLAY_MANIFEST as SIGNALFORGE_INLINE_REPLAY_MANIFEST\\n"
            "except Exception:\\n"
            "    pass"
        )

    return json.dumps(replay_manifest, indent=2, sort_keys=True)

def _build_manifest_module_text(replay_manifest: Mapping[str, Any]) -> str:
    manifest_literal = json.dumps(dict(replay_manifest), indent=2, sort_keys=True)
    return (
        "# SignalForge QuantConnect replay manifest module.\n"
        "# Generated by quantconnect_compact_replay_script.\n\n"
        "SIGNALFORGE_INLINE_REPLAY_MANIFEST = "
        + manifest_literal
        + "\n"
    )



def _force_external_manifest_import(script_text: str) -> str:
    marker = "SIGNALFORGE_INLINE_REPLAY_MANIFEST = "
    start = script_text.find(marker)
    if start < 0:
        return script_text

    next_marker = "\n\nclass "
    end = script_text.find(next_marker, start)
    if end < 0:
        return script_text

    replacement = (
        "SIGNALFORGE_INLINE_REPLAY_MANIFEST = {}\n"
        "try:\n"
        "    from signalforge_replay_manifest import SIGNALFORGE_INLINE_REPLAY_MANIFEST as SIGNALFORGE_INLINE_REPLAY_MANIFEST\n"
        "except Exception:\n"
        "    pass"
    )
    return script_text[:start] + replacement + script_text[end:]



def _force_compressed_inline_manifest(script_text: str, replay_manifest: Mapping[str, Any]) -> str:
    marker = "SIGNALFORGE_INLINE_REPLAY_MANIFEST = "
    start = script_text.find(marker)
    if start < 0:
        return script_text

    next_marker = "\n\nclass "
    end = script_text.find(next_marker, start)
    if end < 0:
        return script_text

    payload_json = json.dumps(dict(replay_manifest), separators=(",", ":"), sort_keys=True)
    encoded = base64.b64encode(gzip.compress(payload_json.encode("utf-8"))).decode("ascii")
    replacement = (
        "SIGNALFORGE_INLINE_REPLAY_MANIFEST = "
        "json.loads(gzip.decompress(base64.b64decode("
        + json.dumps(encoded)
        + ")).decode(\"utf-8\"))"
    )
    return script_text[:start] + replacement + script_text[end:]


def _extract_replay_manifest(handoff_source: Mapping[str, Any]) -> dict[str, Any]:
    manifest = handoff_source.get("quantconnect_replay_request_manifest")
    if isinstance(manifest, Mapping):
        return dict(manifest)
    summary = handoff_source.get("summary") if isinstance(handoff_source.get("summary"), Mapping) else None
    if summary:
        manifest = summary.get("quantconnect_replay_request_manifest")
        if isinstance(manifest, Mapping):
            return dict(manifest)
    return {}


def _expected_result_files(handoff_source: Mapping[str, Any] | None) -> list[str]:
    if isinstance(handoff_source, Mapping):
        contract = handoff_source.get("quantconnect_result_contract")
        if isinstance(contract, Mapping):
            files = contract.get("expected_result_files")
            if isinstance(files, Sequence) and not isinstance(files, (str, bytes, bytearray)):
                cleaned = [str(item) for item in files if str(item)]
                if cleaned:
                    return cleaned
    return list(DEFAULT_RESULT_FILES)


def _summary(
    *,
    handoff_source: Mapping[str, Any] | None,
    replay_manifest: Mapping[str, Any],
    script_text: str,
    script_filename: str,
    class_name: str,
    result_files: Sequence[str],
    forbidden_calls: Sequence[str],
    blocked_reasons: Sequence[str],
    manifest_object_store_key: str,
    embed_manifest: bool,
    external_manifest_module: bool = False,
    compressed_inline_manifest: bool = False,
    manifest_module_filename: str = DEFAULT_MANIFEST_MODULE_FILENAME,
    manifest_module_text: str = "",
) -> dict[str, Any]:
    return {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "source_artifact_type": _source_artifact_type(handoff_source),
        "request_id": replay_manifest.get("request_id"),
        "symbols": list(replay_manifest.get("symbols") or []),
        "symbol_count": len(replay_manifest.get("symbols") or []),
        "candidate_count": int(replay_manifest.get("candidate_count") or len(replay_manifest.get("candidates") or [])),
        "replay_start": replay_manifest.get("start"),
        "replay_end": replay_manifest.get("end"),
        "benchmark_symbol": replay_manifest.get("benchmark_symbol"),
        "object_store_prefix": replay_manifest.get("object_store_prefix"),
        "manifest_object_store_key": manifest_object_store_key,
        "embed_manifest": bool(embed_manifest),
        "script_filename": script_filename,
        "class_name": class_name,
        "script_line_count": len(script_text.splitlines()),
        "script_size_bytes": len(script_text.encode("utf-8")),
        "expected_result_file_count": len(result_files),
        "expected_result_files": list(result_files),
        "forbidden_execution_call_count": len(forbidden_calls),
        "forbidden_execution_calls_found": list(forbidden_calls),
        "blocked_reasons": list(dict.fromkeys(blocked_reasons)),
        "execution_policy": {
            "submit_orders": False,
            "route_orders": False,
            "model_fills": False,
            "model_slippage": False,
            "live_execution": False,
            "produce_compact_replay_results_only": True,
        },
    }


def _forbidden_calls(script_text: str) -> list[str]:
    found: list[str] = []
    for pattern in FORBIDDEN_EXECUTION_PATTERNS:
        if re.search(pattern, script_text):
            found.append(pattern)
    return found


def _safe_class_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", text):
        return ""
    return text


def _source_artifact_type(source: Any) -> str:
    if isinstance(source, Mapping):
        return str(source.get("artifact_type") or "mapping")
    return "missing"





