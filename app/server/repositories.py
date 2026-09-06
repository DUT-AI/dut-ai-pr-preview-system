"""PostgreSQL persistence for the hosted PR review service."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from app.server.config import ServerConfig
# Compatibility export for older callers; GitHub operations live in github.py.
from app.server.github import GitHubAppClient

logger = logging.getLogger(__name__)

class PostgresStore:
    JOB_LEASE_SECONDS = 60

    def __init__(self, database_url: str):
        self.database_url = database_url

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _json(value):
        from psycopg.types.json import Jsonb

        return Jsonb(value)

    def migrate(self) -> None:
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        with self._connect() as connection:
            connection.execute(schema)

    def health(self) -> bool:
        with self._connect() as connection:
            return connection.execute("SELECT 1 AS ok").fetchone()["ok"] == 1

    def sync_installation(
        self, installation: dict[str, Any], repositories: list[dict[str, Any]]
    ) -> None:
        account = installation.get("account") or {}
        installation_id = int(installation["id"])
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO installations (id, account_login, account_type)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET
                     account_login=EXCLUDED.account_login,
                     account_type=EXCLUDED.account_type, updated_at=NOW()""",
                (installation_id, account.get("login", ""), account.get("type", "")),
            )
            for repo in repositories:
                owner = repo["full_name"].split("/", 1)[0]
                connection.execute(
                    """INSERT INTO repositories
                       (github_id, installation_id, full_name, owner, name,
                        is_private, default_branch)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (full_name) DO UPDATE SET
                         github_id=EXCLUDED.github_id,
                         installation_id=EXCLUDED.installation_id,
                         is_private=EXCLUDED.is_private,
                         default_branch=EXCLUDED.default_branch, updated_at=NOW()""",
                    (repo.get("id"), installation_id, repo["full_name"], owner,
                     repo.get("name", ""), repo.get("private", True),
                     repo.get("default_branch")),
                )

    def record_delivery_and_enqueue(
        self, delivery_id: str, event: str, action: str, payload: dict[str, Any],
        repository: str, pr_number: int, head_sha: str,
    ) -> bool:
        with self._connect() as connection:
            inserted = connection.execute(
                """INSERT INTO deliveries (delivery_id,event,action,payload)
                   VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING
                   RETURNING delivery_id""",
                (delivery_id, event, action, self._json(payload)),
            ).fetchone()
            if not inserted:
                return False
            connection.execute(
                """INSERT INTO jobs
                   (delivery_id,repository,pr_number,head_sha,status)
                   VALUES (%s,%s,%s,%s,'queued')""",
                (delivery_id, repository, pr_number, head_sha),
            )
            return True

    def _recover_stale_jobs(self, connection) -> int:
        """Return abandoned running jobs to the queue after their lease expires."""
        result = connection.execute(
            """UPDATE jobs SET status='queued',
                 error='worker stopped before completing the job; retrying',
                 available_at=NOW(), locked_at=NULL, heartbeat_at=NULL,
                 lease_id=NULL, updated_at=NOW()
               WHERE status='running' AND (
                 heartbeat_at IS NULL OR
                 heartbeat_at < NOW() - (%s * INTERVAL '1 second')
               )""",
            (self.JOB_LEASE_SECONDS,),
        )
        return result.rowcount

    def claim_job(self, lease_id: str) -> ReviewJob | None:
        if not lease_id:
            raise ValueError("lease_id is required")
        with self._connect() as connection:
            self._recover_stale_jobs(connection)
            row = connection.execute(
                """WITH candidate AS (
                     SELECT id FROM jobs
                     WHERE status='queued' AND available_at <= NOW()
                     ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
                   )
                   UPDATE jobs SET status='running', attempt=attempt+1,
                     locked_at=NOW(), heartbeat_at=NOW(), lease_id=%s,
                     error=NULL, updated_at=NOW()
                   WHERE id=(SELECT id FROM candidate)
                   RETURNING id,delivery_id,repository,pr_number,head_sha,
                     attempt,lease_id""",
                (lease_id,),
            ).fetchone()
        if not row:
            return None
        return ReviewJob(
            id=row["id"], delivery_id=row["delivery_id"],
            repository=row["repository"], pr_number=row["pr_number"],
            head_sha=row["head_sha"], attempt=row["attempt"],
            lease_id=row["lease_id"],
        )

    def heartbeat_job(self, job: ReviewJob) -> bool:
        with self._connect() as connection:
            result = connection.execute(
                """UPDATE jobs SET heartbeat_at=NOW(),updated_at=NOW()
                   WHERE id=%s AND status='running' AND lease_id=%s""",
                (job.id, job.lease_id),
            )
            return result.rowcount == 1

    @staticmethod
    def _require_job_lease(connection, job: ReviewJob) -> None:
        row = connection.execute(
            "SELECT status,lease_id FROM jobs WHERE id=%s FOR UPDATE", (job.id,)
        ).fetchone()
        if not row or row["status"] != "running" or row["lease_id"] != job.lease_id:
            raise RuntimeError(f"job {job.id} no longer owns its worker lease")

    def _upsert_snapshot(self, connection, snapshot: dict[str, Any]) -> int:
        full_name = f"{snapshot['owner']}/{snapshot['repo']}"
        repository = connection.execute(
            """INSERT INTO repositories (full_name,owner,name)
               VALUES (%s,%s,%s) ON CONFLICT (full_name) DO UPDATE
               SET updated_at=NOW() RETURNING id""",
            (full_name, snapshot["owner"], snapshot["repo"]),
        ).fetchone()
        repository_id = repository["id"]
        connection.execute(
            """INSERT INTO pull_requests
               (repository_id,number,title,body,author,base_ref,head_ref,head_sha,
                state,html_url,additions,deletions,changed_files,files)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (repository_id,number) DO UPDATE SET
                 title=EXCLUDED.title,body=EXCLUDED.body,author=EXCLUDED.author,
                 base_ref=EXCLUDED.base_ref,head_ref=EXCLUDED.head_ref,
                 head_sha=EXCLUDED.head_sha,state=EXCLUDED.state,
                 html_url=EXCLUDED.html_url,additions=EXCLUDED.additions,
                 deletions=EXCLUDED.deletions,changed_files=EXCLUDED.changed_files,
                 files=EXCLUDED.files,updated_at=NOW()""",
            (
                repository_id,
                snapshot["pr"],
                snapshot.get("title", ""),
                snapshot.get("body", ""),
                snapshot.get("author", ""),
                snapshot.get("base", ""),
                snapshot.get("head", ""),
                snapshot["head_sha"],
                snapshot.get("state", "open"),
                snapshot.get("html_url"),
                sum(item.get("additions", 0) for item in snapshot.get("files", [])),
                sum(item.get("deletions", 0) for item in snapshot.get("files", [])),
                len(snapshot.get("files", [])),
                self._json(snapshot.get("files", [])),
            ),
        )
        for commit in snapshot.get("commits", []):
            connection.execute(
                """INSERT INTO commits
                   (repository_id,pr_number,sha,message,author,committed_at)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (repository_id,pr_number,sha) DO UPDATE SET
                     message=EXCLUDED.message,author=EXCLUDED.author,
                     committed_at=EXCLUDED.committed_at""",
                (repository_id, snapshot["pr"], commit.get("sha", ""),
                 commit.get("message", ""), commit.get("author", ""),
                 commit.get("committed_at")),
            )
        return repository_id

    def complete_job(
        self, job: ReviewJob, snapshot: dict[str, Any], output: ReviewOutput
    ) -> int:
        with self._connect() as connection:
            self._require_job_lease(connection, job)
            self._upsert_snapshot(connection, snapshot)
            run = connection.execute(
                """INSERT INTO runs
                   (job_id,repository,pr_number,head_sha,status,session_path,
                    report,findings,preview_comment,completed_at)
                   VALUES (%s,%s,%s,%s,'complete',%s,%s,%s,%s,NOW())
                   RETURNING id""",
                (job.id, job.repository, job.pr_number, job.head_sha,
                 output.session_path, output.report, self._json(output.findings),
                 output.preview_comment),
            ).fetchone()
            connection.execute(
                """UPDATE jobs SET status='complete',locked_at=NULL,
                   heartbeat_at=NULL,lease_id=NULL,updated_at=NOW()
                   WHERE id=%s""",
                (job.id,),
            )
            return run["id"]

    def fail_job(
        self, job: ReviewJob, error: str, *, retry: bool = True
    ) -> None:
        safe_error = error[:2000]
        with self._connect() as connection:
            self._require_job_lease(connection, job)
            if retry and job.attempt < 3:
                connection.execute(
                    """UPDATE jobs SET status='queued', error=%s,
                       available_at=NOW() + (%s * INTERVAL '1 minute'),
                       locked_at=NULL,heartbeat_at=NULL,lease_id=NULL,
                       updated_at=NOW() WHERE id=%s""",
                    (safe_error, job.attempt, job.id),
                )
            else:
                connection.execute(
                    """UPDATE jobs SET status='failed',error=%s,locked_at=NULL,
                       heartbeat_at=NULL,lease_id=NULL,updated_at=NOW()
                       WHERE id=%s""",
                    (safe_error, job.id),
                )

    def interrupt_job(self, job: ReviewJob, error: str) -> bool:
        """Release a job immediately when this worker receives a stop signal."""
        with self._connect() as connection:
            result = connection.execute(
                """UPDATE jobs SET status='queued',error=%s,available_at=NOW(),
                   locked_at=NULL,heartbeat_at=NULL,lease_id=NULL,updated_at=NOW()
                   WHERE id=%s AND status='running' AND lease_id=%s""",
                (error[:2000], job.id, job.lease_id),
            )
            return result.rowcount == 1

    def list_repositories(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return list(connection.execute(
                """SELECT r.*,
                   COUNT(DISTINCT COALESCE(p.number,j.pr_number))
                     AS pull_request_count,
                   COUNT(DISTINCT runs.id) AS run_count,
                   COUNT(DISTINCT j.id) FILTER (
                     WHERE j.status IN ('queued','running')
                   ) AS active_job_count
                   FROM repositories r
                   LEFT JOIN pull_requests p ON p.repository_id=r.id
                   LEFT JOIN jobs j ON j.repository=r.full_name
                   LEFT JOIN runs ON runs.repository=r.full_name
                   GROUP BY r.id ORDER BY r.full_name"""
            ).fetchall())

    def repository_detail(self, full_name: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            repo = connection.execute(
                "SELECT * FROM repositories WHERE full_name=%s", (full_name,)
            ).fetchone()
            if not repo:
                return None
            prs = list(connection.execute(
                """SELECT p.*, latest.id AS latest_run_id,
                   latest.status AS latest_run_status, latest.created_at AS run_created_at
                   FROM pull_requests p
                   LEFT JOIN LATERAL (
                     SELECT id,status,created_at FROM runs
                     WHERE repository=%s AND pr_number=p.number
                     ORDER BY created_at DESC LIMIT 1
                   ) latest ON TRUE
                   WHERE p.repository_id=%s ORDER BY p.updated_at DESC""",
                (full_name, repo["id"]),
            ).fetchall())
            jobs = list(connection.execute(
                """SELECT id,pr_number,head_sha,status,attempt,error,
                      created_at,updated_at
                   FROM jobs WHERE repository=%s
                   ORDER BY created_at DESC LIMIT 50""",
                (full_name,),
            ).fetchall())
            return {"repository": repo, "pull_requests": prs, "jobs": jobs}

    def record_job_log(self, job_id: int, phase: str, message: str,
                       level: str = "info") -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO job_logs (job_id,phase,level,message)
                   VALUES (%s,%s,%s,%s)""",
                (job_id, phase[:80], level[:20], message[:4000]),
            )

    def job_logs(self, job_id: int) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return list(connection.execute(
                """SELECT id,job_id,phase,level,message,created_at
                   FROM job_logs WHERE job_id=%s ORDER BY created_at, id""",
                (job_id,),
            ).fetchall())

    def run_detail(self, run_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            run = connection.execute(
                "SELECT * FROM runs WHERE id=%s", (run_id,)
            ).fetchone()
            if not run:
                return None
            commits = list(connection.execute(
                """SELECT c.* FROM commits c JOIN repositories r
                   ON r.id=c.repository_id
                   WHERE r.full_name=%s AND c.pr_number=%s
                   ORDER BY c.committed_at NULLS LAST""",
                (run["repository"], run["pr_number"]),
            ).fetchall())
            audit = list(connection.execute(
                "SELECT * FROM publish_audit WHERE run_id=%s ORDER BY created_at DESC",
                (run_id,),
            ).fetchall())
            pr = connection.execute(
                """SELECT * FROM pull_requests p JOIN repositories r
                   ON r.id=p.repository_id WHERE r.full_name=%s AND p.number=%s""",
                (run["repository"], run["pr_number"]),
            ).fetchone()
            logs = self.job_logs(run["job_id"])
            return {"run": run, "pr": pr, "commits": commits,
                    "publish_audit": audit, "logs": logs}

    def record_publish(
        self, run_id: int, head_sha: str, status: str, *, action: str = "publish",
        comment_id: int | None = None, error: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO publish_audit
                   (run_id,action,status,comment_id,head_sha,error)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (run_id, action, status, comment_id, head_sha,
                 error[:2000] if error else None),
            )
