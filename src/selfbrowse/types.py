"""Plain data types shared across the package."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Usage:
    """Token accounting for one or more model calls."""

    input_tokens: int = 0          # uncached input
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    calls: int = 0

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens
        self.calls += other.calls

    @property
    def total_input(self) -> int:
        """All input tokens, cached or not."""
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens


@dataclass
class Step:
    """One tool call the agent made."""

    number: int
    tool: str
    input: dict[str, Any]
    result: str
    url: str = ""
    from_cache: bool = False       # replayed from learned site knowledge, no model call
    screenshot: str = ""           # path of this step's evidence image, when screenshots are on


@dataclass
class RunResult:
    success: bool
    output: str
    steps: int
    usage: Usage
    history: list[Step] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
