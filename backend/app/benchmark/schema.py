from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

@dataclass
class Expected:
    lever: str
    failure_mode: str
    should_be_clean: bool = False

@dataclass
class BenchmarkCase:
    id: str
    parent_id: str | None
    kind: str
    question: str
    criteria: str
    expected: Expected
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d
