from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..sources.local import LocalSource
from ..sources.remote import RemoteSourceFetcher
from ..state import StateStore
from ..subscription.merge import merge_nodes
from ..subscription.models import ConversionIssue, ParsedNode, SourceResult
from ..subscription.output import build_mihomo_yaml
from ..subscription.parser import parse_source
from ..subscription.profile import build_rule_profile


@dataclass(frozen=True)
class RefreshReport:
    output: str
    nodes: list[ParsedNode]
    added: list[ParsedNode]
    updated: list[ParsedNode]
    removed: list[ParsedNode]
    issues: list[ConversionIssue]
    published: bool


class RefreshService:
    def __init__(self, state: StateStore, *, user_agent: str = "clash-verge", timeout_seconds: int = 20, rule_profile: str = "metacubex"):
        self.state = state
        self.rule_profile = rule_profile
        self.fetcher = RemoteSourceFetcher(timeout_seconds=timeout_seconds, user_agent=user_agent)
        self.lock = asyncio.Lock()

    async def close(self) -> None:
        await self.fetcher.close()

    async def refresh(self, sources: Iterable[dict[str, Any]]) -> RefreshReport:
        async with self.lock:
            results: list[SourceResult] = []
            for raw in sources:
                if not isinstance(raw, dict) or not raw.get("enabled", True):
                    continue
                name = str(raw.get("name") or "source").strip() or "source"
                try:
                    if self._is_local(raw):
                        if self._is_local_file(raw):
                            result = parse_source(Path(str(raw.get("file_path"))).read_bytes(), name)
                        else:
                            result = LocalSource(name, str(raw.get("content") or raw.get("yaml") or "")).parse()
                    else:
                        response = await self.fetcher.fetch(str(raw.get("url") or ""), user_agent=str(raw.get("user_agent") or ""))
                        result = parse_source(response.text, name)
                except Exception as exc:
                    self._append_log("error", "source fetch or parse failed", source=name, error=type(exc).__name__)
                    result = SourceResult(name, kind=parse_source("", name).kind, issues=[ConversionIssue(name, "fetch", type(exc).__name__)])
                results.append(result)
            if not results:
                raise RuntimeError("没有启用的订阅源")
            issues = [issue for result in results for issue in result.issues]
            source_nodes = [(result.source, [node.proxy for node in result.nodes]) for result in results if result.nodes]
            current, added, updated, removed = merge_nodes(source_nodes, self.state.load_nodes())
            if not current:
                self._append_log("error", "refresh produced no usable nodes", issue_count=len(issues))
                raise RuntimeError("没有解析到可用节点")
            output = build_mihomo_yaml(
                [node.proxy for node in current],
                build_rule_profile([node.name for node in current], self.rule_profile),
            )
            published = not issues
            if published:
                self.state.save_success(output, current, source_count=len(results), issue_count=len(issues))
                self._append_log("info", "refresh published", node_count=len(current), source_count=len(results))
            else:
                self._append_log("warning", "refresh kept last success", node_count=len(current), issue_count=len(issues))
                output = self.state.load_output()
            return RefreshReport(
                output=output,
                nodes=current,
                added=added,
                updated=updated,
                removed=removed,
                issues=issues,
                published=published,
            )

    def _append_log(self, level: str, message: str, **details: object) -> None:
        writer = getattr(self.state, "append_log", None)
        if callable(writer):
            writer(level, message, **details)
            return
        path = self.state.root / "subagg.log"
        detail_text = " ".join(f"{key}={value}" for key, value in details.items())
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{level}] {message} {detail_text}\n")

    @staticmethod
    def _is_local(source: dict[str, Any]) -> bool:
        return str(source.get("source_type") or "remote").lower() in {"local", "yaml", "upload", "local_file"}

    @staticmethod
    def _is_local_file(source: dict[str, Any]) -> bool:
        return str(source.get("source_type") or "").lower() == "local_file"
