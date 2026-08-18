from __future__ import annotations

import hmac
from typing import Awaitable, Callable

from aiohttp import web

from .state import StateStore


class SubscriptionHttpServer:
    def __init__(self, state: StateStore, *, host: str, port: int, path_prefix: str, access_token: str, health_path: str):
        self.state = state
        self.host = host
        self.port = int(port)
        self.path_prefix = "/" + path_prefix.strip("/")
        self.access_token = access_token
        self.health_path = health_path if health_path.startswith("/") else "/" + health_path
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    async def start(self) -> None:
        if self._runner is not None:
            return
        app = web.Application()
        app.router.add_get(self.health_path, self.handle_health)
        app.router.add_get(f"{self.path_prefix}/{{token}}", self.handle_subscription)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
        self._runner = None
        self._site = None

    async def handle_health(self, request: web.Request) -> web.Response:
        return web.Response(status=204)

    async def handle_subscription(self, request: web.Request) -> web.Response:
        token = request.match_info.get("token", "")
        if not self.access_token or not hmac.compare_digest(token, self.access_token):
            raise web.HTTPNotFound()
        output = self.state.load_output()
        if not output:
            raise web.HTTPServiceUnavailable(text="subscription is not ready")
        return web.Response(text=output, content_type="text/yaml", charset="utf-8")
