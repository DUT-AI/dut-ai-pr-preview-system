# WI-OPS-002 - Khởi chạy server, kiểm webhook, và merge có guard từ dev1 vào dev

## Parent

- Initiative: INIT-04, INIT-05, INIT-08
- Owner: DUT AI Club
- Status: ready
- Priority: P0

## Problem

Khi có mạng và người dùng bảo khởi chạy, agent cần thực hiện đúng một quy
trình vận hành trên server thay vì tự suy diễn. Việc này có side effect thật:
SSH vào server, dùng runtime env thật, start Docker stack, nhận webhook GitHub,
có thể gọi model và merge nhanh `dev1` vào `dev` nếu hệ thống chạy được.

Work item này là runbook để "đọc và làm" khi được giao. Không thực hiện trước
khi người dùng ra lệnh rõ ràng trong turn hiện tại.

## Scope

### In

- SSH vào server đã được người dùng chỉ định hoặc đã có alias hợp lệ trong máy.
- Tìm đúng folder repository/runtime tương ứng với DUT AI PR Preview System.
- Ghi nhận trạng thái hiện có trên server trước khi sửa: branch, commit, file
  compose, ignored env/secrets presence, container, volume, port binding, webhook
  URL và health endpoints nếu có.
- Gắn đúng env/runtime config từ file sẵn có trên server, không in secret ra log.
- Kiểm tra port có đúng yêu cầu không, ưu tiên bind web vào loopback sau reverse
  proxy/tunnel nếu chưa có auth/edge protection mới.
- Build/start Docker Compose cho `postgres`, `web`, `worker`.
- Kiểm tra Docker/container health, DB có đọc được, web health, dashboard login
  hoặc UI render, và webhook endpoint.
- Khi stack đã chạy được, merge `dev1` vào `dev` bằng head guard hoặc merge
  strategy được người dùng chấp thuận.
- Kiểm tra sau merge bằng web UI hoặc signed webhook/test PR delivery tùy mức
  an toàn có sẵn.
- Cập nhật Evidence trong task này bằng kết quả thật sau khi làm.

### Out

- Không deploy public/reverse proxy mới nếu chưa có yêu cầu riêng.
- Không thay đổi GitHub App permissions, webhook URL, DNS, Cloudflare, Nginx hay
  tunnel nếu chưa được yêu cầu rõ.
- Không đăng/sửa GitHub comment review nếu người dùng chưa cho phép trong turn
  đó; `PUBLISH_ENABLED=false` là mặc định an toàn.
- Không xóa volume PostgreSQL/session, không `docker compose down -v`.
- Không push/merge branch nào khác ngoài `dev1` vào `dev`.
- Không commit secret, không in nội dung `.env`, PEM, token, password hash.

## Trạng thái đã biết trước khi SSH

- Theo `WI-MVP-001`, ngày 2026-09-03/2026-09-04 đã từng có live pipeline:
  webhook GitHub -> PostgreSQL -> Harness/LLM -> persisted preview -> GitHub App
  comment. PR #1 `dev1 -> dev` đã merge bằng head guard thành commit
  `7a30cabac2b3b3c6aef5ffa77032234977d3b398` trong đợt E2E cũ.
- Theo `WI-E2E-002`, PR #2 `dev -> main` đã được live review, publish một
  comment bot, đọc lại độc lập, merge thành commit `1c235465`; sau đó local và
  remote `dev`/`dev1` được ghi nhận là absent, web và PostgreSQL còn healthy,
  worker stopped để dashboard inspection.
- Theo checkout hiện tại, `docker-compose.yml` truyền env mặc định:
  `GITHUB_ALLOWED_REPOSITORIES=DUT-AI/dut-ai-pr-preview-system`,
  `LLM_BASE_URL=https://llm2.dutai.site/v1`,
  `LLM_MODEL=ggml-org/gemma-4-e4b-it-GGUF:Q4_0`,
  `PUBLISH_ENABLED=false`, `DSH_SESSION_ROOT=/data/sessions`.
