from __future__ import annotations

"""Stage 24A backtesting shim for value-ranked allocator v2.

The implementation has been promoted to:
signalforge.engines.portfolio_construction.value_ranked_allocator_v2

This file remains so existing backtesting imports keep working.
"""

import signalforge.engines.portfolio_construction.value_ranked_allocator_v2 as _core


def main(*args, **kwargs):
    return _core.main(*args, **kwargs)


__all__ = [
    "main",
]
