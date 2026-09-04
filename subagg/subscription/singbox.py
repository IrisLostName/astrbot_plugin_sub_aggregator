"""sing-box subscription output builder.

Converts Mihomo proxy dicts to sing-box outbound format and generates
complete portable configuration (DNS + inbounds + outbounds + route + ntp).
"""

import hashlib
import json
from typing import Any


class AdapterError(Exception):
    """Raised when a proxy type is unsupported or malformed."""
    pass


def _make_unique_tag(name: str, seen_tags: dict[str, int]) -> str:
    """Generate unique tag for sing-box outbound from potentially duplicate names."""
    if name not in seen_tags:
        seen_tags[name] = 0
        return name

    seen_tags[name] += 1
    return f"{name}_{seen_tags[name]}"


def _convert_tls(proxy: dict[str, Any]) -> dict[str, Any] | None:
    """Convert Mihomo TLS fields to sing-box tls object."""
    if not proxy.get("tls"):
        return None

    tls_obj: dict[str, Any] = {
        "enabled": True,
    }

    if "servername" in proxy:
        tls_obj["server_name"] = proxy["servername"]

    if "alpn" in proxy:
        alpn = proxy["alpn"]
        if isinstance(alpn, list):
            tls_obj["alpn"] = alpn
        elif isinstance(alpn, str):
            tls_obj["alpn"] = [alpn]

    if "skip-cert-verify" in proxy:
        tls_obj["insecure"] = proxy["skip-cert-verify"]

    if "client-fingerprint" in proxy:
        tls_obj["utls"] = {
            "enabled": True,
            "fingerprint": proxy["client-fingerprint"]
        }

    if "reality-opts" in proxy:
        reality = proxy["reality-opts"]
        tls_obj["reality"] = {
            "enabled": True,
            "public_key": reality["public-key"],
            "short_id": reality.get("short-id", "")
        }

    return tls_obj


def _convert_transport(proxy: dict[str, Any]) -> dict[str, Any] | None:
    """Convert Mihomo transport/network fields to sing-box transport object."""
    network = proxy.get("network")

    if network == "ws":
        ws_opts = proxy.get("ws-opts", {})
        return {
            "type": "ws",
            "path": ws_opts.get("path", "/"),
            "headers": ws_opts.get("headers", {})
        }

    if network == "h2" or network == "http":
        h2_opts = proxy.get("h2-opts", {})
        host = h2_opts.get("host", [])
        if isinstance(host, str):
            host = [host]
        return {
            "type": "http",
            "host": host,
            "path": h2_opts.get("path", "/")
        }

    if network == "grpc":
        grpc_opts = proxy.get("grpc-opts", {})
        return {
            "type": "grpc",
            "service_name": grpc_opts.get("grpc-service-name", "")
        }

    return None


