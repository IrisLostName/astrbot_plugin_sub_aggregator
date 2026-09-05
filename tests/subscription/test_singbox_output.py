"""Tests for sing-box 1.14 output generation."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from subagg.subscription.singbox import AdapterError, build_singbox_config, mihomo_to_singbox_outbound


@pytest.fixture
def vless_reality_proxy():
    return {
        "name": "美国节点",
        "type": "vless",
        "server": "example.com",
        "port": 8443,
        "uuid": "00000000-0000-0000-0000-000000000000",
        "flow": "xtls-rprx-vision",
        "packet-encoding": "xudp",
        "tls": True,
        "skip-cert-verify": False,
        "servername": "apple.com",
        "reality-opts": {"public-key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "short-id": "565cbfa64314"},
        "client-fingerprint": "chrome",
    }


@pytest.fixture
def vmess_ws_proxy():
    return {
        "name": "香港节点",
        "type": "vmess",
        "server": "example.com",
        "port": 39551,
        "uuid": "00000000-0000-0000-0000-000000000000",
        "alterId": 0,
        "cipher": "auto",
        "network": "ws",
        "ws-opts": {"path": "/vmess", "headers": {"Host": "example.com"}},
    }


@pytest.fixture
def hysteria2_proxy():
    return {
        "name": "韩国节点",
        "type": "hysteria2",
        "server": "example.com",
        "port": 8443,
        "password": "test-password",
        "sni": "www.amazon.com",
        "skip-cert-verify": True,
        "up": "100",
        "down": "500",
    }


@pytest.fixture
def anytls_proxy():
    return {
        "name": "日本 AnyTLS",
        "type": "anytls",
        "server": "example.com",
        "port": 10000,
        "password": "test-password",
        "sni": "anytls.example.com",
    }


def test_vless_reality_conversion(vless_reality_proxy):
    outbound = mihomo_to_singbox_outbound(vless_reality_proxy, "test-tag")

    assert outbound["type"] == "vless"
    assert outbound["tag"] == "test-tag"
    assert outbound["flow"] == "xtls-rprx-vision"
    assert outbound["packet_encoding"] == "xudp"
    assert outbound["tls"]["server_name"] == "apple.com"
    assert outbound["tls"]["utls"]["fingerprint"] == "chrome"
    assert outbound["tls"]["reality"]["public_key"] == "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


def test_vmess_ws_conversion(vmess_ws_proxy):
    outbound = mihomo_to_singbox_outbound(vmess_ws_proxy, "vmess-tag")

    assert outbound["type"] == "vmess"
    assert outbound["security"] == "auto"
    assert outbound["alter_id"] == 0
    assert outbound["transport"] == {"type": "ws", "path": "/vmess", "headers": {"Host": "example.com"}}


def test_hysteria2_conversion(hysteria2_proxy):
    outbound = mihomo_to_singbox_outbound(hysteria2_proxy, "hy2-tag")

    assert outbound["type"] == "hysteria2"
    assert outbound["up_mbps"] == 100
    assert outbound["down_mbps"] == 500
    assert outbound["tls"]["server_name"] == "www.amazon.com"
    assert outbound["tls"]["insecure"] is True


def test_anytls_conversion(anytls_proxy):
    outbound = mihomo_to_singbox_outbound(anytls_proxy, "anytls-tag")

    assert outbound["type"] == "anytls"
    assert outbound["password"] == "test-password"
    assert outbound["tls"]["server_name"] == "anytls.example.com"


def test_unsupported_protocol_raises_adapter_error():
    with pytest.raises(AdapterError, match="Unsupported proxy type"):
        mihomo_to_singbox_outbound({"type": "unsupported"}, "test-tag")


def test_unsupported_transport_raises_adapter_error(vless_reality_proxy):
    vless_reality_proxy["network"] = "quic"
    with pytest.raises(AdapterError, match="Unsupported transport"):
        mihomo_to_singbox_outbound(vless_reality_proxy, "test-tag")


def test_config_uses_template_contract_and_manual_selector(vless_reality_proxy, vmess_ws_proxy):
    config = json.loads(build_singbox_config([vless_reality_proxy, vmess_ws_proxy]))

    selector = config["outbounds"][0]
    assert selector == {
        "type": "selector",
        "tag": "proxy",
        "outbounds": ["美国节点", "香港节点"],
        "default": "美国节点",
        "interrupt_exist_connections": True,
    }
    assert sum(outbound["type"] == "selector" for outbound in config["outbounds"]) == 1
    assert {outbound["tag"] for outbound in config["outbounds"] if outbound["type"] in {"vless", "vmess"}} == {"美国节点", "香港节点"}
    assert {outbound["tag"] for outbound in config["outbounds"] if outbound["type"] == "direct"} == {"direct"}
    assert not any(outbound["type"] in {"urltest", "block"} for outbound in config["outbounds"])

    assert config["inbounds"] == [
        {
            "type": "tun",
            "tag": "tun-in",
            "interface_name": "singtun0",
            "address": ["172.19.0.1/30"],
            "mtu": 1500,
            "auto_route": True,
            "strict_route": True,
            "stack": "mixed",
        }
    ]
    assert config["experimental"]["clash_api"] == {
        "default_mode": "rule",
        "external_controller": "127.0.0.1:20123",
    }
    assert config["dns"]["rules"][:2] == [
        {"clash_mode": "direct", "action": "route", "server": "dns-cn"},
        {"clash_mode": "global", "action": "route", "server": "dns-global"},
    ]
    assert config["dns"]["strategy"] == "ipv4_only"
    assert config["dns"]["servers"][1]["detour"] == "proxy"
    assert config["http_clients"] == [{"tag": "rules-via-proxy", "detour": "proxy"}]

    assert config["route"]["final"] == "proxy"
    assert config["route"]["rules"] == [
        {"action": "sniff"},
        {"protocol": "dns", "action": "hijack-dns"},
        {"ip_version": 6, "action": "reject"},
        {"clash_mode": "direct", "action": "route", "outbound": "direct"},
        {"clash_mode": "global", "action": "route", "outbound": "proxy"},
        {"ip_is_private": True, "action": "route", "outbound": "direct"},
        {"rule_set": "geosite-cn", "action": "route", "outbound": "direct"},
        {"rule_set": "geoip-cn", "action": "route", "outbound": "direct"},
    ]
    assert {rule_set["tag"] for rule_set in config["route"]["rule_set"]} == {"geosite-cn", "geoip-cn"}
    assert all(rule_set["http_client"] == "rules-via-proxy" for rule_set in config["route"]["rule_set"])

    rendered = json.dumps(config)
    for forbidden in ("fakeip", "urltest", "block", "ntp", '"type": "mixed"'):
        assert forbidden not in rendered


def test_tun_can_be_disabled_without_falling_back_to_mixed(vless_reality_proxy):
    config = json.loads(build_singbox_config([vless_reality_proxy], tun_enabled=False))

    assert config["inbounds"] == []
    assert not any(inbound["type"] == "mixed" for inbound in config["inbounds"])


    ipv6_literal = {**vless_reality_proxy, "name": "IPv6 literal", "server": "2001:db8::1"}
    ipv6_named = {**vless_reality_proxy, "name": "IPv6 domain", "server": "example.net"}
    duplicate_name = {**vless_reality_proxy}
    config = json.loads(build_singbox_config([vless_reality_proxy, ipv6_literal, ipv6_named, duplicate_name]))

    selector = config["outbounds"][0]
    assert selector["outbounds"] == ["美国节点", "美国节点_1"]
    assert all(outbound.get("server") not in {"2001:db8::1", "example.net"} for outbound in config["outbounds"])


def test_selector_handles_more_than_one_hundred_nodes(vless_reality_proxy):
    proxies = [{**vless_reality_proxy, "name": f"node-{number}", "server": f"198.51.100.{number % 255}"} for number in range(1, 126)]
    config = json.loads(build_singbox_config(proxies))

    assert len(config["outbounds"][0]["outbounds"]) == 125
    assert len({outbound["tag"] for outbound in config["outbounds"]}) == 127


def test_singbox_check_validation(vless_reality_proxy, vmess_ws_proxy, hysteria2_proxy, anytls_proxy, tmp_path):
    executable = Path(os.environ.get("SING_BOX_EXE", r"D:\Program Files\webui.for.singbox\data\sing-box\sing-box.exe"))
    if not executable.exists():
        pytest.skip("sing-box 1.14 executable not found")

    config_file = tmp_path / "test-config.json"
    config_file.write_text(build_singbox_config([vless_reality_proxy, vmess_ws_proxy, hysteria2_proxy, anytls_proxy]), encoding="utf-8")
    result = subprocess.run([str(executable), "check", "-c", str(config_file)], capture_output=True, text=True)

    assert result.returncode == 0, f"sing-box check failed:\n{result.stdout}\n{result.stderr}"
