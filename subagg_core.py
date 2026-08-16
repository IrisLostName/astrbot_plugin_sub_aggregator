from __future__ import annotations

try:
    from .src.subagg_core import *  # noqa: F401,F403
except ImportError:
    from src.subagg_core import *  # noqa: F401,F403
