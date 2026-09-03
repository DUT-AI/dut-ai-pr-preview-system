from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ReviewInput:
    snapshot: dict[str, Any]
    workspace: Path
    session_dir: Path


@dataclass(frozen=True)
class ReviewResult:
    findings: dict[str, Any]
    report: str
    preview_comment: str
    session_path: str
