# ISW Repair Management System

Dashboard thống kê + quản lý nhật ký sửa chữa hộp thử nghiệm ISW, xây bằng Streamlit + SQLite.

## 📁 Cấu trúc thư mục cần có khi deploy

```
.
├── isw_dashboard.py              # File chính, chạy bằng `streamlit run isw_dashboard.py`
├── db.py                         # Lớp truy cập dữ liệu SQLite
├── ISW_Repair_Logs_Cleaned.csv   # Dữ liệu gốc, chỉ dùng để nạp lần đầu
├── requirements.txt              # Khai báo thư viện cần cài
├── assets/                       # Thư mục lưu file PDF/Video tải lên (tự tạo nếu chưa có)
│   └── .gitkeep
└── .gitignore
```

**Lưu ý:** file `isw_repair.db` (database SQLite) KHÔNG cần đưa lên GitHub — ứng dụng
sẽ tự tạo nó từ `ISW_Repair_Logs_Cleaned.csv` trong lần chạy đầu tiên (xem `.gitignore`).


## 🚀 Cách 1 — Chạy thử ngay trên máy của bạn (2 phút)

```bash
pip install -r requirements.txt
streamlit run isw_dashboard.py
```

Trình duyệt sẽ tự mở tại `http://localhost:8501`.


## ☁️ Cách 2 — Đẩy lên GitHub + Deploy lên Streamlit Community Cloud (có link công khai)

### Bước 1 — Tạo repo GitHub

1. Vào https://github.com/new, tạo 1 repository mới (có thể để **Public** hoặc **Private**
   đều deploy được), ví dụ đặt tên `isw-repair-dashboard`.
2. Trên máy bạn, vào thư mục chứa các file ở trên và chạy:

```bash
git init
git add .
git commit -m "Khởi tạo ISW Repair Dashboard"
git branch -M main
git remote add origin https://github.com/<tên-tài-khoản-của-bạn>/isw-repair-dashboard.git
git push -u origin main
```

### Bước 2 — Deploy lên Streamlit Community Cloud

1. Vào https://share.streamlit.io, đăng nhập bằng tài khoản GitHub.
2. Bấm **"New app"**.
3. Chọn đúng repo `isw-repair-dashboard`, nhánh `main`, và file chính là `isw_dashboard.py`.
4. Bấm **"Deploy"**. Sau khoảng 1–2 phút build, bạn sẽ nhận được 1 link dạng:

   ```
   https://<tên-app-của-bạn>.streamlit.app
   ```

   Bấm vào link này là xem được ngay trên trình duyệt, có thể gửi cho đồng nghiệp cùng xem.

### Bước 3 — Cập nhật code sau này

Mỗi khi bạn sửa code và `git push` lên `main`, Streamlit Community Cloud sẽ **tự động
build lại và deploy bản mới** — không cần thao tác gì thêm trên trang share.streamlit.io.


## ⚠️ Giới hạn quan trọng cần biết trước khi dùng thật (rất quan trọng)

**Streamlit Community Cloud (gói miễn phí) KHÔNG lưu trữ file lâu dài (ephemeral storage).**
Ứng dụng chạy trong 1 container tạm thời — mỗi khi app "ngủ" do không có người dùng
trong 1 khoảng thời gian, được reboot thủ công, hoặc khi bạn `git push` code mới, **toàn
bộ dữ liệu ghi trực tiếp xuống đĩa trong lúc chạy sẽ bị MẤT**, bao gồm:

- File `isw_repair.db` — mọi dòng nhật ký sửa chữa được kỹ sư nhập qua form "Nhật Ký & Nhập
  Liệu" sau khi deploy sẽ biến mất khi app khởi động lại (chỉ dữ liệu gốc từ CSV được nạp
  lại mỗi lần, vì đó là file có trong repo).
- Toàn bộ file PDF/Video trong thư mục `assets/` được tải lên qua tab "Thư Viện SOP/Video".

Đây không phải lỗi trong code — cộng đồng Streamlit đã xác nhận đây là hành vi mặc định
của Community Cloud (tham khảo thảo luận chính thức trên diễn đàn Streamlit:
https://discuss.streamlit.io/t/can-streamlit-community-cloud-recover-a-lost-local-sqlite-file-after-a-reboot-redeploy/121770).

**Vậy nên dùng link Streamlit Cloud để làm gì?**
- ✅ Rất phù hợp để **demo giao diện, xem thử tính năng, gửi link cho sếp/đồng nghiệp xem**
  trước khi quyết định đầu tư hạ tầng thật.
- ❌ **Không phù hợp để vận hành thật, nơi kỹ sư nhập liệu hàng ngày** — dữ liệu sẽ mất bất
  cứ lúc nào app bị reboot.

**Nếu muốn dùng thật lâu dài, có 2 hướng nâng cấp** (tôi có thể giúp bạn triển khai khi cần):

1. **Đơn giản nhất**: chuyển `assets/` và `isw_repair.db` sang lưu ở 1 dịch vụ lưu trữ bền
   vững ngoài (vd: gắn ổ đĩa persistent qua Streamlit Cloud add-on, hoặc dùng SQLite trên
   1 volume mount của Docker/VPS riêng thay vì Community Cloud).
2. **Chuẩn production hơn**: chuyển từ SQLite sang cơ sở dữ liệu quản lý (Postgres/MySQL)
   được host riêng (vd: Supabase, Railway, PlanetScale, RDS...) — đúng với schema `.sql`
   đã thiết kế ở giai đoạn trước, chỉ cần đổi lớp kết nối trong `db.py`.
