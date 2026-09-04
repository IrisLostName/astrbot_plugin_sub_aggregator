from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from .base import apply_tls, clean_proxy, parse_query, require_host_port, required


def convert(raw: str, name: str) -> dict[str, Any]:
    parsed, query = parse_query(raw)
    server, port = require_host_port(parsed, "anytls")
    if query.get("reality", "").lower() in {"1", "true"} or query.get("security", "").lower() == "reality":
        raise ValueError("anytls: Mihomo 不支持 AnyTLS-Reality")
    proxy: dict[str, Any] = {
        "name": name,
        "type": "anytls",
        "server": server,
        "port": port,
        "password": required(unquote(parsed.username or query.get("password", "")), "password", "anytls"),
        "udp": query.get("udp", "true").lower() not in {"0", "false"},
    }
    if query.get("sni"):
        proxy["sni"] = query["sni"]
    apply_tls(proxy, query, "anytls")
    return clean_proxy(proxy, "anytls")
