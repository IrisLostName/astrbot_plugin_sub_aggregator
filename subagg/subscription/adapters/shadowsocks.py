from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from .base import clean_proxy, decode_urlsafe, parse_query, require_host_port, required


def convert(raw: str, name: str) -> dict[str, Any]:
    parsed, query = parse_query(raw)
    server, port = require_host_port(parsed, "ss")
    userinfo = unquote(parsed.username or "")
    password_part = unquote(parsed.password or "")
    if password_part:
        cipher, password = userinfo, password_part
    elif ":" in userinfo:
        cipher, password = userinfo.split(":", 1)
    else:
        decoded = decode_urlsafe(userinfo)
        if ":" not in decoded:
            raise ValueError("ss: 缺少 cipher:password")
        cipher, password = decoded.split(":", 1)
    if not cipher or not password:
        raise ValueError("ss: cipher 或 password 为空")
    proxy: dict[str, Any] = {"name": name, "type": "ss", "server": server, "port": port, "cipher": cipher, "password": password, "udp": True}
    if query.get("plugin"):
        proxy["plugin"] = query["plugin"]
    return clean_proxy(proxy, "ss")
