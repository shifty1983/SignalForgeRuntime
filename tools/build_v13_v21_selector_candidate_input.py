from __future__ import annotations

"""Stage 15 tool shim for selector candidate input.

The implementation has been promoted to:
signalforge.engines.strategy_selection.selector_candidate_input

This file remains so existing workflow commands keep working.
"""

from signalforge.engines.strategy_selection.selector_candidate_input import *  # noqa: F401,F403
from signalforge.engines.strategy_selection import selector_candidate_input as _core


if __name__ == "__main__":
    raise SystemExit(_core.main())
