from __future__ import annotations

import re

from typing import Any

from .adapters.registry import convert_share_link
from .detect import DetectedPayload, decode_text, extract_share_links
from .models import AdapterError, ConversionIssue, ParsedNode, PayloadKind, SourceResult


def parse_source(raw: bytes | str, source: str) -> SourceResult:
    detected = decode_text(raw)
    if detected.kind is PayloadKind.CLASH_YAML:
        return _parse_yaml(detected, source)
    if detected.kind in {PayloadKind.SHARE_LINKS, PayloadKind.MIXED}:
        return _parse_links(detected, source)
    issue = ConversionIssue(source, detected.kind.value, _content_reason(detected.kind))
    return SourceResult(source=source, kind=detected.kind, issues=[issue])


def _parse_yaml(detected: DetectedPayload, source: str) -> SourceResult:
    assert detected.data is not None
    nodes: list[ParsedNode] = []
    issues: list[ConversionIssue] = []
    for index, proxy in enumerate(detected.data.get("proxies", []), start=1):
        if not isinstance(proxy, dict):
            issues.append(ConversionIssue(source, "clash_yaml", "proxy 不是对象", index))
            continue
        name = str(proxy.get("name") or f"{source}#{index}")
        if not proxy.get("type") or not proxy.get("server") or not proxy.get("port"):
            issues.append(ConversionIssue(source, "clash_yaml", "proxy 缺少 type/server/port", index))
            continue
        if not _has_valid_reality_short_id(proxy):
            issues.append(ConversionIssue(source, "clash_yaml", "Reality short-id 非法", index))
            continue
        nodes.append(ParsedNode(source=source, name=name, proxy=dict(proxy)))
    return SourceResult(source=source, kind=PayloadKind.CLASH_YAML, nodes=nodes, issues=issues)


def _has_valid_reality_short_id(proxy: dict) -> bool:
    reality = proxy.get("reality-opts")
    if not isinstance(reality, dict):
        return True
    short_id = reality.get("short-id", reality.get("short_id"))
    if short_id in (None, ""):
        return True
    text = str(short_id).strip()
    return bool(re.fullmatch(r"(?:[0-9a-fA-F]{2}){1,8}", text)) and int(text, 16) != 0


def _parse_links(detected: DetectedPayload, source: str) -> SourceResult:
    nodes: list[ParsedNode] = []
    issues: list[ConversionIssue] = []
    for line_number, raw in extract_share_links(detected.text):
        scheme = raw.split("://", 1)[0].lower()
        name = _name_from_link(raw, source, len(nodes) + 1)
        try:
            proxy = convert_share_link(raw, name)
        except AdapterError as exc:
            issues.append(ConversionIssue(source, exc.protocol or scheme, exc.reason, line_number))
            continue
        nodes.append(ParsedNode(source=source, name=name, proxy=proxy))
    return SourceResult(source=source, kind=detected.kind, nodes=nodes, issues=issues)


def _name_from_link(raw: str, source: str, index: int) -> str:
    if "#" in raw:
        value = raw.rsplit("#", 1)[1].strip()
        if value:
            from urllib.parse import unquote
            return unquote(value)
    return f"{source}#{index}"


def _content_reason(kind: PayloadKind) -> str:
    return {
        PayloadKind.HTML: "响应是 HTML 或登录/风控页面",
        PayloadKind.UNKNOWN: "内容不是已识别的 YAML、Base64 或分享链接",
    }.get(kind, "内容无法解析")
