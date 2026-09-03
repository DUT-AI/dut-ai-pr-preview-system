# Static Security Baseline — 2026-08-26

Phạm vi: source, scripts, config, dashboard, dependency metadata và installed
SDK source có sẵn. Không chạy model, GitHub API, installer, dependency audit
online hoặc binary runtime.

## Kết luận

Code không có dấu hiệu đơn giản của malware/hijack như Git hook, `shell=True`,
PowerShell payload hoặc autostart Windows. Tuy nhiên **chưa an toàn để bật
production/hosted autoreview** vì còn các trust-boundary blocker dưới đây.

## P0 — phải đóng trước khi dùng credential thật

### SEC-01: CWD `.env` có thể điều khiển endpoint trước home config

`src/config.py` đọc `./.env` trước home config của DUT AI (và legacy upstream),
và giá trị đầu tiên thắng. Nếu CLI được chạy từ thư mục không tin cậy, file `.env` tại đó có
thể đặt `DEEPSEEK_BASE_URL`; API key từ home file sau đó có thể được gửi tới
endpoint sai. Chỉ load file config explicit/trusted và test precedence.

### SEC-02: DeepSeek runtime kế thừa toàn bộ environment

Installed SDK tạo environment bằng `os.environ.copy()`. Cordis config cấp
persistent Bash tool cho agent. Chưa có bằng chứng terminal tool bị strip
`DEEPSEEK_API_KEY`/credential. Cần enforce secret isolation ở process/tool
boundary và có prompt-injection regression trước khi đưa key thật.

## P1 — blocker cho hosted/organization use

### SEC-03: Dashboard có state-changing API nhưng không authentication

API có thể sửa `autoreview.yml` và trigger review có khả năng đăng GitHub
comment. Bind mặc định `127.0.0.1` giảm exposure, nhưng không được reverse proxy
hoặc bind public trước auth, CSRF và authorization.

### SEC-04: HTTP owner/repo chưa validate trước khi ghép filesystem path

Web route dùng trực tiếp `owner`/`repo` để tạo/đọc dưới `DSH_SESSION_ROOT`, khác
CLI vốn có parser allowlist. Cần reject traversal/encoded separator và xác minh
resolved path vẫn nằm trong session root.

### SEC-05: External write bật mặc định

`post_comment` và `ping_comment` mặc định true. Lần adoption đầu phải dùng
manual + no-post/dry-run và bot token quyền tối thiểu.

### SEC-06: Runtime dependency còn prerelease và không có Windows wheel

Lock dùng `deepseek-harness-sdk/runtime-bin 0.1.1rc1`; runtime wheel chỉ có
macOS ARM và Linux. Windows hiện không phải platform được chứng minh hỗ trợ.

## P2 — hardening

### SEC-07: Self-update và one-line installer dùng nguồn mutable

`update`/`install.sh` tải từ branch GitHub và cài trực tiếp. Production nên pin
tag/commit, kiểm hash/signature và review release trước rollout.

### SEC-08: Xóa repo config theo basename có thể xóa nhầm owner

`remove_repo` fallback so sánh phần basename; hai owner cùng tên repo có thể bị
xóa ngoài ý muốn. Chỉ xóa exact resolved key.

## Điểm tích cực đã thấy

- `subprocess` chủ yếu dùng argv list; không thấy `shell=True`.
- CLI owner/repo có regex allowlist.
- YAML dùng `safe_load` và config write atomic.
- GitHub comment body đi qua temporary file, không shell interpolate.
- Prompt verify đánh dấu PR content là untrusted.
- Claude backend giới hạn tool và bỏ project settings trong reviewed repo.

## Chưa xác minh

- Nội dung/runtime binary DeepSeek vì binary Windows không có và không được chạy.
- CVE/advisory hiện tại của dependency bằng scanner online.
- Prompt-injection containment thực tế.
- GitHub permission behavior với bot/token thật.
- Unit/integration test sau rebrand.
