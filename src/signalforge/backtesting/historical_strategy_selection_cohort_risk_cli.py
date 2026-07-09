from __future__ import annotations

"""Stage 21 backtesting shim for cohort-risk / pruned strategy selection.

The implementation has been promoted to:
signalforge.engines.strategy_selection.pruned_selection

This file remains so existing workflow commands keep working.
"""

from signalforge.engines.strategy_selection.pruned_selection import *  # noqa: F401,F403
from signalforge.engines.strategy_selection import pruned_selection as _core


if __name__ == "__main__":
    raise SystemExit(_core.main())
