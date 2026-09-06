"""Functional GitHub App client used by the web worker."""
from __future__ import annotations

import base64
import io
import json
import logging
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx

from app.server.config import repository_is_allowed, validate_repo
from src.snapshot import ISSUE_BODY_MAX
from src.synthesize import MARKER

logger = logging.getLogger(__name__)


def create_client(config, *, transport=None):
    state = {"token": "", "token_expires_at": 0.0}

    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode().rstrip("=")

    def b64json(data: dict[str, Any]) -> str:
        return b64(json.dumps(data, separators=(",", ":")).encode())

    def app_jwt() -> str:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        from app.server import repositories as db_repositories

        now = int(db_repositories.time.time())
        header = b64json({"alg": "RS256", "typ": "JWT"})
        payload = b64json({"iat": now - 30, "exp": now + 300, "iss": config.github_app_id})
        key = serialization.load_pem_private_key(
            config.github_private_key_path.read_bytes(), password=None
        )
        signature = key.sign(
            f"{header}.{payload}".encode(), padding.PKCS1v15(), hashes.SHA256()
        )
        return f"{header}.{payload}.{b64(signature)}"

    def client(token: str) -> httpx.Client:
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
            transport=transport,
        )

    def installation_token() -> str:
        if state["token"] and time.time() < state["token_expires_at"] - 60:
            return state["token"]
        github_api = state["api"]
        with client(github_api._app_jwt()) as api:
            response = api.post(
                f"/app/installations/{config.github_installation_id}/access_tokens"
            )
            response.raise_for_status()
            data = response.json()
        state["token"] = data["token"]
        expires = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        state["token_expires_at"] = expires.astimezone(timezone.utc).timestamp()
        logger.info("github installation token refreshed installation=%s", config.github_installation_id)
        return state["token"]

    def request(method: str, path: str, **kwargs) -> httpx.Response:
        start = time.monotonic()
        logger.info("github request start method=%s path=%s", method, path)
        github_api = state["api"]
        with client(github_api.installation_token()) as api:
            response = api.request(method, path, **kwargs)
        logger.info(
            "github request complete method=%s path=%s status=%s elapsed_ms=%s",
            method, path, response.status_code, int((time.monotonic() - start) * 1000),
        )
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

    def get_pages(path: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = request("GET", path, params={"per_page": 100, "page": page}).json()
            if not isinstance(batch, list):
                raise RuntimeError(f"GitHub {path} did not return a list")
            items.extend(batch)
            if len(batch) < 100:
                return items
            page += 1

    def installation() -> dict[str, Any]:
        github_api = state["api"]
        with client(github_api._app_jwt()) as api:
            response = api.get(f"/app/installations/{config.github_installation_id}")
            response.raise_for_status()
            return response.json()

    def repositories() -> list[dict[str, Any]]:
        repositories: list[dict[str, Any]] = []
        page = 1
        while True:
            data = request(
                "GET", "/installation/repositories",
                params={"per_page": 100, "page": page},
            ).json()
            batch = data.get("repositories")
            if not isinstance(batch, list):
                raise RuntimeError("GitHub repository response is invalid")
            repositories.extend(
                repo for repo in batch
                if repository_is_allowed(
                    str(repo.get("full_name") or ""), config.allowed_repositories
                )
            )
            if len(batch) < 100:
                return repositories
            page += 1

    def graphql_context(owner: str, repo: str, pr_number: int):
        query = """query($owner:String!,$repo:String!,$pr:Int!){repository(owner:$owner,name:$repo){pullRequest(number:$pr){closingIssuesReferences(first:10){nodes{number title body}} reviewThreads(first:100){nodes{isResolved isOutdated comments(first:100){nodes{path line author{login} body}}}}}}}"""
        data = request("POST", "/graphql", json={"query": query, "variables": {"owner": owner, "repo": repo, "pr": pr_number}}).json()
        if data.get("errors"):
            raise RuntimeError(f"GitHub GraphQL failed: {data['errors']}")
        pr = data["data"]["repository"]["pullRequest"]
        threads = []
        for thread in pr["reviewThreads"]["nodes"]:
            for comment in thread["comments"]["nodes"]:
                threads.append({"path": comment.get("path"), "line": comment.get("line"), "author": (comment.get("author") or {}).get("login"), "body": comment.get("body") or "", "resolved": thread["isResolved"], "outdated": thread["isOutdated"]})
        issues = [{"number": item.get("number"), "title": item.get("title") or "", "body": (item.get("body") or "")[:ISSUE_BODY_MAX]} for item in pr["closingIssuesReferences"]["nodes"]]
        return threads, issues

    def snapshot(repository: str, pr_number: int) -> dict[str, Any]:
        repository = validate_repo(repository)
        if not repository_is_allowed(repository, config.allowed_repositories):
            raise PermissionError(f"repository is not allowlisted: {repository}")
        owner, repo = repository.split("/", 1)
        prefix = f"/repos/{owner}/{repo}/pulls/{pr_number}"
        meta = request("GET", prefix).json()
        files = get_pages(prefix + "/files")
        commits = get_pages(prefix + "/commits")
        threads, issues = graphql_context(owner, repo, pr_number)
        return {
            "owner": owner, "repo": repo, "pr": pr_number,
            "title": meta.get("title") or "", "body": meta.get("body") or "",
            "author": (meta.get("user") or {}).get("login") or "",
            "base": (meta.get("base") or {}).get("ref") or "",
            "head": (meta.get("head") or {}).get("ref") or "",
            "head_sha": (meta.get("head") or {}).get("sha") or "",
            "state": meta.get("state") or "", "html_url": meta.get("html_url") or "",
            "labels": [label.get("name") for label in meta.get("labels", [])],
            "files": [{"filename": item.get("filename") or "", "status": item.get("status") or "", "additions": item.get("additions") or 0, "deletions": item.get("deletions") or 0, "patch": item.get("patch") or ""} for item in files],
            "commits": [{"sha": item.get("sha") or "", "message": (item.get("commit") or {}).get("message") or "", "author": (((item.get("commit") or {}).get("author") or {}).get("name") or ""), "committed_at": (((item.get("commit") or {}).get("author") or {}).get("date"))} for item in commits],
            "threads": threads, "linked_issues": issues,
        }

    def download_workspace(repository: str, ref: str, target: Path) -> None:
        repository = validate_repo(repository)
        if not repository_is_allowed(repository, config.allowed_repositories):
            raise PermissionError(f"repository is not allowlisted: {repository}")
        response = request("GET", f"/repos/{repository}/zipball/{ref}")
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
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(archive.read(item))

    def publish_preview(repository: str, pr_number: int, head_sha: str, body: str):
        repository = validate_repo(repository)
        if not repository_is_allowed(repository, config.allowed_repositories):
            raise PermissionError(f"repository is not allowlisted: {repository}")
        current = request("GET", f"/repos/{repository}/pulls/{pr_number}").json()
        if (current.get("head") or {}).get("sha") != head_sha:
            raise RuntimeError("stale review: current PR head changed")
        comments = get_pages(f"/repos/{repository}/issues/{pr_number}/comments")
        existing = next((item for item in comments if MARKER in (item.get("body") or "")), None)
        if existing:
            saved = request("PATCH", f"/repos/{repository}/issues/comments/{existing['id']}", json={"body": body}).json()
            action = "updated"
        else:
            saved = request("POST", f"/repos/{repository}/issues/{pr_number}/comments", json={"body": body}).json()
            action = "created"
        readback = request("GET", f"/repos/{repository}/issues/comments/{saved['id']}").json()
        if readback.get("body") != body:
            raise RuntimeError("GitHub comment readback did not match the preview")
        return {"action": action, "comment_id": saved["id"], "url": saved.get("html_url")}

    api = SimpleNamespace(
        _app_jwt=app_jwt,
        installation_token=installation_token,
        _request=request,
        _get_pages=get_pages,
        installation=installation,
        repositories=repositories,
        snapshot=snapshot,
        download_workspace=download_workspace,
        publish_preview=publish_preview,
    )
    state["api"] = api
    return api


def GitHubAppClient(config, *, transport=None):
    """Compatibility factory retained for old imports and tests."""
    return create_client(config, transport=transport)
