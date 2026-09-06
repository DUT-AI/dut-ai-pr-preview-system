# WI-WEB-002 — Dashboard và review detail rõ ràng hơn

## Parent

- Initiative: INIT-04/05
- Owner: Codex
- Status: Done
- Priority: P1

## Problem

Dashboard hiện khó quét nhanh, còn trang run chỉ hiện report dạng text nên người vận hành
không thấy trực tiếp các bảng nhận xét mà GitHub comment sẽ chứa.

## Scope

### In

- Làm mới landing page, dashboard, repository và run detail.
- Hiện findings theo claims/docs/impact/threads và nội dung comment GitHub nguyên bản.
- Thêm link tới comment đã publish khi có audit thành công.
- Test phần trình bày và escaping dữ liệu không tin cậy.

### Out

- Không đổi pipeline review, schema database hoặc marker comment.
- Không tự bật publish hay đăng comment GitHub.

## Acceptance criteria

- [x] Các trang responsive, có trạng thái trống và điều hướng rõ ràng.
- [x] Run detail hiện bảng findings và exact preview đã persist.
- [x] Nội dung PR/model được HTML-escape, không render bằng `safe`.
- [x] Compile, pytest và `git diff --check` đều pass.

## Security and external effects

- Dữ liệu không tin cậy: PR title/body, findings, report và preview comment.
- Credential cần dùng: không thêm credential mới.
- GitHub/model/network side effect: push/PR/review/deploy theo yêu cầu người dùng; publish giữ tắt.
- Cách chạy an toàn đầu tiên: test local với store giả, sau đó Compose scope đúng project.

## Verification

```text
python -m compileall src app
python -m pytest -v
git diff --check
```

## Evidence

- `python -m compileall src app`: pass.
- Docker dev từ `.env.local`: web/PostgreSQL/worker healthy; `127.0.0.1:3636/healthz` trả `ok`.
- `python -m pytest -q` trong container Linux: 293 passed.
- Test web riêng: 5 passed, gồm structured findings và escaping exact preview.
- `git diff --check`: pass.

## Rollback/recovery

- Revert commit UI; không có migration dữ liệu.
