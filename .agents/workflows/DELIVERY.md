# Delivery Workflow

## 1. Trước khi sửa

1. Chọn một work item trong `tasks/BOARD.md`.
2. Đọc module và test liên quan.
3. Xác định có side effect GitHub/model/install hay không.
4. Nếu chỉ review: không thay đổi runtime.

## 2. Sửa code

- Diff nhỏ, có test cho bug/contract mới.
- Không thêm dependency nếu chưa được người dùng duyệt.
- Không thay đổi attribution/license của upstream.
- Rebrand phải giữ alias/marker cũ khi cần tương thích dữ liệu đã tồn tại.

## 3. Validation không side effect

Windows, với environment đã tồn tại:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m compileall src app
```

Linux/WSL:

```bash
python -m pytest -v
python -m compileall src app
```

Không chạy `uv sync`, `pip install`, `dut-ai-pr-review update`, review thật hoặc
dashboard trigger chỉ để “kiểm tra nhanh”.

## 4. Kiểm tra diff

```powershell
git diff --check
git status --short
```

Review các nhóm: source, tests, docs, package metadata và generated lock.

## 5. Definition of Done

- Acceptance criteria có bằng chứng.
- Không còn branding sai ngoài attribution/compatibility có chủ ý.
- Không lộ secret, không phát sinh comment/API/model call ngoài ý muốn.
- Platform limitation được ghi đúng, đặc biệt Windows runtime.
