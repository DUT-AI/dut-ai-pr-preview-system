# Roadmap

## Mục tiêu sản phẩm dài hạn

Xây dựng **DUT AI PR Preview System** thành một ứng dụng web chạy 24/7 cho các
dự án của DUT AI Club. Hệ thống kết nối repository qua GitHub App, tự động nhận
Pull Request mới hoặc thay đổi, dùng review engine để phân tích code/docs/impact
và đưa ra lời khuyên có evidence cho đội dự án. Mỗi repository tiến tới duy trì
một contract `specs/` có version cho nghiệp vụ, thiết kế và acceptance criteria;
engine kiểm tra cả độ đầy đủ của spec lẫn sự nhất quán giữa spec và code trên mỗi PR.

Web không chỉ là màn hình chạy CLI. Đây là lớp ứng dụng do DUT AI sở hữu để:

- quản lý những GitHub installation và repository nào đang được theo dõi;
- xem PR nào đã/chưa/đang được review và review đúng head SHA nào;
- xem lời khuyên theo PR, nhóm vấn đề, mức độ, evidence và trạng thái xử lý;
- kiểm soát policy chỉ lưu nội bộ, chờ duyệt hay đăng comment lên GitHub;
- theo dõi job lỗi, retry, lịch sử chạy và audit hành động GitHub.

Đích triển khai là một server Linux của CLB chạy liên tục bằng Docker Compose,
dùng PostgreSQL để lưu trạng thái bền vững và gọi model self-hosted của CLB qua
API tương thích OpenAI do `llama.cpp` phục vụ.

## Ranh giới sản phẩm

### Web application sở hữu sản phẩm

Web application sở hữu HTTP/UI, GitHub App, authentication/authorization,
application services, PostgreSQL, job worker, policy đăng kết quả, audit và cấu
hình vận hành. Đây là nơi quyết định khi nào review, review repository nào và
kết quả được phép đi đâu.

### Review engine giữ vai trò lõi

Logic Harness hiện có được giữ và dần gom vào `src/engine/`. Engine chịu trách
nhiệm biến một review input chuẩn hóa thành review result có schema/evidence:
snapshot/claims, kiểm tra code/docs/impact, hợp nhất kết quả và tạo report.

Engine cung cấp một cổng công khai ổn định, dự kiến `src/engine/gateway.py`, cùng
các contract `ReviewInput`/`ReviewResult`. Application service chỉ gọi qua cổng
này, không import trực tiếp các phase nội bộ. Engine không sở hữu HTTP route,
GitHub credential, database session, web user hay policy đăng comment.

DeepSeek Harness được giữ làm agent harness/runtime và tool environment. Model
đầu tiên của kiến trúc đích là `llama.cpp` self-hosted, được gọi qua adapter API
tương thích OpenAI; không đồng nhất Harness với model/provider DeepSeek.

## Kiến trúc N-layer mục tiêu

```text
Presentation
  FastAPI routes, web UI, GitHub webhook
        |
Application
  use cases/services, job orchestration, posting policy
        |
Domain / ports
  entities, state transitions, repository and engine interfaces
        |
Infrastructure
  GitHub App, PostgreSQL, worker, artifact storage, Harness/LLM adapters
        |
ReviewEnginePort -> src/engine/gateway.py -> Harness -> llama.cpp /v1
```

Tên package cuối cùng có thể được tinh chỉnh khi lập work item migration, nhưng
dependency direction phải được giữ: web/app gọi engine qua contract; engine
không gọi ngược vào web hoặc infrastructure.

## Luồng hoạt động đích

1. GitHub gửi webhook PR tới public endpoint.
2. Webhook controller xác minh `X-Hub-Signature-256`, installation/repository và
   delivery ID, sau đó lưu delivery + tạo job PostgreSQL và trả `200/202` sớm.
3. Worker claim job bền vững, sinh GitHub App installation token ngắn hạn và lấy
   dữ liệu PR/source cần thiết.
4. Application service chuẩn hóa `ReviewInput` rồi gọi `ReviewEnginePort`.
5. Engine điều phối Harness; Harness gọi `llama.cpp` qua OpenAI-compatible API.
6. Worker lưu review run, findings/lời khuyên, report và head SHA vào PostgreSQL
   cùng artifact storage phù hợp.
7. Policy quyết định chỉ hiển thị trên web, chờ người duyệt hay tạo/cập nhật
   comment GitHub.
8. Dashboard hiển thị repository -> PR -> review/lời khuyên, job state và audit.

## Dữ liệu bền vững mục tiêu

PostgreSQL là nguồn trạng thái production cho tối thiểu:

- GitHub installations và repositories được cấp quyền;
- webhook deliveries để chống xử lý trùng;
- review jobs/runs, head SHA, trạng thái, attempt và lỗi;
- findings/lời khuyên, report metadata và quyết định policy;
- GitHub publish actions/comment identity và audit trail;
- web users/sessions/roles nếu application tự sở hữu đăng nhập.

