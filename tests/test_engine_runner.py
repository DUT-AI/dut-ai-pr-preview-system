from __future__ import annotations

import json

from src.engine import runner


def test_runner_connects_claims_verify_report_and_preview(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    session_dir = tmp_path / "session"
    workspace.mkdir()
    session_dir.mkdir()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    snapshot = {"head_sha": "a" * 40, "files": [], "commits": []}
    request_path.write_text(json.dumps({
        "snapshot": snapshot, "workspace": str(workspace),
        "session_dir": str(session_dir), "base_url": "http://llm/v1",
        "model": "gemma",
    }), encoding="utf-8")
    calls = []

    def extract(received_snapshot, cfg, received_session):
        calls.append(("claims", received_snapshot, cfg, received_session))
        return [{"id": "C1", "source": "inferred"}]

    def verify(cfg, received_workspace, received_session, received_snapshot, claims):
        calls.append(("verify", cfg, received_workspace, received_session,
                      received_snapshot, claims))
        return {
            "claims": [], "docs": [], "impact": [], "threads": [],
            "unresolved_questions": [],
        }

    monkeypatch.setenv("DEEPSEEK_API_KEY", "public-placeholder")
    monkeypatch.setattr(runner, "extract_claims", extract)
    monkeypatch.setattr(runner, "run_verify", verify)
    monkeypatch.setattr(runner, "build_report", lambda *args: "report")
    monkeypatch.setattr(runner, "build_comment", lambda *args, **kwargs: "preview")

    runner.run(request_path, result_path)

    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["report"] == "report"
    assert result["preview_comment"] == "preview"
    assert calls[0][0] == "claims"
    assert calls[0][2] == {
        "provider": "deepseek", "model": "gemma",
        "base_url": "http://llm/v1", "api_key": "public-placeholder",
    }
    assert calls[1][0] == "verify"
    assert (session_dir / "findings.json").exists()
