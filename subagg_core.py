from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import quote, urlencode, unquote, urlsplit

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
REALITY_SHORT_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{2,32}$")


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
                v2ray_uri = clash_proxy_to_v2ray_uri(tagged_proxy)
                if v2ray_uri:
                    v2ray_links.append(v2ray_uri)
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
    tagged = deepcopy(proxy)
    original = str(tagged.get("name") or f"{source}#{index}")
    tagged["name"] = tag_node_name(original, source)
    sanitize_clash_proxy(tagged)
    return tagged


def sanitize_clash_proxy(proxy: dict) -> dict:
    """Make provider YAML tolerant of malformed REALITY short-id values."""
    _sanitize_reality_opts_recursive(proxy)
    return proxy


def clash_proxy_to_v2ray_uri(proxy: dict) -> str:
    proxy_type = str(proxy.get("type") or "").strip().lower()
    if proxy_type in {"vless", "trojan"}:
        return _build_vless_or_trojan_uri(proxy, proxy_type)
    if proxy_type == "vmess":
        return _build_vmess_uri(proxy)
    if proxy_type == "ss":
        return _build_ss_uri(proxy)
    if proxy_type in {"hysteria2", "hy2"}:
        return _build_hysteria2_uri(proxy)
    return ""


def _sanitize_reality_opts_recursive(value) -> None:
    if isinstance(value, dict):
        if isinstance(value.get("reality-opts"), dict):
            _sanitize_reality_opts(value["reality-opts"])
        for item in value.values():
            _sanitize_reality_opts_recursive(item)
    elif isinstance(value, list):
        for item in value:
            _sanitize_reality_opts_recursive(item)


def _sanitize_reality_opts(reality_opts: dict) -> None:
    if "short_id" in reality_opts and "short-id" not in reality_opts:
        reality_opts["short-id"] = reality_opts.pop("short_id")

    if "short-id" not in reality_opts:
        return

    normalized = _normalize_reality_short_id(reality_opts.get("short-id"))
    if normalized is None:
        reality_opts.pop("short-id", None)
    else:
        reality_opts["short-id"] = normalized


def _normalize_reality_short_id(value) -> str | None:
    if value is None or isinstance(value, bool):
        return None

    text = str(value).strip()
    if not text:
        return None

    if text.lower().startswith("0x"):
        text = text[2:]
    text = re.sub(r"[\s:_-]+", "", text)

    if not text or re.search(r"[^0-9a-fA-F]", text):
        return None
    if len(text) > 32:
        return None
    if len(text) % 2 == 1:
        text = "0" + text
    if not REALITY_SHORT_ID_PATTERN.match(text):
        return None
    return text.lower()


def _build_vless_or_trojan_uri(proxy: dict, scheme: str) -> str:
    server = _required_proxy_text(proxy, "server")
    port = _required_proxy_text(proxy, "port")
    credential_key = "uuid" if scheme == "vless" else "password"
    credential = _required_proxy_text(proxy, credential_key)
    if not server or not port or not credential:
        return ""

    params = _common_v2ray_params(proxy)
    if scheme == "vless":
        params.setdefault("encryption", str(proxy.get("encryption") or "none"))
    return _build_uri(scheme, credential, server, port, params, str(proxy.get("name") or ""))


def _build_hysteria2_uri(proxy: dict) -> str:
    server = _required_proxy_text(proxy, "server")
    port = _required_proxy_text(proxy, "port")
    password = _required_proxy_text(proxy, "password")
    if not server or not port or not password:
        return ""

    params: dict[str, str] = {}
    _add_param(params, "sni", proxy.get("sni") or proxy.get("servername"))
    if proxy.get("skip-cert-verify") is True:
        params["insecure"] = "1"
    _add_param(params, "obfs", proxy.get("obfs"))
    _add_param(params, "obfs-password", proxy.get("obfs-password"))
    _add_param(params, "alpn", _join_if_list(proxy.get("alpn")))
    return _build_uri("hysteria2", password, server, port, params, str(proxy.get("name") or ""))


def _build_ss_uri(proxy: dict) -> str:
    server = _required_proxy_text(proxy, "server")
    port = _required_proxy_text(proxy, "port")
    cipher = _required_proxy_text(proxy, "cipher")
    password = _required_proxy_text(proxy, "password")
    if not server or not port or not cipher or not password:
        return ""

    userinfo = base64.urlsafe_b64encode(f"{cipher}:{password}".encode("utf-8")).decode("ascii").rstrip("=")
    params: dict[str, str] = {}
    _add_param(params, "plugin", proxy.get("plugin"))
    _add_param(params, "plugin-opts", proxy.get("plugin-opts"))
    return _build_uri("ss", userinfo, server, port, params, str(proxy.get("name") or ""))


