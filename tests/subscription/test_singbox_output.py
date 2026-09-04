"""Tests for sing-box output generation."""

import json
import subprocess
from pathlib import Path

import pytest

from subagg.subscription.singbox import (
    AdapterError,
    build_singbox_config,
    mihomo_to_singbox_outbound,
)


# Desensitized fixtures based on real airport subscriptions


@pytest.fixture
def vless_reality_proxy():
    """VLESS Reality + Vision + packet_encoding (星尘云风格)."""
    return {
        "name": "美国🇺🇸｜DMIT Premium",
        "type": "vless",
        "server": "example.com",
        "port": 8443,
        "uuid": "00000000-0000-0000-0000-000000000000",
        "udp": True,
        "flow": "xtls-rprx-vision",
        "packet-encoding": "xudp",
        "tls": True,
        "skip-cert-verify": False,
        "servername": "apple.com",
        "reality-opts": {
            "public-key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "short-id": "565cbfa64314"
        },
        "client-fingerprint": "chrome"
    }


@pytest.fixture
def vmess_ws_proxy():
    """VMess + WS transport (EasyCloud风格)."""
    return {
        "name": "HKG 01 RFC",
        "type": "vmess",
        "server": "example.com",
        "port": 39551,
        "uuid": "00000000-0000-0000-0000-000000000000",
        "alterId": 0,
        "cipher": "auto",
        "udp": True,
        "network": "ws",
        "ws-opts": {
            "path": "/vmess",
            "headers": {"Host": "example.com"}
        }
    }


@pytest.fixture
def ss_2022_proxy():
    """Shadowsocks 2022 (念云风格)."""
    return {
        "name": "fcc/gd",
        "type": "ss",
        "server": "example.com",
        "port": 32531,
        "cipher": "2022-blake3-aes-256-gcm",
        "password": "base64encodedpassword==",
        "udp": True
    }


@pytest.fixture
def hysteria2_proxy():
    """Hysteria2 (念云韩国节点风格)."""
    return {
        "name": "🇰🇷Korea AWS｜薛定谔的三网",
        "type": "hysteria2",
        "server": "example.com",
        "port": 8443,
        "password": "test-password",
        "sni": "www.amazon.com",
        "skip-cert-verify": True,
        "up": "100",
        "down": "500"
    }


@pytest.fixture
def anytls_proxy():
    """anytls (星尘云日本节点风格)."""
    return {
        "name": "日本🇯🇵｜三网优化 AnyTLS",
        "type": "anytls",
        "server": "example.com",
        "port": 10000,
        "password": "test-password",
        "udp": True,
        "sni": "anytls.example.com"
    }


@pytest.fixture
def trojan_ws_proxy():
    """Trojan + WS transport."""
    return {
        "name": "Trojan WS",
        "type": "trojan",
        "server": "example.com",
        "port": 443,
        "password": "test-password",
        "udp": True,
        "tls": True,
        "servername": "example.com",
        "network": "ws",
        "ws-opts": {
            "path": "/trojan"
        }
    }


def test_vless_reality_conversion(vless_reality_proxy):
    """Test VLESS Reality node conversion with all critical fields."""
    outbound = mihomo_to_singbox_outbound(vless_reality_proxy, "test-tag")

    assert outbound["type"] == "vless"
    assert outbound["tag"] == "test-tag"
    assert outbound["server"] == "example.com"
    assert outbound["server_port"] == 8443
    assert outbound["uuid"] == "00000000-0000-0000-0000-000000000000"
    assert outbound["flow"] == "xtls-rprx-vision"
    assert outbound["packet_encoding"] == "xudp"

    assert "tls" in outbound
    tls = outbound["tls"]
    assert tls["enabled"] is True
    assert tls["server_name"] == "apple.com"
    assert tls["insecure"] is False
    assert tls["utls"]["enabled"] is True
    assert tls["utls"]["fingerprint"] == "chrome"
    assert tls["reality"]["enabled"] is True
    assert tls["reality"]["public_key"] == "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    assert tls["reality"]["short_id"] == "565cbfa64314"


def test_vmess_ws_conversion(vmess_ws_proxy):
    """Test VMess + WS transport conversion."""
    outbound = mihomo_to_singbox_outbound(vmess_ws_proxy, "vmess-tag")

    assert outbound["type"] == "vmess"
    assert outbound["tag"] == "vmess-tag"
    assert outbound["server"] == "example.com"
    assert outbound["server_port"] == 39551
    assert outbound["uuid"] == "00000000-0000-0000-0000-000000000000"
    assert outbound["security"] == "auto"
    assert outbound["alter_id"] == 0

    assert "transport" in outbound
    transport = outbound["transport"]
    assert transport["type"] == "ws"
    assert transport["path"] == "/vmess"
    assert transport["headers"]["Host"] == "example.com"


