# WI-MVP-001 — Single-repository GitHub App review MVP

## Parent

- Initiative: INIT-02, INIT-04, INIT-05, INIT-06, INIT-07, INIT-08
- Owner: DUT AI
- Status: done
- Priority: P0

## Problem

The current application authenticates through a developer's `gh` session, polls
GitHub, stores state in `sessions/`, and has no authenticated hosted UI. The MVP
must review PRs for `DUT-AI/dut-ai-pr-preview-system` through a club-owned GitHub
App, retain commit/review history, expose a small admin dashboard, and run as a
Docker stack on a Linux server.

## Scope

### In

- One private GitHub App owned by `DUT-AI`, installed only on this repository.
- Repository permissions: metadata read, contents read, pull requests write, and
  issues write for preview-comment publication.
- `pull_request` webhook ingestion with HMAC verification and delivery dedupe.
- PostgreSQL-backed installations, repositories, PRs, commits, deliveries,
  jobs, runs, findings, comment previews, and publish audit.
- A single `admin` web user configured by runtime secrets, session cookies, and
  CSRF protection.
- Review-engine gateway over the existing claims/verify/report pipeline.
- Provider-neutral OpenAI-compatible LLM configuration targeting
  `https://llm2.dutai.site/v1`.
- Docker images and Compose stack for web, worker, and PostgreSQL.
- Controlled `dev1` -> `dev` PR proof on this repository.

### Out

- Organization-wide installation or discovery across every DUT AI repository.
- Multiple users, registration, RBAC, billing, or public signup.
- Automatic merge, contents write, workflow write, or repository administration.
- Posting outside the one allowlisted test repository.

## Target layers

```text
app/server/controller.py    FastAPI pages, JSON API, login, webhook
app/server/services.py      webhook, review-job, and publish use cases
app/server/repositories.py  GitHub App API and PostgreSQL persistence
app/server/config.py        trusted process environment configuration
app/server/models.py        shared server data objects
app/ui/                     Jinja templates and CSS
src/engine                  ReviewInput/ReviewResult gateway and review core
```

## External API contract

- GitHub App JWT and installation access-token endpoints.
- GitHub REST: repository, pull request, files, commits, contents/archive, and
  issue comments.
- GitHub GraphQL: review threads and linked issues when REST is insufficient.
- GitHub webhook: `pull_request` actions `opened`, `reopened`, `synchronize`, and
  `ready_for_review`.
- llama.cpp OpenAI-compatible `/v1/models` and `/v1/chat/completions`.

## Acceptance criteria

- [x] App installation token reads the allowlisted repository without `gh` user auth.
- [x] Invalid webhook signatures are rejected and duplicate delivery IDs do not
      create duplicate jobs.
- [x] Each job/result is pinned to the PR head SHA; stale runs cannot publish.
- [x] A comment is previewed in the dashboard before an explicit publish action.
- [x] Publication uses the stable legacy marker and is idempotent.
- [x] The admin UI shows the configured repository, PRs, commit history, runs,
      findings, preview comment, and publish audit.
- [x] GitHub private key, webhook secret, admin password, database password, and
      future LLM credential do not enter source, logs, reports, or Harness tools.
- [x] Docker Compose builds and starts web, worker, and PostgreSQL with health checks.
- [x] A real `dev1` -> `dev` PR produces one persisted review for the correct head SHA.
- [x] Tests, compileall, `git diff --check`, and relevant Docker smoke checks pass.

## Security and external effects

- Dữ liệu không tin cậy: PR body, commits, code, review threads, webhook payload.
- Credential cần dùng: GitHub App private key, webhook secret, admin/session
  secrets, PostgreSQL password, optional LLM credential reference.
- GitHub/model/network side effect: App registration/installation, test branches,
  one test PR, LLM calls, and one explicitly selected preview-comment publish.
- Cách chạy an toàn đầu tiên: one repository, one worker, no automatic posting,
  persisted preview first, then one guarded publication/readback.

## Verification

```text
python -m pytest -v
python -m compileall src app
docker compose build
docker compose up -d postgres web worker
docker compose ps
git diff --check
```

## Evidence

### Progress log — 2026-09-03

- [x] Chọn `app/` làm FastAPI/control-plane duy nhất; xóa dashboard local
      `web/` và test chỉ phục vụ dashboard cũ.
- [x] Xóa site/screenshot-design text legacy trong `docs/` vốn chỉ mô tả
      dashboard cũ và lệnh `dut-ai-pr-review web`; tài liệu hiện hành nằm ở
      `README.md` và `.agents/`.
