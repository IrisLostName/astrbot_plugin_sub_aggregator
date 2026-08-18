from __future__ import annotations

from typing import Any

from .base import apply_tls, apply_transport, clean_proxy, json_b64, required


def convert(raw: str, name: str) -> dict[str, Any]:
    payload = raw.split("://", 1)[1]
    data = json_b64(payload)
    proxy: dict[str, Any] = {
        "name": name,
        "type": "vmess",
        "server": required(data.get("add"), "server", "vmess"),
        "port": int(data.get("port", 443)),
        "uuid": required(data.get("id"), "uuid", "vmess"),
        "alterId": int(data.get("aid", 0)),
        "cipher": data.get("scy") or "auto",
        "udp": True,
    }
    if proxy["cipher"] not in {"auto", "none", "zero", "aes-128-gcm", "chacha20-poly1305"}:
        raise ValueError("vmess: cipher 不受支持")
    query = {
        "security": "tls" if str(data.get("tls", "")).lower() in {"tls", "true", "1"} else "",
        "sni": data.get("sni", ""),
        "alpn": data.get("alpn", ""),
        "type": data.get("net", ""),
        "path": data.get("path", ""),
        "host": data.get("host", ""),
        "serviceName": data.get("path", ""),
    }
    apply_tls(proxy, query, "vmess")
    apply_transport(proxy, query, "vmess")
    return clean_proxy(proxy, "vmess")
