from __future__ import annotations

from pathlib import Path

import pytest

from app.server.config import ServerConfig
from app.server.models import ReviewJob, ReviewOutput
from app.server.repositories import PostgresStore
from app.server.services import process_one_job


def config(tmp_path: Path, *, publish_enabled: bool = False) -> ServerConfig:
    return ServerConfig(
        database_url="postgresql://unused", github_app_id="1",
        github_installation_id=42, github_private_key_path=Path("unused.pem"),
        github_webhook_secret="hook-secret",
        allowed_repositories=frozenset({"DUT-AI/dut-ai-pr-preview-system"}),
        admin_username="admin", admin_password_hash="unused",
        session_secret="session-secret", session_secure=False,
        llm_base_url="https://llm2.dutai.site/v1", llm_model="model",
        llm_api_key="", publish_enabled=publish_enabled,
        session_root=tmp_path / "sessions",
    )


class Store:
    def __init__(self):
        self.job = ReviewJob(
            id=7, repository="DUT-AI/dut-ai-pr-preview-system", pr_number=9,
            head_sha="a" * 40, attempt=1, lease_id="worker-1",
        )
        self.completed = None
        self.failed = None
        self.failed_retry = None
        self.interrupted = None
        self.publish_audit = []

    def claim_job(self, lease_id):
        assert lease_id == "worker-1"
        return self.job

    def heartbeat_job(self, job):
        return job == self.job

    def complete_job(self, job, snapshot, output):
        self.completed = (job, snapshot, output)
        return 11

    def run_detail(self, run_id):
        assert run_id == 11
        return {"run": {
            "repository": self.job.repository,
            "pr_number": self.job.pr_number,
            "head_sha": self.job.head_sha,
            "preview_comment": "preview",
        }}

    def record_publish(
        self, run_id, head_sha, status, *, action="publish", comment_id=None,
        error=None,
    ):
        self.publish_audit.append({
            "run_id": run_id, "head_sha": head_sha, "status": status,
            "action": action, "comment_id": comment_id, "error": error,
        })

    def fail_job(self, job, error, *, retry=True):
        self.failed = (job, error)
        self.failed_retry = retry

    def interrupt_job(self, job, error):
        self.interrupted = (job, error)
        return True


class GitHub:
    def __init__(self):
        self.published = []

    def snapshot(self, repository, pr_number):
        return {
            "owner": "DUT-AI", "repo": "dut-ai-pr-preview-system",
            "pr": pr_number, "head_sha": "a" * 40, "files": [],
            "commits": [],
        }

    def download_workspace(self, repository, ref, target):
        assert repository == "DUT-AI/dut-ai-pr-preview-system"
        assert ref == "a" * 40
        target.mkdir(parents=True, exist_ok=True)
        (target / "README.md").write_text("workspace", encoding="utf-8")

    def publish_preview(self, repository, pr_number, head_sha, body):
        self.published.append((repository, pr_number, head_sha, body))
        return {"action": "created", "comment_id": 12345}


class Engine:
    def review(self, snapshot, workspace, session_dir):
        assert (workspace / "README.md").read_text(encoding="utf-8") == "workspace"
        return ReviewOutput(
            findings={"claims": []}, report="report", preview_comment="preview",
            session_path=str(session_dir),
        )


def test_postgres_store_claim_job_builds_review_job(monkeypatch):
    row = {
        "id": 7,
        "delivery_id": "delivery-7",
        "repository": "DUT-AI/dut-ai-pr-preview-system",
        "pr_number": 4,
        "head_sha": "a" * 40,
        "attempt": 1,
        "lease_id": "worker-1",
    }

    class Result:
        rowcount = 0

        def __init__(self, value=None):
            self.value = value

        def fetchone(self):
            return self.value

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, params=()):
            if "RETURNING id,delivery_id" in query:
                return Result(row)
            return Result()

    store = PostgresStore("postgresql://unused")
    monkeypatch.setattr(store, "_connect", Connection)

    job = store.claim_job("worker-1")

    assert job == ReviewJob(
        id=7,
        delivery_id="delivery-7",
        repository="DUT-AI/dut-ai-pr-preview-system",
        pr_number=4,
        head_sha="a" * 40,
        attempt=1,
        lease_id="worker-1",
    )


