from __future__ import annotations

from typing import Any, Iterable


def sort_sources(sources: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(sources, key=lambda source: int(source.get("priority", 100)))
