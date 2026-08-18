import base64
import json

import pytest

from subagg.subscription.adapters.registry import convert_share_link
from subagg.subscription.detect import PayloadKind, decode_text
from subagg.subscription.models import AdapterError
from subagg.subscription.parser import parse_source


def test_content_detection_ignores_filename_and_recognizes_mixed_hy2_vless():
    payload = "\n".join(
        [
            "hysteria2://password@example.com:443?sni=edge.example#hy2",
            "vless://00000000-0000-0000-0000-000000000000@example.com:443?security=tls&sni=edge.example#vless",
        ]
    )
    detected = decode_text(payload)
    assert detected.kind is PayloadKind.SHARE_LINKS


def test_content_detection_recognizes_no_suffix_clash_yaml():
    detected = decode_text("proxies:\n  - name: node\n    type: ss\n    server: 127.0.0.1\n    port: 443\n    cipher: aes-128-gcm\n    password: test")
    assert detected.kind is PayloadKind.CLASH_YAML
    assert detected.data["proxies"][0]["name"] == "node"


def test_base64_wrapped_yaml_is_detected_by_content():
    raw = "proxies:\n  - name: node\n    type: ss\n    server: 127.0.0.1\n    port: 443\n    cipher: aes-128-gcm\n    password: test"
    detected = decode_text(base64.b64encode(raw.encode()).decode())
    assert detected.kind is PayloadKind.CLASH_YAML


def test_vless_xhttp_vision_and_encryption_fields():
    raw = (
        "vless://00000000-0000-0000-0000-000000000000@example.com:443"
        "?security=reality&pbk=public&sid=abcd&flow=xtls-rprx-vision"
        "&type=xhttp&path=%2Fapi&host=cdn.example&mode=stream-one"
        "&alpn=h3&encryption=native%3Avalue#node"
    )
    proxy = convert_share_link(raw, "node")
    assert proxy["type"] == "vless"
    assert proxy["flow"] == "xtls-rprx-vision"
    assert proxy["network"] == "xhttp"
    assert proxy["xhttp-opts"]["mode"] == "stream-one"
    assert proxy["reality-opts"]["short-id"] == "abcd"
    assert proxy["encryption"].startswith("native")


def test_vless_rejects_unknown_flow():
    with pytest.raises(AdapterError, match="flow"):
        convert_share_link("vless://id@example.com:443?flow=vision", "node")


def test_vless_rejects_all_zero_reality_short_id():
    with pytest.raises(AdapterError, match="short-id"):
        convert_share_link(
            "vless://id@example.com:443?security=reality&pbk=public&sid=0000",
            "node",
        )


def test_hysteria_is_not_mapped_to_hysteria2():
    proxy = convert_share_link("hysteria://auth@example.com:443?protocol=udp&up=10&down=20", "h1")
    assert proxy["type"] == "hysteria"
    assert proxy["auth-str"] == "auth"


def test_tuic_v4_uses_token_not_uuid_and_password():
    proxy = convert_share_link("tuic://token@example.com:443?version=4", "tuic-v4")
    assert proxy["token"] == "token"
    assert "uuid" not in proxy


def test_anytls_reality_is_explicitly_rejected():
    with pytest.raises(AdapterError, match="不支持 AnyTLS-Reality"):
        convert_share_link("anytls://password@example.com:443?security=reality", "node")


def test_hysteria2_tuic_and_ss2022_convert():
    hy2 = convert_share_link("hy2://password@example.com:443?sni=edge.example", "hy2")
    tuic = convert_share_link("tuic://uuid:password@example.com:443?congestion_control=bbr", "tuic")
    ss = convert_share_link("ss://2022-blake3-aes-128-gcm:password@example.com:443", "ss")
    assert hy2["type"] == "hysteria2"
    assert tuic["type"] == "tuic"
    assert tuic["congestion-controller"] == "bbr"
    assert ss["type"] == "ss"
    assert ss["cipher"].startswith("2022-")


def test_vmess_required_fields_and_transport():
    payload = {"v": "2", "ps": "vmess", "add": "example.com", "port": "443", "id": "uuid", "aid": "0", "scy": "auto", "tls": "tls", "net": "grpc", "path": "service"}
    raw = "vmess://" + base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    proxy = convert_share_link(raw, "vmess")
    assert proxy["type"] == "vmess"
    assert proxy["network"] == "grpc"
    assert proxy["grpc-opts"]["grpc-service-name"] == "service"


def test_yaml_proxy_with_invalid_reality_short_id_is_reported_and_skipped():
    source = parse_source(
        """proxies:
  - name: bad-reality
    type: vless
    server: example.com
    port: 443
    uuid: 00000000-0000-0000-0000-000000000000
    reality-opts:
      public-key: public-key
      short-id: 0000
""",
        "yaml-source",
    )
    assert source.nodes == []
    assert source.issues[0].reason == "Reality short-id 非法"


def test_vless_none_encryption_is_legacy_no_extra_encryption():
    raw = "vless://00000000-0000-0000-0000-000000000000@example.com:443?encryption=none"
    proxy = convert_share_link(raw, "node")
    assert "encryption" not in proxy
