from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any


def tag_source_name(name: str, source: str) -> str:
    name = (name or "").strip()
    source = source.strip()
    if not source or f"[{source}]" in name:
        return name
    if name and _is_emoji_prefix(name):
        prefix, remainder = _split_emoji_prefix(name)
        return f"{prefix}[{source}]" + (f" {remainder}" if remainder else "")
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


def _is_emoji_prefix(value: str) -> bool:
    return bool(value and ord(value[0]) >= 0x2600)


def _split_emoji_prefix(value: str) -> tuple[str, str]:
    index = 0
    while index < len(value) and (ord(value[index]) >= 0x2600 or value[index].isspace()):
        index += 1
    return value[:index].strip(), value[index:].strip()
