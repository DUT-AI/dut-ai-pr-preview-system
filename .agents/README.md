# DUT AI PR Preview System — Agent Knowledge Hub

`.agents/` chứa context ngắn gọn, đúng repository cho coding agent và thành
viên DUT AI Club. Code, test và bằng chứng chạy hiện tại vẫn là nguồn sự thật.

## Đọc theo nhu cầu

| Nhu cầu | Tài liệu |
|---|---|
| Mọi task | Root [`AGENTS.md`](../AGENTS.md) → [`tasks/BOARD.md`](tasks/BOARD.md) |
| Hướng thiết kế đang thảo luận | [`memories/README.md`](memories/README.md) |
| Hiểu module và pipeline | [`architecture/CODEBASE.md`](architecture/CODEBASE.md) |
| Secret, GitHub và prompt injection | [`architecture/AUTHORIZATION.md`](architecture/AUTHORIZATION.md) |
| Sửa code/test | [`workflows/DELIVERY.md`](workflows/DELIVERY.md) |
| Audit dashboard/API | [`workflows/API-SECURITY-TESTING.md`](workflows/API-SECURITY-TESTING.md) |
| Baseline an toàn hiện tại | [`reviews/SECURITY-BASELINE.md`](reviews/SECURITY-BASELINE.md) |
| Mục tiêu dài hạn | [`tasks/ROADMAP.md`](tasks/ROADMAP.md) |
| Vận hành autoreview | [`tasks/OPERATIONS-AUTOMATION-DESIGN.md`](tasks/OPERATIONS-AUTOMATION-DESIGN.md) |

## Nguồn sự thật

| Loại | Nguồn chính |
|---|---|
| Package, dependency, entry point | `pyproject.toml`, `uv.lock` |
| CLI/pipeline | `src/run.py`, `src/snapshot.py`, `src/claims.py`, `src/verify.py` |
| GitHub side effect | `src/gh.py`, `src/synthesize.py`, `src/autoreview.py` |
| Hosted app | `app/server/controller.py`, `services.py`, `repositories.py`, `app/ui/` |
| Test contract | `tests/` |
| Runtime output | `sessions/` local, không phải source |

## Quy tắc

- Không chép knowledge hub từ project khác.
- Không lưu secret hoặc nội dung `.env` thật.
- Không biến review tĩnh thành cài đặt/chạy model.
- Ghi rõ điều đã xác minh và điều mới chỉ suy luận từ code.
