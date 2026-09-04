from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from .base import clean_proxy, parse_query, require_host_port


def convert(raw: str, name: str) -> dict[str, Any]:
    parsed, query = parse_query(raw)
    protocol = "socks5"
    server, port = require_host_port(parsed, protocol)
    proxy: dict[str, Any] = {"name": name, "type": "socks5", "server": server, "port": port}
    if parsed.username:
        proxy["username"] = unquote(parsed.username)
    if parsed.password:
        proxy["password"] = unquote(parsed.password)
    proxy["udp"] = query.get("udp", "true").lower() not in {"0", "false"}
    return clean_proxy(proxy, protocol)
