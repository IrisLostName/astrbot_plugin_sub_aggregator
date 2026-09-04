from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PayloadKind(str, Enum):
    CLASH_YAML = "clash_yaml"
    SHARE_LINKS = "share_links"
    MIXED = "mixed"
    BASE64 = "base64"
    HTML = "html"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ConversionIssue:
    source: str
    protocol: str
    reason: str
    line: int | None = None


@dataclass(frozen=True)
class ParsedNode:
    source: str
    name: str
    proxy: dict[str, Any]
    fingerprint: str = ""


@dataclass
class SourceResult:
    source: str
    kind: PayloadKind
    nodes: list[ParsedNode] = field(default_factory=list)
    issues: list[ConversionIssue] = field(default_factory=list)


@dataclass(frozen=True)
class MergeResult:
    nodes: list[ParsedNode]
    added: list[ParsedNode]
    updated: list[ParsedNode]
    removed: list[ParsedNode]
    issues: list[ConversionIssue]
    output_text: str = ""


class AdapterError(ValueError):
    def __init__(self, protocol: str, reason: str):
        self.protocol = protocol
        self.reason = reason
        super().__init__(f"{protocol}: {reason}")
