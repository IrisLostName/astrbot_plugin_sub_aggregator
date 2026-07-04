from __future__ import annotations

import asyncio
import json
import secrets
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import aiohttp
from aiohttp import web
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register

try:
    from .subagg_core import decode_subscription, merge_nodes, summarize_changes
except ImportError:
    from subagg_core import decode_subscription, merge_nodes, summarize_changes


PLUGIN_NAME = "astrbot_plugin_sub_aggregator"
KV_LAST_FINGERPRINTS = "last_node_fingerprints"
KV_LAST_OUTPUT = "last_subscription_output"
KV_LAST_OUTPUT_FORMAT = "last_subscription_output_format"
KV_LAST_OUTPUT_FILE = "last_subscription_output_file"
KV_LAST_V2RAY_OUTPUT = "last_v2ray_subscription_output"
KV_LAST_V2RAY_FILE = "last_v2ray_subscription_file"
KV_LAST_NODE_COUNT = "last_node_count"
KV_LAST_REFRESH_AT = "last_refresh_at"

UA_PRESETS = {
    "mihomo": "mihomo/1.19.27",
    "clashmeta": "ClashMeta",
    "clash-meta": "ClashMeta",
    "clash": "ClashforWindows/0.20.39",
    "clashforwindows": "ClashforWindows/0.20.39",
    "v2ray": "v2rayN/6.60",
    "flclash": "FLClash",
    "karing": "Karing/1.2.21.2406 platform/windows",
    "custom": "",
}


@dataclass(frozen=True)
class FetchResult:
    name: str
    text: str


@filter.command_group("subagg")
def subagg():
    pass


