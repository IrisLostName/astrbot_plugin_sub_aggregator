from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from .base import apply_tls, apply_transport, clean_proxy, parse_query, require_host_port, required


def convert(raw: str, name: str) -> dict[str, Any]:
    parsed, query = parse_query(raw)
    server, port = require_host_port(parsed, "trojan")
    proxy: dict[str, Any] = {
        "name": name,
        "type": "trojan",
        "server": server,
        "port": port,
        "password": required(unquote(parsed.username or ""), "password", "trojan"),
        "udp": True,
        "tls": True,
    }
    apply_tls(proxy, query, "trojan")
    apply_transport(proxy, query, "trojan")
    return clean_proxy(proxy, "trojan")
