from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from .base import apply_tls, apply_transport, clean_proxy, parse_query, require_host_port, required


def convert(raw: str, name: str) -> dict[str, Any]:
    parsed, query = parse_query(raw)
    server, port = require_host_port(parsed, "vless")
    proxy: dict[str, Any] = {
        "name": name,
        "type": "vless",
        "server": server,
        "port": port,
        "uuid": required(unquote(parsed.username or ""), "uuid", "vless"),
        "udp": True,
    }
    flow = query.get("flow", "")
    if flow:
        if flow != "xtls-rprx-vision":
            raise ValueError("vless: flow 必须是 xtls-rprx-vision")
        proxy["flow"] = flow
    packet_encoding = query.get("packet-encoding", query.get("packetEncoding", ""))
    if packet_encoding:
        if packet_encoding not in {"packetaddr", "xudp"}:
            raise ValueError("vless: packet-encoding 不受支持")
        proxy["packet-encoding"] = packet_encoding
    encryption = query.get("encryption", "")
    if encryption and encryption != "none":
        if not (encryption.startswith("native") or encryption.startswith("xorpub")):
            raise ValueError("vless: encryption 模式必须是 native 或 xorpub")
        if "(" in encryption or ")" in encryption:
            raise ValueError("vless: encryption 含未替换模板括号")
        proxy["encryption"] = encryption
    apply_tls(proxy, query, "vless")
    apply_transport(proxy, query, "vless")
    return clean_proxy(proxy, "vless")
