from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiohttp


FETCH_TIMEOUT_SECONDS = 60
FETCH_MAX_ATTEMPTS = 3
FETCH_RETRY_DELAYS_SECONDS = (2, 5)


@dataclass(frozen=True)
class RemoteResponse:
    text: str
    status: int
    content_type: str


class _RetryableRemoteError(RuntimeError):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


class RemoteFetchError(RuntimeError):
    def __init__(self, status: int, message: str, url: str):
        self.status = status
        self.message = message
        self.url = redact_url(url)
        super().__init__(f"{status}, message='{message}', url='{self.url}'")


class RemoteSourceFetcher:
    def __init__(self, *, timeout_seconds: int = 20, user_agent: str = "clash-verge"):
        self.timeout_seconds = FETCH_TIMEOUT_SECONDS
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
        timeout = aiohttp.ClientTimeout(total=FETCH_TIMEOUT_SECONDS)
        last_error: Exception | None = None
        for attempt in range(FETCH_MAX_ATTEMPTS):
            try:
                async with session.get(url, headers=headers, timeout=timeout) as response:
                    if response.status >= 400:
                        body = (await response.text(errors="replace")).strip()
                        message = body[:160] or response.reason or "HTTP error"
                        if response.status == 429 or response.status >= 500:
                            raise _RetryableRemoteError(response.status, message)
                        raise RemoteFetchError(response.status, message, url)
                    text = await response.text(errors="replace")
                    return RemoteResponse(text=text, status=response.status, content_type=response.headers.get("Content-Type", ""))
            except _RetryableRemoteError as exc:
                last_error = exc
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = exc
            if attempt < FETCH_MAX_ATTEMPTS - 1:
                await asyncio.sleep(FETCH_RETRY_DELAYS_SECONDS[attempt])
        if isinstance(last_error, _RetryableRemoteError):
            raise RemoteFetchError(last_error.status, last_error.message, url) from last_error
        if last_error is not None:
            raise last_error
        raise RuntimeError("remote fetch ended without a result")

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
