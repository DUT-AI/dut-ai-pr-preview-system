"""E2E runs the full pipeline via --fixtures (no gh/model calls)."""
import json
import subprocess
import sys
from pathlib import Path

FIXTURES = {
    "snapshot.json": {
        "owner": "demo", "repo": "app", "pr": 7, "title": "Add checkout",
        "body": "Adds checkout. Fixes retry.", "author": "dev1",
        "base": "main", "head": "feature/x", "labels": ["feature"],
        "files": [{"filename": "src/checkout.py", "status": "added",
                   "additions": 10, "deletions": 0, "patch": ""}],
        "commits": [{"sha": "a", "message": "feat"}],
        "threads": [{"path": "src/checkout.py", "line": 1, "author": "r",
                     "body": "check validation", "resolved": False,
                     "outdated": False}],
    },
    "claims.json": [
        {"id": "C1", "text": "Adds checkout", "category": "feature",
         "files": ["src/checkout.py"], "docs": []},
    ],
    "findings.json": {
        "claims": [{"id": "C1", "status": "PASS",
                    "evidence": ["src/checkout.py:1"], "note": ""}],
        "docs": [{"path": "docs/checkout.md", "status": "WRONG",
                  "what": "doc says X, code does Y"}],
        "impact": [{"requirement": "REQ-1", "impact": "CHANGED", "detail": "d"}],
        "threads": [{"text": "check validation", "status": "STILL_VALID",
                     "note": "not fixed yet"}],
        "unresolved_questions": ["Is the checkout doc wrong?"],
    },
}


def test_e2e_fixtures(tmp_path):
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    for name, data in FIXTURES.items():
        (fixtures / name).write_text(json.dumps(data))

    env = {"PYTHONPATH": "src", "DSH_SESSION_ROOT": str(tmp_path / "sessions")}
    proc = subprocess.run(
        [sys.executable, "-m", "src.run", "demo/app", "7",
         "--fixtures", str(fixtures), "--no-post", "--skip-human"],
        capture_output=True, text=True, encoding="utf-8", env=env,
        cwd=Path(__file__).resolve().parents[1])
    assert proc.returncode == 0, proc.stderr

    report = Path(env["DSH_SESSION_ROOT"]) / "demo" / "app" / "pr-7" / "report.md"
    text = report.read_text(encoding="utf-8")
    assert "## Đánh giá" in text
    assert "docs/checkout.md" in text
    assert "REQ-1" in text
    assert "SKIPPED" in text