- [x] Giữ review engine kế thừa upstream trong `src/`, CLI chính
      `dut-ai-pr-review`, alias `harness-pr-review`, marker comment và MIT
      attribution.
- [x] Cắt dependency ngược `src/engine -> app`: gateway trả contract
      `ReviewResult` riêng của engine, không import domain model của FastAPI app.
- [x] Tách Dockerfile thành target `development` và `production`; thêm
      `compose.dev.yml` cho reload/source mounts.
- [x] Thêm bootstrap `.env` local sinh DB/admin/session/webhook secret mà không
      in secret ra terminal.
- [x] Hoàn tất GitHub App credential local và live authentication.
  - App owner `@DUT-AI`, App ID `4817992` đã được điền vào `.env`.
  - PEM tải từ GitHub đã được chép sang `secrets/github-app.pem`; hash nguồn/đích
    khớp và cả `.env`, `.ask/`, `secrets/` đều được Git ignore.
  - Installation ID `158779209` do người dùng cung cấp từ trang installation
    đã được điền vào `.env`.
  - PEM mới `dut-ai-pr-preview.2026-09-03.private-key (1).pem` đã được thay vào
    runtime, validate và mount lại thành công; fingerprint mới
    `TL9zzsXutcIfvyl8IPD4BNvWKanGVhcFNE2N4o9CiF8=` và khớp fingerprint GitHub.
  - Sửa lỗi `_app_jwt()` trả thiếu payload (`header.signature` thay vì
    `header.payload.signature`) và thu lifetime còn 5 phút; App JWT, installation
    token, repository listing và target-repository read đều pass live.
  - GitHub metadata xác nhận event `pull_request`, permissions `metadata:read`,
    `pull_requests:read`, `issues:write`, `contents:write`; contents hiện rộng hơn
    mức tối thiểu read-only. Installation chỉ chọn repo mục tiêu theo ảnh người dùng.
  - Read-only probe `GET /orgs/DUT-AI/installations` ngày 2026-09-03 trả
    `404`; phiên `gh` hiện có thiếu scope `admin:org`. Không refresh auth, không
    tạo/sửa GitHub App và không có external write.
  - Điều kiện tạo App: tài khoản có quyền quản lý GitHub App của `DUT-AI`, một
    webhook URL HTTPS public trỏ tới `/webhooks/github`, và quyền cài App vào
    đúng repository này.
  - Repository permissions yêu cầu sau live publish probe: Metadata read, Contents
    read, Pull requests read/write, Issues read/write; subscribe duy nhất event Pull request;
    không cần OAuth callback hay organization permission cho MVP.
  - Kế hoạch ingress dev: giữ web bind loopback ở host port `${WEB_PORT:-8000}`;
    `cloudflared` trỏ tới `http://127.0.0.1:8000`, còn GitHub App dùng
    `https://<tunnel-host>/webhooks/github`. Webhook URL có thể đổi sau mà
    không phải tạo lại App; Quick Tunnel chỉ dùng smoke, named tunnel dùng khi
    cần hostname ổn định.
  - Runtime dev hiện ghi `PUBLIC_BASE_URL=https://fairinsight.luongduytoan.io.vn`
    và `WEB_PORT=8000` trong `.env` ignored. Webhook URL đã được sửa qua GitHub
    API thành `${PUBLIC_BASE_URL}/webhooks/github`; GET read-back và GitHub ping
    redelivery thật trả `200`.
- [x] Docker development image build trên Linux, gồm Harness runtime
      `manylinux_x86_64`.
- [x] Full pytest trong Linux container: latest `285 passed, 2 warnings`.
  - Lần 1: `255 passed`, dừng ở 90% vì base image thiếu executable `git` cho
    workspace engine; đã bổ sung `git` vào Docker base.
  - Lần 2: `284 passed, 2 warnings in 22.00s`; warning chỉ là deprecation từ
    Starlette/httpx.
  - Sau regression fix GitHub JWT: `285 passed, 2 warnings in 22.25s`.
- [x] Docker Compose production build cho `web` và `worker`.
- [x] Production container `compileall src app`, dev Compose config và
      `git diff --check` đều pass.
- [x] Final audit không còn import, package extra, Docker copy, CLI command hay
      compile target trỏ tới `web/` legacy; `.env` được ignore và không tracked.
- [x] `uv lock` cập nhật metadata extra `server` và dependency server.
- [x] Docker Compose PostgreSQL runtime smoke đạt trạng thái `healthy`; container
      đã stop sau smoke, volume được giữ lại.
