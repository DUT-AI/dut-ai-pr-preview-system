from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(frozen=True)
class ReviewJob:
    id: int
    repository: str
    pr_number: int
    head_sha: str
    delivery_id: str | None = None
    attempt: int = 0
    lease_id: str = ""


@dataclass(frozen=True)
class ReviewOutput:
    findings: dict[str, Any]
    report: str
    preview_comment: str
    session_path: str


@dataclass(frozen=True)
class RunRecord:
    id: int
    repository: str
    pr_number: int
    head_sha: str
    status: str
    report: str | None
    preview_comment: str | None
    created_at: datetime