- Theo evidence cũ, runtime dev từng dùng `PUBLIC_BASE_URL=https://fairinsight.luongduytoan.io.vn`
  và `WEB_PORT=8000`; giá trị trên server cần đọc lại, không được coi là hiện
  trạng nếu chưa SSH kiểm tra.
- Chưa có evidence trong task này về server folder hiện tại, container hiện tại,
  port hiện tại, webhook URL hiện tại, branch `dev1` hiện tại, hay khả năng UI
  sau merge mới. Các mục đó phải được xác minh live khi task được kích hoạt.

## Acceptance criteria

- [ ] Agent đọc task này, `AGENTS.md`, `.agents/README.md`, `.agents/tasks/BOARD.md`
      và code/runtime liên quan trước khi thực hiện.
- [ ] SSH target và repository folder trên server được xác định bằng lệnh read-only
      trước khi chạy build/start.
- [ ] Trạng thái ban đầu được ghi lại: `pwd`, `git status --short`, branch/commit,
      `docker compose config --services`, `docker compose ps`, port binding và
      env key names cần thiết. Secret values không được hiển thị.
- [ ] Runtime env được gắn đúng từ file/server config tương ứng; các key bắt buộc
      được kiểm tra theo tên, không log giá trị secret.
- [ ] Port public/internal khớp yêu cầu trong `.env`/compose/reverse proxy và
      `/healthz` trả thành công trên endpoint phù hợp.
- [ ] Docker stack `postgres`, `web`, `worker` build/start thành công và health
      không bị restart loop.
- [ ] Webhook endpoint được kiểm tra tối thiểu bằng unsigned negative test `403`
      và, nếu có webhook secret trong runtime, signed synthetic `ping` hoặc
      GitHub redelivery trả `200`/`202` theo event.
- [ ] Chỉ merge `dev1` vào `dev` sau khi stack chạy và branch/head được đọc lại.
- [ ] Sau merge, web UI hoặc webhook/test PR proof cho thấy app vẫn chạy đúng,
      job/run không stale head, và DB/audit không có duplicate bất thường.
- [ ] Kết quả thật, lệnh chính và bằng chứng commit/container/URL được ghi vào
      Evidence của task này.

## Security and external effects

- Dữ liệu không tin cậy: PR title/body, commit message, diff, review threads,
  webhook payload, file trên branch `dev1`.
- Credential cần dùng: SSH key/session, ignored `.env` trên server, GitHub App
  private key, webhook secret, admin/session secret, PostgreSQL password, optional
  LLM key nếu server dùng endpoint có auth.
- GitHub/model/network side effect: SSH vào server, Docker build/start, webhook
  delivery/redelivery, có thể gọi LLM nếu worker xử lý job, merge `dev1` vào
  `dev`; publish comment chỉ khi được cho phép riêng.
- Cách chạy an toàn đầu tiên: read-only inventory -> start stack với
  `PUBLISH_ENABLED=false` -> health/UI/webhook smoke -> head-guard merge ->
  post-merge UI/webhook proof.

## Runbook chi tiết

### 0. Activation gate

Chỉ bắt đầu khi người dùng nói rõ rằng hãy đọc task này và làm. Nếu yêu cầu
chưa nêu SSH target hoặc folder, tìm alias/path bằng read-only command; nếu vẫn
không xác định được thì hỏi một câu ngắn.

### 1. Preflight local trước khi SSH

```text
git status --short
git branch --show-current
git rev-parse HEAD
git remote -v
```

Mục tiêu là biết checkout local đang ở đâu, không sửa local dirty changes không
liên quan.

### 2. SSH và tìm đúng folder server

```text
ssh <target> 'pwd; hostname; id; find ~/ /opt /srv -maxdepth 4 -type d -name ".git" 2>/dev/null | sed "s#/.git$##" | grep -Ei "dut-ai|pr-preview|preview-system"'
```

Nếu đã có đường dẫn ứng viên:

```text
ssh <target> 'cd <repo_dir> && pwd && git remote -v && git status --short && git branch --show-current && git rev-parse HEAD'
```

