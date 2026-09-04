from pathlib import Path

from subagg.sources.file_store import LocalFileStore


def test_local_file_store_copies_content_without_embedding_it_in_config(tmp_path):
    incoming = tmp_path / "incoming.data"
    incoming.write_bytes(b"c2FtcGxl")
    store = LocalFileStore(tmp_path / "local_sources")
    saved = store.save_path("airport", "original.subscription", str(incoming))
    assert saved.read_bytes() == b"c2FtcGxl"
    assert saved.parent.name == "local_sources"
