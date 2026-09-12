import pytest
import yaml

from subagg.services.refresh import RefreshService
from subagg.state import StateStore


@pytest.mark.asyncio
async def test_refresh_publishes_local_file_source_relative_to_base_dir(tmp_path):
    source_file = tmp_path / "sub" / "Easycloud.yaml"
    source_file.parent.mkdir()
    source_file.write_text(
        """proxies:
  - name: file-node
    type: ss
    server: example.com
    port: 443
    cipher: aes-128-gcm
    password: test
""",
        encoding="utf-8",
    )
    state = StateStore(tmp_path / "runtime")
    service = RefreshService(state, source_base_dir=tmp_path)
    try:
        report = await service.refresh(
            [{"name": "Easycloud", "source_type": "local", "file_path": "sub/Easycloud.yaml"}]
        )
    finally:
        await service.close()
    assert report.published is True
    assert report.issues == []
    assert report.nodes[0].name == "[Easycloud]file-node"


@pytest.mark.asyncio
async def test_refresh_reports_missing_local_file_and_keeps_last_output(tmp_path):
    state = StateStore(tmp_path / "runtime")
    service = RefreshService(state, source_base_dir=tmp_path)
    try:
        with pytest.raises(RuntimeError, match="没有解析到可用节点"):
            await service.refresh(
                [{"name": "missing", "source_type": "local", "file_path": "sub/missing.yaml"}]
            )
    finally:
        await service.close()


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


@pytest.mark.asyncio
async def test_refresh_strict_mode_keeps_previous_output_for_invalid_nodes(tmp_path):
    state = StateStore(tmp_path / "runtime")
    service = RefreshService(state)
    content = """proxies:
  - name: good
    type: ss
    server: example.com
    port: 443
    cipher: aes-128-gcm
    password: test
  - name: contact
    type: http
    server: ""
    port: 0
"""
    try:
        report = await service.refresh([{"name": "dirty", "source_type": "local", "content": content}])
    finally:
        await service.close()
    assert report.published is False
    assert len(report.nodes) == 1
    assert report.issues[0].reason == "proxy 缺少 type/server/port"
    assert state.load_output() == ""


@pytest.mark.asyncio
async def test_refresh_filters_invalid_nodes_when_enabled(tmp_path):
    state = StateStore(tmp_path / "runtime")
    service = RefreshService(state)
    content = """proxies:
  - name: good
    type: ss
    server: example.com
    port: 443
    cipher: aes-128-gcm
    password: test
  - name: contact
    type: http
    server: ""
    port: 0
  - name: bad-reality
    type: vless
    server: example.com
    port: 443
    uuid: 00000000-0000-0000-0000-000000000000
    reality-opts:
      public-key: public-key
      short-id: 0000
"""
    try:
        report = await service.refresh(
            [
                {
                    "name": "dirty",
                    "source_type": "local",
                    "content": content,
                    "filter_invalid_nodes": True,
                }
            ]
        )
    finally:
        await service.close()
    assert report.published is True
    assert report.issues == []
    assert [node.name for node in report.nodes] == ["[dirty]good"]


@pytest.mark.asyncio
async def test_refresh_applies_include_exclude_name_filters(tmp_path):
    state = StateStore(tmp_path / "runtime")
    service = RefreshService(state)
    content = """proxies:
  - name: Japan fast
    type: ss
    server: japan.example.com
    port: 443
    cipher: aes-128-gcm
    password: test
  - name: Japan expired
    type: ss
    server: expired.example.com
    port: 443
    cipher: aes-128-gcm
    password: test
  - name: US fast
    type: ss
    server: us.example.com
    port: 443
    cipher: aes-128-gcm
    password: test
"""
    try:
        report = await service.refresh(
            [
                {
                    "name": "filtered",
                    "source_type": "local",
                    "content": content,
                    "include_regex": "Japan|US",
                    "exclude_regex": "expired",
                }
            ]
        )
    finally:
        await service.close()
    assert report.published is True
    assert [node.name for node in report.nodes] == ["[filtered]Japan fast", "[filtered]US fast"]


@pytest.mark.asyncio
async def test_refresh_invalid_name_regex_blocks_publish(tmp_path):
    state = StateStore(tmp_path / "runtime")
    service = RefreshService(state)
    try:
        report = await service.refresh(
            [
                {
                    "name": "filtered",
                    "source_type": "local",
                    "content": """proxies:
  - name: node
    type: ss
    server: example.com
    port: 443
    cipher: aes-128-gcm
    password: test
""",
                    "include_regex": "[",
                }
            ]
        )
    finally:
        await service.close()
    assert report.published is False
    assert report.issues[0].protocol == "filter"


@pytest.mark.asyncio
async def test_refresh_writes_raw_share_links_to_node_list(tmp_path):
    state = StateStore(tmp_path / "runtime")
    service = RefreshService(state)
    first = "vless://00000000-0000-0000-0000-000000000000@example.com:443?security=none#first"
    second = "ss://2022-blake3-aes-128-gcm:password@example.com:8443#second"
    try:
        report = await service.refresh(
            [
                {
                    "name": "links",
                    "source_type": "local",
                    "content": f"{first}\n{second}\n",
                    "node_list_output": True,
                }
            ]
        )
    finally:
        await service.close()
    assert report.published is True
    assert report.node_list_output == f"{first}\n{second}\n"
    assert state.load_node_list_output() == report.node_list_output


@pytest.mark.asyncio
async def test_yaml_source_does_not_fabricate_node_list_links(tmp_path):
    state = StateStore(tmp_path / "runtime")
    service = RefreshService(state)
    try:
        report = await service.refresh(
            [
                {
                    "name": "yaml",
                    "source_type": "local",
                    "content": """proxies:
  - name: yaml-node
    type: ss
    server: example.com
    port: 443
    cipher: aes-128-gcm
    password: test
""",
                    "node_list_output": True,
                }
            ]
        )
    finally:
        await service.close()
    assert report.published is True
    assert report.node_list_output == ""
    assert state.load_node_list_output() == ""
