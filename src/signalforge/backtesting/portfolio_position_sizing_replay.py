from __future__ import annotations

"""Stage 24 backtesting shim for position sizing.

The implementation has been promoted to:
signalforge.engines.portfolio_construction.position_sizing

This file remains so existing backtesting imports and CLI commands keep working.
"""

import signalforge.engines.portfolio_construction.position_sizing as _core


def read_json(*args, **kwargs):
    return _core.read_json(*args, **kwargs)


def read_jsonl(*args, **kwargs):
    return _core.read_jsonl(*args, **kwargs)


def write_json(*args, **kwargs):
    return _core.write_json(*args, **kwargs)


def write_jsonl(*args, **kwargs):
    return _core.write_jsonl(*args, **kwargs)


def _coerce_float(*args, **kwargs):
    return _core._coerce_float(*args, **kwargs)


def _coerce_int(*args, **kwargs):
    return _core._coerce_int(*args, **kwargs)


def _get_by_path(*args, **kwargs):
    return _core._get_by_path(*args, **kwargs)


def _truthy(*args, **kwargs):
    return _core._truthy(*args, **kwargs)


def _extract_execution_realism_fields(*args, **kwargs):
    return _core._extract_execution_realism_fields(*args, **kwargs)


def _execution_realism_coverage(*args, **kwargs):
    return _core._execution_realism_coverage(*args, **kwargs)


def _sequence_sort_key(*args, **kwargs):
    return _core._sequence_sort_key(*args, **kwargs)


def _as_list(*args, **kwargs):
    return _core._as_list(*args, **kwargs)


def _mean(*args, **kwargs):
    return _core._mean(*args, **kwargs)


def _breakdown_by(*args, **kwargs):
    return _core._breakdown_by(*args, **kwargs)


def build_portfolio_position_sizing_replay(*args, **kwargs):
    return _core.build_portfolio_position_sizing_replay(*args, **kwargs)


def build_from_paths(*args, **kwargs):
    return _core.build_from_paths(*args, **kwargs)


__all__ = [
    "read_json",
    "read_jsonl",
    "write_json",
    "write_jsonl",
    "_coerce_float",
    "_coerce_int",
    "_get_by_path",
    "_truthy",
    "_extract_execution_realism_fields",
    "_execution_realism_coverage",
    "_sequence_sort_key",
    "_as_list",
    "_mean",
    "_breakdown_by",
    "build_portfolio_position_sizing_replay",
    "build_from_paths",
]
