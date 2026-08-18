from __future__ import annotations

import base64
import json
import re
from copy import deepcopy
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from ..models import AdapterError


def parse_query(url: str) -> tuple[Any, dict[str, str]]:
    parsed = urlsplit(url)
    query = {key: values[-1] for key, values in parse_qs(parsed.query, keep_blank_values=True).items()}
    return parsed, {key: unquote(value) for key, value in query.items()}


def decode_urlsafe(value: str) -> str:
    try:
        value = unquote(value).strip()
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode("utf-8")
    except (UnicodeError, ValueError):
        raise AdapterError("base64", "无法解码")


def require_host_port(parsed, protocol: str) -> tuple[str, int]:
    if not parsed.hostname or not parsed.port:
        raise AdapterError(protocol, "缺少 server 或 port")
    return parsed.hostname, parsed.port


def required(value: Any, field: str, protocol: str) -> Any:
    if value is None or str(value).strip() == "":
        raise AdapterError(protocol, f"缺少 {field}")
    return value


def apply_tls(proxy: dict[str, Any], query: dict[str, str], protocol: str) -> None:
    security = query.get("security", "").lower()
    if security in {"tls", "reality"} or query.get("tls", "").lower() in {"1", "true", "tls"}:
        proxy["tls"] = True
    servername = query.get("sni") or query.get("peer") or query.get("servername")
    if servername:
        proxy["servername" if protocol in {"vless", "vmess", "trojan"} else "sni"] = servername
    if query.get("alpn"):
        proxy["alpn"] = [item for item in query["alpn"].split(",") if item]
    if query.get("fp") or query.get("client-fingerprint"):
        proxy["client-fingerprint"] = query.get("fp") or query["client-fingerprint"]
    if query.get("allowInsecure", query.get("insecure", "")).lower() in {"1", "true"}:
        proxy["skip-cert-verify"] = True
    public_key = query.get("pbk") or query.get("public-key")
    short_id = query.get("sid") or query.get("short-id")
    if security == "reality" or public_key or short_id:
        if not public_key or not short_id:
            raise AdapterError(protocol, "Reality 缺少 public-key 或 short-id")
        if not re.fullmatch(r"(?:[0-9a-fA-F]{2}){1,8}", short_id) or int(short_id, 16) == 0:
            raise AdapterError(protocol, "Reality short-id 不是 Mihomo 可接受的十六进制值")
        proxy["reality-opts"] = {"public-key": public_key, "short-id": short_id.lower()}


def apply_transport(proxy: dict[str, Any], query: dict[str, str], protocol: str) -> None:
    network = (query.get("type") or query.get("network") or "").lower()
    if not network:
        return
    if network not in {"ws", "http", "h2", "grpc", "xhttp"}:
        raise AdapterError(protocol, f"不支持的传输层: {network}")
    proxy["network"] = network
    if network == "ws":
        opts: dict[str, Any] = {"path": query.get("path", "/")}
        if query.get("host"):
            opts["headers"] = {"Host": query["host"]}
        proxy["ws-opts"] = opts
    elif network == "http":
        proxy["http-opts"] = {"path": [query.get("path", "/")]}
        if query.get("host"):
            proxy["http-opts"]["headers"] = {"Host": [query["host"]]}
    elif network == "h2":
        proxy["h2-opts"] = {"path": query.get("path", "/")}
        if query.get("host"):
            proxy["h2-opts"]["host"] = [query["host"]]
    elif network == "grpc":
        proxy["grpc-opts"] = {"grpc-service-name": query.get("serviceName", query.get("path", ""))}
    elif network == "xhttp":
        proxy["xhttp-opts"] = {"path": query.get("path", "/"), "mode": query.get("mode", "auto")}
        if query.get("host"):
            proxy["xhttp-opts"]["host"] = query["host"]


def clean_proxy(proxy: dict[str, Any], protocol: str) -> dict[str, Any]:
    result = deepcopy({key: value for key, value in proxy.items() if value not in (None, "")})
    required(result.get("server"), "server", protocol)
    required(result.get("port"), "port", protocol)
    required(result.get("type"), "type", protocol)
    return result


def json_b64(value: str) -> dict[str, Any]:
    try:
        decoded = decode_urlsafe(value)
        data = json.loads(decoded)
    except (json.JSONDecodeError, AdapterError):
        raise AdapterError("vmess", "VMess payload 不是合法 JSON")
    if not isinstance(data, dict):
        raise AdapterError("vmess", "VMess payload 不是对象")
    return data
