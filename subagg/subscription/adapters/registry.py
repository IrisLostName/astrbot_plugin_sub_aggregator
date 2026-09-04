from __future__ import annotations

from typing import Callable

from ..models import AdapterError
from . import anytls, http_proxy, hysteria, hysteria2, shadowsocks, socks, trojan, tuic, vless, vmess, wireguard


Adapter = Callable[[str, str], dict]
ADAPTERS: dict[str, Adapter] = {
    "ss": shadowsocks.convert,
    "vmess": vmess.convert,
    "vless": vless.convert,
    "trojan": trojan.convert,
    "hysteria2": hysteria2.convert,
    "hy2": hysteria2.convert,
    "hysteria": hysteria.convert,
    "tuic": tuic.convert,
    "anytls": anytls.convert,
    "http": http_proxy.convert,
    "https": http_proxy.convert,
    "socks": socks.convert,
    "socks5": socks.convert,
    "wireguard": wireguard.convert,
}


def convert_share_link(raw: str, name: str) -> dict:
    scheme = raw.split("://", 1)[0].lower()
    adapter = ADAPTERS.get(scheme)
    if adapter is None:
        raise AdapterError(scheme or "unknown", "没有安全的 Mihomo 映射")
    try:
        return adapter(raw, name)
    except AdapterError:
        raise
    except (TypeError, ValueError) as exc:
        raise AdapterError(scheme, str(exc)) from exc
