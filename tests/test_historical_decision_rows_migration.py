from __future__ import annotations

import importlib


def test_historical_decision_rows_module_imports():
    module = importlib.import_module("signalforge.backtesting.historical_decision_rows")

    assert module is not None


def test_historical_decision_rows_cli_module_imports():
    module = importlib.import_module("signalforge.backtesting.historical_decision_rows_cli")

    assert module is not None