- [x] Docker Compose dev `postgres + web` runtime smoke với App ID,
      installation ID và PEM thật: cả hai container healthy; local và public
      `/healthz` trả `200`; signed synthetic `ping` qua Cloudflare tới
      `/webhooks/github` trả `200`, `accepted=true`, `queued=false`.
- [x] Worker continuous mode đã khởi động thật với healthcheck PostgreSQL và đạt
      `healthy`; không có queued job nên không phát sinh inference. SIGTERM dừng
      sạch với exit code 0. Worker được giữ stopped trong khi chờ publish/merge.
- [ ] Model/publish E2E thật đang tiến hành; GitHub ingress, source retrieval
      và inference tối thiểu đã pass.
  - Connectivity audit 2026-09-03: dashboard login + CSRF/session qua domain và
    authenticated `/api/repositories` đều `200`; webhook thiếu signature bị `403`;
    initial DB sạch với `deliveries=0`, `jobs=0`, `runs=0`, `publish_audit=0`.
  - Model endpoint đã hồi phục: `GET /v1/models` trả `200` với model
    `ggml-org/gemma-4-e4b-it-GGUF:Q4_0`; chat completion tối thiểu trả
    `200`, nội dung đúng `OK`, `finish_reason=stop` (14 prompt + 2 completion
    tokens, thinking disabled). Probe không gửi code/PR data.
  - Tạo live PR #1 `dev1 -> dev`, đi qua draft `opened`, commit `synchronize`,
    rồi `ready_for_review`; cả ba webhook trả `202` và tạo đúng 3 queued jobs.
    Event `review_requested` ngoài allowlist trả `200` nhưng không enqueue.
  - Redeliver event `opened` trả `200` và DB vẫn giữ 3 delivery/3 job, chứng minh
    delivery idempotency.
  - `GitHubAppClient.snapshot()` đọc được PR #1, patch của một file, hai commit;
    `download_workspace()` lấy đúng head `f8c6ad23aa5bdf79ea48eed7a99e0c59071c6726`.
    Git blob SHA file tải về khớp GitHub (`d695515337fc341858ae18edd02523a8bf48c660`).
    Sau proof này DB vẫn `runs=0`, `publish_audit=0`: không gọi model/publish.
  - Full worker E2E đã tìm và sửa ba incompatibility runtime: App endpoint
    dùng nhầm installation token (GitHub `401`), client `urllib` bị Cloudflare
    chặn User-Agent (`403/1010`), và SDK 0.1.1rc1 đã thay `session_root`/`cordis`
    bằng `dsh_home`/`profile`/`patches`. Request llama.cpp hiện tắt thinking;
    Harness boot bằng `sdk-minimal`, workspace-write và không nhận app secrets.
  - Runtime wheel thiếu Linux `pty.node`; terminal/subprocess được disable trong
    Cordis patch, giữ file editor. Adapter truyền trusted absolute workspace root
    và salvage JSON inline khi agent không ghi part file.
  - Live event `closed` trả `200` không enqueue; `reopened` trả `202` và tạo job 4.
    Job 4 hoàn tất attempt 1 tại head `f8c6ad23aa5b`: model đọc
    `e2e-fixtures/review_target.py:6`, báo `ZeroDivisionError`, C1 `FAIL`, C2
    `PASS`, 2 impact và 7 doc findings. DB lưu run 2 và preview 9,890 chars.
  - Dashboard login/run 2 trả `200`, hiển thị đúng head/evidence/marker;
    publish disabled không hiện nút và POST cưỡng bức trả `403`.
  - Hai lần publish có kiểm soát đều bị GitHub từ chối `403 Resource
    not accessible by integration`; read-back xác nhận 0 marker comment. Token
    có `issues:write`, nhưng GitHub response chấp nhận `issues=write;
    pull_requests=write`; cần nâng Pull requests sang write và approve installation
    trước guarded retry. `PUBLISH_ENABLED` đã trả về `false`.
  - Pin `deepseek-harness-sdk` và runtime-bin `0.1.2a3`; `uv.lock` đã đồng
    bộ. Bản này boot được terminal native Linux, Cordis patch giữ
    `workspace-write`. Final live job 5 complete attempt 1 trên head `f8c6ad23aa5b`:
    C1 `FAIL` với evidence `e2e-fixtures/review_target.py:6`, 7 docs, 2 impacts,
    preview 9,689 chars.
  - Audit đa nền tảng phát hiện artifact report dùng encoding mặc định Windows
    và lỗi `UnicodeEncodeError` với ký tự `→`. Toàn bộ file text/JSON/YAML runtime
    trong pipeline đã chuyển sang UTF-8 rõ ràng; test stale-lock cũng bỏ phụ thuộc
    Unix-only `os.fork()`. Windows regression subset hiện đạt `134 passed` và
    `compileall src app tests` đạt.
  - Docker app runtime đã pin rõ `python:3.12-slim-bookworm` theo lựa chọn triển
    khai: build development xác nhận Debian `12.15`, Python `3.12.14`; compileall
    trong container đạt và full Linux suite đạt `289 passed, 2 warnings in
    22.92s`. Hai warning là deprecation từ Starlette/httpx/AnyIO, không có test fail.
  - Production image Python `3.12.14` build thành công, cài đúng SDK/runtime
    `0.1.2a3`, chạy user không đặc quyền `dutai` (UID 100), không chứa `.env`,
    `secrets/`, `.git` hay `tests/`. Harness boot độc lập từ production image
    không nhận Compose env/App secrets đạt `sdk_boot=ok`.
  - Recreate production `postgres + web` giữ nguyên volume: cả hai healthy,
    local và public `/healthz` cùng trả `200`; DB còn nguyên 5 deliveries, 5 jobs,
    3 completed runs và 2 failed publish audits. Compose production/development,
    production compileall, 17 local-doc link checks, private-key marker scan và
    `git diff --check` đều đạt.
  - Guard live sau rebuild: installation `158779209` vẫn có `issues:write` nhưng
    `pull_requests:read`, PR #1 vẫn OPEN/CLEAN/MERGEABLE và marker comment bằng 0.
    Không thử publish lần ba cho đến khi App được nâng Pull requests lên read/write
    và installation approve quyền mới.
  - Kiểm tra tách hai lớp sau khi người dùng cập nhật quyền: App registration đã
    đúng `pull_requests:write`, nhưng installation `158779209` vẫn trả
    `pull_requests:read`; installation không suspended, token đọc được đúng 1 repo.
    Vì vậy thay đổi đã lưu ở App nhưng chưa được organization approve cho installation.
  - Worker production đã được bổ sung DB healthcheck, lên `healthy` cùng web và
    PostgreSQL. Trước/sau worker smoke, jobs giữ nguyên `3 complete + 2 failed`,
    không có queued job; SIGTERM được xử lý sạch và worker exit code 0.
  - Theo yêu cầu giữ code cơ bản, hosted app được gom thành N-layer nhỏ:
    `server/controller.py`, `services.py`, `repositories.py`, `config.py`, một
    `models.py` và một `schema.sql`; toàn bộ template/CSS nằm trong `app/ui/`.
    Các package `presentation/application/domain/infrastructure` cũ được bỏ.
  - Installation cũ `158779209` đã bị GitHub xóa (`404`) khi người dùng cài lại
    App. `.env` ignored đã cập nhật sang installation mới `158829700`; live App
    JWT đọc lại xác nhận installation active, selected-repository và quyền
    `contents/issues/pull_requests:write`, `metadata:read`.
  - Guard trước publish: PR #1 open tại head `f8c6ad23aa5b`, run 3 khớp head,
    preview 9.689 ký tự và marker count bằng 0. One-shot publish qua application
    service tạo comment `5529742737`; GET độc lập xác nhận đúng một marker,
    author `dut-ai-pr-preview[bot]`, body khớp persisted preview. PostgreSQL ghi
    audit `created/success` cho run 3.
  - PR #1 đã merge `dev1 -> dev` bằng head guard; merge commit
    `7a30cabac2b3b3c6aef5ffa77032234977d3b398`. GitHub App webhook delivery
    `pull_request/closed` trả 200; action closed không enqueue nên DB giữ nguyên
    5 deliveries, 5 jobs, 3 runs và 1 successful publish. Remote `dev1` được giữ
    lại để người dùng đối chiếu.
  - Final cleanup chạy `docker compose down` không dùng `-v`: toàn bộ container
    và project network đã dừng/xóa; named volumes
    `dut-ai-pr-preview_postgres-data` và `dut-ai-pr-preview_sessions` vẫn còn để
    người dùng có thể dựng lại và kiểm tra đúng dữ liệu E2E.

  - Follow-up 2026-09-04: `.env` runtime was reduced to 8 operator-managed
    values. Database URL, container PEM path, port, allowlist, cookie mode,
    llama.cpp settings, and no-publish policy now use Compose/code defaults;
    existing credentials were preserved and no GitHub/model call was made.

## Rollback/recovery

- Disable the GitHub App webhook and suspend/uninstall the single-repo installation.
- Stop `web` and `worker`; preserve PostgreSQL and artifacts for audit.
- Keep publication disabled and revoke/rotate credentials if exposure is suspected.
