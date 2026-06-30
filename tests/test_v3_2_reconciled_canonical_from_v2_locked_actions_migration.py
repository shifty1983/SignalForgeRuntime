from __future__ import annotations

import importlib


def test_v3_2_reconciled_canonical_from_v2_locked_actions_imports():
    module = importlib.import_module(
        "signalforge.backtesting.v3_2_reconciled_canonical_from_v2_locked_actions"
    )

    assert module is not None




