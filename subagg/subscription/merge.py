from __future__ import annotations

from copy import deepcopy
from typing import Iterable

from .models import ParsedNode
from .normalize import fingerprint_proxy, normalize_proxy


def merge_nodes(
    sources: Iterable[tuple[str, list[dict] | list[ParsedNode]]],
    previous: Iterable[ParsedNode] = (),
) -> tuple[list[ParsedNode], list[ParsedNode], list[ParsedNode], list[ParsedNode]]:
    previous_list = list(previous)
    previous_by_name = {(node.source, node.name): node for node in previous_list}
    current: list[ParsedNode] = []
    seen: set[str] = set()
    for source, proxies in sources:
        for index, item in enumerate(proxies, start=1):
            if isinstance(item, ParsedNode):
                raw_proxy = item.proxy
                raw_link = item.raw_link
            else:
                raw_proxy = item
                raw_link = None
            proxy = normalize_proxy(deepcopy(raw_proxy), source, index)
            fingerprint = fingerprint_proxy(proxy)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            current.append(
                ParsedNode(
                    source=source,
                    name=proxy["name"],
                    proxy=proxy,
                    fingerprint=fingerprint,
                    raw_link=raw_link,
                )
            )
    current_by_name = {(node.source, node.name): node for node in current}
    previous_fingerprints = {old.fingerprint for old in previous_list}
    added = [
        node
        for node in current
        if node.fingerprint not in previous_fingerprints
        and (node.source, node.name) not in previous_by_name
    ]
    updated = [
        node
        for key, node in current_by_name.items()
        if key in previous_by_name
        and node.fingerprint != previous_by_name[key].fingerprint
    ]
    removed = [node for key, node in previous_by_name.items() if key not in current_by_name]
    return current, added, updated, removed