Workspace, patch lớn, log và report render có thể nằm ở persistent filesystem
hoặc object storage; PostgreSQL giữ metadata và liên kết. Không lưu GitHub App
private key hoặc installation token dài hạn trong database.

## Đóng gói và vận hành

Docker Compose tối thiểu có các process/container độc lập:

- `web` hoặc `app`: FastAPI, dashboard, API và webhook;
- `worker`: thực thi review job ngoài request lifecycle;
- `postgres`: dữ liệu bền vững;
- `llama-cpp`: model server self-hosted, hoặc một endpoint nội bộ tương đương do
  CLB vận hành;
- reverse proxy/TLS theo hạ tầng server.

Production cần persistent volume, migration có kiểm soát, health/readiness,
restart policy, backup/restore, resource/concurrency limit và observability.
Secret được inject lúc chạy từ secret store/server config, không bake vào image
và không commit vào repository.

## Initiatives

| Initiative | Status | Outcome |
|---|---|---|
| INIT-01 — Safe Adoption | active | Fork DUT AI có branding, attribution, baseline security và compatibility rõ ràng |
| INIT-02 — Engine Boundary and Runtime | proposed | Harness logic nằm sau contract/gateway ổn định; provider/runtime tách khỏi web application |
| INIT-03 — Review Reliability | active | Review output có schema/evidence, gắn head SHA, lặp lại được và không dùng part file cũ |
| INIT-04 — GitHub App and Secure Web | blocked | Webhook, installation auth, UI auth/CSRF, path confinement và posting policy đạt production gate |
| INIT-05 — PostgreSQL Jobs and Recovery | proposed | Delivery/job/run/finding/audit bền vững, idempotent, retry và phục hồi được sau restart |
| INIT-06 — Repository and Advice Dashboard | proposed | Quản lý repo và xem repository -> PR -> lời khuyên/trạng thái/audit trên web |
| INIT-07 — Self-hosted LLM | proposed | Harness gọi `llama.cpp` của CLB qua OpenAI-compatible adapter với contract/tool/JSON/load tests |
| INIT-08 — Docker 24/7 Operations | proposed | Stack Linux Docker Compose có health, persistence, backup, observability và quy trình rollout/rollback |
| INIT-09 — Specs-Driven Review | proposed | Repository có contract `specs/`; mỗi PR được kiểm tra spec coverage và code–spec compliance bằng evidence/rubric có version |

## Trình tự dài hạn

1. Đóng baseline adoption/security và xác định contract engine công khai.
2. Bọc Harness hiện tại sau `ReviewEnginePort` mà vẫn giữ CLI compatibility cần
   thiết để so sánh kết quả.
3. Thêm contract `specs/` và trục spec-compliance: deterministic coverage,
   evidence reader, rubric judge và report có version/evidence.
4. Thêm PostgreSQL schema, delivery/job state machine và worker durable.
5. Thêm GitHub App webhook/auth adapter với test repository và quyền tối thiểu.
6. Thêm adapter `llama.cpp` OpenAI-compatible và acceptance tests cho tool use,
   structured JSON, context, timeout và concurrency.
7. Xây dashboard repository/PR/advice và authentication/authorization.
8. Đóng Docker Compose, migration, persistent volume, health, backup/restore và
   observability.
9. Chạy E2E trên repo thử nghiệm: webhook -> job -> engine -> lời khuyên trên UI;
   chỉ sau khi duyệt mới thử một GitHub comment thật.
10. Pilot allowlist ít repository, đo chất lượng/tải/lỗi rồi mới mở rộng toàn CLB.

## Production gate

Không gọi hệ thống production-ready chỉ vì container build hoặc unit test pass.
Tối thiểu phải chứng minh:

- GitHub App được install đúng repo và quyền thực tế khớp cấu hình;
- webhook signature, replay/idempotency và event filtering hoạt động;
- dashboard có auth, authorization, CSRF và path confinement;
- GitHub/provider secret không lọt vào engine, Harness tool, log hoặc report;
- PostgreSQL migration, restart recovery, retry và backup/restore đã được thử;
- `llama.cpp` đạt contract review, structured output và tải mục tiêu;
- pilot repository chứng minh missing/unmapped/mismatch spec được phát hiện, rubric
  có version và spec trong PR không thể tự hạ policy chấm;
- một E2E test-repo chạy đúng head SHA, lưu đúng lời khuyên và không post ngoài
  policy;
- có kill switch, quota/concurrency limit, observability và rollback plan.

Roadmap này ghi kiến trúc đích và thứ tự outcome. Nó không tự tạo quyền triển
khai, không thay `BOARD.md` và không phải bằng chứng rằng các phần trên đã có.
