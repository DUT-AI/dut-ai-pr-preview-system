from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from src.claims import extract_claims
from src.synthesize import build_comment, build_report
from src.verify import run_verify


def run(request_path: Path, result_path: Path) -> None:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    snapshot = request["snapshot"]
    workspace = Path(request["workspace"]).resolve()
    session_dir = Path(request["session_dir"]).resolve()
    cfg = {
        "provider": "deepseek", "model": request["model"],
        "base_url": request["base_url"],
        # The gateway supplies only a public placeholder for a keyless internal
        # endpoint. A real provider secret is rejected before this process.
        "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
    }
    claims = extract_claims(snapshot, cfg, session_dir)
    findings = run_verify(cfg, workspace, session_dir, snapshot, claims)
    (session_dir / "findings.json").write_text(
        json.dumps(findings, indent=2), encoding="utf-8"
    )
    report = build_report(snapshot, claims, findings, [], session_dir)
    preview = build_comment(snapshot, claims, findings, [], report_content=report)
    result_path.write_text(json.dumps({
        "findings": findings, "report": report, "preview_comment": preview,
    }), encoding="utf-8")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: python -m src.engine.runner REQUEST RESULT")
    run(Path(sys.argv[1]), Path(sys.argv[2]))


if __name__ == "__main__":
    main()
