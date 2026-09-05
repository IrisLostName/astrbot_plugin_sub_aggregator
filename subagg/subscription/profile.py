from __future__ import annotations

from copy import deepcopy
from typing import Any


RULE_BASE = "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/meta/geo/geosite"
RULESETS: tuple[tuple[str, str, str], ...] = (
    ("ads", "category-ads-all.mrs", "REJECT"),
    ("cn", "cn.mrs", "DIRECT"),
)


DNS_PROFILE: dict[str, Any] = {
    "enable": True,
    "ipv6": False,
    "enhanced-mode": "fake-ip",
    "fake-ip-range": "198.18.0.1/16",
    "default-nameserver": ["223.5.5.5", "119.29.29.29"],
    "nameserver": ["https://dns.alidns.com/dns-query", "https://doh.pub/dns-query"],
    "fallback": ["https://1.1.1.1/dns-query", "https://dns.google/dns-query"],
    "fallback-filter": {"geoip": False},
    "proxy-server-nameserver": ["https://1.1.1.1/dns-query", "https://dns.google/dns-query"],
    "respect-rules": True,
}


def build_rule_profile(proxy_names: list[str], profile_name: str = "metacubex") -> dict[str, Any]:
    if profile_name == "minimal":
        return _minimal_profile(proxy_names)
    if profile_name != "metacubex":
        raise ValueError(f"未知规则 profile: {profile_name}")
    rules = ["DST-PORT,3478,REJECT"]
    rules.extend(f"RULE-SET,{provider},{policy}" for provider, _filename, policy in RULESETS)
    rules.append("MATCH,PROXY")
    providers = {
        provider: {
            "type": "http",
            "behavior": "domain",
            "format": "mrs",
            "url": f"{RULE_BASE}/{filename}",
            "path": f"./providers/metacubex/{provider}.mrs",
            "interval": 86400,
        }
        for provider, filename, _policy in RULESETS
    }
    return {
        "mixed-port": 7890,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "info",
        "dns": deepcopy(DNS_PROFILE),
        "proxy-groups": [
            {
                "name": "PROXY",
                "type": "select",
                "proxies": proxy_names or ["DIRECT"],
            }
        ],
        "rule-providers": providers,
        "rules": rules,
    }


def _minimal_profile(proxy_names: list[str]) -> dict[str, Any]:
    return {
        "mixed-port": 7890,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "info",
        "proxy-groups": [{"name": "PROXY", "type": "select", "proxies": proxy_names or ["DIRECT"]}],
        "rules": ["MATCH,PROXY"],
    }
