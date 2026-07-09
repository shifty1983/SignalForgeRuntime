from __future__ import annotations

"""Stage 24A backtesting shim for value-ranked allocator.

The implementation has been promoted to:
signalforge.engines.portfolio_construction.value_ranked_allocator

This file remains so existing CLI commands keep working.
"""

from signalforge.engines.portfolio_construction.value_ranked_allocator import *  # noqa: F401,F403
from signalforge.engines.portfolio_construction import value_ranked_allocator as _core


if __name__ == "__main__":
    raise SystemExit(_core.main())
