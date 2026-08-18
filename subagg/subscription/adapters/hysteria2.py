from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from .base import apply_tls, clean_proxy, parse_query, require_host_port, required


def convert(raw: str, name: str) -> dict[str, Any]:
    parsed, query = parse_query(raw)
    server, port = require_host_port(parsed, "hysteria2")
    password = unquote(parsed.username or "") or query.get("password", "")
    proxy: dict[str, Any] = {
        "name": name,
        "type": "hysteria2",
        "server": server,
        "port": port,
        "password": required(password, "password", "hysteria2"),
        "udp": True,
    }
    if query.get("obfs"):
        proxy["obfs"] = query["obfs"]
    if query.get("obfs-password"):
        proxy["obfs-password"] = query["obfs-password"]
    apply_tls(proxy, query, "hysteria2")
    return clean_proxy(proxy, "hysteria2")
