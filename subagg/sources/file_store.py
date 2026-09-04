from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

import aiohttp


class LocalFileStore:
    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_path(self, source_name: str, original_name: str, source_path: str) -> Path:
        source = Path(source_path)
        if not source.is_file():
            raise FileNotFoundError(f"本地文件不存在：{source}")
        target = self._target(source_name, original_name)
        shutil.copyfile(source, target)
        return target

    async def download_url(self, source_name: str, original_name: str, url: str) -> Path:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("文件 URL 必须是 HTTP 或 HTTPS")
        target = self._target(source_name, original_name)
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                target.write_bytes(await response.read())
        return target

    def _target(self, source_name: str, original_name: str) -> Path:
        safe_source = re.sub(r"[^0-9A-Za-z._-]+", "_", source_name).strip("._") or "source"
        safe_name = re.sub(r"[^0-9A-Za-z._-]+", "_", Path(original_name).name).strip("._") or "subscription.data"
        return self.root / f"{safe_source}__{safe_name}"