def test_process_one_job_connects_snapshot_workspace_engine_and_store(tmp_path):
    store = Store()
    github = GitHub()

    assert process_one_job(
        config(tmp_path), store, github, Engine(), lease_id="worker-1"
    )

    job, snapshot, output = store.completed
    assert job == store.job
    assert snapshot["head_sha"] == store.job.head_sha
    assert output.preview_comment == "preview"
    saved = (
        tmp_path / "sessions" / "DUT-AI" / "dut-ai-pr-preview-system" /
        "pr-9" / ("a" * 40) / "snapshot.json"
    )
    assert saved.exists()
    assert store.failed is None
    assert github.published == []
    assert store.publish_audit == []


def test_process_one_job_auto_publishes_completed_review(tmp_path):
    store = Store()
    github = GitHub()

    assert process_one_job(
        config(tmp_path, publish_enabled=True), store, github, Engine(),
        lease_id="worker-1",
    )

    assert github.published == [(
        store.job.repository, store.job.pr_number, store.job.head_sha, "preview",
    )]
    assert store.publish_audit == [{
        "run_id": 11, "head_sha": store.job.head_sha, "status": "success",
        "action": "created", "comment_id": 12345, "error": None,
    }]
    assert store.failed is None


def test_process_one_job_keeps_completed_review_when_auto_publish_fails(tmp_path):
    class FailedPublishGitHub(GitHub):
        def publish_preview(self, repository, pr_number, head_sha, body):
            raise RuntimeError("GitHub unavailable")

    store = Store()

    assert process_one_job(
        config(tmp_path, publish_enabled=True), store, FailedPublishGitHub(), Engine(),
        lease_id="worker-1",
    )

    assert store.completed is not None
    assert store.failed is None
    assert store.publish_audit == [{
        "run_id": 11, "head_sha": store.job.head_sha, "status": "failed",
        "action": "publish", "comment_id": None,
        "error": "GitHub unavailable",
    }]


def test_process_one_job_persists_failure(tmp_path):
    class FailedEngine(Engine):
        def review(self, snapshot, workspace, session_dir):
            raise RuntimeError("model failed")

    store = Store()
    assert process_one_job(
        config(tmp_path), store, GitHub(), FailedEngine(), lease_id="worker-1"
    )
    assert store.completed is None
    assert store.failed[1] == "review engine failed: model failed"
    assert store.failed_retry is True


def test_process_one_job_persists_github_snapshot_phase(tmp_path):
    class FailedGitHub(GitHub):
        def snapshot(self, repository, pr_number):
            raise OSError("network unreachable")

        def download_workspace(self, repository, ref, target):
            pytest.fail("snapshot failures must stop before download")

    store = Store()
    assert process_one_job(
        config(tmp_path), store, FailedGitHub(), Engine(), lease_id="worker-1"
    )
    assert store.completed is None
    assert store.failed[1] == "github snapshot failed: network unreachable"
    assert store.failed_retry is True


def test_process_one_job_does_not_retry_stale_head(tmp_path):
    class StaleGitHub(GitHub):
        def snapshot(self, repository, pr_number):
            snapshot = super().snapshot(repository, pr_number)
            snapshot["head_sha"] = "b" * 40
            return snapshot

        def download_workspace(self, repository, ref, target):
            pytest.fail("stale jobs must stop before downloading the workspace")

    store = Store()
    assert process_one_job(
        config(tmp_path), store, StaleGitHub(), Engine(), lease_id="worker-1"
    )
    assert store.completed is None
    assert "stale" in store.failed[1]
    assert store.failed_retry is False


def test_process_one_job_requeues_on_keyboard_interrupt(tmp_path):
    class InterruptedEngine(Engine):
        def review(self, snapshot, workspace, session_dir):
            raise KeyboardInterrupt

    store = Store()
    with pytest.raises(KeyboardInterrupt):
        process_one_job(
            config(tmp_path), store, GitHub(), InterruptedEngine(),
            lease_id="worker-1",
        )
    assert store.interrupted is not None
    assert "interrupted" in store.interrupted[1]
    assert store.failed is None
