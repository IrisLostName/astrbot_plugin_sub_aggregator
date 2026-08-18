from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from .base import apply_tls, clean_proxy, parse_query, require_host_port, required


_PROTOCOLS = {"udp", "wechat-video", "faketcp"}


def convert(raw: str, name: str) -> dict[str, Any]:
    parsed, query = parse_query(raw)
    server, port = require_host_port(parsed, "hysteria")
    protocol = query.get("protocol", "udp")
    if protocol not in _PROTOCOLS:
        raise ValueError("hysteria: protocol 不受支持")
    proxy: dict[str, Any] = {
        "name": name,
        "type": "hysteria",
        "server": server,
        "port": port,
        "auth-str": required(unquote(parsed.username or query.get("auth", "")), "auth-str", "hysteria"),
        "protocol": protocol,
    }
    for key in ("up", "down", "obfs"):
        if query.get(key):
            proxy[key] = query[key]
    apply_tls(proxy, query, "hysteria")
    return clean_proxy(proxy, "hysteria")
