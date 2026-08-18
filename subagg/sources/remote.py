from __future__ import annotations

from dataclasses import dataclass

import aiohttp


@dataclass(frozen=True)
class RemoteResponse:
    text: str
    status: int
    content_type: str


class RemoteSourceFetcher:
    def __init__(self, *, timeout_seconds: int = 20, user_agent: str = "clash-verge"):
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.user_agent = user_agent or "clash-verge"
        self._session: aiohttp.ClientSession | None = None

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def fetch(self, url: str, *, user_agent: str = "") -> RemoteResponse:
        if not url.strip():
            raise ValueError("远程订阅 URL 为空")
        session = await self._client()
        headers = {"User-Agent": user_agent.strip() or self.user_agent}
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        async with session.get(url, headers=headers, timeout=timeout) as response:
            response.raise_for_status()
            text = await response.text(errors="replace")
            return RemoteResponse(text=text, status=response.status, content_type=response.headers.get("Content-Type", ""))

    async def _client(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
