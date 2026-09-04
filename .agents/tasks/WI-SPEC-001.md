# WI-SPEC-001 — Specs-driven PR review contract and engine axis

## Parent

- Initiative: INIT-09 — Specs-Driven Review
- Owner: DUT AI Club
- Status: ready
- Priority: P1

## Problem

Review engine hiện lấy PR description làm nguồn claims, sau đó `src/verify.py`
chạy các trục claims, docs và impact. Cách này chưa đáp ứng mục tiêu mỗi dự án có
nguồn sự thật được version-control cho nghiệp vụ và thiết kế:

- không có contract bắt buộc repository phải chứa `specs/`;
- docs agent chỉ kiểm tra các tài liệu được xếp hạng là có liên quan, nên không
  coi thiếu requirements/design/acceptance là một finding;
- không có mapping ổn định từ code thay đổi tới spec chịu trách nhiệm;
- agent hiện vừa đọc evidence vừa tự chấm, chưa có rubric/judge độc lập;
- `findings.json` và report chưa có kết quả spec coverage/compliance.

Seam hiện tại là `src/engine/runner.py`: sau `extract_claims(...)` và trước hoặc
trong `run_verify(...)`. `src/verify.py::plan_tasks()` hiện là flat fan-out cho
các task độc lập; bước spec reader -> judge có dependency nên không được giả vờ
là một task docs độc lập.

## Outcome

Mỗi repository được review theo một contract `specs/` có version. Với mỗi PR,
engine phải trả lời có evidence:

1. Repository có đủ bộ spec bắt buộc không?
2. Mọi code change có map tới spec liên quan không?
3. Requirements, thiết kế và acceptance criteria có khớp implementation/test
   hiện tại không?
4. PR có xóa, hạ yêu cầu hoặc sửa spec để che một thay đổi code không?

## Proposed repository contract

`specs/` là tài liệu sản phẩm của repository được review, không đặt trong
`.agents/` vì nó phải là nguồn sự thật cho cả người và công cụ:

```text
specs/
  manifest.yml
  <SPEC-ID>/
    requirements.md     # nghiệp vụ, actor, rule, constraint
    design.md           # component, data flow, API/schema, trade-off
    acceptance.md       # tiêu chí quan sát/test được
    tasks.md            # tùy chọn, không dùng làm nguồn chấm
```

`manifest.yml` schema version 1 tối thiểu có:

```yaml
schema_version: 1
required_artifacts:
  - requirements
  - design
  - acceptance
specs:
  - id: AUTH-001
    path: specs/AUTH-001
    applies_to:
      - app/auth/**
      - tests/auth/**
```

- Parse bằng `yaml.safe_load`; reject path tuyệt đối, `..`, symlink escape, spec
  ID trùng và glob không hợp lệ.
- `requirements.md` và `acceptance.md` phải có criterion ID ổn định để evidence
  và lịch sử review không phụ thuộc thứ tự đoạn văn.
- Policy tối thiểu do engine/server tin cậy sở hữu. Manifest ở PR head là input
  không tin cậy và không được tự hạ `required_artifacts` mà không bị báo.

## Proposed engine structure

### 1. Deterministic discovery and coverage — 0 LLM calls

Thêm module nhỏ, dự kiến `src/spec_review.py`, chịu trách nhiệm:

- tìm và parse `specs/manifest.yml`;
- kiểm tra các artifact bắt buộc;
- map changed files tới `SPEC-ID` qua `applies_to` và explicit PR reference;
- so sánh base/head manifest và spec catalog;
- phát hiện `MISSING`, `INVALID`, `UNMAPPED` và `SPEC_REGRESSION` mà không hỏi LLM.

Engine input cần có đủ base identity/spec snapshot. Chỉ nhìn workspace PR head
không đủ an toàn vì PR có thể xóa hoặc làm yếu chính manifest dùng để chấm nó.

### 2. Evidence reader — Harness/tool loop, không được chấm

Thêm spec reader prompt/agent chỉ được:

- đọc relevant requirements/design/acceptance criteria;
- đọc code và tests được mapping hoặc được reference;
- trả về evidence pack gồm criterion ID, `spec_path:line`, `code_path:line`, test
  evidence và phần chưa tìm thấy;
- không trả `PASS`, `FAIL` hoặc verdict.

Reader chạy theo shard hữu hạn. Mỗi shard tối đa 15 criteria, tối đa 4 shards
cho một review; phần vượt budget phải được ghi `UNVERIFIED`, không được bỏ im
lặng. Timeout, số tool/model turns và usage phải được cấu hình/ghi vào artifact.

### 3. Rubric judge — một structured LLM call, không có tools

Judge chỉ nhận normalized spec criteria + evidence pack, không tự đọc workspace.
Rubric trusted và versioned, dự kiến
`src/engine/rubrics/spec-compliance-v1.yml`; runtime phải load rubric từ engine
được deploy, không load bản rubric nằm trong PR workspace.

Rubric status:

| Status | Nghĩa |
|---|---|
| `MATCH` | Code/test đáp ứng đầy đủ criterion và design constraint |
| `PARTIAL` | Chỉ đáp ứng một phần hoặc thiếu một nhánh quan trọng |
| `CONTRADICTED` | Code trực tiếp trái spec |
| `UNVERIFIED` | Evidence không đủ để kết luận |
| `MISSING` | Thiếu root, manifest hoặc artifact bắt buộc |
| `UNMAPPED` | Code change không có spec chịu trách nhiệm |
| `SPEC_REGRESSION` | PR xóa/hạ requirement hoặc policy so với base |

