# WI-WEB-003 — Lịch sử Pull Request theo repository

## Parent

- Initiative: INIT-04/05
- Owner: Codex
- Status: Done
- Priority: P1

## Problem

Trang repository hiện chỉ dẫn thẳng tới review run mới nhất. Người vận hành
không có một trang riêng cho từng Pull Request để xem toàn bộ lịch sử run, job,
commit và trạng thái publish đã được hệ thống ghi nhận.

## Scope

### In

- Đổi danh sách repository thành danh sách PR đã được hệ thống nhận và persist.
- Persist trạng thái `closed`/`merged` mà không enqueue review thừa.
- Thêm trang lịch sử riêng cho từng PR.
- Hiện tất cả review run, job, commit và trạng thái publish của PR.
- Cho phép đi từ repository → PR history → run detail và quay lại đúng tầng.

### Out

- Không đồng bộ ngược toàn bộ lịch sử PR từ GitHub.
- Không đổi schema, review engine, webhook contract hoặc comment marker.
- Không tự động publish comment.

## Acceptance criteria

- [x] Mỗi PR trong trang repository mở được trang lịch sử riêng.
- [x] Trang PR hiện mọi run đã persist, kể cả run cũ hơn run mới nhất.
- [x] Trạng thái published/preview và số findings được trình bày rõ ràng.
- [x] Route validate repository và PR number trước khi đọc dữ liệu.
- [x] Webhook đóng/merge cập nhật history nhưng không tạo review job mới.
- [x] Test, compileall và `git diff --check` pass.

## Security and external effects

- PR/model output vẫn là dữ liệu không tin cậy và được Jinja escape.
- Thay đổi UI/SQL read-only, không thêm credential và không tự gọi GitHub/model.
- Publish chỉ xảy ra qua action hiện có khi operator chủ động cho phép.

## Verification

```text
python -m compileall src app
python -m pytest -v
git diff --check
```

## Evidence

- Focused web tests: 7 passed trên Windows.
- Full checkout hiện tại trong Linux development image: 296 passed.
- Focused webhook/web tests: 15 passed, gồm `closed` state-only và navigation.
- PostgreSQL local query trả lịch sử PR #4 (3 runs) và PR #5 (1 run).
- `python -m compileall src app` và `git diff --check`: pass.
- Live PR, server và GitHub comment evidence được ghi bổ sung sau deployment.

## Rollback/recovery

- Revert commit UI/history; không có migration dữ liệu.
