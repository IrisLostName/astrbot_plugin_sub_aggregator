from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import quote, unquote, urlsplit

try:
    import yaml
except ImportError:  # pragma: no cover - AstrBot should install requirements.txt
    yaml = None


SUPPORTED_SCHEMES = (
    "ss://",
    "ssr://",
    "vmess://",
    "vless://",
    "trojan://",
    "hysteria://",
    "hysteria2://",
    "hy2://",
    "tuic://",
)
NODE_URL_PATTERN = re.compile(
    r"(?i)("
    + "|".join(re.escape(scheme) for scheme in sorted(SUPPORTED_SCHEMES, key=len, reverse=True))
    + r")[^\s\"'<>`]+"
)
EMOJI_PREFIX_PATTERN = re.compile(
    r"^((?:[\U0001F1E6-\U0001F1FF]{2}|[\U0001F300-\U0001FAFF]\ufe0f?|[\u2600-\u27BF]\ufe0f?|\s)+)"
)


@dataclass(frozen=True)
class NodeInfo:
    raw: str
    name: str
    fingerprint: str
    source: str


@dataclass(frozen=True)
class MergeResult:
    nodes: list[NodeInfo]
    output_text: str
    output_base64: str
    v2ray_text: str
    v2ray_base64: str
    added: list[NodeInfo]
    removed: list[NodeInfo]
    output_format: str


def decode_subscription(raw: bytes | str) -> str:
    """Decode common base64 subscriptions and keep plaintext subscriptions as-is."""
    if isinstance(raw, bytes):
        text = raw.decode("utf-8", errors="replace")
    else:
        text = raw

    normalized = text.strip()
    if _looks_like_subscription_text(normalized):
        return normalized
    if _looks_like_clash_yaml(normalized):
        return normalized

    compact = re.sub(r"\s+", "", normalized)
    if not compact:
        return ""

    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            padded = compact + "=" * (-len(compact) % 4)
            decoded = decoder(padded.encode("utf-8"))
            decoded_text = decoded.decode("utf-8", errors="replace").strip()
        except Exception:
            continue
        if _looks_like_subscription_text(decoded_text):
            return decoded_text
        if _looks_like_clash_yaml(decoded_text):
            return decoded_text

    return normalized


def parse_nodes(subscription_text: str, source: str) -> list[NodeInfo]:
    clash_nodes = parse_clash_nodes(subscription_text, source)
    if clash_nodes:
        return clash_nodes

    nodes: list[NodeInfo] = []
    for raw in extract_node_urls(subscription_text):
        nodes.append(
            NodeInfo(
                raw=raw,
                name=extract_node_name(raw) or f"{source}#{len(nodes) + 1}",
                fingerprint=hash_node(raw),
                source=source,
            )
        )
    return nodes


def extract_node_urls(subscription_text: str) -> list[str]:
    urls: list[str] = []
    for match in NODE_URL_PATTERN.finditer(subscription_text):
        raw = match.group(0).strip().rstrip(".,;)")
        if raw:
            urls.append(raw)
    return urls


def parse_clash_nodes(subscription_text: str, source: str) -> list[NodeInfo]:
    proxies = _extract_clash_proxies(subscription_text)
    nodes: list[NodeInfo] = []
    for index, proxy in enumerate(proxies, start=1):
        stable_raw = _stable_json(proxy)
        nodes.append(
            NodeInfo(
                raw=stable_raw,
                name=str(proxy.get("name") or f"{source}#{index}"),
                fingerprint=hash_node(stable_raw),
                source=source,
            )
        )
    return nodes


