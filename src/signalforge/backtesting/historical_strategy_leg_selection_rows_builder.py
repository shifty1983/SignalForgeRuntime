from __future__ import annotations

"""Stage 16 backtesting shim for historical strategy leg selection rows.

The implementation has been promoted to:
signalforge.engines.strategy_selection.leg_selection

This file remains for existing CLI/artifact compatibility.
"""

import signalforge.engines.strategy_selection.leg_selection as _core


def _as_float(*args, **kwargs):
    return _core._as_float(*args, **kwargs)


def _as_int(*args, **kwargs):
    return _core._as_int(*args, **kwargs)


def _as_date(*args, **kwargs):
    return _core._as_date(*args, **kwargs)


def _median(*args, **kwargs):
    return _core._median(*args, **kwargs)


def _norm_symbol(*args, **kwargs):
    return _core._norm_symbol(*args, **kwargs)


def read_jsonl(*args, **kwargs):
    return _core.read_jsonl(*args, **kwargs)


def write_jsonl(*args, **kwargs):
    return _core.write_jsonl(*args, **kwargs)


def write_json(*args, **kwargs):
    return _core.write_json(*args, **kwargs)


def _candidate_key(*args, **kwargs):
    return _core._candidate_key(*args, **kwargs)


def _option_key(*args, **kwargs):
    return _core._option_key(*args, **kwargs)


def _right(*args, **kwargs):
    return _core._right(*args, **kwargs)


def _mid(*args, **kwargs):
    return _core._mid(*args, **kwargs)


def _valid_option(*args, **kwargs):
    return _core._valid_option(*args, **kwargs)


def _dte(*args, **kwargs):
    return _core._dte(*args, **kwargs)


def _strike(*args, **kwargs):
    return _core._strike(*args, **kwargs)


def _delta_abs(*args, **kwargs):
    return _core._delta_abs(*args, **kwargs)


def _atm_score(*args, **kwargs):
    return _core._atm_score(*args, **kwargs)


def _delta_score(*args, **kwargs):
    return _core._delta_score(*args, **kwargs)


def _group_by_expiration(*args, **kwargs):
    return _core._group_by_expiration(*args, **kwargs)


def _expiration_dte(*args, **kwargs):
    return _core._expiration_dte(*args, **kwargs)


def _select_expiration_group(*args, **kwargs):
    return _core._select_expiration_group(*args, **kwargs)


def _filter_right(*args, **kwargs):
    return _core._filter_right(*args, **kwargs)


def _find_next_higher(*args, **kwargs):
    return _core._find_next_higher(*args, **kwargs)


def _find_next_lower(*args, **kwargs):
    return _core._find_next_lower(*args, **kwargs)


def _best_atm(*args, **kwargs):
    return _core._best_atm(*args, **kwargs)


def _best_delta(*args, **kwargs):
    return _core._best_delta(*args, **kwargs)


def _leg(*args, **kwargs):
    return _core._leg(*args, **kwargs)


def _net_mid_debit(*args, **kwargs):
    return _core._net_mid_debit(*args, **kwargs)


def _selection_payload(*args, **kwargs):
    return _core._selection_payload(*args, **kwargs)


def _blocked_payload(*args, **kwargs):
    return _core._blocked_payload(*args, **kwargs)


def _select_single_long(*args, **kwargs):
    return _core._select_single_long(*args, **kwargs)


def _select_vertical_debit(*args, **kwargs):
    return _core._select_vertical_debit(*args, **kwargs)


def _select_vertical_credit(*args, **kwargs):
    return _core._select_vertical_credit(*args, **kwargs)


def _select_iron_condor(*args, **kwargs):
    return _core._select_iron_condor(*args, **kwargs)


def _select_iron_butterfly(*args, **kwargs):
    return _core._select_iron_butterfly(*args, **kwargs)


def _term_expirations(*args, **kwargs):
    return _core._term_expirations(*args, **kwargs)


def _options_for_expiration(*args, **kwargs):
    return _core._options_for_expiration(*args, **kwargs)


def _front_back_available_for_exit(*args, **kwargs):
    return _core._front_back_available_for_exit(*args, **kwargs)


def _select_calendar(*args, **kwargs):
    return _core._select_calendar(*args, **kwargs)


def _select_diagonal(*args, **kwargs):
    return _core._select_diagonal(*args, **kwargs)


def select_legs_for_candidate(*args, **kwargs):
    return _core.select_legs_for_candidate(*args, **kwargs)


def _load_candidate_rows(*args, **kwargs):
    return _core._load_candidate_rows(*args, **kwargs)


def _build_option_index(*args, **kwargs):
    return _core._build_option_index(*args, **kwargs)


def build_historical_strategy_leg_selection_rows(*args, **kwargs):
    return _core.build_historical_strategy_leg_selection_rows(*args, **kwargs)


def build_historical_strategy_leg_selection_rows_artifact(*args, **kwargs):
    return _core.build_historical_strategy_leg_selection_rows_artifact(*args, **kwargs)


__all__ = [
    "_as_float",
    "_as_int",
    "_as_date",
    "_median",
    "_norm_symbol",
    "read_jsonl",
    "write_jsonl",
    "write_json",
    "_candidate_key",
    "_option_key",
    "_right",
    "_mid",
    "_valid_option",
    "_dte",
    "_strike",
    "_delta_abs",
    "_atm_score",
    "_delta_score",
    "_group_by_expiration",
    "_expiration_dte",
    "_select_expiration_group",
    "_filter_right",
    "_find_next_higher",
    "_find_next_lower",
    "_best_atm",
    "_best_delta",
    "_leg",
    "_net_mid_debit",
    "_selection_payload",
    "_blocked_payload",
    "_select_single_long",
    "_select_vertical_debit",
    "_select_vertical_credit",
    "_select_iron_condor",
    "_select_iron_butterfly",
    "_term_expirations",
    "_options_for_expiration",
    "_front_back_available_for_exit",
    "_select_calendar",
    "_select_diagonal",
    "select_legs_for_candidate",
    "_load_candidate_rows",
    "_build_option_index",
    "build_historical_strategy_leg_selection_rows",
    "build_historical_strategy_leg_selection_rows_artifact",
]
