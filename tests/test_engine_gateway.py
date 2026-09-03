from __future__ import annotations

import json
import subprocess
import sys

import pytest

from src.engine.gateway import KEYLESS_API_TOKEN, SubprocessReviewEngine


def test_harness_environment_excludes_application_secrets(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "hook")
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("DATABASE_URL", "postgresql://secret")
    env = SubprocessReviewEngine(
        base_url="https://llm2.dutai.site/v1", model="gemma"
    )._environment()
    assert "GITHUB_WEBHOOK_SECRET" not in env
    assert "GITHUB_APP_ID" not in env
    assert "DATABASE_URL" not in env
    assert env["DEEPSEEK_BASE_URL"] == "https://llm2.dutai.site/v1"
    assert env["DEEPSEEK_API_KEY"] == KEYLESS_API_TOKEN


def test_harness_refuses_provider_key_until_isolated():
    engine = SubprocessReviewEngine(
        base_url="https://llm2.dutai.site/v1", model="gemma", api_key="secret"
    )
    with pytest.raises(RuntimeError, match="cannot be exposed"):
        engine._environment()


def test_review_runs_the_engine_contract_and_reads_result(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    session_dir = tmp_path / "session"
    workspace.mkdir()
    session_dir.mkdir()
    seen = {}

    class Process:
        def __init__(self, command, **kwargs):
            seen["command"] = command
            seen["kwargs"] = kwargs
            result_path = command[-1]
            with open(result_path, "w", encoding="utf-8") as result:
                json.dump({
                    "findings": {"claims": []}, "report": "report",
                    "preview_comment": "preview",
                }, result)

        def wait(self, timeout=None):
            seen["timeout"] = timeout
            return 0

    monkeypatch.setattr("src.engine.gateway.subprocess.Popen", Process)
    output = SubprocessReviewEngine(
        base_url="https://llm2.dutai.site/v1", model="gemma"
    ).review({"head_sha": "a" * 40}, workspace, session_dir)

    assert output.report == "report"
    assert output.preview_comment == "preview"
    assert seen["command"][:3] == [
        sys.executable, "-m", "src.engine.runner"
    ]
    assert seen["kwargs"]["stdin"] is subprocess.DEVNULL
    assert seen["timeout"] == 1800


def test_review_interrupt_stops_engine_process_tree(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    session_dir = tmp_path / "session"
    workspace.mkdir()
    session_dir.mkdir()
    seen = {"waits": 0, "stopped": False}

    class Process:
        pid = 12345

        def __init__(self, _command, **_kwargs):
            pass

        def wait(self, timeout=None):
            seen["waits"] += 1
            if seen["waits"] == 1:
                raise KeyboardInterrupt
            return 130

    monkeypatch.setattr("src.engine.gateway.subprocess.Popen", Process)
    monkeypatch.setattr(
        "src.engine.gateway.stop_process_tree",
        lambda process: seen.__setitem__("stopped", True),
    )
    engine = SubprocessReviewEngine(base_url="http://llm/v1", model="gemma")

    with pytest.raises(KeyboardInterrupt):
        engine.review({"head_sha": "a" * 40}, workspace, session_dir)

    assert seen["stopped"]
    assert "stopping process tree" in (session_dir / "engine.log").read_text()