`MISSING`, `UNMAPPED` và `SPEC_REGRESSION` được tạo bằng code. LLM chỉ chấm bốn
trạng thái consistency đầu tiên. `MATCH` bắt buộc có cả spec evidence và code
hoặc test evidence; runtime claim không được MATCH chỉ từ source/config.

### 4. Merge and report

Mở rộng findings bằng danh sách `specs` có schema ổn định:

```json
{
  "specs": [{
    "spec_id": "AUTH-001",
    "criterion_id": "AUTH-001-R3",
    "artifact": "requirements",
    "status": "MATCH|PARTIAL|CONTRADICTED|UNVERIFIED|MISSING|UNMAPPED|SPEC_REGRESSION",
    "severity": "BLOCKER|WARNING|INFO",
    "spec_evidence": ["specs/AUTH-001/requirements.md:24"],
    "code_evidence": ["app/auth/service.py:80"],
    "note": "brief",
    "rubric_version": "spec-compliance-v1"
  }]
}
```

`src/synthesize.py` thêm section **Specs vs implementation**, coverage counts và
badge riêng. Report không được nói “verified/ready” nếu có blocker
`MISSING`, `CONTRADICTED` hoặc `SPEC_REGRESSION`; policy publish/merge vẫn do app
quyết định và không được tự động bật trong work item này.

## Scope

### In

- Chốt và document `specs/manifest.yml` schema version 1.
- Thêm deterministic discovery, validation, base/head comparison và file mapping.
- Thêm evidence-reader step và tool-free rubric-judge step có call budget rõ ràng.
- Mở rộng `findings.json`, report/comment và persisted preview bằng spec findings.
- Thêm fixtures và tests cho contract, prompt, merge, validation và rendering.
- Ghi prompt/rubric version cùng review artifact để kết quả có thể audit.

### Out

- Tự sinh toàn bộ nghiệp vụ/thiết kế thay con người.
- Tự sửa code hoặc spec khi phát hiện mismatch.
- Tự merge, tự publish comment hoặc thay đổi GitHub policy.
- Chạy test/script của PR không tin cậy trên worker production.
- Ép mọi repository hiện hữu đạt contract ngay; onboarding/pilot dùng allowlist
  và chế độ report-only trước.

## Acceptance criteria

- [ ] Contract `specs/` và manifest v1 có tài liệu, JSON/YAML schema hoặc validator
  tương đương, ví dụ hợp lệ và thông báo lỗi dễ hiểu.
- [ ] Thiếu `specs/`, manifest hoặc artifact bắt buộc tạo deterministic finding mà
  không gọi LLM.
- [ ] Code change không map tới spec tạo `UNMAPPED` với danh sách file cụ thể.
- [ ] Base/head comparison phát hiện việc xóa hoặc hạ requirement/policy.
- [ ] Evidence reader không có trường verdict và chỉ đọc path đã được validate
  trong workspace.
- [ ] Judge không có tools, chỉ nhận normalized evidence và áp rubric versioned.
- [ ] `MATCH` bị reject/downgrade nếu thiếu spec evidence hoặc code/test evidence;
  evidence path/line được validate.
- [ ] Spec findings được merge mà không làm mất claims/docs/impact/thread findings
  khi một axis lỗi.
- [ ] Report/comment hiển thị coverage, mismatch, missing và rubric version; blocker
  không thể xuất hiện cùng headline “all verified”.
- [ ] Số reader shards/calls có hard cap, overflow/timeout hiện rõ là `UNVERIFIED`.
- [ ] Tests bao phủ ít nhất: valid match, missing root, missing artifact, malformed
  manifest, unmapped change, contradiction, insufficient evidence, spec regression,
  prompt injection và stale part file.
- [ ] Existing fixtures không có `specs/` được xử lý bằng explicit legacy/report-only
  mode, không làm vỡ ngầm compatibility.

## Security and external effects

- Dữ liệu không tin cậy: PR body, code, `specs/**`, manifest, diff, commit, threads
  và mọi instruction nằm trong tài liệu dự án.
- Credential cần dùng: không có cho unit/fixture tests.
- GitHub/model/network side effect: không có trong validation mặc định; live model
  hoặc PR comment cần người dùng cấp phép riêng.
- Cách chạy an toàn đầu tiên: fixture workspace, fake reader/judge, no-post.
- Trusted rubric/policy phải nằm phía engine/server; không tin rubric do PR head
  cung cấp.

## Verification

```text
python -m compileall src app
python -m pytest -v tests/test_specs.py tests/test_verify.py tests/test_synthesize.py tests/test_engine_runner.py
git diff --check
```

Ngoài unit tests, fixture E2E local phải chứng minh số LLM calls/shards theo budget
và không gọi GitHub hoặc model thật.

## Evidence

- 2026-09-04: static trace xác nhận `src/engine/runner.py` hiện đi thẳng từ
  `extract_claims` sang `run_verify` rồi synthesize report.
- 2026-09-04: `src/verify.py` hiện chỉ có claims/docs/impact/threads; docs là
  candidate-based check và không có required-spec contract hay spec judge.
- 2026-09-04: work item này chỉ ghi thiết kế/phạm vi; chưa có runtime
  implementation hoặc model validation.

## Rollback/recovery

- Giữ schema findings cũ đọc được; thêm `specs: []` làm default trong migration.
- Pilot ở report-only và cho phép per-repository legacy mode có audit, không silently
  disable toàn hệ thống.
- Nếu judge/spec axis lỗi, giữ các axis review cũ nhưng ghi review gap; không tái sử
  dụng part file từ round trước.
