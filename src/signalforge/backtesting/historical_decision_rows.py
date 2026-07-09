from __future__ import annotations

"""Backtesting shim for Stage 06 historical decision rows.

Stage 06 logic has been promoted into core engine namespaces.
This module remains for existing CLI/artifact compatibility.
"""

import signalforge.engines.behavior.historical_decision_rows_core as _decision_core
import signalforge.engines.regime.historical_weekly_regime_index as _regime_core


def normalize_symbol(*args, **kwargs):
    return _decision_core.normalize_symbol(*args, **kwargs)


def parse_date(*args, **kwargs):
    return _decision_core.parse_date(*args, **kwargs)


def iso(*args, **kwargs):
    return _decision_core.iso(*args, **kwargs)


def _first_present(*args, **kwargs):
    return _decision_core._first_present(*args, **kwargs)


def _extract_state(*args, **kwargs):
    return _decision_core._extract_state(*args, **kwargs)


def _records_from_payload(*args, **kwargs):
    return _decision_core._records_from_payload(*args, **kwargs)


def load_records(*args, **kwargs):
    return _decision_core.load_records(*args, **kwargs)


def load_json(*args, **kwargs):
    return _decision_core.load_json(*args, **kwargs)


def _symbols_from_value(*args, **kwargs):
    return _decision_core._symbols_from_value(*args, **kwargs)


def _get_path(*args, **kwargs):
    return _decision_core._get_path(*args, **kwargs)


def _extract_symbols(*args, **kwargs):
    return _decision_core._extract_symbols(*args, **kwargs)


def extract_inventory_sets(*args, **kwargs):
    return _decision_core.extract_inventory_sets(*args, **kwargs)


def _row_date(*args, **kwargs):
    return _regime_core._row_date(*args, **kwargs)


def _row_symbol(*args, **kwargs):
    return _decision_core._row_symbol(*args, **kwargs)


def _extract_state_from_row(*args, **kwargs):
    return _decision_core._extract_state_from_row(*args, **kwargs)


def build_weekly_regime_index(*args, **kwargs):
    return _regime_core.build_weekly_regime_index(*args, **kwargs)


def lookup_asof_weekly_regime(*args, **kwargs):
    return _regime_core.lookup_asof_weekly_regime(*args, **kwargs)


def build_symbol_date_index(*args, **kwargs):
    return _decision_core.build_symbol_date_index(*args, **kwargs)


def build_market_price_index(*args, **kwargs):
    return _decision_core.build_market_price_index(*args, **kwargs)


def build_historical_decision_rows(*args, **kwargs):
    return _decision_core.build_historical_decision_rows(*args, **kwargs)


def write_historical_decision_rows(*args, **kwargs):
    return _decision_core.write_historical_decision_rows(*args, **kwargs)
