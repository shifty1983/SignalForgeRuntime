from __future__ import annotations

"""Stage 12 tool shim for term-structure candidate augmentation.

The implementation has been promoted to:
signalforge.engines.strategy_selection.term_structure_candidate_augmentation

This file remains so existing workflow commands keep working.
"""

from signalforge.engines.strategy_selection.term_structure_candidate_augmentation import *  # noqa: F401,F403
from signalforge.engines.strategy_selection import term_structure_candidate_augmentation as _core


if __name__ == "__main__":
    raise SystemExit(_core.main())
