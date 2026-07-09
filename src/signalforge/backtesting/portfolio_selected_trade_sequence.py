from __future__ import annotations

"""Stage 23 backtesting shim for selected trade sequence.

The implementation has been promoted to:
signalforge.engines.portfolio_construction.selected_trade_sequence

This file remains so existing backtesting imports and CLI commands keep working.
"""

import signalforge.engines.portfolio_construction.selected_trade_sequence as _core


def read_json(*args, **kwargs):
    return _core.read_json(*args, **kwargs)


def read_jsonl(*args, **kwargs):
    return _core.read_jsonl(*args, **kwargs)


def write_json(*args, **kwargs):
    return _core.write_json(*args, **kwargs)


def write_jsonl(*args, **kwargs):
    return _core.write_jsonl(*args, **kwargs)


def _get_by_path(*args, **kwargs):
    return _core._get_by_path(*args, **kwargs)


def _first_present_with_path(*args, **kwargs):
    return _core._first_present_with_path(*args, **kwargs)


def _parse_date(*args, **kwargs):
    return _core._parse_date(*args, **kwargs)


def _coerce_float(*args, **kwargs):
    return _core._coerce_float(*args, **kwargs)


def _string_or_none(*args, **kwargs):
    return _core._string_or_none(*args, **kwargs)


def _collect_data_states(*args, **kwargs):
    return _core._collect_data_states(*args, **kwargs)


def _has_contract_outcome_missing_state(*args, **kwargs):
    return _core._has_contract_outcome_missing_state(*args, **kwargs)


def _extract_execution_realism_fields(*args, **kwargs):
    return _core._extract_execution_realism_fields(*args, **kwargs)


def _execution_realism_coverage(*args, **kwargs):
    return _core._execution_realism_coverage(*args, **kwargs)


def _extract_trade(*args, **kwargs):
    return _core._extract_trade(*args, **kwargs)


def _count_source_fields(*args, **kwargs):
    return _core._count_source_fields(*args, **kwargs)


def build_portfolio_selected_trade_sequence(*args, **kwargs):
    return _core.build_portfolio_selected_trade_sequence(*args, **kwargs)


def build_from_paths(*args, **kwargs):
    return _core.build_from_paths(*args, **kwargs)


__all__ = [
    "read_json",
    "read_jsonl",
    "write_json",
    "write_jsonl",
    "_get_by_path",
    "_first_present_with_path",
    "_parse_date",
    "_coerce_float",
    "_string_or_none",
    "_collect_data_states",
    "_has_contract_outcome_missing_state",
    "_extract_execution_realism_fields",
    "_execution_realism_coverage",
    "_extract_trade",
    "_count_source_fields",
    "build_portfolio_selected_trade_sequence",
    "build_from_paths",
]
