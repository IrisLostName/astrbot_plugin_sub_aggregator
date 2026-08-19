from subagg.subscription.merge import merge_nodes
from subagg.subscription.output import build_mihomo_yaml


def test_merge_tags_sources_and_deduplicates_by_connection():
    proxy = {"name": "🇭🇰 Hong Kong", "type": "ss", "server": "example.com", "port": 443, "cipher": "aes-128-gcm", "password": "test"}
    current, added, updated, removed = merge_nodes([("airport-a", [proxy]), ("airport-b", [proxy])])
    assert len(current) == 1
    assert current[0].name.startswith("[airport-a]🇭🇰")
    assert len(added) == 1
    assert not updated
    assert not removed


def test_output_builds_referentially_complete_yaml():
    proxy = {"name": "[a]node", "type": "ss", "server": "example.com", "port": 443, "cipher": "aes-128-gcm", "password": "test"}
    output = build_mihomo_yaml([proxy])
    assert "proxies:" in output


def test_output_quotes_reality_short_id_to_preserve_leading_zeroes():
    proxy = {
        "name": "[a]reality",
        "type": "vless",
        "server": "example.com",
        "port": 443,
        "uuid": "00000000-0000-0000-0000-000000000000",
        "tls": True,
        "reality-opts": {"public-key": "public", "short-id": "0e11"},
    }
    output = build_mihomo_yaml([proxy])
    assert 'short-id: "0e11"' in output
