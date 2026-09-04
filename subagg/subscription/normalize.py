from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any


def tag_source_name(name: str, source: str) -> str:
    name = (name or "").strip()
    source = source.strip()
    if not source or f"[{source}]" in name:
        return name
    return f"[{source}]{name}"


def normalize_proxy(proxy: dict[str, Any], source: str, index: int) -> dict[str, Any]:
    result = deepcopy(proxy)
    result["name"] = tag_source_name(str(result.get("name") or f"{source}#{index}"), source)
    reality = result.get("reality-opts")
    if isinstance(reality, dict) and "short_id" in reality and "short-id" not in reality:
        reality["short-id"] = reality.pop("short_id")
    return result


def fingerprint_proxy(proxy: dict[str, Any]) -> str:
    stable = {key: value for key, value in proxy.items() if key != "name"}
    encoded = repr(_sorted(stable)).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sorted(value):
    if isinstance(value, dict):
        return tuple((key, _sorted(item)) for key, item in sorted(value.items()))
    if isinstance(value, list):
        return tuple(_sorted(item) for item in value)
    return value
