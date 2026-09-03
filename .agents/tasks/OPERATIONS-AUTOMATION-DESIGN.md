# Operations, Automation and Recovery Design

## Chế độ triển khai

### Phase 1 — Static/local only

- Review source và chạy unit test không network.
- Không provider key, không `gh auth`, không comment.
- Mục tiêu: đóng security baseline và platform compatibility.

### Phase 2 — Test repository manual

- GitHub bot riêng, repo thử nghiệm, quyền tối thiểu.
- `default_mode: manual`, `post_comment: false`.
- Chạy `--dry-run`, kiểm report local, sau đó mới cho phép một comment thử.

### Phase 3 — Controlled autoreview

- Chỉ allowlist repository.
- `max_parallel: 1`, quota/budget thấp, timeout rõ ràng.
- Theo dõi failed/interrupted review và không retry vô hạn.

### Phase 4 — Hosted dashboard

- Chỉ mở sau authentication, authorization, CSRF và path confinement.
- Reverse proxy/TLS không thay thế app authentication.

## Recovery

- `sessions/` là artifact có thể backup; không chứa provider secret.
- Trước re-review, giữ snapshot/report vòng trước hoặc version theo round.
- Interrupted review phải để lại trạng thái thất bại rõ, không đọc part file cũ.
- Restore cần kiểm head SHA để không đăng report cũ lên commit mới.

## Dừng khẩn cấp

1. Tắt poller/dashboard process.
2. Thu hồi hoặc rotate GitHub/provider credential nếu nghi lộ.
3. Đặt mọi repo về manual/no-post.
4. Giữ log/session làm bằng chứng; không xóa trước audit.
