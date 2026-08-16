import base64

from src.subagg_core import (
    NodeInfo,
    build_clash_yaml,
    decode_subscription,
    merge_nodes,
    parse_nodes,
    sanitize_clash_proxy,
    tag_node_name,
    summarize_changes,
)


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


def test_clash_yaml_keeps_provider_proxy_types():
    yaml_text = (
        "proxies:\n"
        "  - {name: A, type: anytls, server: example.com, port: 443, password: p}\n"
        "  - {name: B, type: vless, server: example.org, port: 443, uuid: u}\n"
    )

    result = merge_nodes([("airport", yaml_text)], [], output_format="clash_yaml")

    assert "[airport]A" in result.output_text
    assert "[airport]B" in result.output_text


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
        "reality-opts": {"public-key": "pk", "short-id": "61a09340"},
        "xhttp-opts": {
            "download-settings": {
                "reality-opts": {"public-key": "nested-pk", "short-id": "not-a-hex-value"}
            }
        },
        "grpc-opts": {"reality-opts": {"public-key": "grpc-pk", "short-id": None}},
    }

    sanitize_clash_proxy(proxy)

    assert proxy["reality-opts"]["short-id"] == "61a09340"
    assert isinstance(proxy["reality-opts"]["short-id"], str)
    assert "short-id" not in proxy["xhttp-opts"]["download-settings"]["reality-opts"]
    assert "short-id" not in proxy["grpc-opts"]["reality-opts"]


def test_clash_yaml_quotes_reality_short_id():
    output = build_clash_yaml(
        [
            {
                "name": "A",
                "type": "vless",
                "server": "example.com",
                "port": 443,
                "uuid": "00000000-0000-0000-0000-000000000000",
                "tls": True,
                "reality-opts": {"public-key": "pk", "short-id": "0628"},
            }
        ]
    )

    assert 'short-id: "0628"' in output

def test_metacubex_rule_profile_uses_mrs_rule_providers():
    yaml_text = (
        "proxies:\n"
        "  - {name: A, type: ss, server: example.com, port: 443, cipher: aes-128-gcm, password: p}\n"
    )

    result = merge_nodes([("airport", yaml_text)], [], output_format="clash_yaml", rule_profile="mihomo_metacubex")

    assert 'format: "mrs"' in result.output_text
    assert "MetaCubeX/meta-rules-dat/meta/geo/geosite/openai.mrs" in result.output_text
    assert "MetaCubeX/meta-rules-dat/meta/geo/geoip/cn.mrs" in result.output_text
    assert "RULE-SET,microsoft,Ⓜ️ 微软服务" in result.output_text
    assert "RULE-SET,cn,🎯 全球直连" in result.output_text
    assert "MATCH,🐟 漏网之鱼" in result.output_text


def test_dustinwin_rule_profile_uses_mrs_rule_providers():
    yaml_text = (
        "proxies:\n"
        "  - {name: A, type: ss, server: example.com, port: 443, cipher: aes-128-gcm, password: p}\n"
    )

    result = merge_nodes([("airport", yaml_text)], [], output_format="clash_yaml", rule_profile="mihomo_dustinwin")

    assert 'format: "mrs"' in result.output_text
    assert "DustinWin/ruleset_geodata/releases/download/mihomo-ruleset/ai.mrs" in result.output_text
    assert "DustinWin/ruleset_geodata/releases/download/mihomo-ruleset/cnip.mrs" in result.output_text
    assert "RULE-SET,microsoft,Ⓜ️ 微软服务" in result.output_text
    assert "RULE-SET,cnip,🎯 全球直连" in result.output_text
    assert "MATCH,🐟 漏网之鱼" in result.output_text




def test_explicit_clash_yaml_still_keeps_remarks_for_clash_sources():
    yaml_text = (
        "proxies:\n"
        "  - {name: A, type: ss, server: example.com, port: 443, cipher: aes-128-gcm, password: p}\n"
    )

    result = merge_nodes([("airport", yaml_text)], [], output_format="clash_yaml")

    assert result.output_format == "clash_yaml"
    assert "[airport]A" in result.output_text


def test_updated_and_removed_changes_keep_explicit_names():
    previous = merge_nodes(
        [("airport", "vless://uuid@example.com:443#OldNode")],
        [],
        output_format="plain",
    )
    current = merge_nodes(
        [("airport", "vless://uuid@example.com:8443#OldNode")],
        [node.fingerprint for node in previous.nodes],
        previous_nodes=previous.nodes,
        output_format="plain",
    )

    assert [node.name for node in current.updated] == ["[airport]OldNode"]
    assert not current.added
    assert not current.removed

    removed = merge_nodes(
        [],
        [node.fingerprint for node in previous.nodes],
        previous_nodes=previous.nodes,
        output_format="plain",
    )
    assert [node.name for node in removed.removed] == ["[airport]OldNode"]

    message = summarize_changes(
        removed.added,
        removed.removed,
        updated=current.updated,
        max_names=50,
    )
    assert "更新：" in message
    assert "移除：" in message
    assert "[airport]OldNode" in message


def test_change_summary_lists_each_item_on_own_line_and_limits_total():
    added = [
        type("Node", (), {"name": f"[airport]Node{i}"})()
        for i in range(60)
    ]
    message = summarize_changes(added, [], max_names=50)
    assert "新增：\n[airport]Node0" in message
    assert "[airport]Node49" in message
    assert "[airport]Node50" not in message
    assert "另有 10 个变化未展开。" in message


def test_change_summary_shows_at_most_50_nodes_across_all_change_types():
    added = [type("Node", (), {"name": f"新增{i}"})() for i in range(40)]
    removed = [type("Node", (), {"name": f"移除{i}"})() for i in range(24)]
    message = summarize_changes(added, removed, max_names=50)
    assert "新增39" in message
    assert "移除9" in message
    assert "移除10" not in message
    assert "另有 14 个变化未展开。" in message


def test_change_summary_hard_caps_display_at_50():
    added = [type("Node", (), {"name": f"节点{i}"})() for i in range(60)]
    message = summarize_changes(added, [], max_names=100)
    assert "节点49" in message
    assert "节点50" not in message
    assert "另有 10 个变化未展开。" in message


def test_removed_fingerprint_name_is_never_shown():
    fingerprint = "233934cc635d00112233445566778899"
    previous = NodeInfo(
        raw="vless://uuid@example.com:443#ReadableNode",
        name=fingerprint[:12],
        fingerprint=fingerprint,
        source="airport",
    )
    result = merge_nodes([], [fingerprint], previous_nodes=[previous], output_format="plain")
    assert result.removed[0].name == "[airport]ReadableNode"
    assert fingerprint[:12] not in summarize_changes([], result.removed)