def test_ss_2022_conversion(ss_2022_proxy):
    """Test Shadowsocks 2022 conversion."""
    outbound = mihomo_to_singbox_outbound(ss_2022_proxy, "ss-tag")

    assert outbound["type"] == "shadowsocks"
    assert outbound["tag"] == "ss-tag"
    assert outbound["server"] == "example.com"
    assert outbound["server_port"] == 32531
    assert outbound["method"] == "2022-blake3-aes-256-gcm"
    assert outbound["password"] == "base64encodedpassword=="


def test_hysteria2_conversion(hysteria2_proxy):
    """Test Hysteria2 conversion with bandwidth limits."""
    outbound = mihomo_to_singbox_outbound(hysteria2_proxy, "hy2-tag")

    assert outbound["type"] == "hysteria2"
    assert outbound["tag"] == "hy2-tag"
    assert outbound["server"] == "example.com"
    assert outbound["server_port"] == 8443
    assert outbound["password"] == "test-password"
    assert outbound["up_mbps"] == 100
    assert outbound["down_mbps"] == 500
    assert outbound["tls"]["server_name"] == "www.amazon.com"
    assert outbound["tls"]["insecure"] is True


def test_anytls_conversion(anytls_proxy):
    """Test anytls → shadowtls conversion."""
    outbound = mihomo_to_singbox_outbound(anytls_proxy, "anytls-tag")

    assert outbound["type"] == "shadowtls"
    assert outbound["tag"] == "anytls-tag"
    assert outbound["server"] == "example.com"
    assert outbound["server_port"] == 10000
    assert outbound["password"] == "test-password"
    assert outbound["tls"]["server_name"] == "anytls.example.com"


def test_trojan_ws_conversion(trojan_ws_proxy):
    """Test Trojan + WS conversion."""
    outbound = mihomo_to_singbox_outbound(trojan_ws_proxy, "trojan-tag")

    assert outbound["type"] == "trojan"
    assert outbound["tag"] == "trojan-tag"
    assert outbound["password"] == "test-password"
    assert "tls" in outbound
    assert "transport" in outbound
    assert outbound["transport"]["type"] == "ws"
    assert outbound["transport"]["path"] == "/trojan"


def test_duplicate_names_unique_tags():
    """Test that duplicate node names generate unique tags."""
    proxies = [
        {"name": "香港节点", "type": "vless", "server": "1.1.1.1", "port": 443, "uuid": "uuid1"},
        {"name": "香港节点", "type": "vless", "server": "2.2.2.2", "port": 443, "uuid": "uuid2"},
        {"name": "香港节点", "type": "vless", "server": "3.3.3.3", "port": 443, "uuid": "uuid3"},
    ]

    config_json = build_singbox_config(proxies, rule_set_source="none")
    config = json.loads(config_json)

    tags = [ob["tag"] for ob in config["outbounds"] if ob["type"] == "vless"]
    assert len(tags) == 3
    assert tags[0] == "香港节点"
    assert tags[1] == "香港节点_1"
    assert tags[2] == "香港节点_2"


def test_unsupported_protocol():
    """Test that unsupported proxy type raises AdapterError."""
    proxy = {"name": "test", "type": "unsupported-protocol", "server": "example.com", "port": 443}

    with pytest.raises(AdapterError) as exc_info:
        mihomo_to_singbox_outbound(proxy, "test-tag")

    assert "Unsupported proxy type: unsupported-protocol" in str(exc_info.value)


