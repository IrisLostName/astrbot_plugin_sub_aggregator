from subagg.subscription.output import build_mihomo_yaml, validate_config_references
from subagg.subscription.profile import build_rule_profile


def test_default_profile_uses_one_manual_proxy_group():
    proxy_names = ["[high]node", "[low]node"]
    profile = build_rule_profile(proxy_names)

    assert profile["dns"]["ipv6"] is False
    assert profile["rules"] == ["DST-PORT,3478,REJECT", "RULE-SET,ads,REJECT", "RULE-SET,cn,DIRECT", "MATCH,PROXY"]
    assert profile["proxy-groups"] == [{"name": "PROXY", "type": "select", "proxies": proxy_names}]
    assert set(profile["rule-providers"]) == {"ads", "cn"}
    validate_config_references({**profile, "proxies": [{"name": name} for name in proxy_names]})


def test_profile_output_contains_single_manual_group():
    proxy = {"name": "[source]node", "type": "ss", "server": "example.com", "port": 443, "cipher": "aes-128-gcm", "password": "test"}
    output = build_mihomo_yaml([proxy], build_rule_profile([proxy["name"]]))
    assert "name: PROXY" in output
    assert "type: select" in output
    assert "url-test" not in output
    assert "AUTO" not in output
    assert "FINAL" not in output
    assert "Google" not in output


def test_minimal_profile_remains_available_for_recovery():
    profile = build_rule_profile(["node"], "minimal")
    assert "dns" not in profile
    assert profile["proxy-groups"] == [{"name": "PROXY", "type": "select", "proxies": ["node"]}]
    assert profile["rules"] == ["MATCH,PROXY"]
