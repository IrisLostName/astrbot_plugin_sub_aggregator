import pytest

pytest.importorskip("aiohttp")

from aiohttp.test_utils import TestClient, TestServer

from subagg.http_server import SubscriptionHttpServer
from subagg.state import StateStore


@pytest.mark.asyncio
async def test_health_and_subscription_routes(tmp_path):
    state = StateStore(tmp_path)
    server = SubscriptionHttpServer(state, host="127.0.0.1", port=0, path_prefix="/sub", access_token="token", health_path="/sub/healthz")
    await server.start()
    try:
        client = TestClient(TestServer(server._runner.app))
        await client.start_server()
        health = await client.get("/sub/healthz")
        assert health.status == 204
        missing = await client.get("/sub/token")
        assert missing.status == 503
        await client.close()
    finally:
        await server.stop()
