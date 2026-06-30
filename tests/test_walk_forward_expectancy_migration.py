from __future__ import annotations

import importlib


def test_walk_forward_expectancy_builder_imports():
    module = importlib.import_module(
        "signalforge.backtesting.walk_forward_expectancy_builder"
    )

    assert module is not None


def test_walk_forward_expectancy_cli_imports():
    module = importlib.import_module(
        "signalforge.backtesting.walk_forward_expectancy_cli"
    )

    assert module is not None


def test_walk_forward_expectancy_availability_safe_builder_imports():
    module = importlib.import_module(
        "signalforge.backtesting.walk_forward_expectancy_availability_safe_builder"
    )

    assert module is not None


def test_walk_forward_expectancy_availability_safe_cli_imports():
    module = importlib.import_module(
        "signalforge.backtesting.walk_forward_expectancy_availability_safe_cli"
    )

    assert module is not None


