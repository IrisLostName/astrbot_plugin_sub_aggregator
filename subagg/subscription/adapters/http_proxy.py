from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from .base import clean_proxy, parse_query, require_host_port, required


def convert(raw: str, name: str) -> dict[str, Any]:
    parsed, query = parse_query(raw)
    server, port = require_host_port(parsed, "http")
    proxy: dict[str, Any] = {"name": name, "type": "http", "server": server, "port": port}
    if parsed.username:
        proxy["username"] = unquote(parsed.username)
    if parsed.password:
        proxy["password"] = unquote(parsed.password)
    if query.get("tls", "").lower() in {"1", "true"}:
        proxy["tls"] = True
    return clean_proxy(proxy, "http")
