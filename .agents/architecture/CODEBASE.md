# Codebase Map

## Luồng chính

```text
GitHub App webhook / worker
  -> snapshot GitHub metadata + diff into PostgreSQL
  -> extract claims
  -> clone PR head vào workspace disposable
  -> verify theo claims / docs / requirement impact
  -> human gate
  -> report local
  -> optional GitHub comment + round ping
```

## Module

| Module | Trách nhiệm |
|---|---|
| `src/run.py` | CLI và orchestration 5 phase |
| `src/config.py` | Environment/provider/session config |
| `src/gh.py` | Wrapper `gh` CLI |
| `src/snapshot.py` | PR metadata, files, commits, issues, review threads |
| `src/claims.py` | Claim extraction và no-description fallback |
| `src/verify.py` | Workspace, agent fan-out, merge/validate findings |
| `src/claude_cli.py` | Backend Claude Code headless |
| `src/synthesize.py` | Report và GitHub comments |
| `src/autoreview.py` | Poller và parallel review dispatch |
| `src/agent_pool.py` | Global model-agent concurrency slots |
| `src/engine/` | Gateway/runner cô lập engine review từ app secrets |
| `app/server/controller.py` | FastAPI admin UI, webhook và API routes |
| `app/server/services.py` | Webhook, job orchestration và publication policy |
| `app/server/repositories.py` | GitHub App client và PostgreSQL store |
| `app/server/config.py` | Cấu hình server chỉ đọc từ process environment |
| `app/server/models.py`, `schema.sql` | Data objects và một schema PostgreSQL |
| `app/ui/` | Jinja templates và CSS |
| `app/worker.py` | Worker nhận job PostgreSQL và gọi review engine |

## Persistence

- PostgreSQL giữ installation, repository, PR, delivery, job, run và publish audit.
- `sessions/<owner>/<repo>/pr-<n>/` giữ artifact engine và log dung lượng lớn.
- `.env` chứa cấu hình runtime local, bị Git ignore và không được commit.

## Provider

- `deepseek`: DeepSeek Harness SDK + Cordis runtime.
- `claude`: gọi `claude -p` với tool list bị giới hạn.
- Codex/Antigravity hiện là công cụ phát triển bên ngoài, không phải provider
  runtime được code hỗ trợ.

## Platform hiện tại

- Python package yêu cầu 3.10+; Docker runtime pin Python 3.12 trên Debian Bookworm.
- Runtime đích là Linux container cho cả development và production.
- `deepseek-harness-runtime-bin 0.1.2a3` không dùng native Windows; không dùng
  `.venv` Windows để chứng minh engine production.