def merge_nodes(
    sources: Iterable[tuple[str, str]],
    previous_fingerprints: Iterable[str] | None = None,
    *,
    deduplicate: bool = True,
    output_base64: bool = True,
    output_format: str = "auto",
    rule_profile: str = "mihomo_ruleset",
) -> MergeResult:
    previous = set(previous_fingerprints or [])
    current_nodes: list[NodeInfo] = []
    clash_proxies: list[dict] = []
    v2ray_links: list[str] = []
    seen: set[str] = set()
    has_clash_yaml = False

    for source, subscription_text in sources:
        proxies = _extract_clash_proxies(subscription_text)
        if proxies:
            has_clash_yaml = True
            for index, proxy in enumerate(proxies, start=1):
                tagged_proxy = tag_clash_proxy(proxy, source, index)
                stable_raw = _stable_json(tagged_proxy)
                if deduplicate and stable_raw in seen:
                    continue
                seen.add(stable_raw)
                clash_proxies.append(tagged_proxy)
                current_nodes.append(
                    NodeInfo(
                        raw=stable_raw,
                        name=str(tagged_proxy.get("name") or f"{source}#{index}"),
                        fingerprint=hash_node(stable_raw),
                        source=source,
                    )
                )
            continue

        for node in parse_nodes(subscription_text, source):
            tagged_node = tag_node(node, source)
            if deduplicate and tagged_node.raw in seen:
                continue
            seen.add(tagged_node.raw)
            current_nodes.append(tagged_node)
            v2ray_links.append(tagged_node.raw)

    current_fingerprints = {node.fingerprint for node in current_nodes}
    added = [node for node in current_nodes if node.fingerprint not in previous]
    removed = [
        NodeInfo(raw="", name=fingerprint[:12], fingerprint=fingerprint, source="")
        for fingerprint in sorted(previous - current_fingerprints)
    ]

    selected_format = _select_output_format(output_format, has_clash_yaml)
    if selected_format == "clash_yaml":
        output_text = build_clash_yaml(clash_proxies, rule_profile=rule_profile)
        encoded = base64.b64encode(output_text.encode("utf-8")).decode("ascii")
    else:
        output_text = "\n".join(node.raw for node in current_nodes)
        encoded = base64.b64encode(output_text.encode("utf-8")).decode("ascii")
        output_text = encoded if selected_format == "base64" and output_base64 else output_text

    v2ray_text = "\n".join(v2ray_links)
    v2ray_base64 = base64.b64encode(v2ray_text.encode("utf-8")).decode("ascii") if v2ray_text else ""

    return MergeResult(
        nodes=current_nodes,
        output_text=output_text,
        output_base64=encoded,
        v2ray_text=v2ray_text,
        v2ray_base64=v2ray_base64,
        added=added,
        removed=removed,
        output_format=selected_format,
    )


def build_clash_yaml(proxies: list[dict], *, rule_profile: str = "mihomo_ruleset") -> str:
    names = [str(proxy.get("name")) for proxy in proxies if proxy.get("name")]
    proxy_groups, rules, rule_providers = _build_rule_profile(rule_profile, names)
    config = {
        "mixed-port": 7890,
        "allow-lan": False,
        "mode": "global" if _is_no_rule_profile(rule_profile) else "rule",
        "log-level": "info",
        "proxies": proxies,
        "proxy-groups": proxy_groups,
    }
    if rule_providers:
        config["rule-providers"] = rule_providers
    if rules:
        config["rules"] = rules
    if yaml is None:
        return _dump_basic_yaml(config)
    return yaml.safe_dump(config, allow_unicode=True, sort_keys=False)


