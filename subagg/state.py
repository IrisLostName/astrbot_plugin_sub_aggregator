from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .subscription.models import ParsedNode


class StateStore:
    def __init__(self, runtime_dir: str | os.PathLike[str]):
        self.root = Path(runtime_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "state.json"
        self.output_path = self.root / "merged-subscription.yaml"
        self.metadata_path = self.root / "merged-subscription.metadata.json"
        self.log_path = self.root / "subagg.log"

    def load(self) -> dict[str, Any]:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def load_nodes(self) -> list[ParsedNode]:
        nodes: list[ParsedNode] = []
        for raw in self.load().get("nodes", []):
            if not isinstance(raw, dict):
                continue
            try:
                nodes.append(ParsedNode(source=str(raw["source"]), name=str(raw["name"]), proxy=dict(raw["proxy"]), fingerprint=str(raw.get("fingerprint", ""))))
            except (KeyError, TypeError, ValueError):
                continue
        return nodes

    def load_output(self) -> str:
        try:
            return self.output_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def append_log(self, level: str, message: str, **details: Any) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
            **details,
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def save_success(self, output: str, nodes: list[ParsedNode], *, source_count: int, issue_count: int) -> None:
        metadata = {"source_count": source_count, "node_count": len(nodes), "issue_count": issue_count, "output_file": str(self.output_path)}
        state = {"nodes": [asdict(node) for node in nodes], "metadata": metadata}
        self._atomic_write(self.output_path, output)
        self._atomic_write(self.metadata_path, json.dumps(metadata, ensure_ascii=False, indent=2))
        self._atomic_write(self.state_path, json.dumps(state, ensure_ascii=False, indent=2))

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
