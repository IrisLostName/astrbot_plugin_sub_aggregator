from subagg.subscription.output import build_mihomo_yaml, validate_config_references
from subagg.subscription.profile import RULESETS, build_rule_profile


def test_metacubex_profile_has_dns_and_mrs_rule_providers():
    profile = build_rule_profile(["[source]node"])
    assert profile["dns"]["respect-rules"] is True
    assert profile["dns"]["proxy-server-nameserver"]
    assert "dns.alidns.com" in profile["dns"]["nameserver"][0]
    assert "nameserver-policy" not in profile["dns"]
    assert profile["rule-providers"]["ads"]["format"] == "mrs"
    assert profile["rule-providers"]["cn"]["behavior"] == "domain"
    assert "RULE-SET,ads,REJECT" in profile["rules"]
    assert "RULE-SET,cn,DIRECT" in profile["rules"]
    groups = {group["name"]: group for group in profile["proxy-groups"]}
    assert "FINAL" not in groups["PROXY"]["proxies"]
    validate_config_references({**profile, "proxies": [{"name": "[source]node"}]})


def test_profile_output_contains_dns_groups_rules_and_providers():
    proxy = {"name": "[source]node", "type": "ss", "server": "example.com", "port": 443, "cipher": "aes-128-gcm", "password": "test"}
    output = build_mihomo_yaml([proxy], build_rule_profile([proxy["name"]]))
    assert "rule-providers:" in output
    assert "proxy-server-nameserver:" in output
    assert "dns.alidns.com" in output
    assert "category-ads-all.mrs" in output


def test_minimal_profile_remains_available_for_recovery():
    profile = build_rule_profile(["node"], "minimal")
    assert "dns" not in profile
    assert profile["rules"] == ["MATCH,PROXY"]
