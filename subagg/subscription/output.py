from __future__ import annotations

import re

from typing import Any

import yaml


def minimal_profile(names: list[str]) -> dict[str, Any]:
    return {
        "mixed-port": 7890,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "info",
        "proxy-groups": [{"name": "PROXY", "type": "select", "proxies": names or ["DIRECT"]}],
        "rules": ["MATCH,PROXY"],
    }


def build_mihomo_yaml(proxies: list[dict[str, Any]], profile: dict[str, Any] | None = None) -> str:
    config = dict(profile or minimal_profile([str(proxy["name"]) for proxy in proxies]))
    config["proxies"] = proxies
    validate_config_references(config)
    dumped = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
    return re.sub(r'(?m)^(\s*short-id:\s*)([0-9a-fA-F]+)\s*$', r'\1"\2"', dumped)


def validate_config_references(config: dict[str, Any]) -> None:
    proxy_names = {str(proxy.get("name")) for proxy in config.get("proxies", []) if proxy.get("name")}
    group_names = {str(group.get("name")) for group in config.get("proxy-groups", []) if group.get("name")}
    known = proxy_names | group_names | {"DIRECT", "REJECT", "PASS"}
    for group in config.get("proxy-groups", []):
        for member in group.get("proxies", []):
            if member not in known:
                raise ValueError(f"代理组引用不存在: {member}")
    providers = set(config.get("rule-providers", {}))
    for rule in config.get("rules", []):
        if rule.startswith("RULE-SET,"):
            provider = rule.split(",", 2)[1]
            if provider not in providers:
                raise ValueError(f"规则引用不存在的 provider: {provider}")
