from __future__ import annotations

from ..subscription.models import ParsedNode


def format_change_message(
    added: list[ParsedNode],
    updated: list[ParsedNode],
    removed: list[ParsedNode],
    detailed_sources: set[str],
    *,
    max_names: int = 50,
) -> str:
    if not added and not updated and not removed:
        return ""
    sections = [
        f"订阅节点有变化：新增 {len(added)} 个，更新 {len(updated)} 个，移除 {len(removed)} 个。"
    ]
    remaining = max(0, max_names)
    for label, nodes in (("新增", added), ("更新", updated), ("移除", removed)):
        if remaining <= 0:
            break
        visible = [node for node in nodes if node.source in detailed_sources][:remaining]
        if not visible:
            continue
        remaining -= len(visible)
        sections.append("\n".join([f"{label}：", *(node.name for node in visible)]))
    return "\n\n".join(sections)