Không chạy `git pull`, build, merge hay compose trước khi đúng repo.

### 3. Kiểm kê runtime hiện tại mà không lộ secret

```text
ssh <target> 'cd <repo_dir> && ls -la && test -f docker-compose.yml && docker compose config --services'
ssh <target> 'cd <repo_dir> && if test -f .env; then cut -d= -f1 .env | sed "/^#/d;/^$/d"; else echo "NO_ENV_FILE"; fi'
ssh <target> 'cd <repo_dir> && test -f secrets/github-app.pem && echo "PEM_PRESENT" || echo "PEM_MISSING"'
ssh <target> 'cd <repo_dir> && docker compose ps'
ssh <target> 'cd <repo_dir> && docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'
```

Nếu cần đọc port mà không lộ secret:

```text
ssh <target> 'cd <repo_dir> && awk -F= "/^(WEB_PORT|WEB_INTERNAL_PORT|PUBLIC_BASE_URL|POSTGRES_HOST|POSTGRES_INTERNAL_PORT|PUBLISH_ENABLED)=/ {print \$1\"=\"\$2}" .env 2>/dev/null'
```

### 4. Kiểm tra env key bắt buộc và contract port

Các tên env key bắt buộc cho production Compose:

```text
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_DB
GITHUB_APP_ID
GITHUB_INSTALLATION_ID
GITHUB_WEBHOOK_SECRET
ADMIN_PASSWORD_HASH
SESSION_SECRET
```

Các giá trị default/runtime cần kiểm tra bằng tên hoặc output không chứa secret:

```text
GITHUB_ALLOWED_REPOSITORIES default: DUT-AI/dut-ai-pr-preview-system
GITHUB_PRIVATE_KEY_FILE default: ./secrets/github-app.pem
GITHUB_PRIVATE_KEY_PATH default: /run/secrets/github-app.pem
LLM_BASE_URL default: https://llm2.dutai.site/v1
LLM_MODEL default: ggml-org/gemma-4-e4b-it-GGUF:Q4_0
PUBLISH_ENABLED safe default: false
DSH_SESSION_ROOT default: /data/sessions
```

Kiểm tra port:

```text
ssh <target> 'cd <repo_dir> && docker compose config | grep -nE "published|target|WEB_PORT|WEB_INTERNAL_PORT"'
ssh <target> 'ss -ltnp 2>/dev/null | grep -E "(:8000|:<expected_port>)" || true'
```

Nếu dashboard chưa được production-auth/edge hardening mới, giữ bind loopback
hoặc chỉ expose qua reverse proxy/tunnel đã kiểm soát.

### 5. Build và start Docker

```text
ssh <target> 'cd <repo_dir> && docker compose build'
ssh <target> 'cd <repo_dir> && docker compose up -d postgres web worker'
ssh <target> 'cd <repo_dir> && docker compose ps'
ssh <target> 'cd <repo_dir> && docker compose logs --tail=120 web worker postgres'
```

Nếu container restart loop, dừng lại ở bước diagnose log/config; không merge.

### 6. Smoke test health, UI và webhook

Health local từ server:

```text
ssh <target> 'curl -fsS http://127.0.0.1:${WEB_PORT:-8000}/healthz'
```

Public health nếu có `PUBLIC_BASE_URL`:

```text
curl -fsS <PUBLIC_BASE_URL>/healthz
```

Negative test webhook:

```text
curl -i -X POST <PUBLIC_BASE_URL>/webhooks/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: ping" \
  -H "X-GitHub-Delivery: manual-negative-test" \
  --data "{}"
```

Kỳ vọng unsigned request bị reject `403`. Signed webhook test chỉ làm nếu có
thể sinh signature trên server mà không log secret, hoặc dùng GitHub redelivery
được người dùng cho phép.

UI check tối thiểu:

