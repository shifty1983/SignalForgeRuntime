from __future__ import annotations

import importlib


def test_historical_strategy_selection_rows_builder_imports():
    module = importlib.import_module(
        "signalforge.backtesting.historical_strategy_selection_rows_builder"
    )

    assert module is not None


def test_historical_strategy_selection_rows_cli_imports():
    module = importlib.import_module(
        "signalforge.backtesting.historical_strategy_selection_rows_cli"
    )

    assert module is not None




