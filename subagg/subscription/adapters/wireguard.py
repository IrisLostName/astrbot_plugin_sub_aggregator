from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from .base import clean_proxy, parse_query, require_host_port, required


def convert(raw: str, name: str) -> dict[str, Any]:
    parsed, query = parse_query(raw)
    server, port = require_host_port(parsed, "wireguard")
    proxy: dict[str, Any] = {
        "name": name,
        "type": "wireguard",
        "server": server,
        "port": port,
        "private-key": required(query.get("private-key", unquote(parsed.username or "")), "private-key", "wireguard"),
        "public-key": required(query.get("public-key", ""), "public-key", "wireguard"),
    }
    if query.get("ip"):
        proxy["ip"] = query["ip"]
    if query.get("dns"):
        proxy["dns"] = query["dns"].split(",")
    return clean_proxy(proxy, "wireguard")
