from __future__ import annotations

import importlib


def test_execution_imports():
    module = importlib.import_module(
        "signalforge.runtime.execution.execution"
    )

    assert module is not None