@register(
    PLUGIN_NAME,
    "chenh",
    "聚合多个机场订阅 URL，并通过固定短路径输出一个总订阅链接。",
    "0.1.0",
)
class SubAggregatorPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._session: aiohttp.ClientSession | None = None
        self._refresh_task: asyncio.Task | None = None
        self._web_runner: web.AppRunner | None = None
        self._web_site: web.TCPSite | None = None
        self._refresh_lock = asyncio.Lock()
        self._http_last_error = ""
        self._ensure_token()

    async def terminate(self):
        if self._refresh_task:
            self._refresh_task.cancel()
            await asyncio.gather(self._refresh_task, return_exceptions=True)
        if self._web_runner:
            await self._web_runner.cleanup()
        if self._session:
            await self._session.close()

    @filter.on_astrbot_loaded()
    async def on_astrbot_loaded(self):
        await self._try_ensure_http_server()
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        if self.config.get("startup_push", True):
            await self.refresh_and_notify(reason="AstrBot 已启动", send_url=True)

    @subagg.command("help")
    async def help_cmd(self, event: AstrMessageEvent):
        yield event.plain_result(
            "订阅聚合指令：\n"
            "/subagg bind - 把当前会话设为通知接收处\n"
            "/subagg url - 查看聚合订阅链接\n"
            "/subagg status - 查看 HTTP 出口状态\n"
            "/subagg refresh - 立即拉取并聚合\n"
            "/subagg list - 查看已配置机场\n"
            "/subagg add 名称 URL - 添加机场订阅\n"
            "/subagg remove 名称 - 删除机场订阅"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @subagg.command("bind")
    async def bind_cmd(self, event: AstrMessageEvent):
        targets = list(self.config.get("notify_targets", []))
        if event.unified_msg_origin not in targets:
            targets.append(event.unified_msg_origin)
            self.config["notify_targets"] = targets
            self.config.save_config()
        yield event.plain_result("已把当前会话设为订阅聚合通知接收处。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @subagg.command("url")
    async def url_cmd(self, event: AstrMessageEvent):
        await self._try_ensure_http_server()
        yield event.plain_result(self._public_subscription_url())

    @filter.permission_type(filter.PermissionType.ADMIN)
    @subagg.command("status")
    async def status_cmd(self, event: AstrMessageEvent):
        await self._try_ensure_http_server()
        last_refresh_at = await self.get_kv_data(KV_LAST_REFRESH_AT, "从未刷新")
        output_format = await self.get_kv_data(KV_LAST_OUTPUT_FORMAT, "未知")
        node_count = await self.get_kv_data(KV_LAST_NODE_COUNT, 0)
        http_state = "已启用" if self.config.get("http_enable", True) else "未启用"
        runner_state = "已启动" if self._web_runner else "未启动"
        http_error = self._http_last_error or "无"
        yield event.plain_result(
            "订阅聚合状态：\n"
            f"HTTP 出口：{http_state}，服务：{runner_state}\n"
            f"HTTP 错误：{http_error}\n"
            f"监听：{self.config.get('http_host', '0.0.0.0')}:{self.config.get('http_port', 8077)}\n"
            f"健康检查：{self._health_url()}\n"
            f"订阅链接：{self._public_subscription_url()}\n"
            f"v2ray 订阅：{self._public_v2ray_url()}\n"
            f"最近刷新：{last_refresh_at}\n"
            f"节点数量：{node_count}\n"
            f"输出格式：{output_format}\n"
            f"本地文件：{await self.get_kv_data(KV_LAST_OUTPUT_FILE, '尚未生成')}\n"
            f"v2ray 文件：{await self.get_kv_data(KV_LAST_V2RAY_FILE, '尚未生成')}\n"
            f"全局 UA：{self._resolve_user_agent()}"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @subagg.command("list")
    async def list_cmd(self, event: AstrMessageEvent):
        sources = self._sources()
        if not sources:
            yield event.plain_result("还没有配置机场订阅 URL。")
            return
        lines = ["已配置机场："]
        for index, item in enumerate(sources, start=1):
            state = "启用" if item.get("enabled", True) else "停用"
            lines.append(f"{index}. {item.get('name', '未命名')} [{state}]")
        yield event.plain_result("\n".join(lines))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @subagg.command("add")
    async def add_cmd(self, event: AstrMessageEvent, name: str, url: str):
        sources = list(self.config.get("subscription_sources", []))
        sources.append(
            {
                "__template_key": "source",
                "name": name,
                "url": url,
                "priority": 100,
                "enabled": True,
            }
        )
        self.config["subscription_sources"] = sources
        self.config.save_config()
        yield event.plain_result(f"已添加机场订阅：{name}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @subagg.command("remove")
    async def remove_cmd(self, event: AstrMessageEvent, name: str):
        before = list(self.config.get("subscription_sources", []))
        after = [item for item in before if item.get("name") != name]
        self.config["subscription_sources"] = after
        self.config.save_config()
        yield event.plain_result(f"已删除 {len(before) - len(after)} 条名称为 {name} 的订阅。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @subagg.command("refresh")
    async def refresh_cmd(self, event: AstrMessageEvent):
        await self._try_ensure_http_server()
        result = await self.refresh_and_notify(reason="手动刷新", send_url=True)
        yield event.plain_result(result)

    async def refresh_and_notify(self, *, reason: str, send_url: bool = False) -> str:
        await self._try_ensure_http_server()
        async with self._refresh_lock:
            try:
                result = await self._refresh_once()
            except Exception as exc:
                message = f"订阅聚合失败（{reason}）：{exc}"
                logger.exception(message)
                if self.config.get("notify_on_error", True):
                    await self._broadcast(message)
                return message

        if send_url:
            await self._broadcast(
                f"{reason}完成：{len(result['nodes'])} 个节点，输出格式：{result['output_format']}。\n"
                f"本地文件：{result['output_file']}\n"
                f"{self._public_subscription_url()}"
            )

        change_message = result.get("change_message") or ""
        if change_message and self.config.get("notify_on_node_change", True):
            await self._broadcast(change_message)

        return (
            f"{reason}完成：{len(result['nodes'])} 个节点，"
            f"{len(result['failures'])} 个机场失败，输出格式：{result['output_format']}。\n"
            f"本地文件：{result['output_file']}"
        )

    async def _refresh_once(self) -> dict[str, Any]:
        sources = self._sources()
        if not sources:
            raise RuntimeError("没有启用的机场订阅 URL")

        fetched: list[FetchResult] = []
        failures: list[str] = []
        for source in sources:
            name = str(source.get("name") or "未命名")
            try:
                user_agent = self._resolve_user_agent(str(source.get("user_agent") or ""))
                logger.info("拉取订阅：%s，User-Agent：%s", name, user_agent)
                raw = await self._fetch_text(str(source["url"]), user_agent=user_agent)
                fetched.append(FetchResult(name=name, text=decode_subscription(raw)))
            except Exception as exc:
                failures.append(f"{name}: {exc}")
                logger.exception("拉取订阅失败：%s", name)

        fetched.extend(self._manual_node_sources())

        if not fetched:
            message = "没有成功加载任何订阅或手动节点"
            if failures:
                message += "：" + "；".join(failures)
            raise RuntimeError(message)

        previous = await self.get_kv_data(KV_LAST_FINGERPRINTS, [])
        merge = merge_nodes(
            [(item.name, item.text) for item in fetched],
            previous,
            deduplicate=bool(self.config.get("deduplicate_nodes", True)),
            output_base64=bool(self.config.get("output_base64", True)),
            output_format=str(self.config.get("output_format") or "auto"),
            rule_profile=str(self.config.get("rule_profile") or "mihomo_ruleset"),
        )
        if not merge.nodes:
            raise RuntimeError("订阅拉取成功，但没有解析到支持的节点。请确认订阅不是页面、过期提示或需要特殊 UA。")

        refreshed_at = datetime.now().isoformat(timespec="seconds")
        output_file = self._save_output_files(
            merge.output_text,
            output_format=merge.output_format,
            v2ray_base64=merge.v2ray_base64,
            node_count=len(merge.nodes),
            refreshed_at=refreshed_at,
        )

        await self.put_kv_data(KV_LAST_FINGERPRINTS, [node.fingerprint for node in merge.nodes])
        await self.put_kv_data(KV_LAST_OUTPUT, merge.output_text)
        await self.put_kv_data(KV_LAST_OUTPUT_FORMAT, merge.output_format)
        await self.put_kv_data(KV_LAST_OUTPUT_FILE, output_file)
        await self.put_kv_data(KV_LAST_V2RAY_OUTPUT, merge.v2ray_base64)
        await self.put_kv_data(KV_LAST_V2RAY_FILE, self._v2ray_output_file_path())
        await self.put_kv_data(KV_LAST_NODE_COUNT, len(merge.nodes))
        await self.put_kv_data(KV_LAST_REFRESH_AT, refreshed_at)

        if failures and self.config.get("notify_on_error", True):
            await self._broadcast("部分订阅拉取失败：\n" + "\n".join(failures))

        change_message = summarize_changes(
            merge.added,
            merge.removed,
            max_names=int(self.config.get("max_change_names", 8)),
        )
        return {
            "nodes": merge.nodes,
            "failures": failures,
            "change_message": change_message,
            "output_format": merge.output_format,
            "output_file": output_file,
        }

    async def _fetch_text(self, url: str, *, user_agent: str) -> str:
        session = await self._client()
        timeout = aiohttp.ClientTimeout(total=int(self.config.get("request_timeout_seconds", 20)))
        headers = {"User-Agent": user_agent}
        async with session.get(url, timeout=timeout, headers=headers) as response:
            response.raise_for_status()
            return await response.text(errors="replace")

    async def _refresh_loop(self):
        while True:
            minutes = max(1, int(self.config.get("update_interval_minutes", 180)))
            await asyncio.sleep(minutes * 60)
            await self.refresh_and_notify(reason="定时刷新")

    async def _client(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _ensure_http_server(self):
        if not self.config.get("http_enable", True):
            self._http_last_error = "后台配置 http_enable=false"
            return
        if self._web_runner:
            return
        app = web.Application()
        app.router.add_get(self._health_path(), self._handle_health)
        app.router.add_get(self._v2ray_path(), self._handle_v2ray_subscription)
        app.router.add_get(self._subscription_path(), self._handle_subscription)
        self._web_runner = web.AppRunner(app)
        await self._web_runner.setup()
        self._web_site = web.TCPSite(
            self._web_runner,
            str(self.config.get("http_host") or "0.0.0.0"),
            int(self.config.get("http_port") or 8077),
        )
        await self._web_site.start()
        self._http_last_error = ""
        logger.info("订阅聚合 HTTP 服务已启动：%s", self._public_subscription_url())

    async def _try_ensure_http_server(self):
        try:
            await self._ensure_http_server()
        except Exception as exc:
            self._http_last_error = f"{type(exc).__name__}: {exc}"
            logger.exception("订阅聚合 HTTP 服务启动失败：%s", self._http_last_error)
            if self._web_runner:
                await self._web_runner.cleanup()
            self._web_runner = None
            self._web_site = None

    async def _handle_subscription(self, request: web.Request) -> web.Response:
        token = request.match_info.get("token", "")
        if token != self.config.get("access_token"):
            return web.Response(status=404, text="not found")
        output = await self.get_kv_data(KV_LAST_OUTPUT, "")
        if not output:
            await self.refresh_and_notify(reason="首次访问刷新")
            output = await self.get_kv_data(KV_LAST_OUTPUT, "")
        output_format = await self.get_kv_data(KV_LAST_OUTPUT_FORMAT, "base64")
        content_type = "text/yaml" if output_format == "clash_yaml" else "text/plain"
        return web.Response(
            text=output,
            content_type=content_type,
            charset="utf-8",
            headers={"subscription-userinfo": "upload=0; download=0; total=0; expire=0"},
        )

    async def _handle_health(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "ok",
                "plugin": PLUGIN_NAME,
                "last_refresh_at": await self.get_kv_data(KV_LAST_REFRESH_AT, ""),
                "node_count": await self.get_kv_data(KV_LAST_NODE_COUNT, 0),
                "output_format": await self.get_kv_data(KV_LAST_OUTPUT_FORMAT, ""),
                "output_file": await self.get_kv_data(KV_LAST_OUTPUT_FILE, ""),
                "v2ray_file": await self.get_kv_data(KV_LAST_V2RAY_FILE, ""),
            }
        )

    async def _handle_v2ray_subscription(self, request: web.Request) -> web.Response:
        token = request.match_info.get("token", "")
        if token != self.config.get("access_token"):
            return web.Response(status=404, text="not found")
        output = await self.get_kv_data(KV_LAST_V2RAY_OUTPUT, "")
        if not output:
            await self.refresh_and_notify(reason="首次访问刷新")
            output = await self.get_kv_data(KV_LAST_V2RAY_OUTPUT, "")
        return web.Response(text=output, content_type="text/plain", charset="utf-8")

    def _sources(self) -> list[dict[str, Any]]:
        sources = [
            item
            for item in self.config.get("subscription_sources", [])
            if item.get("enabled", True) and item.get("url")
        ]
        return sorted(sources, key=self._priority)

    def _manual_node_sources(self) -> list[FetchResult]:
        manual_sources: list[FetchResult] = []
        items = [
            item
            for item in self.config.get("manual_node_sources", [])
            if item.get("enabled", True)
        ]
        for item in sorted(items, key=self._priority):
            if not item.get("enabled", True):
                continue
            nodes_text = str(item.get("nodes") or "").strip()
            if not nodes_text:
                continue
            name = str(item.get("name") or "manual").strip() or "manual"
            ua = str(item.get("user_agent") or "").strip()
            if ua:
                logger.info("加载手动节点源：%s，标记 UA：%s", name, ua)
            manual_sources.append(FetchResult(name=name, text=decode_subscription(nodes_text)))
        return manual_sources

    def _ensure_token(self):
        if not self.config.get("access_token"):
            self.config["access_token"] = secrets.token_urlsafe(12)
            self.config.save_config()

    def _priority(self, item: dict[str, Any]) -> int:
        try:
            return int(item.get("priority", 100))
        except (TypeError, ValueError):
            return 100

    def _resolve_user_agent(self, source_user_agent: str = "") -> str:
        source_user_agent = source_user_agent.strip()
        if source_user_agent:
            return source_user_agent

        preset = str(self.config.get("user_agent_preset") or "mihomo").strip().lower()
        if preset != "custom" and preset in UA_PRESETS:
            return UA_PRESETS[preset]

        custom = str(self.config.get("user_agent") or "").strip()
        if custom:
            return custom

        return UA_PRESETS["mihomo"]

    def _save_output_files(
        self,
        output: str,
        *,
        output_format: str,
        v2ray_base64: str,
        node_count: int,
        refreshed_at: str,
    ) -> str:
        if not self.config.get("save_local_files", True):
            return "未启用本地文件保存"

        output_dir = self._local_output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)

        basename = str(self.config.get("local_output_basename") or "merged-subscription").strip()
        if not basename:
            basename = "merged-subscription"

        suffix = {
            "clash_yaml": ".yaml",
            "base64": ".base64.txt",
            "plain": ".txt",
        }.get(output_format, ".txt")

        output_path = output_dir / f"{basename}{suffix}"
        latest_path = output_dir / f"{basename}.latest"
        v2ray_path = output_dir / f"{basename}.v2ray.txt"
        metadata_path = output_dir / f"{basename}.metadata.json"

        output_path.write_text(output, encoding="utf-8")
        latest_path.write_text(output, encoding="utf-8")
        v2ray_path.write_text(v2ray_base64, encoding="utf-8")
        metadata_path.write_text(
            json.dumps(
                {
                    "refreshed_at": refreshed_at,
                    "output_format": output_format,
                    "node_count": node_count,
                    "output_file": str(output_path),
                    "latest_file": str(latest_path),
                    "v2ray_file": str(v2ray_path),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        logger.info("订阅聚合结果已保存到本地文件：%s", output_path)
        return str(output_path)

    def _local_output_dir(self) -> Path:
        configured = str(self.config.get("local_output_dir") or "").strip()
        if configured:
            return Path(configured)
        return Path(__file__).resolve().parent

    def _v2ray_output_file_path(self) -> str:
        basename = str(self.config.get("local_output_basename") or "merged-subscription").strip()
        if not basename:
            basename = "merged-subscription"
        return str(self._local_output_dir() / f"{basename}.v2ray.txt")

    def _subscription_path(self) -> str:
        prefix = str(self.config.get("path_prefix") or "/sub").strip("/") or "sub"
        return f"/{prefix}/{{token}}"

    def _v2ray_path(self) -> str:
        prefix = str(self.config.get("path_prefix") or "/sub").strip("/") or "sub"
        return f"/{prefix}/{{token}}/v2ray"

    def _health_path(self) -> str:
        prefix = str(self.config.get("path_prefix") or "/sub").strip("/") or "sub"
        return f"/{prefix}/health"

    def _public_subscription_url(self) -> str:
        token = self.config.get("access_token")
        prefix = str(self.config.get("path_prefix") or "/sub").strip("/") or "sub"
        base_url = str(self.config.get("public_base_url") or "").strip()
        if not base_url:
            host = self.config.get("http_host") or "127.0.0.1"
            if host == "0.0.0.0":
                host = "你的公网IP或域名"
            base_url = f"http://{host}:{self.config.get('http_port', 8077)}"
        return urljoin(base_url.rstrip("/") + "/", f"{prefix}/{token}")

    def _public_v2ray_url(self) -> str:
        token = self.config.get("access_token")
        prefix = str(self.config.get("path_prefix") or "/sub").strip("/") or "sub"
        base_url = str(self.config.get("public_base_url") or "").strip()
        if not base_url:
            host = self.config.get("http_host") or "127.0.0.1"
            if host == "0.0.0.0":
                host = "你的公网IP或域名"
            base_url = f"http://{host}:{self.config.get('http_port', 8077)}"
        return urljoin(base_url.rstrip("/") + "/", f"{prefix}/{token}/v2ray")

    def _health_url(self) -> str:
        prefix = str(self.config.get("path_prefix") or "/sub").strip("/") or "sub"
        base_url = str(self.config.get("public_base_url") or "").strip()
        if not base_url:
            host = self.config.get("http_host") or "127.0.0.1"
            if host == "0.0.0.0":
                host = "你的公网IP或域名"
            base_url = f"http://{host}:{self.config.get('http_port', 8077)}"
        return urljoin(base_url.rstrip("/") + "/", f"{prefix}/health")

    async def _broadcast(self, text: str):
        targets = self.config.get("notify_targets", [])
        if not targets:
            logger.warning("订阅聚合通知未发送：尚未绑定 notify_targets。内容：%s", text)
            return
        chain = MessageChain().message(text)
        for target in targets:
            try:
                await self.context.send_message(target, chain)
            except Exception:
                logger.exception("订阅聚合通知发送失败：%s", target)
