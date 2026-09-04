from pathlib import Path


def test_subscription_plugin_keeps_refresh_and_http_watch_loops():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "async def _refresh_loop" in source
    assert "async def _http_watch_loop" in source
