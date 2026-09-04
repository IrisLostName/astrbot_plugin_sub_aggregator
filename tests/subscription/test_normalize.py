from subagg.subscription.normalize import tag_source_name


def test_source_tag_precedes_emoji_and_node_name():
    assert tag_source_name("🇰🇷 Korea AWS｜薛定谔的三网", "念云") == "[念云]🇰🇷 Korea AWS｜薛定谔的三网"
