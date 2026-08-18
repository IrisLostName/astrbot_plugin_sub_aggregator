from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiohttp


@dataclass(frozen=True)
class RemoteResponse:
    text: str
    status: int
    content_type: str


class RemoteFetchError(RuntimeError):
    def __init__(self, status: int, message: str, url: str):
        self.status = status
        self.message = message
        self.url = redact_url(url)
        super().__init__(f"{status}, message='{message}', url='{self.url}'")


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
            if response.status >= 400:
                body = (await response.text(errors="replace")).strip()
                message = body[:160] or response.reason or "HTTP error"
                raise RemoteFetchError(response.status, message, url)
            text = await response.text(errors="replace")
            return RemoteResponse(text=text, status=response.status, content_type=response.headers.get("Content-Type", ""))

    async def _client(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session


def redact_url(url: str) -> str:
    parsed = urlsplit(url)
    if not parsed.query:
        return url
    redacted_query = [(key, "<redacted>") for key, _value in parse_qsl(parsed.query, keep_blank_values=True)]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(redacted_query), ""))