```text
ssh <target> 'cd <repo_dir> && docker compose exec -T web python - <<PY
from app.server.config import load_config
from app.server.repositories import PostgresStore
cfg = load_config()
store = PostgresStore(cfg.database_url)
print("db_health", store.health())
print("publish_enabled", cfg.publish_enabled)
print("allowed_repos", ",".join(cfg.allowed_repositories))
PY'
```

Nếu có admin credential trong runtime, login dashboard bằng browser/curl session
nhưng không in password.

### 7. Merge có guard từ `dev1` vào `dev`

Chỉ làm sau khi health/UI/webhook smoke pass.

```text
ssh <target> 'cd <repo_dir> && git fetch origin dev dev1 --prune && git rev-parse origin/dev && git rev-parse origin/dev1'
ssh <target> 'cd <repo_dir> && git switch dev && git status --short'
```

Nếu worktree server dirty, dừng và hỏi trước. Nếu clean:

```text
ssh <target> 'cd <repo_dir> && git merge --no-ff origin/dev1'
```

Nếu cần đẩy remote:

```text
ssh <target> 'cd <repo_dir> && git push origin dev'
```

Lệnh `git push` là external write; chỉ thực hiện nếu lệnh kích hoạt của người
dùng bao gồm quyền merge/push rõ ràng.

### 8. Post-merge runtime verification

```text
ssh <target> 'cd <repo_dir> && docker compose build'
ssh <target> 'cd <repo_dir> && docker compose up -d postgres web worker'
ssh <target> 'cd <repo_dir> && docker compose ps'
ssh <target> 'curl -fsS http://127.0.0.1:${WEB_PORT:-8000}/healthz'
```

Chọn một trong hai proof, tùy người dùng yêu cầu và credential có sẵn:

- Web UI proof: login dashboard, mở repo/PR/run page, xác nhận trang render 200
  và hiện dữ liệu hiện tại.
- Webhook proof: signed synthetic `ping` hoặc GitHub redelivery/test PR event,
  xác nhận response `200`/`202`, DB delivery/job/run thay đổi đúng kỳ vọng và
  không duplicate.

## Verification

```text
python -m compileall src app
git diff --check
docker compose config
docker compose build
docker compose up -d postgres web worker
docker compose ps
curl -fsS http://127.0.0.1:${WEB_PORT:-8000}/healthz
```

Các kiểm tra live chỉ chạy khi được cho phép rõ:

```text
GitHub App webhook ping/redelivery read-back
Dashboard login/UI smoke through PUBLIC_BASE_URL
Git merge/push dev1 into dev with recorded before/after SHAs
PostgreSQL read-back for deliveries/jobs/runs/publish_audit
```

## Evidence

- 2026-09-04: task được tạo dưới dạng ready runbook. Trong lần ghi này không
  SSH, không Docker, không gọi GitHub API, không gọi model, không merge, không
  push, không deploy và không gọi webhook.
- 2026-09-04: nội dung runbook đã được chuyển sang tiếng Việt có dấu; vẫn không
  SSH, không Docker, không gọi GitHub API, không gọi model, không merge, không
  push, không deploy và không gọi webhook.
- Pending live run: cần ghi lại SSH target, repo folder, branch/commit ban đầu,
  compose services, env key presence, port binding, container health, kết quả
  webhook/UI, SHA trước/sau của `dev1`/`dev`, kết quả merge và proof sau merge.

## Rollback/recovery

- Nếu Docker startup fail, thu `docker compose ps` và log liên quan; không merge
  cho đến khi sửa được nguyên nhân gốc.
- Nếu webhook fail, chỉ để worker chạy tiếp khi an toàn và không tạo duplicate
  jobs; nếu không, dừng `worker` trước và giữ nguyên DB.
- Nếu merge tạo conflict, abort merge và báo file; không tự resolve bằng cách
  đoán ý định production.
- Nếu merge đã push làm hỏng runtime, revert merge trên `dev` bằng một revert
  commit mới sau khi người dùng approve; không rewrite history của branch chung
  nếu người dùng chưa yêu cầu rõ.
- Để dừng runtime mà không xóa dữ liệu: `docker compose down` không kèm `-v`.
