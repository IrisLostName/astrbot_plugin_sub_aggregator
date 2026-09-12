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
        node_list_missing = await client.get("/sub/token/node-list")
        assert node_list_missing.status == 503
        state.save_success(
            "proxies: []\n",
            "{\"outbounds\": []}\n",
            [],
            source_count=1,
            issue_count=0,
            node_list_output="ss://example\n",
        )
        node_list = await client.get("/sub/token/node-list")
        assert node_list.status == 200
        assert await node_list.text() == "ss://example\n"
        await client.close()
    finally:
        await server.stop()
