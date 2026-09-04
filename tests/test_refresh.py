import pytest
import yaml

from subagg.services.refresh import RefreshService
from subagg.state import StateStore


@pytest.mark.asyncio
async def test_refresh_publishes_metacubex_profile_for_local_yaml(tmp_path):
    state = StateStore(tmp_path)
    service = RefreshService(state)
    try:
        report = await service.refresh(
            [
                {
                    "name": "local",
                    "source_type": "local",
                    "content": """proxies:
  - name: node
    type: ss
    server: example.com
    port: 443
    cipher: aes-128-gcm
    password: test
""",
                }
            ]
        )
    finally:
        await service.close()
    config = yaml.safe_load(report.output)
    assert report.published is True
    assert state.load_output() == report.output
    assert config["dns"]["respect-rules"] is True
    assert config["rule-providers"]["ads"]["format"] == "mrs"
    assert "RULE-SET,cn,DIRECT" in config["rules"]
