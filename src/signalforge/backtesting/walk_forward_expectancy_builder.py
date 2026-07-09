from __future__ import annotations

"""Stage 18 backtesting shim for walk-forward expectancy.

The implementation has been promoted to:
signalforge.engines.strategy_selection.expectancy

This file remains for existing CLI/artifact compatibility.
"""

import signalforge.engines.strategy_selection.expectancy as _core


def read_jsonl(*args, **kwargs):
    return _core.read_jsonl(*args, **kwargs)


def write_jsonl(*args, **kwargs):
    return _core.write_jsonl(*args, **kwargs)


def write_json(*args, **kwargs):
    return _core.write_json(*args, **kwargs)


def _first_present(*args, **kwargs):
    return _core._first_present(*args, **kwargs)


def _normalise_component(*args, **kwargs):
    return _core._normalise_component(*args, **kwargs)


def _parse_date(*args, **kwargs):
    return _core._parse_date(*args, **kwargs)


def _parse_float(*args, **kwargs):
    return _core._parse_float(*args, **kwargs)


def _decision_date_for_row(*args, **kwargs):
    return _core._decision_date_for_row(*args, **kwargs)


def _field_values(*args, **kwargs):
    return _core._field_values(*args, **kwargs)


def _return_value_for_row(*args, **kwargs):
    return _core._return_value_for_row(*args, **kwargs)


def _availability_date_for_row(*args, **kwargs):
    return _core._availability_date_for_row(*args, **kwargs)


def _scope_key(*args, **kwargs):
    return _core._scope_key(*args, **kwargs)


def _state_for_stats(*args, **kwargs):
    return _core._state_for_stats(*args, **kwargs)


def _select_stats(*args, **kwargs):
    return _core._select_stats(*args, **kwargs)


def _make_training_examples(*args, **kwargs):
    return _core._make_training_examples(*args, **kwargs)


def _add_example_to_aggregators(*args, **kwargs):
    return _core._add_example_to_aggregators(*args, **kwargs)


def _iso(*args, **kwargs):
    return _core._iso(*args, **kwargs)


def build_walk_forward_expectancy_rows(*args, **kwargs):
    return _core.build_walk_forward_expectancy_rows(*args, **kwargs)


def build_walk_forward_expectancy_artifact(*args, **kwargs):
    return _core.build_walk_forward_expectancy_artifact(*args, **kwargs)


__all__ = [
    "read_jsonl",
    "write_jsonl",
    "write_json",
    "_first_present",
    "_normalise_component",
    "_parse_date",
    "_parse_float",
    "_decision_date_for_row",
    "_field_values",
    "_return_value_for_row",
    "_availability_date_for_row",
    "_scope_key",
    "_state_for_stats",
    "_select_stats",
    "_make_training_examples",
    "_add_example_to_aggregators",
    "_iso",
    "build_walk_forward_expectancy_rows",
    "build_walk_forward_expectancy_artifact",
]
