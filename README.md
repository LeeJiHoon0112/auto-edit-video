# Auto Edit Video 🎬

Tool tự động **ghép ảnh/video khớp phụ đề SRT + voiceover → xuất MP4** bằng FFmpeg.
Mỗi đoạn phụ đề (SRT) tương ứng 1 ảnh, hiển thị đúng khoảng thời gian của đoạn đó —
có hiệu ứng zoom Ken Burns, fade chuyển cảnh, và phụ đề tiếng Việt burn sẵn vào video.

> 🆕 **Người mới bắt đầu?** Xem [HƯỚNG DẪN.md](HUONG%20DAN.md) — chỉ từng bước tải, cài, dùng.
> Tóm tắt: `git clone` → bấm **`install.bat`** → bấm **`run.bat`**.

## 🔄 Cập nhật tool

Khi có bản mới, chỉ cần **double-click `update.bat`** — nó tự tải code mới nhất từ GitHub về
(yêu cầu đã tải tool bằng `git clone`). Không cần tải lại thủ công.

## 0. Mở app (giao diện cửa sổ) ⭐

Cách dễ nhất — **double-click** một trong hai:
- Lối tắt **"Auto Edit Video"** ngoài Desktop, hoặc
- File **`Auto Edit Video.bat`** trong thư mục này.

Cửa sổ app hiện ra, làm theo thứ tự:
1. **Mục 1 — Nguyên liệu:** bấm "Chọn..." để trỏ tới thư mục ảnh/video, file voiceover, file SRT.
2. **Mục 2 — Cách ghép ảnh:** chọn kiểu (mặc định "Khớp lời"), chỉnh số giây mỗi cảnh.
3. **Nút:** ① Tạo bảng cảnh → ② Xem trước (kiểm tra nhanh) → ③ RENDER VIDEO.

Nhật ký chạy hiện ngay trong cửa sổ; xong sẽ báo và có nút "Mở thư mục xuất".

> Các phần dưới đây dành cho ai thích chạy bằng dòng lệnh (không bắt buộc).

## 1. Chuẩn bị nguyên liệu

Bỏ file vào thư mục `input/` theo đúng cấu trúc:

```
input/
├── images/          ← ảnh (hoặc video) theo THỨ TỰ: 01.png, 02.png, 03.png ...
│   ├── 01.png
│   ├── 02.png
│   └── 03.png
├── subtitle.srt     ← phụ đề có timestamp (1 đoạn = 1 ảnh tương ứng)
└── voice.mp3        ← voiceover (chấp nhận .mp3/.wav/.m4a)
```

**Quy tắc quan trọng:**
- Ảnh được sắp theo **thứ tự tên file** (đặt `01, 02, 03...` để chắc đúng thứ tự).
- **Ảnh và phụ đề chạy ĐỘC LẬP.** Số ảnh KHÔNG cần bằng số đoạn phụ đề.
  - Phụ đề luôn khớp voiceover theo timestamp trong SRT.
  - Ảnh được rải đều theo tổng thời lượng (đo từ voiceover) → có bao nhiêu ảnh cũng được.
- Tổng thời lượng video = độ dài voiceover (luôn phủ hết tiếng).

## 2. Chạy tool

Mở PowerShell tại thư mục này rồi gõ:

```powershell
python auto_edit.py
```

Kết quả: `output/final.mp4` (1920×1080, 30fps, H.264 + AAC).

### Tùy chọn

```powershell
python auto_edit.py --dry-run               # XEM TRƯỚC phân cảnh (không render) — chạy rất nhanh
python auto_edit.py --seconds-per-image 8   # đổi ảnh mỗi 8s, lặp vòng ảnh nếu thiếu (khuyên dùng)
python auto_edit.py --image-mode spread     # rải đều toàn bộ ảnh theo thời lượng
python auto_edit.py --image-mode srt        # 1 ảnh / 1 đoạn phụ đề (cần nhiều ảnh)
python auto_edit.py --clip-fit auto         # khớp clip Veo vào cảnh: auto|speed|cut|loop
python auto_edit.py --transition fade       # crossfade (tan dần) giữa các ẢNH tĩnh
python auto_edit.py --no-kenburns           # tắt hiệu ứng zoom (ảnh đứng yên)
python auto_edit.py --no-subtitles          # KHÔNG burn phụ đề vào video
python auto_edit.py --out output/tap1.mp4   # đổi tên file ra
python auto_edit.py --images D:\anh --srt D:\sub.srt --voice D:\voice.mp3   # đường dẫn tùy ý
python auto_edit.py --keep-temp             # giữ lại các clip tạm để kiểm tra
```

> 💡 **Mẹo:** Luôn chạy `--dry-run` trước để xem video sẽ có bao nhiêu cảnh, mỗi ảnh
> bao nhiêu giây, có khớp voiceover không — rồi mới render thật.
> Với video dài mà ít ảnh, dùng `--seconds-per-image 6` (hoặc 8) cho video đỡ nhàm.

## 2b. Đảm bảo ẢNH khớp NỘI DUNG lời (scene-based) ⭐

Dùng khi muốn mỗi ảnh **minh hoạ đúng đoạn lời** đang nói (không phải ảnh nền chung).

```powershell
# Bước 1: gom SRT thành bảng cảnh có timestamp + lời
python build_scenes.py --target 8        # mỗi cảnh ~8 giây (chỉnh số tùy ý)
#   -> tạo scenes.csv với các cột: scene | start | end | dur | text | prompt

# Bước 2: viết prompt cho từng cảnh vào cột "prompt" (dựa trên cột "text")
#   -> tạo ảnh từ prompt, đặt tên 01.png, 02.png, ... đúng thứ tự cảnh

# Bước 3: render — ảnh được khóa vào ĐÚNG khung giờ từng cảnh
python auto_edit.py --scenes scenes.csv
```

> **Vì sao không lệch:** `scenes.csv` lấy timestamp từ SRT (vốn sinh ra từ voiceover),
> nên mỗi prompt/ảnh gắn cứng `[start–end]` của lời. Ảnh khớp cả nội dung lẫn thời gian.
> KHÔNG dùng `--seconds-per-image`/`spread` cho nhu cầu này (sẽ làm ảnh trôi lệch lời).

## 3. Tinh chỉnh nhanh (mở `auto_edit.py`, phần đầu file)

| Biến | Ý nghĩa | Mặc định |
|------|---------|----------|
| `WIDTH`, `HEIGHT` | Độ phân giải | 1920×1080 |
| `FPS` | Khung hình/giây | 30 |
| `FADE` | Thời gian fade chuyển cảnh (giây) | 0.4 |
| `KENBURNS_AMOUNT` | Mức zoom (0.12 = +12%) | 0.12 |
| `SUB_STYLE` | Font, cỡ chữ, màu, vị trí phụ đề | Arial 22, trắng viền đen, đáy |

Đổi cỡ chữ phụ đề: sửa `Fontsize=22` trong `SUB_STYLE`.
Đổi màu chữ: `PrimaryColour=&H00FFFFFF` (định dạng `&HAABBGGRR`, ví dụ vàng = `&H0000FFFF`).

## 4. Yêu cầu hệ thống

- **Python 3** (đã có: 3.13)
- **FFmpeg** (đã cài qua winget: Gyan.FFmpeg) — tool tự dò trong PATH/WinGet, không cần cấu hình.

---

> 💡 Hướng làm video qua **draft CapCut** (mở project edit sẵn trong CapCut để chỉnh tay)
> có thể bổ sung sau — hỏi để được dựng thêm module `capcut_draft.py`.
