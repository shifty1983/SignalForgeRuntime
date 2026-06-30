from __future__ import annotations

import importlib


def test_strategy_family_eligibility_engine_imports():
    module = importlib.import_module(
        "signalforge.engines.strategy_selection.strategy_family_eligibility"
    )

    assert module is not None


def test_strategy_family_eligibility_cli_imports():
    module = importlib.import_module(
        "signalforge.engines.strategy_selection.strategy_family_eligibility_cli"
    )

    assert module is not None


def test_strategy_family_eligibility_file_writer_imports():
    module = importlib.import_module(
        "signalforge.engines.strategy_selection.strategy_family_eligibility_file_writer"
    )

    assert module is not None


def test_historical_replay_matrix_metadata_stamp_imports():
    module = importlib.import_module(
        "signalforge.engines.strategy_selection.historical_replay_matrix_metadata_stamp"
    )

    assert module is not None


