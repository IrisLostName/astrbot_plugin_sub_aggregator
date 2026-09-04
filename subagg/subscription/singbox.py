from __future__ import annotations

import ipaddress
import json
from typing import Any


class AdapterError(Exception):
    pass


def _make_unique_tag(name: str, seen_tags: dict[str, int]) -> str:
    if name not in seen_tags:
        seen_tags[name] = 0
        return name

    seen_tags[name] += 1
    return f"{name}_{seen_tags[name]}"


def _convert_tls(proxy: dict[str, Any]) -> dict[str, Any] | None:
    if not (proxy.get("tls") or proxy.get("servername") or proxy.get("sni") or proxy.get("reality-opts")):
        return None

    tls: dict[str, Any] = {"enabled": True}
    server_name = proxy.get("servername") or proxy.get("sni")
    if server_name:
        tls["server_name"] = server_name

    alpn = proxy.get("alpn")
    if isinstance(alpn, list):
        tls["alpn"] = alpn
    elif isinstance(alpn, str):
        tls["alpn"] = [alpn]

    if "skip-cert-verify" in proxy:
        tls["insecure"] = proxy["skip-cert-verify"]

    if "client-fingerprint" in proxy:
        tls["utls"] = {"enabled": True, "fingerprint": proxy["client-fingerprint"]}

    if "reality-opts" in proxy:
        reality = proxy["reality-opts"]
        tls["reality"] = {
            "enabled": True,
            "public_key": reality["public-key"],
            "short_id": reality.get("short-id", ""),
        }

    return tls


def _convert_transport(proxy: dict[str, Any]) -> dict[str, Any] | None:
    network = proxy.get("network")
    if network in (None, "", "tcp"):
        return None

    if network == "ws":
        options = proxy.get("ws-opts", {})
        return {"type": "ws", "path": options.get("path", "/"), "headers": options.get("headers", {})}

    if network in ("h2", "http"):
        options = proxy.get("h2-opts", {})
        host = options.get("host", [])
        return {"type": "http", "host": [host] if isinstance(host, str) else host, "path": options.get("path", "/")}

    if network == "grpc":
        return {"type": "grpc", "service_name": proxy.get("grpc-opts", {}).get("grpc-service-name", "")}

    raise AdapterError(f"Unsupported transport: {network}")


def _with_tls_and_transport(outbound: dict[str, Any], proxy: dict[str, Any]) -> dict[str, Any]:
    tls = _convert_tls(proxy)
    if tls:
        outbound["tls"] = tls

    transport = _convert_transport(proxy)
    if transport:
        outbound["transport"] = transport
    return outbound


