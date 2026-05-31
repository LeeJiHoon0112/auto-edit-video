# 📖 HƯỚNG DẪN TẢI & SỬ DỤNG — Auto Edit Video

Tool tự động ghép **ảnh / video (Veo...) + voiceover + phụ đề SRT** thành video MP4 hoàn chỉnh.
Dành cho làm video faceless (YouTube, TikTok...). Chạy trên **Windows**.

---

## 🧰 Cần chuẩn bị (chỉ làm 1 lần)

### Bước 1 — Cài Git
Git để tải tool và cập nhật về sau.
- Tải tại: https://git-scm.com/download/win → cài đặt (cứ Next đến hết).

### Bước 2 — Tải tool về máy
Mở **Command Prompt** (gõ `cmd` ở thanh Start), rồi dán lệnh:
```
cd Desktop
git clone https://github.com/LeeJiHoon0112/auto-edit-video.git
```
→ Sẽ có thư mục `auto-edit-video` trên Desktop.

> ⚠️ Nên tải bằng `git clone` (đừng bấm "Download ZIP") thì nút **cập nhật** mới dùng được.

### Bước 3 — Cài đặt
Mở thư mục `auto-edit-video`, **bấm đúp vào `install.bat`**.
→ Nó tự kiểm tra & cài **Python** và **FFmpeg** giúp bạn. Cứ chờ đến khi hiện "CÀI ĐẶT XONG".

---

## ▶️ Sử dụng hằng ngày

### 1. Chuẩn bị nguyên liệu — bỏ vào thư mục `input\`
```
input\
├── images\        ← ảnh hoặc video: đặt tên 01, 02, 03... theo thứ tự
├── voice.mp3      ← file voiceover (hoặc .wav)
└── subtitle.srt   ← phụ đề có timestamp
```

### 2. Mở app
Bấm đúp **`run.bat`** → cửa sổ app hiện ra.

### 3. Trong app
1. Mục **1 — Nguyên liệu**: bấm "Chọn..." trỏ tới ảnh/video, voiceover, SRT.
2. Mục **2 — Cách ghép**: chọn kiểu (mặc định "Khớp lời"), đặt số giây mỗi cảnh.
3. Bấm: **① Tạo bảng cảnh → ② Xem trước → ③ RENDER VIDEO**.
4. Video ra nằm trong thư mục `output\`.

---

## 🔄 Cập nhật tool (khi có bản mới)
Chỉ cần bấm đúp **`update.bat`** → tự tải bản mới nhất về. Không cần tải lại từ đầu.

---

## 📂 Bộ file chính

| File | Công dụng |
|------|-----------|
| `install.bat` | Cài đặt lần đầu (Python + FFmpeg) |
| `run.bat` | Mở app để làm video |
| `update.bat` | Cập nhật tool lên bản mới |
| `input\` | Nơi bỏ ảnh/video + voiceover + SRT |
| `output\` | Nơi video thành phẩm xuất ra |

---

## ❓ Gặp lỗi thường gặp

- **Bấm run.bat báo "Chưa cài Python"** → chạy `install.bat` trước, rồi mở lại `run.bat`.
- **install.bat báo đã cài Python xong** → đóng cửa sổ, mở lại `install.bat` một lần nữa.
- **update.bat báo "không phải bản git clone"** → bạn đã tải ZIP; hãy tải lại bằng `git clone` (Bước 2).

Chúc bạn làm video vui vẻ! 🎬