def hash_node(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def extract_node_name(raw: str) -> str:
    scheme = raw.split("://", 1)[0].lower()
    if scheme == "vmess":
        name = _extract_vmess_name(raw)
        if name:
            return name
    if "#" in raw:
        return unquote(raw.rsplit("#", 1)[1]).strip()
    return _extract_uri_host(raw)


def tag_node(node: NodeInfo, source: str) -> NodeInfo:
    name = tag_node_name(node.name, source)
    raw = rewrite_node_name(node.raw, name)
    return NodeInfo(raw=raw, name=name, fingerprint=hash_node(raw), source=node.source)


def tag_clash_proxy(proxy: dict, source: str, index: int) -> dict:
    tagged = dict(proxy)
    original = str(tagged.get("name") or f"{source}#{index}")
    tagged["name"] = tag_node_name(original, source)
    return tagged


def tag_node_name(name: str, source: str) -> str:
    source = source.strip()
    name = (name or "").strip()
    if not source:
        return name
    tag = f"[{source}]"
    if tag in name:
        return name
    match = EMOJI_PREFIX_PATTERN.match(name)
    if match:
        emoji = match.group(1).strip()
        rest = name[match.end() :].lstrip()
        return f"{emoji}{tag}" + (f" {rest}" if rest else "")
    return f"{tag}{name}"


def rewrite_node_name(raw: str, name: str) -> str:
    scheme = raw.split("://", 1)[0].lower()
    if scheme == "vmess":
        rewritten = _rewrite_vmess_name(raw, name)
        if rewritten:
            return rewritten
    encoded_name = quote(name, safe="")
    if "#" in raw:
        return raw.rsplit("#", 1)[0] + "#" + encoded_name
    return raw + "#" + encoded_name


def summarize_changes(
    added: list[NodeInfo],
    removed: list[NodeInfo],
    *,
    max_names: int = 8,
) -> str:
    if not added and not removed:
        return ""
    lines = [f"订阅节点有变化：新增 {len(added)} 个，移除 {len(removed)} 个。"]
    if added:
        lines.append("新增：" + "、".join(node.name for node in added[:max_names]))
    if removed:
        lines.append("移除：" + "、".join(node.name for node in removed[:max_names]))
    hidden = max(0, len(added) + len(removed) - max_names * 2)
    if hidden:
        lines.append(f"另有 {hidden} 个变化未展开。")
    return "\n".join(lines)


def _looks_like_subscription_text(text: str) -> bool:
    return bool(NODE_URL_PATTERN.search(text))


def _looks_like_clash_yaml(text: str) -> bool:
    lower = text.lower()
    return "proxies:" in lower or "proxy-providers:" in lower or "proxy-groups:" in lower


def _extract_clash_proxies(subscription_text: str) -> list[dict]:
    if not _looks_like_clash_yaml(subscription_text):
        return []
    if yaml is None:
        return _extract_inline_clash_proxies(subscription_text)
    try:
        data = yaml.safe_load(subscription_text)
    except Exception:
        return _extract_inline_clash_proxies(subscription_text)
    if not isinstance(data, dict):
        return []
    proxies = data.get("proxies")
    if not isinstance(proxies, list):
        return []
    return [proxy for proxy in proxies if isinstance(proxy, dict) and proxy.get("name")]


def _extract_inline_clash_proxies(subscription_text: str) -> list[dict]:
    proxies: list[dict] = []
    in_proxies = False
    for line in subscription_text.splitlines():
        stripped = line.strip()
        if stripped == "proxies:":
            in_proxies = True
            continue
        if in_proxies and stripped and not line.startswith((" ", "-")):
            break
        if not in_proxies or not stripped.startswith("- {") or not stripped.endswith("}"):
            continue
        body = stripped[3:-1]
        proxy: dict[str, str] = {}
        for part in body.split(","):
            if ":" not in part:
                continue
            key, value = part.split(":", 1)
            proxy[key.strip()] = value.strip().strip("'\"")
        if proxy.get("name"):
            proxies.append(proxy)
    return proxies


def _select_output_format(configured: str, has_clash_yaml: bool) -> str:
    configured = (configured or "auto").lower()
    if configured in {"clash", "clash_yaml", "yaml"}:
        return "clash_yaml"
    if configured in {"base64", "plain"}:
        return configured
    return "clash_yaml" if has_clash_yaml else "base64"


def _build_rule_profile(rule_profile: str, names: list[str]) -> tuple[list[dict], list[str], dict]:
    rule_profile = (rule_profile or "mihomo_ruleset").strip().lower()
    if _is_no_rule_profile(rule_profile):
        return _basic_proxy_groups(names), [], {}
    if rule_profile in {"basic", "simple"}:
        return _basic_proxy_groups(names), _basic_rules(), {}
    if rule_profile in {"emoji_microsoft_proxy", "inline", "inline_emoji"}:
        return _emoji_proxy_groups(names), _inline_emoji_rules(), {}
    return _emoji_proxy_groups(names), _mihomo_ruleset_rules(), _mihomo_rule_providers()


def _is_no_rule_profile(rule_profile: str) -> bool:
    return (rule_profile or "").strip().lower() in {"none", "off", "disabled", "global"}


def _basic_proxy_groups(names: list[str]) -> list[dict]:
    return [
        {"name": "Proxy", "type": "select", "proxies": ["Auto", "DIRECT", *names]},
        {
            "name": "Auto",
            "type": "url-test",
            "proxies": names,
            "url": "http://www.gstatic.com/generate_204",
            "interval": 300,
        },
    ]


def _basic_rules() -> list[str]:
    return [
        "DOMAIN-SUFFIX,local,DIRECT",
        "IP-CIDR,127.0.0.0/8,DIRECT,no-resolve",
        "IP-CIDR,172.16.0.0/12,DIRECT,no-resolve",
        "IP-CIDR,192.168.0.0/16,DIRECT,no-resolve",
        "IP-CIDR,10.0.0.0/8,DIRECT,no-resolve",
        "GEOIP,CN,DIRECT",
        "MATCH,Proxy",
    ]


def _emoji_proxy_groups(names: list[str]) -> list[dict]:
    selectable = ["♻️ 自动选择", "DIRECT", *names]
    return [
        {"name": "🚀 节点选择", "type": "select", "proxies": selectable},
        {
            "name": "♻️ 自动选择",
            "type": "url-test",
            "proxies": names,
            "url": "http://www.gstatic.com/generate_204",
            "interval": 300,
        },
        {"name": "🛑 广告拦截", "type": "select", "proxies": ["REJECT", "DIRECT", "🚀 节点选择"]},
        {"name": "🤖 OpenAI", "type": "select", "proxies": ["🚀 节点选择", "♻️ 自动选择", *names, "DIRECT"]},
        {"name": "🧠 AI 服务", "type": "select", "proxies": ["🚀 节点选择", "♻️ 自动选择", *names, "DIRECT"]},
        {"name": "Ⓜ️ 微软服务", "type": "select", "proxies": ["🚀 节点选择", "♻️ 自动选择", *names, "DIRECT"]},
        {"name": "🛠️ 开发平台", "type": "select", "proxies": ["🚀 节点选择", "♻️ 自动选择", *names, "DIRECT"]},
        {"name": "💬 电报消息", "type": "select", "proxies": ["🚀 节点选择", "♻️ 自动选择", *names, "DIRECT"]},
        {"name": "🍎 苹果服务", "type": "select", "proxies": ["DIRECT", "🚀 节点选择", "♻️ 自动选择", *names]},
        {"name": "🌍 国外媒体", "type": "select", "proxies": ["🚀 节点选择", "♻️ 自动选择", *names, "DIRECT"]},
        {"name": "🎯 全球直连", "type": "select", "proxies": ["DIRECT", "🚀 节点选择"]},
        {"name": "🐟 漏网之鱼", "type": "select", "proxies": ["🚀 节点选择", "DIRECT", "♻️ 自动选择", *names]},
    ]


def _inline_emoji_rules() -> list[str]:
    return [
        "DOMAIN-SUFFIX,local,DIRECT",
        "IP-CIDR,127.0.0.0/8,DIRECT,no-resolve",
        "IP-CIDR,172.16.0.0/12,DIRECT,no-resolve",
        "IP-CIDR,192.168.0.0/16,DIRECT,no-resolve",
        "IP-CIDR,10.0.0.0/8,DIRECT,no-resolve",
        "DOMAIN-SUFFIX,openai.com,🤖 OpenAI",
        "DOMAIN-SUFFIX,chatgpt.com,🤖 OpenAI",
        "DOMAIN-SUFFIX,oaistatic.com,🤖 OpenAI",
        "DOMAIN-SUFFIX,oaiusercontent.com,🤖 OpenAI",
        "GEOSITE,microsoft,Ⓜ️ 微软服务",
        "GEOSITE,onedrive,Ⓜ️ 微软服务",
        "DOMAIN-SUFFIX,microsoft.com,Ⓜ️ 微软服务",
        "DOMAIN-SUFFIX,windowsupdate.com,Ⓜ️ 微软服务",
        "DOMAIN-SUFFIX,office.com,Ⓜ️ 微软服务",
        "DOMAIN-SUFFIX,office365.com,Ⓜ️ 微软服务",
        "DOMAIN-SUFFIX,live.com,Ⓜ️ 微软服务",
        "DOMAIN-SUFFIX,onedrive.com,Ⓜ️ 微软服务",
        "DOMAIN-SUFFIX,sharepoint.com,Ⓜ️ 微软服务",
        "DOMAIN-SUFFIX,github.com,🚀 节点选择",
        "DOMAIN-SUFFIX,githubusercontent.com,🚀 节点选择",
        "GEOSITE,apple,🍎 苹果服务",
        "GEOSITE,youtube,🌍 国外媒体",
        "GEOSITE,netflix,🌍 国外媒体",
        "GEOSITE,telegram,🚀 节点选择",
        "GEOSITE,cn,🎯 全球直连",
        "GEOIP,CN,🎯 全球直连",
        "MATCH,🐟 漏网之鱼",
    ]


def _mihomo_rule_providers() -> dict:
    base = "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Clash"
    return {
        "reject": _rule_provider(f"{base}/Advertising/Advertising.yaml", "reject"),
        "private": _rule_provider(f"{base}/Lan/Lan.yaml", "private"),
        "openai": _rule_provider(f"{base}/OpenAI/OpenAI.yaml", "openai"),
        "microsoft": _rule_provider(f"{base}/Microsoft/Microsoft.yaml", "microsoft"),
        "onedrive": _rule_provider(f"{base}/OneDrive/OneDrive.yaml", "onedrive"),
        "github": _rule_provider(f"{base}/GitHub/GitHub.yaml", "github"),
        "telegram": _rule_provider(f"{base}/Telegram/Telegram.yaml", "telegram"),
        "youtube": _rule_provider(f"{base}/YouTube/YouTube.yaml", "youtube"),
        "netflix": _rule_provider(f"{base}/Netflix/Netflix.yaml", "netflix"),
        "spotify": _rule_provider(f"{base}/Spotify/Spotify.yaml", "spotify"),
        "tiktok": _rule_provider(f"{base}/TikTok/TikTok.yaml", "tiktok"),
        "apple": _rule_provider(f"{base}/Apple/Apple.yaml", "apple"),
        "proxy": _rule_provider(f"{base}/Global/Global.yaml", "proxy"),
        "direct": _rule_provider(f"{base}/China/China.yaml", "direct"),
    }


def _rule_provider(url: str, name: str) -> dict:
    return {
        "type": "http",
        "behavior": "classical",
        "format": "yaml",
        "url": url,
        "path": f"./ruleset/{name}.yaml",
        "interval": 86400,
    }


def _mihomo_ruleset_rules() -> list[str]:
    return [
        "RULE-SET,reject,🛑 广告拦截",
        "RULE-SET,private,🎯 全球直连",
        "DOMAIN-SUFFIX,local,🎯 全球直连",
        "IP-CIDR,127.0.0.0/8,🎯 全球直连,no-resolve",
        "IP-CIDR,172.16.0.0/12,🎯 全球直连,no-resolve",
        "IP-CIDR,192.168.0.0/16,🎯 全球直连,no-resolve",
        "IP-CIDR,10.0.0.0/8,🎯 全球直连,no-resolve",
        "RULE-SET,openai,🤖 OpenAI",
        "DOMAIN-SUFFIX,anthropic.com,🧠 AI 服务",
        "DOMAIN-SUFFIX,claude.ai,🧠 AI 服务",
        "DOMAIN-SUFFIX,gemini.google.com,🧠 AI 服务",
        "DOMAIN-SUFFIX,perplexity.ai,🧠 AI 服务",
        "RULE-SET,microsoft,Ⓜ️ 微软服务",
        "RULE-SET,onedrive,Ⓜ️ 微软服务",
        "RULE-SET,github,🛠️ 开发平台",
        "RULE-SET,telegram,💬 电报消息",
        "RULE-SET,youtube,🌍 国外媒体",
        "RULE-SET,netflix,🌍 国外媒体",
        "RULE-SET,spotify,🌍 国外媒体",
        "RULE-SET,tiktok,🌍 国外媒体",
        "RULE-SET,apple,🍎 苹果服务",
        "RULE-SET,proxy,🚀 节点选择",
        "RULE-SET,direct,🎯 全球直连",
        "GEOSITE,cn,🎯 全球直连",
        "GEOIP,CN,🎯 全球直连",
        "MATCH,🐟 漏网之鱼",
    ]


def _stable_json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _dump_basic_yaml(value, indent: int = 0) -> str:
    lines: list[str] = []
    prefix = " " * indent
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.append(_dump_basic_yaml(item, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {_yaml_scalar(item)}")
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                lines.append(f"{prefix}-")
                lines.append(_dump_basic_yaml(item, indent + 2))
            else:
                lines.append(f"{prefix}- {_yaml_scalar(item)}")
    return "\n".join(line for line in lines if line != "")


def _yaml_scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _extract_uri_host(raw: str) -> str:
    try:
        parsed = urlsplit(raw)
        return parsed.hostname or ""
    except Exception:
        return ""


def _extract_vmess_name(raw: str) -> str:
    payload = raw.split("://", 1)[1].strip()
    try:
        payload += "=" * (-len(payload) % 4)
        decoded = base64.b64decode(payload).decode("utf-8", errors="replace")
        data = json.loads(decoded)
    except Exception:
        return ""
    return str(data.get("ps") or data.get("add") or "").strip()


def _rewrite_vmess_name(raw: str, name: str) -> str:
    payload = raw.split("://", 1)[1].strip()
    try:
        payload += "=" * (-len(payload) % 4)
        decoded = base64.b64decode(payload).decode("utf-8", errors="replace")
        data = json.loads(decoded)
    except Exception:
        return ""
    data["ps"] = name
    encoded = base64.b64encode(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return "vmess://" + encoded.decode("ascii")
