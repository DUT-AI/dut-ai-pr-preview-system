from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from src.engine.contracts import ReviewResult
from src.process_control import process_group_options, stop_process_tree


# dsh-llm-deepseek validates that a bearer credential exists before it sends
# any request. The configured internal llama.cpp endpoint is intentionally
# keyless, so use a public placeholder rather than exposing an application
# secret to the terminal-capable Harness.
KEYLESS_API_TOKEN = "dut-ai-keyless-endpoint"


class SubprocessReviewEngine:
    """Run Harness without inheriting GitHub, database, or web secrets."""

    def __init__(self, *, base_url: str, model: str, api_key: str = ""):
        self.base_url = base_url
        self.model = model
        self.api_key = api_key

    def _environment(self) -> dict[str, str]:
        # A future authenticated LLM needs a credential broker/sandbox. The
        # terminal-capable Harness must not receive a provider API key.
        if self.api_key:
            raise RuntimeError(
                "LLM_API_KEY cannot be exposed to Harness; configure a keyless "
                "internal endpoint or add a credential-isolating proxy"
            )
        project_root = str(Path(__file__).resolve().parents[2])
        allowed = {
            name: os.environ[name]
            for name in (
                "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE",
                "HOME", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR",
            )
            if name in os.environ
        }
        allowed.update({
            "PYTHONPATH": project_root,
            "HARNESS_PROVIDER": "deepseek",
            "DEEPSEEK_BASE_URL": self.base_url,
            "DEEPSEEK_API_KEY": KEYLESS_API_TOKEN,
            "DSH_MODEL": self.model,
            "PYTHONUNBUFFERED": "1",
            "PYTHONUTF8": "1",
        })
        return allowed

    def review(self, snapshot: dict, workspace: Path, session_dir: Path) -> ReviewResult:
        request_path = session_dir / "engine-request.json"
        result_path = session_dir / "engine-result.json"
        request_path.write_text(json.dumps({
            "snapshot": snapshot,
            "workspace": str(workspace.resolve()),
            "session_dir": str(session_dir.resolve()),
            "base_url": self.base_url,
            "model": self.model,
        }), encoding="utf-8")
        command = [
            sys.executable, "-m", "src.engine.runner", str(request_path),
            str(result_path),
        ]
        log_path = session_dir / "engine.log"
        with log_path.open("w", encoding="utf-8", buffering=1) as log:
            process = subprocess.Popen(
                command, cwd=Path(__file__).resolve().parents[2],
                env=self._environment(), stdout=log, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                **process_group_options(),
            )
            try:
                return_code = process.wait(timeout=1800)
            except subprocess.TimeoutExpired as exc:
                log.write("\n[engine] timed out after 1800 seconds; stopping process tree\n")
                stop_process_tree(process)
                raise RuntimeError(
                    "review engine timed out after 1800 seconds; see engine.log"
                ) from exc
            except BaseException:
                log.write("\n[engine] interrupted; stopping process tree\n")
                stop_process_tree(process)
                raise
        if return_code != 0:
            raise RuntimeError(
                f"review engine exited {return_code}; see engine.log"
            )
        if not result_path.exists():
            raise RuntimeError("review engine exited without engine-result.json")
        data = json.loads(result_path.read_text(encoding="utf-8"))
        return ReviewResult(
            findings=data["findings"], report=data["report"],
            preview_comment=data["preview_comment"],
            session_path=str(session_dir),
        )