def _build_vmess_uri(proxy: dict) -> str:
    server = _required_proxy_text(proxy, "server")
    port = _required_proxy_text(proxy, "port")
    uuid = _required_proxy_text(proxy, "uuid")
    if not server or not port or not uuid:
        return ""

    network = str(proxy.get("network") or "tcp")
    ws_opts = proxy.get("ws-opts") if isinstance(proxy.get("ws-opts"), dict) else {}
    grpc_opts = proxy.get("grpc-opts") if isinstance(proxy.get("grpc-opts"), dict) else {}
    headers = ws_opts.get("headers") if isinstance(ws_opts.get("headers"), dict) else {}
    tls = "tls" if proxy.get("tls") is True else ""
    data = {
        "v": "2",
        "ps": str(proxy.get("name") or ""),
        "add": server,
        "port": port,
        "id": uuid,
        "aid": str(proxy.get("alterId") if proxy.get("alterId") is not None else proxy.get("alter-id") or 0),
        "scy": str(proxy.get("cipher") or "auto"),
        "net": network,
        "type": str(proxy.get("http-opts", {}).get("method") or "none")
        if isinstance(proxy.get("http-opts"), dict)
        else "none",
        "host": str(headers.get("Host") or headers.get("host") or proxy.get("servername") or ""),
        "path": str(ws_opts.get("path") or grpc_opts.get("grpc-service-name") or ""),
        "tls": tls,
        "sni": str(proxy.get("servername") or proxy.get("sni") or ""),
        "alpn": _join_if_list(proxy.get("alpn")),
        "fp": str(proxy.get("client-fingerprint") or ""),
    }
    encoded = base64.b64encode(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return "vmess://" + encoded.decode("ascii")


def _common_v2ray_params(proxy: dict) -> dict[str, str]:
    params: dict[str, str] = {}
    reality_opts = proxy.get("reality-opts") if isinstance(proxy.get("reality-opts"), dict) else {}
    network = str(proxy.get("network") or "tcp")

    if reality_opts:
        params["security"] = "reality"
        _add_param(params, "pbk", reality_opts.get("public-key"))
        _add_param(params, "sid", reality_opts.get("short-id"))
        _add_param(params, "spx", reality_opts.get("spider-x"))
    elif proxy.get("tls") is True:
        params["security"] = "tls"
    else:
        params["security"] = "none"

    _add_param(params, "type", network)
    _add_param(params, "flow", proxy.get("flow"))
    _add_param(params, "sni", proxy.get("servername") or proxy.get("sni"))
    _add_param(params, "fp", proxy.get("client-fingerprint"))
    _add_param(params, "alpn", _join_if_list(proxy.get("alpn")))
    if proxy.get("skip-cert-verify") is True:
        params["allowInsecure"] = "1"

    ws_opts = proxy.get("ws-opts") if isinstance(proxy.get("ws-opts"), dict) else {}
    grpc_opts = proxy.get("grpc-opts") if isinstance(proxy.get("grpc-opts"), dict) else {}
    http_opts = proxy.get("http-opts") if isinstance(proxy.get("http-opts"), dict) else {}
    xhttp_opts = proxy.get("xhttp-opts") if isinstance(proxy.get("xhttp-opts"), dict) else {}

    headers = ws_opts.get("headers") if isinstance(ws_opts.get("headers"), dict) else {}
    _add_param(params, "path", ws_opts.get("path") or http_opts.get("path") or xhttp_opts.get("path"))
    _add_param(params, "host", headers.get("Host") or headers.get("host") or xhttp_opts.get("host"))
    _add_param(params, "serviceName", grpc_opts.get("grpc-service-name"))
    _add_param(params, "mode", xhttp_opts.get("mode"))
    return params


def _build_uri(scheme: str, userinfo: str, server: str, port: str, params: dict[str, str], name: str) -> str:
    query = urlencode(params, doseq=False, safe="/:,")
    suffix = f"?{query}" if query else ""
    return f"{scheme}://{quote(str(userinfo), safe='')}@{_format_uri_host(server)}:{port}{suffix}#{quote(name, safe='')}"


def _format_uri_host(server: str) -> str:
    if ":" in server and not server.startswith("[") and not server.endswith("]"):
        return f"[{server}]"
    return server


def _required_proxy_text(proxy: dict, key: str) -> str:
    value = proxy.get(key)
    if value is None or isinstance(value, bool):
        return ""
    return str(value).strip()


def _add_param(params: dict[str, str], key: str, value) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, (list, tuple)):
        value = _join_if_list(value)
    text = str(value).strip()
    if text:
        params[key] = text


def _join_if_list(value) -> str:
    if isinstance(value, (list, tuple)):
        return ",".join(str(item).strip() for item in value if str(item).strip())
    if value is None:
        return ""
    return str(value).strip()


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
