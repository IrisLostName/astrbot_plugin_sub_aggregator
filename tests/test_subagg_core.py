import base64

from subagg_core import decode_subscription, merge_nodes, parse_nodes, sanitize_clash_proxy, tag_node_name


def test_decode_base64_subscription():
    raw = "ss://abc#NodeA\nvmess://def"
    encoded = base64.b64encode(raw.encode()).decode()

    assert decode_subscription(encoded) == raw


def test_merge_preserves_source_order_and_deduplicates():
    result = merge_nodes(
        [
            ("a", "ss://one#A\nss://two#B"),
            ("b", "ss://two#B\nss://three#C"),
        ],
        [],
        deduplicate=True,
    )

    assert [node.name for node in result.nodes] == ["[a]A", "[a]B", "[b]B", "[b]C"]
    decoded = base64.b64decode(result.output_text).decode()
    assert "ss://one#%5Ba%5DA" in decoded
    assert "ss://three#%5Bb%5DC" in decoded


def test_merge_clash_yaml_subscription():
    yaml_text = (
        "proxies:\n"
        "  - {name: A, type: ss, server: example.com, port: 443, cipher: aes-128-gcm, password: p}\n"
        "proxy-groups: []\n"
        "rules: []\n"
    )

    result = merge_nodes([("airport", yaml_text)], [], deduplicate=True, output_format="auto")

    assert result.output_format == "clash_yaml"
    assert [node.name for node in result.nodes] == ["[airport]A"]
    assert "proxies:" in result.output_text
    assert "🚀 节点选择" in result.output_text


def test_extract_plain_links_from_downloaded_text_file():
    text = (
        "Quantum-Air.xyz\n"
        "- hysteria2://password@example.com:443?insecure=1#HY2Node\n"
        "1. vless://uuid@example.org:443?security=tls&type=ws#VLESSNode\n"
    )

    nodes = parse_nodes(text, "quantum")

    assert [node.name for node in nodes] == ["HY2Node", "VLESSNode"]
    assert nodes[0].raw.startswith("hysteria2://")
    assert nodes[1].raw.startswith("vless://")


def test_tag_node_name_after_emoji_prefix():
    assert tag_node_name("🇭🇰 Hong Kong 01", "机场A") == "🇭🇰[机场A] Hong Kong 01"
    assert tag_node_name("Node 01", "机场A") == "[机场A]Node 01"


def test_v2ray_export_for_plain_links():
    result = merge_nodes([("airport", "vless://uuid@example.com:443#Node")], [], output_format="base64")

    assert result.v2ray_base64
    decoded = base64.b64decode(result.v2ray_base64).decode()
    assert "vless://uuid@example.com:443#%5Bairport%5DNode" in decoded


def test_rule_profile_none_uses_global_mode_without_rules():
    yaml_text = (
        "proxies:\n"
        "  - {name: A, type: ss, server: example.com, port: 443, cipher: aes-128-gcm, password: p}\n"
    )

    result = merge_nodes([("airport", yaml_text)], [], output_format="clash_yaml", rule_profile="none")

    assert "global" in result.output_text
    assert "rules:" not in result.output_text


def test_default_rule_profile_uses_remote_rule_providers():
    yaml_text = (
        "proxies:\n"
        "  - {name: A, type: ss, server: example.com, port: 443, cipher: aes-128-gcm, password: p}\n"
    )

    result = merge_nodes([("airport", yaml_text)], [], output_format="clash_yaml")

    assert "rule-providers:" in result.output_text
    assert "RULE-SET,microsoft,Ⓜ️ 微软服务" in result.output_text
    assert "RULE-SET,openai,🤖 OpenAI" in result.output_text
    assert "RULE-SET,github,🛠️ 开发平台" in result.output_text


def test_clash_reality_short_id_is_sanitized():
    proxy = {
        "name": "A",
        "type": "vless",
        "reality-opts": {"public-key": "pk", "short-id": 12345},
        "xhttp-opts": {
            "download-settings": {
                "reality-opts": {"public-key": "nested-pk", "short-id": "not-a-hex-value"}
            }
        },
        "grpc-opts": {"reality-opts": {"public-key": "grpc-pk", "short-id": None}},
    }

    sanitize_clash_proxy(proxy)

    assert proxy["reality-opts"]["short-id"] == "012345"
    assert isinstance(proxy["reality-opts"]["short-id"], str)
    assert "short-id" not in proxy["xhttp-opts"]["download-settings"]["reality-opts"]
    assert "short-id" not in proxy["grpc-opts"]["reality-opts"]
