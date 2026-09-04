from subagg.services.changes import format_change_message
from subagg.subscription.models import ParsedNode


def node(source: str, name: str) -> ParsedNode:
    return ParsedNode(source=source, name=name, proxy={"name": name})


def test_change_details_only_include_sources_with_notifications_enabled():
    message = format_change_message(
        [node("quiet", "[quiet]hidden"), node("loud", "[loud]shown")],
        [],
        [],
        {"loud"},
    )
    assert "新增 2 个" in message
    assert "[loud]shown" in message
    assert "[quiet]hidden" not in message
