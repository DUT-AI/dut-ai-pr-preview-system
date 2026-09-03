# Work Item Board

## Baseline — 2026-08-26

- Source là adaptation từ upstream MIT cho DUT AI Club.
- Chưa cài/chạy thêm runtime trong đợt review này.
- DeepSeek runtime lock chưa có Windows wheel.
- Static security review phát hiện blocker trước production.

## In progress

| ID | Parent | Outcome |
|---|---|---|
| [WI-E2E-002](WI-E2E-002.md) | INIT-01/04 | Live GitHub App review of the complete `dev -> main` adoption PR |
| WI-ADOPT-001 | INIT-01 | Rebrand package/CLI/docs và thay knowledge hub bị chép nhầm |

## Ready

| ID | Parent | Priority | Outcome |
|---|---|---|---|
| WI-SEC-001 | INIT-01 | P0 | Không load CWD `.env` không tin cậy trước home key/base URL |
| WI-SEC-002 | INIT-04 | P0 | Chứng minh/ép terminal runtime không thể đọc provider secret |
| WI-SEC-003 | INIT-04 | P1 | Validate route params và confine mọi session path trong root |
| WI-WIN-001 | INIT-02 | P1 | Tách DeepSeek dependency hoặc fail-fast rõ ràng trên Windows |
| WI-WEB-001 | INIT-04 | P1 | Auth + CSRF trước khi expose dashboard ngoài loopback |
| WI-OPS-001 | INIT-04 | P1 | Bootstrap manual/no-post với GitHub bot quyền tối thiểu |
| WI-REC-001 | INIT-05 | P2 | Thiết kế backup/restore session và recovery sau interrupted review |

## Done

| ID | Parent | Evidence |
|---|---|---|
| WI-AUDIT-001 | INIT-01 | Static audit ghi tại `reviews/SECURITY-BASELINE.md` |
| [WI-MVP-001](WI-MVP-001.md) | INIT-02/04/05/06/07/08 | Live webhook → PostgreSQL → Harness/LLM → persisted preview → GitHub App comment; PR #1 merged `dev1` vào `dev` |

Không link tới work-item file chưa tồn tại. Khi bắt đầu một item, tạo spec từ
`templates/TASK.md` rồi mới thêm link.
