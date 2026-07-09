from __future__ import annotations

"""Stage 18 backtesting shim for availability-safe walk-forward expectancy.

The implementation has been promoted to:
signalforge.engines.strategy_selection.expectancy_availability_safe

This file remains for existing CLI/artifact compatibility.
"""

import signalforge.engines.strategy_selection.expectancy_availability_safe as _core


def _as_float(*args, **kwargs):
    return _core._as_float(*args, **kwargs)


def _as_date(*args, **kwargs):
    return _core._as_date(*args, **kwargs)


def _parse_date(*args, **kwargs):
    return _core._parse_date(*args, **kwargs)


def _date_text(*args, **kwargs):
    return _core._date_text(*args, **kwargs)


def read_jsonl(*args, **kwargs):
    return _core.read_jsonl(*args, **kwargs)


def write_jsonl(*args, **kwargs):
    return _core.write_jsonl(*args, **kwargs)


def write_json(*args, **kwargs):
    return _core.write_json(*args, **kwargs)


def _field_any(*args, **kwargs):
    return _core._field_any(*args, **kwargs)


def _field(*args, **kwargs):
    return _core._field(*args, **kwargs)


def _strategy_key(*args, **kwargs):
    return _core._strategy_key(*args, **kwargs)


def _scope_keys(*args, **kwargs):
    return _core._scope_keys(*args, **kwargs)


def _row_id(*args, **kwargs):
    return _core._row_id(*args, **kwargs)


def _training_sample(*args, **kwargs):
    return _core._training_sample(*args, **kwargs)


def _valid_samples(*args, **kwargs):
    return _core._valid_samples(*args, **kwargs)


def _metrics(*args, **kwargs):
    return _core._metrics(*args, **kwargs)


def _classify(*args, **kwargs):
    return _core._classify(*args, **kwargs)


def _choose_scope(*args, **kwargs):
    return _core._choose_scope(*args, **kwargs)


def _stage6_expectancy_min_max_compatibility_patch(*args, **kwargs):
    return _core._stage6_expectancy_min_max_compatibility_patch(*args, **kwargs)


def build_walk_forward_expectancy_rows(*args, **kwargs):
    return _core.build_walk_forward_expectancy_rows(*args, **kwargs)


__all__ = [
    "_as_float",
    "_as_date",
    "_parse_date",
    "_date_text",
    "read_jsonl",
    "write_jsonl",
    "write_json",
    "_field_any",
    "_field",
    "_strategy_key",
    "_scope_keys",
    "_row_id",
    "_training_sample",
    "_valid_samples",
    "_metrics",
    "_classify",
    "_choose_scope",
    "_stage6_expectancy_min_max_compatibility_patch",
    "build_walk_forward_expectancy_rows",
]
