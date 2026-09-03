from __future__ import annotations

import json
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Mapping

from app.security import verify_webhook_signature
from app.server.config import ServerConfig, validate_repo

_ACTIONS = {"opened", "reopened", "synchronize", "ready_for_review"}
_DELIVERY_RE = re.compile(r"^[A-Za-z0-9-]{1,100}$")
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")

def ingest_webhook(
    body: bytes, headers: Mapping[str, str], config: ServerConfig, store
) -> dict[str, Any]:
    signature = headers.get("x-hub-signature-256", "")
    if not verify_webhook_signature(body, signature, config.github_webhook_secret):
        raise PermissionError("invalid webhook signature")
    event = headers.get("x-github-event", "")
    delivery_id = headers.get("x-github-delivery", "")
    if not _DELIVERY_RE.fullmatch(delivery_id):
        raise ValueError("invalid delivery id")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON payload") from exc
    if event == "ping":
        return {"accepted": True, "queued": False, "event": "ping"}
    if event != "pull_request":
        return {"accepted": False, "queued": False, "reason": "event ignored"}
    action = str(payload.get("action", ""))
    if action not in _ACTIONS:
        return {"accepted": False, "queued": False, "reason": "action ignored"}
    installation_id = int((payload.get("installation") or {}).get("id") or 0)
    if installation_id != config.github_installation_id:
        raise PermissionError("webhook installation is not configured")
    repository = validate_repo(
        str((payload.get("repository") or {}).get("full_name") or "")
    )
    if repository not in config.allowed_repositories:
        raise PermissionError("webhook repository is not allowlisted")
    pull_request = payload.get("pull_request") or {}
    pr_number = int((payload.get("number") or pull_request.get("number") or 0))
    head_sha = str((pull_request.get("head") or {}).get("sha") or "")
    if pr_number <= 0 or not _SHA_RE.fullmatch(head_sha):
        raise ValueError("webhook PR identity is invalid")
    queued = store.record_delivery_and_enqueue(
        delivery_id, event, action, payload, repository, pr_number, head_sha
    )
    return {"accepted": True, "queued": queued, "duplicate": not queued}

HEARTBEAT_SECONDS = 10

def _heartbeat(store, job, stop: threading.Event) -> None:
    """Keep the DB lease alive while GitHub/model work is blocking."""
    while not stop.wait(HEARTBEAT_SECONDS):
        try:
            if not store.heartbeat_job(job):
                return
        except Exception:
            # A transient DB outage must not kill this daemon thread. The
            # completion transaction verifies ownership before committing.
            continue

def process_one_job(
    config: ServerConfig, store, github, engine, *, lease_id: str
) -> bool:
    job = store.claim_job(lease_id)
    if job is None:
        return False
    heartbeat_stop = threading.Event()
    heartbeat = threading.Thread(
        target=_heartbeat, args=(store, job, heartbeat_stop),
        name=f"job-{job.id}-heartbeat", daemon=True,
    )
    heartbeat.start()
    try:
        snapshot = github.snapshot(job.repository, job.pr_number)
        if snapshot["head_sha"] != job.head_sha:
            store.fail_job(
                job,
                "queued head SHA is stale; a newer synchronize delivery should run",
                retry=False,
            )
            return True
        owner, repo = job.repository.split("/", 1)
        session_dir = (
            config.session_root / owner / repo / f"pr-{job.pr_number}" / job.head_sha
        ).resolve()
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "snapshot.json").write_text(
            json.dumps(snapshot, indent=2), encoding="utf-8"
        )
        with tempfile.TemporaryDirectory(prefix="dut-ai-review-") as temp:
            workspace = Path(temp).resolve()
            github.download_workspace(job.repository, job.head_sha, workspace)
            output = engine.review(snapshot, workspace, session_dir)
        store.complete_job(job, snapshot, output)
    except KeyboardInterrupt:
        store.interrupt_job(job, "worker interrupted by shutdown signal; retrying")
        raise
    except Exception as exc:  # worker boundary: persist failure, then continue
        message = str(exc)
        for secret in (
            config.github_webhook_secret, config.session_secret, config.llm_api_key
        ):
            if secret:
                message = message.replace(secret, "[REDACTED]")
        store.fail_job(job, message)
    finally:
        heartbeat_stop.set()
        heartbeat.join(timeout=1)
    return True

def publish_run(config: ServerConfig, store, github, run_id: int) -> dict[str, Any]:
    """Publish one stored preview and persist the GitHub read-back result."""
    if not config.publish_enabled:
        raise PermissionError("publication is disabled")
    detail = store.run_detail(run_id)
    if detail is None:
        raise LookupError("run not found")
    run = detail["run"]
    if run["repository"] not in config.allowed_repositories:
        raise LookupError("run not found")
    try:
        result = github.publish_preview(
            run["repository"],
            run["pr_number"],
            run["head_sha"],
            run["preview_comment"],
        )
        store.record_publish(
            run_id,
            run["head_sha"],
            "success",
            action=result["action"],
            comment_id=result["comment_id"],
        )
        return result
    except Exception as exc:
        store.record_publish(run_id, run["head_sha"], "failed", error=str(exc))
        raise
