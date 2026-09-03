from __future__ import annotations

import base64
import io
import json
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.server.config import ServerConfig, validate_repo
from app.server.models import ReviewJob, ReviewOutput
from src.snapshot import ISSUE_BODY_MAX
from src.synthesize import MARKER


class GitHubAppClient:
    """GitHub REST/GraphQL client authenticated as one App installation."""

    def __init__(self, config: ServerConfig, *, transport=None):
        self.config = config
        self._transport = transport
        self._token = ""
        self._token_expires_at = 0.0

    def _app_jwt(self) -> str:
        # cryptography is a server extra and is imported only in the hosted path.
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        now = int(time.time())
        header = self._b64json({"alg": "RS256", "typ": "JWT"})
        payload = self._b64json(
            {"iat": now - 30, "exp": now + 300, "iss": self.config.github_app_id}
        )
        signing_input = f"{header}.{payload}".encode()
        key = serialization.load_pem_private_key(
            self.config.github_private_key_path.read_bytes(), password=None
        )
        signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        return f"{header}.{payload}.{self._b64(signature)}"

    @staticmethod
    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode().rstrip("=")

    @classmethod
    def _b64json(cls, data: dict[str, Any]) -> str:
        return cls._b64(json.dumps(data, separators=(",", ":")).encode())

    def _client(self, token: str) -> httpx.Client:
        return httpx.Client(
            base_url="https://api.github.com",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "dut-ai-pr-preview-system/1.4",
            },
            timeout=60,
            follow_redirects=True,
            transport=self._transport,
        )

    def installation_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        with self._client(self._app_jwt()) as client:
            response = client.post(
                f"/app/installations/{self.config.github_installation_id}/access_tokens"
            )
            response.raise_for_status()
            data = response.json()
        self._token = data["token"]
        expires = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        self._token_expires_at = expires.astimezone(timezone.utc).timestamp()
        return self._token

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        with self._client(self.installation_token()) as client:
            response = client.request(method, path, **kwargs)
            if response.is_error:
                accepted = response.headers.get(
                    "X-Accepted-GitHub-Permissions", "unspecified"
                )
                try:
                    detail = response.json().get("message", response.text)
                except (ValueError, AttributeError):
                    detail = response.text
                raise RuntimeError(
                    f"GitHub {method} {path} failed ({response.status_code}): "
                    f"{str(detail)[:500]}; accepted permissions: {accepted}"
                )
            return response

    def _get_pages(self, path: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            response = self._request(
                "GET", path, params={"per_page": 100, "page": page}
            )
            batch = response.json()
            if not isinstance(batch, list):
                raise RuntimeError(f"GitHub {path} did not return a list")
            items.extend(batch)
            if len(batch) < 100:
                return items
            page += 1

    def installation(self) -> dict[str, Any]:
        # This is an App-level endpoint. GitHub rejects an installation access
        # token here even though that token is correct for repository APIs.
        with self._client(self._app_jwt()) as client:
            response = client.get(
                f"/app/installations/{self.config.github_installation_id}"
            )
            response.raise_for_status()
            return response.json()

    def repositories(self) -> list[dict[str, Any]]:
        data = self._request(
            "GET", "/installation/repositories", params={"per_page": 100}
        ).json()
        return [
            repo for repo in data.get("repositories", [])
            if repo.get("full_name") in self.config.allowed_repositories
        ]

    def _graphql_context(
        self, owner: str, repo: str, pr_number: int
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        query = """
        query($owner:String!,$repo:String!,$pr:Int!){
          repository(owner:$owner,name:$repo){pullRequest(number:$pr){
            closingIssuesReferences(first:10){nodes{number title body}}
            reviewThreads(first:100){nodes{isResolved isOutdated comments(first:100){
              nodes{path line author{login} body}
            }}}
          }}
        }
        """
        data = self._request(
            "POST", "/graphql",
            json={"query": query, "variables": {
                "owner": owner, "repo": repo, "pr": pr_number,
            }},
        ).json()
        if data.get("errors"):
            raise RuntimeError(f"GitHub GraphQL failed: {data['errors']}")
        pr = data["data"]["repository"]["pullRequest"]
        threads = []
        for thread in pr["reviewThreads"]["nodes"]:
            for comment in thread["comments"]["nodes"]:
                threads.append({
                    "path": comment.get("path"), "line": comment.get("line"),
                    "author": (comment.get("author") or {}).get("login"),
                    "body": comment.get("body") or "",
                    "resolved": thread["isResolved"],
                    "outdated": thread["isOutdated"],
                })
        issues = [{
            "number": item.get("number"), "title": item.get("title") or "",
            "body": (item.get("body") or "")[:ISSUE_BODY_MAX],
        } for item in pr["closingIssuesReferences"]["nodes"]]
        return threads, issues

    def snapshot(self, repository: str, pr_number: int) -> dict[str, Any]:
        repository = validate_repo(repository)
        if repository not in self.config.allowed_repositories:
            raise PermissionError(f"repository is not allowlisted: {repository}")
        owner, repo = repository.split("/", 1)
        prefix = f"/repos/{owner}/{repo}/pulls/{pr_number}"
        meta = self._request("GET", prefix).json()
        files = self._get_pages(prefix + "/files")
        commits = self._get_pages(prefix + "/commits")
        threads, issues = self._graphql_context(owner, repo, pr_number)
        return {
            "owner": owner, "repo": repo, "pr": pr_number,
            "title": meta.get("title") or "", "body": meta.get("body") or "",
            "author": (meta.get("user") or {}).get("login") or "",
            "base": (meta.get("base") or {}).get("ref") or "",
            "head": (meta.get("head") or {}).get("ref") or "",
            "head_sha": (meta.get("head") or {}).get("sha") or "",
            "state": meta.get("state") or "",
            "labels": [label.get("name") for label in meta.get("labels", [])],
            "files": [{
                "filename": item.get("filename") or "",
                "status": item.get("status") or "",
                "additions": item.get("additions") or 0,
                "deletions": item.get("deletions") or 0,
                "patch": item.get("patch") or "",
            } for item in files],
            "commits": [{
                "sha": item.get("sha") or "",
                "message": (item.get("commit") or {}).get("message") or "",
                "author": (((item.get("commit") or {}).get("author") or {})
                           .get("name") or ""),
                "committed_at": (((item.get("commit") or {}).get("author") or {})
                                 .get("date")),
            } for item in commits],
            "threads": threads, "linked_issues": issues,
        }

    def download_workspace(self, repository: str, ref: str, target: Path) -> None:
        repository = validate_repo(repository)
        if repository not in self.config.allowed_repositories:
            raise PermissionError(f"repository is not allowlisted: {repository}")
        response = self._request("GET", f"/repos/{repository}/zipball/{ref}")
        target.mkdir(parents=True, exist_ok=True)
        root = target.resolve()
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            members = archive.infolist()
            prefixes = {item.filename.split("/", 1)[0] for item in members}
            if len(prefixes) != 1:
                raise RuntimeError("GitHub archive has an unexpected layout")
            prefix = next(iter(prefixes)) + "/"
            for item in members:
                relative = item.filename.removeprefix(prefix)
                if not relative:
                    continue
                destination = (root / relative).resolve()
                if root not in destination.parents and destination != root:
                    raise RuntimeError("GitHub archive attempted path traversal")
                if item.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(item))

    def publish_preview(
        self, repository: str, pr_number: int, head_sha: str, body: str
    ) -> dict[str, Any]:
        repository = validate_repo(repository)
        if repository not in self.config.allowed_repositories:
            raise PermissionError(f"repository is not allowlisted: {repository}")
        current = self._request(
            "GET", f"/repos/{repository}/pulls/{pr_number}"
        ).json()
        current_sha = (current.get("head") or {}).get("sha")
        if current_sha != head_sha:
            raise RuntimeError(
                f"stale review: run={head_sha[:12]} current={str(current_sha)[:12]}"
            )
        comments = self._get_pages(
            f"/repos/{repository}/issues/{pr_number}/comments"
        )
        existing = next(
            (item for item in comments if MARKER in (item.get("body") or "")), None
        )
        if existing:
            saved = self._request(
                "PATCH", f"/repos/{repository}/issues/comments/{existing['id']}",
                json={"body": body},
            ).json()
            action = "updated"
        else:
            saved = self._request(
                "POST", f"/repos/{repository}/issues/{pr_number}/comments",
                json={"body": body},
            ).json()
            action = "created"
        readback = self._request(
            "GET", f"/repos/{repository}/issues/comments/{saved['id']}"
        ).json()
        if readback.get("body") != body:
            raise RuntimeError("GitHub comment readback did not match the preview")
        return {"action": action, "comment_id": saved["id"],
                "url": saved.get("html_url")}


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
               (repository_id,number,title,author,base_ref,head_ref,head_sha,state)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (repository_id,number) DO UPDATE SET
                 title=EXCLUDED.title,author=EXCLUDED.author,
                 base_ref=EXCLUDED.base_ref,head_ref=EXCLUDED.head_ref,
                 head_sha=EXCLUDED.head_sha,state=EXCLUDED.state,updated_at=NOW()""",
            (repository_id, snapshot["pr"], snapshot.get("title", ""),
             snapshot.get("author", ""), snapshot.get("base", ""),
             snapshot.get("head", ""), snapshot["head_sha"],
             snapshot.get("state", "open")),
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
            return {"run": run, "commits": commits, "publish_audit": audit}

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
