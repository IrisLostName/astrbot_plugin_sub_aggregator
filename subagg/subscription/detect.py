from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass
from typing import Any

import yaml

from .models import PayloadKind


@dataclass(frozen=True)
class DetectedPayload:
    kind: PayloadKind
    text: str
    data: dict[str, Any] | None = None


_SCHEME_RE = re.compile(r"(?i)^(ss|ssr|vmess|vless|trojan|hysteria|hysteria2|hy2|tuic|anytls|http|https|socks|socks5|wireguard)://")


def decode_text(raw: bytes | str, *, max_base64_rounds: int = 1) -> DetectedPayload:
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    text = text.lstrip("﻿").strip()
    for _ in range(max_base64_rounds + 1):
        detected = classify_payload(text)
        if detected.kind is not PayloadKind.UNKNOWN:
            return detected
        compact = re.sub(r"\s+", "", text)
        if not compact or len(compact) > 4_000_000:
            break
        try:
            decoded = base64.b64decode(compact + "=" * (-len(compact) % 4), validate=True)
            candidate = decoded.decode("utf-8", errors="strict").lstrip("﻿").strip()
        except (UnicodeDecodeError, ValueError, binascii.Error):
            break
        if candidate == text:
            break
        text = candidate
    return classify_payload(text)


def classify_payload(text: str) -> DetectedPayload:
    text = text.lstrip("﻿").strip()
    if not text:
        return DetectedPayload(PayloadKind.UNKNOWN, text)
    lowered = text.lower()
    if "<html" in lowered or "<!doctype html" in lowered:
        return DetectedPayload(PayloadKind.HTML, text)
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError:
        parsed = None
    if isinstance(parsed, dict) and isinstance(parsed.get("proxies"), list):
        return DetectedPayload(PayloadKind.CLASH_YAML, text, parsed)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    link_lines = [_SCHEME_RE.match(line) is not None for line in lines]
    if lines and all(link_lines):
        return DetectedPayload(PayloadKind.SHARE_LINKS, text)
    if any(link_lines):
        return DetectedPayload(PayloadKind.MIXED, text)
    return DetectedPayload(PayloadKind.UNKNOWN, text)


def extract_share_links(text: str) -> list[tuple[int, str]]:
    links: list[tuple[int, str]] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if _SCHEME_RE.match(line):
            links.append((line_number, line))
    return links
