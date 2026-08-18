from __future__ import annotations

import asyncio
import os
import secrets
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register


PLUGIN_ROOT = Path(__file__).resolve().parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from subagg.http_server import SubscriptionHttpServer
from subagg.services.refresh import RefreshReport, RefreshService
from subagg.sources.file_store import LocalFileStore
from subagg.state import StateStore


PLUGIN_NAME = "astrbot_plugin_sub_aggregator"
SUBSCRIPTION_PREFIX = "/sub"
INTERNAL_HEALTH_PATH = "/sub/healthz"


@filter.command_group("subagg")
def subagg():
    pass


@register(PLUGIN_NAME, "chenh", "按内容识别并聚合订阅，输出 Mihomo/Clash YAML。", "0.3.4")
class SubscriptionAggregatorPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.config = config
        self._ensure_access_token()
        self.state = StateStore(self._runtime_dir())
        local_dir = str(config.get("local_sources_dir") or "").strip() or str(self.state.root / "local_sources")
        self.local_file_store = LocalFileStore(local_dir)
        self.refresh_service = RefreshService(
            self.state,
            user_agent=str(config.get("user_agent") or "clash-verge"),
            timeout_seconds=int(config.get("request_timeout_seconds") or 20),
            rule_profile=str(config.get("rule_profile") or "metacubex"),
        )
        self.http_server = SubscriptionHttpServer(
            self.state,
            host=str(config.get("http_host") or "127.0.0.1"),
            port=int(config.get("http_port") or 8077),
            path_prefix=SUBSCRIPTION_PREFIX,
            access_token=str(config.get("access_token") or ""),
            health_path=INTERNAL_HEALTH_PATH,
        )
        self._refresh_task: asyncio.Task | None = None
        self._stopping = False
        self._http_start_error = ""
        self._next_refresh_at = ""

    @filter.on_astrbot_loaded()
    async def on_astrbot_loaded(self):
        self._stopping = False
        if self.config.get("http_enable", True):
            try:
                await self.http_server.start()
                self._http_start_error = ""
                self.state.append_log("info", "http server started", host=self.http_server.host, port=self.http_server.port)
            except Exception as exc:
                self._http_start_error = f"{type(exc).__name__}: {exc}"
                self.state.append_log("error", "http server start failed", error=type(exc).__name__)
                logger.exception("订阅 HTTP 服务启动失败：%s", self._http_start_error)
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        message = await self._refresh_once("启动刷新")
        if self.config.get("startup_push", False):
            await self._broadcast(message)

    async def terminate(self):
        self._stopping = True
        if self._refresh_task:
            self._refresh_task.cancel()
            await asyncio.gather(self._refresh_task, return_exceptions=True)
        await self.http_server.stop()
        await self.refresh_service.close()

    @subagg.command("help")
    async def help_cmd(self, event: AstrMessageEvent):
        yield event.plain_result(
            "订阅聚合命令：\n"
            "/subagg bind - 绑定当前会话接收故障通知\n"
            "/subagg url - 查看带 token 的订阅地址\n"
            "/subagg status - 查看运行、节点和 HTTP 状态\n"
            "/subagg refresh - 立即刷新\n"
            "/subagg list - 查看已配置源\n"
            "/subagg add 名称 URL - 添加远程订阅源\n"
            "/subagg localfile 名称 [本地路径或URL] - 保存本地文件订阅\n"
            "/subagg remove 名称 - 删除同名订阅源"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @subagg.command("bind")
    async def bind_cmd(self, event: AstrMessageEvent):
        targets = list(self.config.get("notify_targets", []))
        if event.unified_msg_origin not in targets:
            targets.append(event.unified_msg_origin)
            self.config["notify_targets"] = targets
            self.config.save_config()
        yield event.plain_result("已绑定当前会话为订阅聚合通知接收处。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @subagg.command("url")
    async def url_cmd(self, event: AstrMessageEvent):
        yield event.plain_result(self._public_subscription_url())

    @filter.permission_type(filter.PermissionType.ADMIN)
    @subagg.command("status")
    async def status_cmd(self, event: AstrMessageEvent):
        metadata = self.state.load().get("metadata", {})
        http_status = "运行中" if self._runner_active() else ("启动失败" if self._http_start_error else "未启用")
        public_url = self._public_subscription_url()
        yield event.plain_result(
            "订阅聚合状态：\n"
            f"运行目录：{self.state.root}\n"
            f"日志：{self.state.log_path}\n"
            f"节点数：{metadata.get('node_count', 0)}\n"
            f"源数量：{metadata.get('source_count', 0)}\n"
            f"规则 profile：{self.config.get('rule_profile', 'metacubex')}\n"
            f"HTTP：{http_status}\n"
            f"HTTP 错误：{self._http_start_error or '无'}\n"
            f"内部监听：{self.config.get('http_host', '127.0.0.1')}:{self.config.get('http_port', 8077)}\n"
            f"公网订阅：{public_url}\n"
            f"内部 health（仅 Tunnel）：{self.http_server.health_path}\n"
            f"自动刷新：{'运行中' if self._refresh_task and not self._refresh_task.done() else '已停止'}\n"
            f"下次刷新：{self._next_refresh_at or '未排程'}"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @subagg.command("refresh")
    async def refresh_cmd(self, event: AstrMessageEvent):
        yield event.plain_result(await self._refresh_once("手动刷新"))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @subagg.command("list")
    async def list_cmd(self, event: AstrMessageEvent):
        sources = self._sources()
        if not sources:
            yield event.plain_result("没有启用的订阅源。")
            return
        lines = ["已配置订阅源："]
        for index, source in enumerate(sources, start=1):
            kind = "本地文件" if str(source.get("source_type") or "").lower() == "local_file" else ("本地内容" if self._is_local(source) else "远程 URL")
            state = "启用" if source.get("enabled", True) else "停用"
            lines.append(f"{index}. {source.get('name', '未命名')} | {kind} | {state}")
        yield event.plain_result("\n".join(lines))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @subagg.command("add")
    async def add_cmd(self, event: AstrMessageEvent, name: str, url: str):
        if not url.lower().startswith(("http://", "https://")):
            yield event.plain_result("订阅 URL 必须以 http:// 或 https:// 开头。")
            return
        sources = list(self.config.get("subscription_sources", []))
        sources.append(
            {
                "__template_key": "source",
                "name": name,
                "source_type": "remote",
                "url": url,
                "user_agent": "",
                "priority": 100,
                "enabled": True,
            }
        )
        self.config["subscription_sources"] = sources
        self.config.save_config()
        yield event.plain_result(f"已添加订阅源：{name}。请执行 /subagg refresh 验证。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @subagg.command("localfile")
    async def localfile_cmd(self, event: AstrMessageEvent, name: str, source: str = ""):
        try:
            saved = await self._save_local_file(event, name, source)
        except Exception as exc:
            self.state.append_log("error", "local file import failed", source=name, error=type(exc).__name__)
            yield event.plain_result(f"本地文件导入失败：{type(exc).__name__}。日志：{self.state.log_path}")
            return
        sources = [item for item in self.config.get("subscription_sources", []) if isinstance(item, dict)]
        sources = [item for item in sources if str(item.get("name") or "") != name]
        sources.append({
            "__template_key": "source",
            "name": name,
            "source_type": "local_file",
            "file_path": str(saved),
            "original_name": saved.name,
            "priority": 100,
            "enabled": True,
        })
        self.config["subscription_sources"] = sources
        self.config.save_config()
        self.state.append_log("info", "local file imported", source=name, file=str(saved))
        yield event.plain_result(f"已保存本地订阅文件：{name}\n路径：{saved}\n请执行 /subagg refresh 验证。")


    async def _save_local_file(self, event: AstrMessageEvent, name: str, source: str) -> Path:
        if source:
            if source.lower().startswith(("http://", "https://")):
                return await self.local_file_store.download_url(name, Path(source).name or "subscription.data", source)
            return self.local_file_store.save_path(name, Path(source).name, source)
        try:
            from astrbot.core.message.components import File
        except ImportError as exc:
            raise RuntimeError("当前 AstrBot 没有 File 消息组件") from exc
        file_segment = next((item for item in event.get_messages() if isinstance(item, File)), None)
        if file_segment is None:
            raise ValueError("请在同一条消息附带文件，或提供本地路径/URL")
        original_name = str(getattr(file_segment, "name", "subscription.data") or "subscription.data")
        local_path = str(getattr(file_segment, "file", "") or getattr(file_segment, "file_", ""))
        if local_path and Path(local_path).is_file():
            return self.local_file_store.save_path(name, original_name, local_path)
        url = str(getattr(file_segment, "url", "") or "")
        if not url:
            local_path = await file_segment.get_file()
            return self.local_file_store.save_path(name, original_name, str(local_path))
        return await self.local_file_store.download_url(name, original_name, url)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @subagg.command("remove")
    async def remove_cmd(self, event: AstrMessageEvent, name: str):
        before = list(self.config.get("subscription_sources", []))
        after = [source for source in before if str(source.get("name") or "") != name]
        self.config["subscription_sources"] = after
        self.config.save_config()
        yield event.plain_result(f"已删除 {len(before) - len(after)} 个名为 {name} 的订阅源。")

    async def _refresh_loop(self):
        while not self._stopping:
            interval = max(1, int(self.config.get("refresh_interval_minutes") or 180))
            self._next_refresh_at = (datetime.now() + timedelta(minutes=interval)).isoformat(timespec="seconds")
            try:
                await asyncio.sleep(interval * 60)
                self._next_refresh_at = ""
                message = await self._refresh_once("定时刷新")
                if "失败" in message and self.config.get("notify_on_error", True):
                    await self._broadcast(message)
            except asyncio.CancelledError:
                self._next_refresh_at = ""
                raise

    async def _refresh_once(self, reason: str) -> str:
        try:
            report = await self.refresh_service.refresh(self._sources())
        except Exception as exc:
            self.state.append_log("error", "refresh failed", reason=reason, error=type(exc).__name__)
            logger.exception("订阅刷新失败：%s", type(exc).__name__)
            return f"{reason}失败：{type(exc).__name__}"
        return self._format_refresh_report(reason, report)

    def _format_refresh_report(self, reason: str, report: RefreshReport) -> str:
        if report.published:
            changes = f"新增 {len(report.added)}，更新 {len(report.updated)}，移除 {len(report.removed)}"
            return f"{reason}完成：{len(report.nodes)} 个节点；{changes}。"
        return f"{reason}未发布新结果：{len(report.issues)} 项输入问题，已保留上次成功订阅。"

    def _sources(self) -> list[dict]:
        sources = [source for source in self.config.get("subscription_sources", []) if isinstance(source, dict)]
        return sorted(sources, key=lambda source: int(source.get("priority", 100)))

    @staticmethod
    def _is_local(source: dict) -> bool:
        return str(source.get("source_type") or "remote").lower() in {"local", "yaml", "upload", "local_file"}

    def _runtime_dir(self) -> Path:
        configured = os.environ.get("ASTRBOT_SUBAGG_RUNTIME_DIR") or str(self.config.get("runtime_dir") or "").strip()
        return Path(configured) if configured else Path("/AstrBot/data/runtime") / PLUGIN_NAME

    def _ensure_access_token(self) -> None:
        if not self.config.get("access_token"):
            self.config["access_token"] = secrets.token_urlsafe(24)
            self.config.save_config()

    def _public_subscription_url(self) -> str:
        token = str(self.config.get("access_token") or "")
        prefix = SUBSCRIPTION_PREFIX.strip("/")
        base = str(os.environ.get("ASTRBOT_SUBAGG_PUBLIC_BASE_URL") or self.config.get("public_base_url") or "https://bot.tomori.cloud").strip()
        return urljoin(base.rstrip("/") + "/", f"{prefix}/{token}")

    async def _broadcast(self, text: str) -> None:
        for target in self.config.get("notify_targets", []):
            try:
                await self.context.send_message(target, MessageChain().message(text))
            except Exception:
                logger.exception("订阅聚合通知发送失败")

    def _runner_active(self) -> bool:
        return self.http_server._runner is not None
