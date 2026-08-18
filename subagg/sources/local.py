from __future__ import annotations

from dataclasses import dataclass

from ..subscription.parser import parse_source


@dataclass(frozen=True)
class LocalSource:
    name: str
    content: str

    def parse(self):
        if not self.content.strip():
            raise ValueError("本地订阅内容为空")
        return parse_source(self.content, self.name)