def test_build_config_sagernet_ruleset(vless_reality_proxy, vmess_ws_proxy):
    """Test complete config generation with SagerNet rule sets."""
    proxies = [vless_reality_proxy, vmess_ws_proxy]
    config_json = build_singbox_config(proxies, rule_set_source="sagernet")
    config = json.loads(config_json)

    assert "dns" in config
    assert config["dns"]["strategy"] == "prefer_ipv4"
    assert config["dns"]["fakeip"]["enabled"] is True
    assert config["dns"]["fakeip"]["inet4_range"] == "198.18.0.0/15"

    assert len(config["inbounds"]) == 1
    assert config["inbounds"][0]["type"] == "mixed"
    assert config["inbounds"][0]["listen_port"] == 7890

    outbounds = config["outbounds"]
    node_outbounds = [ob for ob in outbounds if ob["type"] in ("vless", "vmess")]
    assert len(node_outbounds) == 2

    proxy_selector = next(ob for ob in outbounds if ob["tag"] == "PROXY")
    assert proxy_selector["type"] == "selector"
    assert "自动选择" in proxy_selector["outbounds"]

    urltest = next(ob for ob in outbounds if ob["tag"] == "自动选择")
    assert urltest["type"] == "urltest"
    assert urltest["url"] == "https://www.gstatic.com/generate_204"

    assert any(ob["tag"] == "DIRECT" for ob in outbounds)
    assert any(ob["tag"] == "REJECT" for ob in outbounds)

    assert "route" in config
    assert config["route"]["final"] == "PROXY"
    assert len(config["route"]["rule_set"]) == 3
    assert any("geosite-cn" in rs["url"] for rs in config["route"]["rule_set"])
    assert any("geoip-cn" in rs["url"] for rs in config["route"]["rule_set"])

    assert "experimental" in config
    assert config["experimental"]["clash_api"]["external_controller"] == "127.0.0.1:9090"

    assert "ntp" in config
    assert config["ntp"]["enabled"] is True
    assert config["ntp"]["server"] == "time.apple.com"


def test_build_config_no_ruleset(vless_reality_proxy):
    """Test config generation with rule_set_source=none."""
    config_json = build_singbox_config([vless_reality_proxy], rule_set_source="none")
    config = json.loads(config_json)

    assert config["route"]["rule_set"] == []
    assert config["route"]["rules"] == []
    assert config["route"]["final"] == "PROXY"
    assert config["dns"]["rules"] == []


def test_build_config_metacubex_ruleset(vless_reality_proxy):
    """Test config generation with MetaCubeX rule sets."""
    config_json = build_singbox_config([vless_reality_proxy], rule_set_source="metacubex")
    config = json.loads(config_json)

    assert len(config["route"]["rule_set"]) == 2
    rule_set_urls = [rs["url"] for rs in config["route"]["rule_set"]]
    assert any("MetaCubeX/meta-rules-dat" in url for url in rule_set_urls)


def test_build_config_custom_ruleset(vless_reality_proxy):
    """Test config generation with custom rule set URLs."""
    custom_urls = {
        "geosite_cn": "https://example.com/geosite-cn.srs",
        "geoip_cn": "https://example.com/geoip-cn.srs"
    }
    config_json = build_singbox_config(
        [vless_reality_proxy],
        rule_set_source="custom",
        custom_rule_set_urls=custom_urls
    )
    config = json.loads(config_json)

    assert len(config["route"]["rule_set"]) == 2
    rule_set_urls = [rs["url"] for rs in config["route"]["rule_set"]]
    assert "https://example.com/geosite-cn.srs" in rule_set_urls
    assert "https://example.com/geoip-cn.srs" in rule_set_urls


@pytest.mark.skipif(
    not Path(r"C:\Program Files\sing-box\sing-box.exe").exists(),
    reason="sing-box.exe not found"
)
def test_singbox_check_validation(vless_reality_proxy, vmess_ws_proxy, tmp_path):
    """Test generated config passes sing-box check command."""
    proxies = [vless_reality_proxy, vmess_ws_proxy]
    config_json = build_singbox_config(proxies, rule_set_source="sagernet")

    config_file = tmp_path / "test-config.json"
    config_file.write_text(config_json, encoding="utf-8")

    result = subprocess.run(
        [r"C:\Program Files\sing-box\sing-box.exe", "check", "-c", str(config_file)],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, f"sing-box check failed:\n{result.stderr}"


def test_node_conservation(
    vless_reality_proxy,
    vmess_ws_proxy,
    ss_2022_proxy,
    hysteria2_proxy,
    anytls_proxy,
    trojan_ws_proxy
):
    """Test that all supported nodes are converted (no silent drops)."""
    proxies = [
        vless_reality_proxy,
        vmess_ws_proxy,
        ss_2022_proxy,
        hysteria2_proxy,
        anytls_proxy,
        trojan_ws_proxy
    ]

    config_json = build_singbox_config(proxies, rule_set_source="none")
    config = json.loads(config_json)

    protocol_outbounds = [
        ob for ob in config["outbounds"]
        if ob["type"] not in ("selector", "urltest", "direct", "block")
    ]

    assert len(protocol_outbounds) == 6, "All nodes should be converted"