def _convert_vless(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    """Convert Mihomo VLESS proxy to sing-box outbound."""
    outbound: dict[str, Any] = {
        "type": "vless",
        "tag": tag,
        "server": proxy["server"],
        "server_port": proxy["port"],
        "uuid": proxy["uuid"]
    }

    if "flow" in proxy:
        outbound["flow"] = proxy["flow"]

    if "packet-encoding" in proxy:
        outbound["packet_encoding"] = proxy["packet-encoding"]

    tls = _convert_tls(proxy)
    if tls:
        outbound["tls"] = tls

    transport = _convert_transport(proxy)
    if transport:
        outbound["transport"] = transport

    return outbound


def _convert_vmess(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    """Convert Mihomo VMess proxy to sing-box outbound."""
    outbound: dict[str, Any] = {
        "type": "vmess",
        "tag": tag,
        "server": proxy["server"],
        "server_port": proxy["port"],
        "uuid": proxy["uuid"],
        "security": proxy.get("cipher", "auto")
    }

    if "alterId" in proxy:
        outbound["alter_id"] = proxy["alterId"]

    tls = _convert_tls(proxy)
    if tls:
        outbound["tls"] = tls

    transport = _convert_transport(proxy)
    if transport:
        outbound["transport"] = transport

    return outbound


def _convert_shadowsocks(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    """Convert Mihomo Shadowsocks proxy to sing-box outbound."""
    outbound: dict[str, Any] = {
        "type": "shadowsocks",
        "tag": tag,
        "server": proxy["server"],
        "server_port": proxy["port"],
        "method": proxy["cipher"],
        "password": proxy["password"]
    }

    if "plugin" in proxy:
        outbound["plugin"] = proxy["plugin"]

    if "plugin-opts" in proxy:
        outbound["plugin_opts"] = proxy["plugin-opts"]

    return outbound


def _convert_trojan(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    """Convert Mihomo Trojan proxy to sing-box outbound."""
    outbound: dict[str, Any] = {
        "type": "trojan",
        "tag": tag,
        "server": proxy["server"],
        "server_port": proxy["port"],
        "password": proxy["password"]
    }

    tls = _convert_tls(proxy)
    if tls:
        outbound["tls"] = tls

    transport = _convert_transport(proxy)
    if transport:
        outbound["transport"] = transport

    return outbound


def _convert_hysteria2(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    """Convert Mihomo Hysteria2 proxy to sing-box outbound."""
    outbound: dict[str, Any] = {
        "type": "hysteria2",
        "tag": tag,
        "server": proxy["server"],
        "server_port": proxy["port"],
        "password": proxy["password"]
    }

    if "up" in proxy and proxy["up"]:
        outbound["up_mbps"] = int(proxy["up"])

    if "down" in proxy and proxy["down"]:
        outbound["down_mbps"] = int(proxy["down"])

    if "obfs" in proxy:
        outbound["obfs"] = {
            "type": proxy["obfs"]
        }
        if "obfs-password" in proxy:
            outbound["obfs"]["password"] = proxy["obfs-password"]

    if "sni" in proxy:
        outbound["tls"] = {
            "enabled": True,
            "server_name": proxy["sni"]
        }
        if "skip-cert-verify" in proxy:
            outbound["tls"]["insecure"] = proxy["skip-cert-verify"]

    return outbound


def _convert_hysteria(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    """Convert Mihomo Hysteria proxy to sing-box outbound."""
    outbound = _convert_hysteria2(proxy, tag)
    outbound["type"] = "hysteria"
    return outbound


def _convert_shadowtls(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    """Convert Mihomo anytls proxy to sing-box shadowtls outbound."""
    outbound: dict[str, Any] = {
        "type": "shadowtls",
        "tag": tag,
        "server": proxy["server"],
        "server_port": proxy["port"],
        "password": proxy["password"]
    }

    if "sni" in proxy:
        outbound["tls"] = {
            "enabled": True,
            "server_name": proxy["sni"]
        }

    return outbound


def _convert_http(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    """Convert Mihomo HTTP proxy to sing-box outbound."""
    outbound: dict[str, Any] = {
        "type": "http",
        "tag": tag,
        "server": proxy["server"],
        "server_port": proxy["port"]
    }

    if "username" in proxy:
        outbound["username"] = proxy["username"]

    if "password" in proxy:
        outbound["password"] = proxy["password"]

    return outbound


def _convert_socks(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    """Convert Mihomo SOCKS proxy to sing-box outbound."""
    outbound: dict[str, Any] = {
        "type": "socks",
        "tag": tag,
        "server": proxy["server"],
        "server_port": proxy["port"]
    }

    if "username" in proxy:
        outbound["username"] = proxy["username"]

    if "password" in proxy:
        outbound["password"] = proxy["password"]

    return outbound


def mihomo_to_singbox_outbound(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    """Convert single Mihomo proxy dict to sing-box outbound.

    Args:
        proxy: Mihomo proxy dict (from ParsedNode.proxy)
        tag: Unique tag for this outbound

    Returns:
        sing-box outbound dict

    Raises:
        AdapterError: If proxy type is unsupported or malformed
    """
    proxy_type = proxy.get("type", "").lower()

    if proxy_type == "vless":
        return _convert_vless(proxy, tag)
    elif proxy_type == "vmess":
        return _convert_vmess(proxy, tag)
    elif proxy_type == "ss":
        return _convert_shadowsocks(proxy, tag)
    elif proxy_type == "trojan":
        return _convert_trojan(proxy, tag)
    elif proxy_type == "hysteria2":
        return _convert_hysteria2(proxy, tag)
    elif proxy_type == "hysteria":
        return _convert_hysteria(proxy, tag)
    elif proxy_type == "anytls":
        return _convert_shadowtls(proxy, tag)
    elif proxy_type == "http":
        return _convert_http(proxy, tag)
    elif proxy_type == "socks5" or proxy_type == "socks":
        return _convert_socks(proxy, tag)
    else:
        raise AdapterError(f"Unsupported proxy type: {proxy_type}")


def build_singbox_config(
    proxies: list[dict[str, Any]],
    rule_set_source: str = "sagernet",
    custom_rule_set_urls: dict[str, str] | None = None,
    ntp_server: str = "time.apple.com",
    clash_api_secret: str = ""
) -> str:
    """Build complete sing-box configuration JSON from Mihomo proxy dicts.

    Args:
        proxies: List of Mihomo proxy dicts (from ParsedNode.proxy)
        rule_set_source: "sagernet", "metacubex", "custom", or "none"
        custom_rule_set_urls: Custom rule set URLs when rule_set_source="custom"
        ntp_server: NTP server address
        clash_api_secret: Clash API controller secret

    Returns:
        JSON string of complete sing-box config

    Raises:
        AdapterError: If any proxy conversion fails
    """
    seen_tags: dict[str, int] = {}
    node_outbounds: list[dict[str, Any]] = []
    node_tags: list[str] = []

    # Convert all proxies to outbounds
    for proxy in proxies:
        name = proxy.get("name", "Unnamed")
        tag = _make_unique_tag(name, seen_tags)
        outbound = mihomo_to_singbox_outbound(proxy, tag)
        node_outbounds.append(outbound)
        node_tags.append(tag)

    # Build final outbounds: selector first, then all nodes, then direct/block
    outbounds = [
        {
            "type": "selector",
            "tag": "proxy",
            "outbounds": node_tags,
            "default": node_tags[0] if node_tags else "direct"
        }
    ]
    outbounds.extend(node_outbounds)
    outbounds.extend([
        {
            "type": "direct",
            "tag": "direct"
        },
        {
            "type": "block",
            "tag": "block"
        }
    ])

    # Rule sets (matching template structure with http_client and update_interval)
    rule_sets = [
        {
            "type": "remote",
            "tag": "geosite-cn",
            "format": "binary",
            "url": "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-cn.srs",
            "http_client": "rules-via-proxy",
            "update_interval": "1d"
        },
        {
            "type": "remote",
            "tag": "geoip-cn",
            "format": "binary",
            "url": "https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/geoip-cn.srs",
            "http_client": "rules-via-proxy",
            "update_interval": "1d"
        }
    ]

    config = {
        "$schema": "https://sing-box.sagernet.org/schema.json",
        "log": {
            "level": "info",
            "timestamp": True
        },
        "dns": {
            "servers": [
                {
                    "type": "https",
                    "tag": "dns-cn",
                    "server": "223.5.5.5",
                    "server_port": 443,
                    "path": "/dns-query",
                    "tls": {
                        "enabled": True,
                        "server_name": "dns.alidns.com"
                    }
                },
                {
                    "type": "https",
                    "tag": "dns-global",
                    "server": "1.1.1.1",
                    "server_port": 443,
                    "path": "/dns-query",
                    "tls": {
                        "enabled": True,
                        "server_name": "cloudflare-dns.com"
                    },
                    "detour": "proxy"
                }
            ],
            "rules": [
                {
                    "rule_set": ["geosite-cn"],
                    "action": "route",
                    "server": "dns-cn"
                }
            ],
            "final": "dns-global",
            "strategy": "prefer_ipv4",
            "reverse_mapping": True
        },
        "http_clients": [
            {
                "tag": "rules-via-proxy",
                "detour": "proxy"
            }
        ],
        "inbounds": [
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": "127.0.0.1",
                "listen_port": 2080
            }
        ],
        "outbounds": outbounds,
        "route": {
            "rules": [
                {"action": "sniff"},
                {"ip_is_private": True, "action": "route", "outbound": "direct"},
                {"rule_set": ["geosite-cn"], "action": "route", "outbound": "direct"},
                {"rule_set": ["geoip-cn"], "action": "route", "outbound": "direct"}
            ],
            "rule_set": rule_sets,
            "final": "proxy",
            "auto_detect_interface": True,
            "default_http_client": "rules-via-proxy",
            "default_domain_resolver": "dns-cn"
        },
        "experimental": {
            "cache_file": {
                "enabled": True,
                "path": "cache.db",
                "store_dns": True
            }
        }
    }

    return json.dumps(config, indent=2, ensure_ascii=False)
