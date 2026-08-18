from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from .base import apply_tls, clean_proxy, parse_query, require_host_port, required


def convert(raw: str, name: str) -> dict[str, Any]:
    parsed, query = parse_query(raw)
    server, port = require_host_port(parsed, "tuic")
    version = query.get("version", "5")
    proxy: dict[str, Any] = {"name": name, "type": "tuic", "server": server, "port": port, "udp": True}
    if version == "4":
        proxy["token"] = required(unquote(parsed.username or query.get("token", "")), "token", "tuic")
    elif version == "5":
        proxy["uuid"] = required(unquote(parsed.username or ""), "uuid", "tuic")
        proxy["password"] = required(unquote(parsed.password or query.get("password", "")), "password", "tuic")
    else:
        raise ValueError("tuic: 只支持 version=4 或 version=5")
    congestion = query.get("congestion_control") or query.get("congestion-controller")
    if congestion:
        if congestion not in {"cubic", "new_reno", "bbr"}:
            raise ValueError("tuic: congestion-controller 不受支持")
        proxy["congestion-controller"] = congestion
    relay = query.get("udp_relay_mode") or query.get("udp-relay-mode")
    if relay:
        if relay not in {"native", "quic"}:
            raise ValueError("tuic: udp-relay-mode 不受支持")
        proxy["udp-relay-mode"] = relay
    if query.get("heartbeat"):
        proxy["heartbeat-interval"] = int(query["heartbeat"])
    apply_tls(proxy, query, "tuic")
    return clean_proxy(proxy, "tuic")
