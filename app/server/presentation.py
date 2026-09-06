"""Small, side-effect-free view helpers for the server-rendered dashboard."""
from __future__ import annotations

from typing import Any

from src.synthesize import summary_counts


def dashboard_summary(repositories: list[dict[str, Any]]) -> dict[str, int]:
    """Return stable dashboard totals even when a store field is missing."""
    return {
        "repositories": len(repositories),
        "pull_requests": sum(int(repo.get("pull_request_count") or 0) for repo in repositories),
        "runs": sum(int(repo.get("run_count") or 0) for repo in repositories),
        "active_jobs": sum(int(repo.get("active_job_count") or 0) for repo in repositories),
    }


def run_review_view(detail: dict[str, Any]) -> dict[str, Any]:
    """Normalize persisted review output for a safe Jinja presentation."""
    run = detail["run"]
    raw_findings = run.get("findings")
    findings = raw_findings if isinstance(raw_findings, dict) else {}
    normalized = {
        key: value if isinstance(value, list) else []
        for key, value in {
            "claims": findings.get("claims"),
            "docs": findings.get("docs"),
            "impact": findings.get("impact"),
            "threads": findings.get("threads"),
            "unresolved_questions": findings.get("unresolved_questions"),
        }.items()
    }
    counts = summary_counts(normalized)

    published = next(
        (
            item for item in detail.get("publish_audit", [])
            if item.get("status") == "success" and item.get("comment_id")
        ),
        None,
    )
    github_comment_url = None
    if published:
        github_comment_url = (
            f"https://github.com/{run['repository']}/pull/{run['pr_number']}"
            f"#issuecomment-{int(published['comment_id'])}"
        )

    return {
        "findings": normalized,
        "counts": counts,
        "github_comment_url": github_comment_url,
        "has_preview": bool(run.get("preview_comment")),
    }
