# Hướng Dẫn Đóng Góp & Quy Tắc Mã Nguồn Tối Thiểu (CONTRIBUTING)

Tài liệu này định hình các chuẩn mực đóng góp và quy tắc chất lượng mã nguồn tối thiểu cho dự án **DUT AI PR Preview System**. Cả thành viên dự án và hệ thống AI Reviewer (`dut-ai-pr-review`) đều lấy các quy tắc này làm thước đo chuẩn để đánh giá mọi Pull Request (PR).

---

## 1. Quy Tắc Mã Nguồn Tối Thiểu (Minimal Code Rules)

Mọi thay đổi trong PR cần tuân thủ nghiêm ngặt 5 nhóm quy tắc cốt lõi sau:

### 1.1. Đúng & Đủ — Kiểm Soát Phạm Vi (YAGNI & Scope Control)
- **Không code thừa (No Dead Code):** Tuyệt đối không commit các hàm, biến, class hoặc import không còn được sử dụng.
- **Không phình to phạm vi (Anti-Scope Creep):** Code chỉ thay đổi đúng phạm vi của task/đặc tả (`specs/`). Không tiện tay sửa các phần không liên quan nếu chưa có issue/spec tương ứng.
- **Dọn dẹp mã nháp:** Xóa bỏ toàn bộ `print()`, `console.log()`, mã thử nghiệm hoặc các dòng code bị chú thích (commented-out code) trước khi tạo PR.
- **Không tùy tiện thêm dependency:** Không cài thêm package/thư viện ngoài nếu các công cụ chuẩn sẵn có (stdlib) đã đáp ứng tốt yêu cầu.

### 1.2. An Toàn & Bảo Mật Tuyệt Đối (Security Baseline)
- **Không lộ bí mật:** Nghiêm cấm ghi hardcode API key, secret token, mật khẩu hoặc thông tin nhạy cảm vào code, log, commit message hoặc file cấu hình được track bởi Git.
- **Bảo vệ đường dẫn:** Không hardcode đường dẫn tuyệt đối của máy cá nhân (ví dụ: `C:\Users\...` hoặc `/home/...`). Mọi thao tác file phải qua đường dẫn tương đối hoặc cấu hình `Path`.
- **Ranh giới an toàn (Trust Boundary):** Dữ liệu từ PR (tiêu đề, mô tả, diff, bình luận, tên file) là **dữ liệu không tin cậy**. Luôn validate hoặc sanitize trước khi nối chuỗi hoặc ghép path (ngăn ngừa Path Traversal).
- **Hạn chế thực thi nguy hiểm:** Tuyệt đối không dùng `eval()`, `exec()`, `subprocess(..., shell=True)`. Sử dụng `yaml.safe_load` thay vì `yaml.load`.

### 1.3. Clean Code & Khả Năng Bảo Trì (Maintainability)
- **Đặt tên chuẩn xác:** Tên biến, hàm, class phải mang tính tự diễn đạt (self-documenting), phản ánh đúng chức năng. Tránh viết tắt tùy tiện hoặc đặt tên tối nghĩa (`data1`, `temp`, `res2`).
- **Hàm đơn nhiệm (Single Responsibility):** Mỗi hàm chỉ làm một việc duy nhất và làm trọn vẹn việc đó. Khuyến nghị độ dài hàm không vượt quá 40–50 dòng.
- **Hạn chế lồng ghép sâu:** Không lồng quá 3 cấp điều kiện (`if`, `for`, `while`). Ưu tiên sử dụng *Guard Clauses* (early return) để giảm độ phức tạp nhận thức (cognitive complexity).
- **Xử lý ngoại lệ tường minh:** Không nuốt lỗi ngầm bằng khối `except:` rỗng hoặc `except Exception: pass`. Khi bắt lỗi, phải ghi log hoặc xử lý fallback rõ ràng.

### 1.4. Tính Đúng Đắn Khi Chạy & Fallback (Runtime Correctness)
- **Kiểm tra tính khả thi thực tế:** Code không chỉ cần vượt qua kiểm tra cú pháp (syntax pass), mà phải đảm bảo hành vi chạy đúng kịch bản mong đợi.
- **Xử lý trạng thái biên & Fallback:**
  - Đối với giao diện (UI): Khi hình ảnh, avatar hoặc tài nguyên không tải được (load error), phải luôn có component fallback/placeholder thay thế, không để vỡ bố cục giao diện.
  - Đối với API/Dịch vụ: Khi gặp lỗi mạng hoặc timeout, phải có mã phản hồi chuẩn và thông báo lỗi rõ ràng.
- **Kiểm thử đi kèm:** Bất kỳ thay đổi nào liên quan đến logic nghiệp vụ cốt lõi đều phải bổ sung hoặc cập nhật unit tests tương ứng.

### 1.5. Chuẩn Hóa Ngôn Ngữ Nhận Xét
- **100% Tiếng Việt:** Toàn bộ báo cáo nhận xét, bình luận review, thông báo lỗi trả về cho người dùng phải được viết bằng tiếng Việt rõ ràng, chuẩn mực.
- **Thuật ngữ chuyên ngành:** Giữ nguyên các thuật ngữ kỹ thuật phổ biến theo thông lệ quốc tế (ví dụ: *repository, commit, PR, diff, patch, token, branch, workspace...*).

---

## 2. Quy Trình Tạo Pull Request (PR Checklist)

Trước khi gửi PR hoặc yêu cầu review:

1. [ ] Đã chạy kiểm tra cú pháp cục bộ: `python -m compileall src app`.
2. [ ] Đã dọn dẹp các lệnh in debug, dead code và các file tạm không liên quan.
3. [ ] Đã đối chiếu với đặc tả (`specs/`) hoặc mô tả yêu cầu: code không làm thiếu và không làm thừa.
4. [ ] Đã kiểm tra tính đúng đắn khi chạy thực tế (runtime behavior, fallback khi lỗi dữ liệu/ảnh).
5. [ ] Đảm bảo không chứa bất kỳ secret/token hoặc đường dẫn cá nhân nào.
