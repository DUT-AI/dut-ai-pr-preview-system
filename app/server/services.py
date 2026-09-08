from __future__ import annotations

import json
import logging
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Mapping

from app.security import verify_webhook_signature
from app.server.config import ServerConfig, repository_is_allowed, validate_repo

_ACTIONS = {"opened", "reopened", "synchronize", "ready_for_review"}
_STATE_ONLY_ACTIONS = {"closed"}
_DELIVERY_RE = re.compile(r"^[A-Za-z0-9-]{1,100}$")
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")
logger = logging.getLogger(__name__)


def _short_sha(value: str) -> str:
    return value[:10] if value else "-"


def _safe_error(config: ServerConfig, exc: Exception) -> str:
    message = str(exc)
    for secret in (
        config.github_webhook_secret, config.session_secret, config.llm_api_key
    ):
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return message


def _job_log(store, job, phase: str, message: str, level: str = "info") -> None:
    """Persist operational breadcrumbs when the store supports them."""
    record = getattr(store, "record_job_log", None)
    if record:
        try:
            record(job.id, phase, message, level)
        except Exception:
            logger.exception("job log persistence failed id=%s phase=%s", job.id, phase)

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
    if action not in _ACTIONS | _STATE_ONLY_ACTIONS:
        return {"accepted": False, "queued": False, "reason": "action ignored"}
    installation_id = int((payload.get("installation") or {}).get("id") or 0)
    if installation_id != config.github_installation_id:
        raise PermissionError("webhook installation is not configured")
    repository = validate_repo(
        str((payload.get("repository") or {}).get("full_name") or "")
    )
    if not repository_is_allowed(repository, config.allowed_repositories):
        raise PermissionError("webhook repository is not allowlisted")
    pull_request = payload.get("pull_request") or {}
    pr_number = int((payload.get("number") or pull_request.get("number") or 0))
    head_sha = str((pull_request.get("head") or {}).get("sha") or "")
    if pr_number <= 0 or not _SHA_RE.fullmatch(head_sha):
        raise ValueError("webhook PR identity is invalid")
    if action in _STATE_ONLY_ACTIONS:
        recorded = store.record_delivery_without_enqueue(
            delivery_id, event, action, payload, repository, pr_number, head_sha
        )
        logger.info(
            "webhook accepted event=%s action=%s delivery=%s repository=%s "
            "pr=%s head=%s queued=False",
            event, action, delivery_id, repository, pr_number, _short_sha(head_sha),
        )
        return {"accepted": True, "queued": False, "duplicate": not recorded}
    queued = store.record_delivery_and_enqueue(
        delivery_id, event, action, payload, repository, pr_number, head_sha
    )
    logger.info(
        "webhook accepted event=%s action=%s delivery=%s repository=%s pr=%s "
        "head=%s queued=%s",
        event, action, delivery_id, repository, pr_number, _short_sha(head_sha),
        queued,
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
    phase = "claimed"
    logger.info(
        "job claimed id=%s repository=%s pr=%s head=%s attempt=%s",
        job.id, job.repository, job.pr_number, _short_sha(job.head_sha),
        job.attempt,
    )
    _job_log(store, job, phase, "job claimed")
    heartbeat_stop = threading.Event()
    heartbeat = threading.Thread(
        target=_heartbeat, args=(store, job, heartbeat_stop),
        name=f"job-{job.id}-heartbeat", daemon=True,
    )
    heartbeat.start()
    try:
        phase = "github snapshot"
        logger.info(
            "job phase start id=%s phase=%s repository=%s pr=%s",
            job.id, phase, job.repository, job.pr_number,
        )
        _job_log(store, job, phase, "started")
        snapshot = github.snapshot(job.repository, job.pr_number)
        logger.info(
            "job phase ok id=%s phase=%s head=%s files=%s commits=%s",
            job.id, phase, _short_sha(snapshot.get("head_sha", "")),
            len(snapshot.get("files", [])), len(snapshot.get("commits", [])),
        )
        _job_log(
            store,
            job,
            phase,
            "ok; files=%s; commits=%s"
            % (len(snapshot.get("files", [])), len(snapshot.get("commits", []))),
        )
        if snapshot["head_sha"] != job.head_sha:
            logger.warning(
                "job stale id=%s queued_head=%s current_head=%s",
                job.id, _short_sha(job.head_sha),
                _short_sha(snapshot.get("head_sha", "")),
            )
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
        phase = "session prepare"
        logger.info("job phase start id=%s phase=%s path=%s", job.id, phase, session_dir)
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "snapshot.json").write_text(
            json.dumps(snapshot, indent=2), encoding="utf-8"
        )
        logger.info("job phase ok id=%s phase=%s", job.id, phase)
        _job_log(store, job, phase, "ok")
        with tempfile.TemporaryDirectory(prefix="dut-ai-review-") as temp:
            workspace = Path(temp).resolve()
            phase = "github workspace download"
            logger.info(
                "job phase start id=%s phase=%s repository=%s head=%s",
                job.id, phase, job.repository, _short_sha(job.head_sha),
            )
            _job_log(store, job, phase, "started")
            github.download_workspace(job.repository, job.head_sha, workspace)
            logger.info("job phase ok id=%s phase=%s path=%s", job.id, phase, workspace)
            _job_log(store, job, phase, "ok")
            phase = "review engine"
            logger.info(
                "job phase start id=%s phase=%s session=%s",
                job.id, phase, session_dir,
            )
            _job_log(store, job, phase, "started")
            output = engine.review(snapshot, workspace, session_dir)
            logger.info(
                "job phase ok id=%s phase=%s session=%s",
                job.id, phase, output.session_path,
            )
            _job_log(store, job, phase, "ok")
        run_id = store.complete_job(job, snapshot, output)
        logger.info(
            "job complete id=%s repository=%s pr=%s head=%s",
            job.id, job.repository, job.pr_number, _short_sha(job.head_sha),
        )
        _job_log(store, job, "complete", "review persisted")
        if config.publish_enabled:
            phase = "github publish"
            _job_log(store, job, phase, "automatic publish started")
            try:
                result = publish_run(config, store, github, run_id)
            except Exception as exc:
                # The review is already complete and durable. Publication has
                # its own audit record, so a GitHub failure must not retry the
                # expensive review or overwrite the completed job state.
                safe_error = _safe_error(config, exc)
                logger.error(
                    "automatic publish failed run=%s repository=%s pr=%s head=%s "
                    "error=%s",
                    run_id, job.repository, job.pr_number, _short_sha(job.head_sha),
                    safe_error,
                )
                _job_log(
                    store, job, phase,
                    f"automatic publish failed: {safe_error}", "error",
                )
            else:
                logger.info(
                    "automatic publish ok run=%s repository=%s pr=%s head=%s "
                    "action=%s comment=%s",
                    run_id, job.repository, job.pr_number, _short_sha(job.head_sha),
                    result["action"], result["comment_id"],
                )
                _job_log(
                    store,
                    job,
                    phase,
                    "automatic publish ok; action=%s; comment=%s"
                    % (result["action"], result["comment_id"]),
                )
        else:
            _job_log(store, job, "github publish", "skipped; publication disabled")
    except KeyboardInterrupt:
        store.interrupt_job(job, "worker interrupted by shutdown signal; retrying")
        raise
    except Exception as exc:  # worker boundary: persist failure, then continue
        logger.exception(
            "job failed id=%s phase=%s repository=%s pr=%s head=%s",
            job.id, phase, job.repository, job.pr_number, _short_sha(job.head_sha),
        )
        _job_log(store, job, phase, str(exc), "error")
        message = f"{phase} failed: {_safe_error(config, exc)}"
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
    if not repository_is_allowed(run["repository"], config.allowed_repositories):
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
        store.record_publish(
            run_id, run["head_sha"], "failed", error=_safe_error(config, exc)
        )
        raise
