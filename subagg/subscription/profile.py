from __future__ import annotations

from copy import deepcopy
from typing import Any


RULE_BASE = "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/meta/geo/geosite"
RULESETS: tuple[tuple[str, str, str], ...] = (
    ("ads", "category-ads-all.mrs", "REJECT"),
    ("apple", "apple.mrs", "Apple"),
    ("microsoft", "microsoft.mrs", "Microsoft"),
    ("google", "google.mrs", "Google"),
    ("github", "github.mrs", "GitHub"),
    ("youtube", "youtube.mrs", "YouTube"),
    ("telegram", "telegram.mrs", "Telegram"),
    ("netflix", "netflix.mrs", "Netflix"),
    ("tiktok", "tiktok.mrs", "TikTok"),
    ("discord", "discord.mrs", "Discord"),
    ("openai", "openai.mrs", "OpenAI"),
    ("cn", "cn.mrs", "DIRECT"),
)

REGIONS: dict[str, str] = {
    "Hong Kong": "(?i)🇭🇰|香港|hong kong|HK|HKG",
    "Taiwan": "(?i)🇹🇼|台湾|台灣|臺灣|taiwan|TW|TWN",
    "Japan": "(?i)🇯🇵|日本|japan|JP|JPN",
    "Singapore": "(?i)🇸🇬|新加坡|singapore|SG|SGP",
    "United States": "(?i)🇺🇸|美国|美國|united states|america|US|USA",
}

DNS_PROFILE: dict[str, Any] = {
    "enable": True,
    "ipv6": True,
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
    region_names = list(REGIONS)
    groups = [
        {
            "name": "PROXY",
            "type": "select",
            "proxies": ["AUTO", *region_names, "DIRECT", *proxy_names],
        },
        {
            "name": "AUTO",
            "type": "url-test",
            "proxies": proxy_names or ["DIRECT"],
            "url": "https://www.gstatic.com/generate_204",
            "interval": 300,
        },
    ]
    for name, filter_pattern in REGIONS.items():
        groups.append(
            {
                "name": name,
                "type": "url-test",
                "proxies": proxy_names or ["DIRECT"],
                "filter": filter_pattern,
                "url": "https://www.gstatic.com/generate_204",
                "interval": 300,
            }
        )
    groups.append(
        {
            "name": "FINAL",
            "type": "select",
            "proxies": ["PROXY", "AUTO", *region_names, "DIRECT", *proxy_names],
        }
    )
    for _provider, _filename, group_name in RULESETS:
        if group_name in {"REJECT", "DIRECT"}:
            continue
        groups.append(
            {
                "name": group_name,
                "type": "select",
                "proxies": ["PROXY", "AUTO", *region_names, "FINAL", "DIRECT", *proxy_names],
            }
        )
    rules = ["DST-PORT,3478,REJECT"]
    rules.extend(f"RULE-SET,{provider},{policy}" for provider, _filename, policy in RULESETS)
    rules.append("MATCH,FINAL")
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
        "proxy-groups": groups,
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