def _convert_vless(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    outbound = {
        "type": "vless",
        "tag": tag,
        "server": proxy["server"],
        "server_port": proxy["port"],
        "uuid": proxy["uuid"],
    }
    if proxy.get("flow"):
        outbound["flow"] = proxy["flow"]
    if "packet-encoding" in proxy:
        outbound["packet_encoding"] = proxy["packet-encoding"]
    return _with_tls_and_transport(outbound, proxy)


def _convert_vmess(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    outbound = {
        "type": "vmess",
        "tag": tag,
        "server": proxy["server"],
        "server_port": proxy["port"],
        "uuid": proxy["uuid"],
        "security": proxy.get("cipher", "auto"),
    }
    if "alterId" in proxy:
        outbound["alter_id"] = proxy["alterId"]
    return _with_tls_and_transport(outbound, proxy)


def _convert_shadowsocks(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    outbound = {
        "type": "shadowsocks",
        "tag": tag,
        "server": proxy["server"],
        "server_port": proxy["port"],
        "method": proxy["cipher"],
        "password": proxy["password"],
    }
    if "plugin" in proxy:
        outbound["plugin"] = proxy["plugin"]
    if "plugin-opts" in proxy:
        outbound["plugin_opts"] = proxy["plugin-opts"]
    return outbound


def _convert_trojan(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    outbound = {
        "type": "trojan",
        "tag": tag,
        "server": proxy["server"],
        "server_port": proxy["port"],
        "password": proxy["password"],
    }
    return _with_tls_and_transport(outbound, proxy)


def _convert_hysteria2(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    outbound: dict[str, Any] = {
        "type": "hysteria2",
        "tag": tag,
        "server": proxy["server"],
        "server_port": proxy["port"],
        "password": proxy["password"],
    }
    if proxy.get("up"):
        outbound["up_mbps"] = int(proxy["up"])
    if proxy.get("down"):
        outbound["down_mbps"] = int(proxy["down"])
    if "obfs" in proxy:
        outbound["obfs"] = {"type": proxy["obfs"]}
        if "obfs-password" in proxy:
            outbound["obfs"]["password"] = proxy["obfs-password"]
    tls = _convert_tls(proxy)
    if tls:
        outbound["tls"] = tls
    return outbound


def _convert_hysteria(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    outbound: dict[str, Any] = {
        "type": "hysteria",
        "tag": tag,
        "server": proxy["server"],
        "server_port": proxy["port"],
        "auth": proxy["auth-str"],
    }
    if proxy.get("up"):
        outbound["up_mbps"] = int(proxy["up"])
    if proxy.get("down"):
        outbound["down_mbps"] = int(proxy["down"])
    if "obfs" in proxy:
        outbound["obfs"] = proxy["obfs"]
    tls = _convert_tls(proxy)
    if tls:
        outbound["tls"] = tls
    return outbound


def _convert_anytls(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    outbound = {
        "type": "anytls",
        "tag": tag,
        "server": proxy["server"],
        "server_port": proxy["port"],
        "password": proxy["password"],
    }
    tls = _convert_tls(proxy)
    if tls:
        outbound["tls"] = tls
    return outbound


def _convert_http(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    outbound: dict[str, Any] = {"type": "http", "tag": tag, "server": proxy["server"], "server_port": proxy["port"]}
    if "username" in proxy:
        outbound["username"] = proxy["username"]
    if "password" in proxy:
        outbound["password"] = proxy["password"]
    return outbound


def _convert_socks(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    outbound: dict[str, Any] = {"type": "socks", "tag": tag, "server": proxy["server"], "server_port": proxy["port"]}
    if "username" in proxy:
        outbound["username"] = proxy["username"]
    if "password" in proxy:
        outbound["password"] = proxy["password"]
    return outbound


def mihomo_to_singbox_outbound(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    proxy_type = proxy.get("type", "").lower()
    if proxy_type == "vless":
        return _convert_vless(proxy, tag)
    if proxy_type == "vmess":
        return _convert_vmess(proxy, tag)
    if proxy_type == "ss":
        return _convert_shadowsocks(proxy, tag)
    if proxy_type == "trojan":
        return _convert_trojan(proxy, tag)
    if proxy_type == "hysteria2":
        return _convert_hysteria2(proxy, tag)
    if proxy_type == "hysteria":
        return _convert_hysteria(proxy, tag)
    if proxy_type == "anytls":
        return _convert_anytls(proxy, tag)
    if proxy_type == "http":
        return _convert_http(proxy, tag)
    if proxy_type in {"socks", "socks5"}:
        return _convert_socks(proxy, tag)
    raise AdapterError(f"Unsupported proxy type: {proxy_type}")


def _is_ipv6_proxy(proxy: dict[str, Any]) -> bool:
    if "ipv6" in str(proxy.get("name", "")).lower():
        return True
    try:
        return ipaddress.ip_address(str(proxy["server"])).version == 6
    except ValueError:
        return False


def build_singbox_config(proxies: list[dict[str, Any]], *, tun_enabled: bool = True) -> str:
    seen_tags: dict[str, int] = {}
    node_outbounds: list[dict[str, Any]] = []
    node_tags: list[str] = []

    for proxy in proxies:
        if _is_ipv6_proxy(proxy):
            continue
        tag = _make_unique_tag(str(proxy.get("name", "Unnamed")), seen_tags)
        node_outbounds.append(mihomo_to_singbox_outbound(proxy, tag))
        node_tags.append(tag)

    selector_members = node_tags or ["direct"]
    rule_sets = [
        {
            "type": "remote",
            "tag": "geosite-cn",
            "format": "binary",
            "url": "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-cn.srs",
            "http_client": "rules-via-proxy",
            "update_interval": "1d",
        },
        {
            "type": "remote",
            "tag": "geoip-cn",
            "format": "binary",
            "url": "https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/geoip-cn.srs",
            "http_client": "rules-via-proxy",
            "update_interval": "1d",
        },
    ]
    config = {
        "$schema": "https://sing-box.sagernet.org/schema.json",
        "log": {"level": "info", "timestamp": True},
        "dns": {
            "servers": [
                {
                    "type": "https",
                    "tag": "dns-cn",
                    "server": "223.5.5.5",
                    "server_port": 443,
                    "path": "/dns-query",
                    "tls": {"enabled": True, "server_name": "dns.alidns.com"},
                },
                {
                    "type": "https",
                    "tag": "dns-global",
                    "server": "1.1.1.1",
                    "server_port": 443,
                    "path": "/dns-query",
                    "tls": {"enabled": True, "server_name": "cloudflare-dns.com"},
                    "detour": "proxy",
                },
            ],
            "rules": [
                {"clash_mode": "direct", "action": "route", "server": "dns-cn"},
                {"clash_mode": "global", "action": "route", "server": "dns-global"},
                {"rule_set": "geosite-cn", "action": "route", "server": "dns-cn"},
            ],
            "final": "dns-global",
            "strategy": "ipv4_only",
            "reverse_mapping": True,
        },
        "http_clients": [{"tag": "rules-via-proxy", "detour": "proxy"}],
        "inbounds": (
            [
                {
                    "type": "tun",
                    "tag": "tun-in",
                    "interface_name": "singtun0",
                    "address": ["172.19.0.1/30"],
                    "mtu": 1500,
                    "auto_route": True,
                    "strict_route": True,
                    "stack": "mixed",
                }
            ]
            if tun_enabled
            else []
        ),
        "outbounds": [
            {
                "type": "selector",
                "tag": "proxy",
                "outbounds": selector_members,
                "default": selector_members[0],
                "interrupt_exist_connections": True,
            },
            *node_outbounds,
            {"type": "direct", "tag": "direct"},
        ],
        "route": {
            "rules": [
                {"action": "sniff"},
                {"protocol": "dns", "action": "hijack-dns"},
                {"ip_version": 6, "action": "reject"},
                {"clash_mode": "direct", "action": "route", "outbound": "direct"},
                {"clash_mode": "global", "action": "route", "outbound": "proxy"},
                {"ip_is_private": True, "action": "route", "outbound": "direct"},
                {"rule_set": "geosite-cn", "action": "route", "outbound": "direct"},
                {"rule_set": "geoip-cn", "action": "route", "outbound": "direct"},
            ],
            "rule_set": rule_sets,
            "final": "proxy",
            "auto_detect_interface": True,
            "default_http_client": "rules-via-proxy",
            "default_domain_resolver": "dns-cn",
        },
        "experimental": {
            "cache_file": {"enabled": True, "path": "cache.db", "store_dns": True},
            "clash_api": {"default_mode": "rule", "external_controller": "127.0.0.1:20123"},
        },
    }
    return json.dumps(config, indent=2, ensure_ascii=False)
