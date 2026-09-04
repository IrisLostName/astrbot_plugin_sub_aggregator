import pytest

from subagg.sources.remote import RemoteSourceFetcher


class FakeResponse:
    def __init__(self, status, text):
        self.status = status
        self.reason = "temporary"
        self.headers = {"Content-Type": "text/plain"}
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def text(self, errors=None):
        return self._text


class FakeSession:
    closed = False

    def __init__(self):
        self.responses = [FakeResponse(503, "busy"), FakeResponse(502, "busy"), FakeResponse(200, "ok")]
        self.calls = 0

    def get(self, url, headers, timeout):
        response = self.responses[self.calls]
        self.calls += 1
        return response


@pytest.mark.asyncio
async def test_remote_fetch_retries_transient_failures(monkeypatch):
    fetcher = RemoteSourceFetcher()
    session = FakeSession()
    fetcher._session = session
    delays = []

    async def fake_sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr("subagg.sources.remote.asyncio.sleep", fake_sleep)
    result = await fetcher.fetch("https://example.com/sub")
    assert result.text == "ok"
    assert session.calls == 3
    assert delays == [2, 5]


@pytest.mark.asyncio
async def test_remote_fetch_does_not_retry_not_found(monkeypatch):
    fetcher = RemoteSourceFetcher()
    fetcher._session = FakeSession()
    fetcher._session.responses = [FakeResponse(404, "not found")]
    calls = []

    async def fake_sleep(seconds):
        calls.append(seconds)

    monkeypatch.setattr("subagg.sources.remote.asyncio.sleep", fake_sleep)
    with pytest.raises(Exception):
        await fetcher.fetch("https://example.com/sub")
    assert fetcher._session.calls == 1
    assert calls == []
