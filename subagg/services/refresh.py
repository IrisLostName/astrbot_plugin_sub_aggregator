from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..sources.remote import RemoteFetchError, RemoteSourceFetcher
from ..state import StateStore
from ..subscription.merge import merge_nodes
from ..subscription.models import ConversionIssue, ParsedNode, SourceResult
from ..subscription.output import build_mihomo_yaml
from ..subscription.parser import parse_source
from ..subscription.profile import build_rule_profile
from ..subscription.singbox import build_singbox_config


@dataclass(frozen=True)
class RefreshReport:
    output: str
    singbox_output: str
    node_list_output: str
    nodes: list[ParsedNode]
    added: list[ParsedNode]
    updated: list[ParsedNode]
    removed: list[ParsedNode]
    issues: list[ConversionIssue]
    output_file: str
    singbox_output_file: str
    node_list_output_file: str
    published: bool


class RefreshService:
    def __init__(
        self,
        state: StateStore,
        *,
        user_agent: str = "clash-verge",
        timeout_seconds: int = 20,
        rule_profile: str = "metacubex",
        tun_enabled: bool = True,
        source_base_dir: str | os.PathLike[str] | None = None,
    ):
        self.state = state
        self.rule_profile = rule_profile
        self.tun_enabled = tun_enabled
        self.source_base_dir = Path(source_base_dir) if source_base_dir else Path.cwd()
        self.fetcher = RemoteSourceFetcher(timeout_seconds=timeout_seconds, user_agent=user_agent)
        self.lock = asyncio.Lock()

    async def close(self) -> None:
        await self.fetcher.close()

    async def refresh(self, sources: Iterable[dict[str, Any]]) -> RefreshReport:
        async with self.lock:
            results: list[SourceResult] = []
            node_list_links: list[str] = []
            seen_node_list_links: set[str] = set()
            for raw in sources:
                if not isinstance(raw, dict) or not raw.get("enabled", True):
                    continue
                name = str(raw.get("name") or "source").strip() or "source"
                filter_invalid_nodes = bool(raw.get("filter_invalid_nodes", False))
                try:
                    if self._is_local(raw):
                        file_path = self._local_file_path(raw)
                        if file_path is not None:
                            result = parse_source(
                                file_path.read_bytes(),
                                name,
                                filter_invalid_nodes=filter_invalid_nodes,
                            )
                        else:
                            result = parse_source(
                                str(raw.get("content") or raw.get("yaml") or ""),
                                name,
                                filter_invalid_nodes=filter_invalid_nodes,
                            )
                    else:
                        response = await self.fetcher.fetch(
                            str(raw.get("url") or ""),
                            user_agent=str(raw.get("user_agent") or ""),
                        )
                        result = parse_source(
                            response.text,
                            name,
                            filter_invalid_nodes=filter_invalid_nodes,
                        )
                except RemoteFetchError as exc:
                    self._append_log("error", "source fetch failed", source=name, status=exc.status, url=exc.url)
                    result = SourceResult(
                        name,
                        kind=parse_source("", name).kind,
                        issues=[ConversionIssue(name, "fetch", str(exc))],
                    )
                except Exception as exc:
                    self._append_log("error", "source fetch or parse failed", source=name, error=type(exc).__name__)
                    result = SourceResult(
                        name,
                        kind=parse_source("", name).kind,
                        issues=[ConversionIssue(name, "fetch", type(exc).__name__)],
                    )

                result = self._apply_name_filters(result, raw)
                if raw.get("node_list_output"):
                    for node in result.nodes:
                        if node.raw_link and node.raw_link not in seen_node_list_links:
                            seen_node_list_links.add(node.raw_link)
                            node_list_links.append(node.raw_link)
                results.append(result)

            if not results:
                raise RuntimeError("没有启用的订阅源")
            issues = [issue for result in results for issue in result.issues]
            source_nodes = [
                (result.source, result.nodes)
                for result in results
                if result.nodes
            ]
            current, added, updated, removed = merge_nodes(source_nodes, self.state.load_nodes())
            if not current:
                self._append_log("error", "refresh produced no usable nodes", issue_count=len(issues))
                raise RuntimeError("没有解析到可用节点")

            mihomo_output = build_mihomo_yaml(
                [node.proxy for node in current],
                build_rule_profile([node.name for node in current], self.rule_profile),
            )
            singbox_output = build_singbox_config(
                [node.proxy for node in current],
                tun_enabled=self.tun_enabled,
            )
            node_list_output = "\n".join(node_list_links)
            if node_list_output:
                node_list_output += "\n"

            published = not issues
            if published:
                self.state.save_success(
                    mihomo_output,
                    singbox_output,
                    current,
                    source_count=len(results),
                    issue_count=len(issues),
                    node_list_output=node_list_output,
                )
                self._append_log(
                    "info",
                    "refresh published",
                    node_count=len(current),
                    source_count=len(results),
                    node_list_count=len(node_list_links),
                )
            else:
                self._append_log("warning", "refresh kept last success", node_count=len(current), issue_count=len(issues))
                mihomo_output = self.state.load_output()
                singbox_output = self.state.load_singbox_output()
                node_list_output = self.state.load_node_list_output()

            return RefreshReport(
                output=mihomo_output,
                singbox_output=singbox_output,
                node_list_output=node_list_output,
                nodes=current,
                added=added,
                updated=updated,
                removed=removed,
                issues=issues,
                output_file=str(self.state.output_path),
                singbox_output_file=str(self.state.singbox_output_path),
                node_list_output_file=str(self.state.node_list_output_path),
                published=published,
            )

    @staticmethod
    def _apply_name_filters(result: SourceResult, source: dict[str, Any]) -> SourceResult:
        include_text = str(source.get("include_regex") or "").strip()
        exclude_text = str(source.get("exclude_regex") or "").strip()
        include_pattern = None
        exclude_pattern = None
        if include_text:
            try:
                include_pattern = re.compile(include_text)
            except re.error as exc:
                result.issues.append(
                    ConversionIssue(result.source, "filter", f"包含节点正则表达式非法: {exc}")
                )
        if exclude_text:
            try:
                exclude_pattern = re.compile(exclude_text)
            except re.error as exc:
                result.issues.append(
                    ConversionIssue(result.source, "filter", f"排除节点正则表达式非法: {exc}")
                )
        if include_pattern is None and exclude_pattern is None:
            return result
        result.nodes = [
            node
            for node in result.nodes
            if not (exclude_pattern and exclude_pattern.search(node.name))
            and not (include_pattern and not include_pattern.search(node.name))
        ]
        return result

    def _append_log(self, level: str, message: str, **details: object) -> None:
        writer = getattr(self.state, "append_log", None)
        if callable(writer):
            writer(level, message, **details)
            return
        path = self.state.root / "subagg.log"
        detail_text = " ".join(f"{key}={value}" for key, value in details.items())
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{level}] {message} {detail_text}\n")

    def _local_file_path(self, source: dict[str, Any]) -> Path | None:
        value = str(source.get("file_path") or "").strip()
        if not value:
            return None
        path = Path(value).expanduser()
        return path if path.is_absolute() else self.source_base_dir / path

    @staticmethod
    def _is_local(source: dict[str, Any]) -> bool:
        return str(source.get("source_type") or "remote").lower() in {"local", "yaml", "upload", "local_file"}

    @staticmethod
    def _is_local_file(source: dict[str, Any]) -> bool:
        return str(source.get("source_type") or "").lower() == "local_file"
