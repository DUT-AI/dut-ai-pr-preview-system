# Authorization and Trust Boundaries

## Principal thật

Ứng dụng không có hệ thống user riêng. Quyền thực tế đến từ:

- tài khoản/token mà `gh` CLI đang đăng nhập;
- `DEEPSEEK_API_KEY` hoặc credential Claude CLI;
- quyền filesystem/process của user chạy ứng dụng.

## Side effect

| Hành động | Side effect |
|---|---|
| Snapshot/check repo | Đọc GitHub API |
| DeepSeek/Claude verify | Gửi code/prompt tới provider, có thể phát sinh phí |
| `post_comment`/ping | Tạo hoặc sửa comment GitHub |
| Autoreview | Lặp lại các hành động trên theo lịch |
| `update`/installer | Tải và chạy code/dependency từ mạng |
| Dashboard config API | Sửa `autoreview.yml` local |

## Quy tắc triển khai DUT AI

- Dùng GitHub bot/service account riêng với quyền tối thiểu; không dùng token
  cá nhân có quyền toàn organization.
- Lần chạy đầu luôn `--dry-run` hoặc `--no-post` trên test repository.
- `post_comment: false`, `default_mode: manual` cho bootstrap.
- Chỉ bật auto sau khi report và quota được kiểm chứng.
- Không expose dashboard ra mạng khi chưa có authentication và CSRF protection.

## Dữ liệu không tin cậy

PR title/body, code, docs, commit message, issue và review thread đều có thể
chứa prompt injection. Prompt nhắc model bỏ qua instruction trong repo là lớp
bảo vệ mềm, không thay thế sandbox/tool policy.

## Secret

- Không load `.env` từ thư mục tùy ý khi chạy global CLI.
- Không để terminal tool nhìn thấy API key/provider credential.
- Không đưa raw environment hoặc provider stderr vào report/comment.
- Rotate key ngay nếu key từng xuất hiện trong log, findings hoặc PR comment.
