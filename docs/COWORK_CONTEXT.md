# CONTEXT cho Cowork — Soạn TÀI LIỆU HƯỚNG DẪN SỬ DỤNG (PDF, CÓ HÌNH) cho tool "Auto Edit Video"

## 0. HƯỚNG DẪN CHO COWORK (đọc kỹ phần này trước)

**Nhiệm vụ:** Soạn 1 file **PDF hướng dẫn sử dụng** cho người dùng cuối, **tiếng Việt**, **nhiều hình minh hoạ**.

**Đối tượng 2 mức:**
- **Người mới** (chưa rành): cần giải thích từng bước, từng nút, có ảnh.
- **Người rành** làm YouTube faceless: cần phần nâng cao (style JSON, mẹo).
→ Chia tài liệu thành **PHẦN CƠ BẢN** và **PHẦN NÂNG CAO**, hoặc đánh dấu rõ mục nâng cao.

**QUY ƯỚC HÌNH ẢNH (quan trọng):**
- Trong tài liệu này, mỗi chỗ cần hình mình đánh dấu bằng `[📷 HÌNH N — mô tả]`.
- **Ảnh thật do người dùng (Boss) chụp màn hình** — xem **DANH SÁCH ẢNH CẦN CHỤP** ở Mục 12.
- Cowork hãy **chèn đúng ảnh có số N vào đúng vị trí `[📷 HÌNH N]`**, kèm chú thích ngắn dưới mỗi ảnh.
- Nếu chưa có ảnh, Cowork để **khung trống ghi "Hình N: ..."** làm chỗ dán sau.
- Bố cục đẹp: mỗi bước = 1 đoạn mô tả ngắn + 1 ảnh minh hoạ + (nếu cần) 1 ô "Lưu ý".

**Văn phong:** thân thiện, ngắn gọn, nhiều ví dụ, có bảng tra cứu nhanh, có mục "Lỗi thường gặp".

**Cấu trúc PDF đề xuất:**
1. Trang bìa + Mục lục
2. Giới thiệu tool (Mục 1)
3. Cài đặt (Mục 2) — kèm hình
4. Quy trình tổng thể (Mục 3) — kèm sơ đồ
5. Hướng dẫn từng bước có hình (Mục 4–8)
6. Style Profile (Mục 6) — cơ bản + nâng cao
7. Mẹo & xử lý lỗi (Mục 10)
8. Bảng thuật ngữ (Mục 11)

---

## 1. TOOL LÀ GÌ

**Auto Edit Video** tự động **ghép ảnh/clip (do AI tạo) khớp phụ đề + giọng đọc → ra video MP4 hoàn chỉnh**, cho kênh YouTube faceless (không lộ mặt).

- Giao diện ứng dụng cửa sổ, **sidebar dọc bên trái 4 trang**.
- Render bằng **FFmpeg**. Viết prompt bằng **AI** (Gemini / OpenAI / Claude). Chạy trên **Windows**.

`[📷 HÌNH 1 — Toàn cảnh giao diện app khi mới mở: thấy rõ sidebar 4 mục bên trái + vùng nội dung + khung Nhật ký phía dưới]`

**Tool giúp gì:** thay vì tự viết prompt từng cảnh, tạo ảnh, rồi ghép tay cho khớp tiếng — tool tự gom phụ đề thành cảnh, nhờ AI viết prompt hàng loạt, rồi ghép ảnh/clip khớp đúng thời gian + chèn phụ đề + giọng đọc.

---

## 2. YÊU CẦU & CÀI ĐẶT

**Cần có sẵn:** Python 3.13 (tích "Add to PATH" khi cài) · FFmpeg (cài qua `winget install Gyan.FFmpeg`) · Windows.

**Các file chạy (double-click):**

| File | Công dụng |
|---|---|
| `install.bat` | Cài đặt lần đầu |
| `run.bat` | **Mở app** (dùng hằng ngày) |
| `update.bat` | Cập nhật bản mới |

`[📷 HÌNH 2 — Thư mục tool, thấy rõ 3 file install.bat / run.bat / update.bat]`

**Lần đầu mở:** app hỏi **mật khẩu** → nhập đúng → ghi nhớ **30 ngày** trên máy đó.

`[📷 HÌNH 3 — Hộp thoại nhập mật khẩu khi mở app]`

---

## 3. QUY TRÌNH TỔNG THỂ (giải thích kỹ cho người mới)

```
①  Viết kịch bản → tạo giọng đọc (voiceover) → xuất file SRT (phụ đề có thời gian)
②  Tool → trang "Tạo Prompt": chọn SRT → bấm TẠO PROMPT
        → tool gom phụ đề thành CẢNH (~8s) + AI viết prompt cho từng cảnh
③  Đưa prompt vào công cụ AI tạo ảnh (vd Veo) → tạo ảnh/clip
        → ĐẶT TÊN ảnh theo thứ tự 01, 02, 03... → bỏ vào 1 thư mục
④  Tool → trang "Render Video": chọn SRT + thư mục ảnh + giọng đọc → bấm RENDER
        → ra video MP4 (ảnh khớp tiếng + phụ đề)
```

`[📷 HÌNH 4 — Sơ đồ 4 bước (Cowork có thể vẽ lại sơ đồ này cho đẹp, dạng infographic)]`

**Nguyên tắc cốt lõi:** Giọng đọc là gốc → SRT khớp tiếng → ảnh/clip co/cắt cho vừa khung giờ từng cảnh.

**3 nguyên liệu mỗi video cần:** ① File **SRT** · ② **Thư mục ảnh/clip** (tên `01, 02...`) · ③ File **giọng đọc**.

---

## 4. TRANG ✍️ TẠO PROMPT (nhờ AI viết prompt)

`[📷 HÌNH 5 — Toàn bộ trang Tạo Prompt, thấy đủ các ô từ trên xuống]`

| Ô / Nút | Ý nghĩa |
|---|---|
| **File PHỤ ĐỀ (SRT)** | Chọn file SRT của video. |
| **📌 Tiêu đề video** | Tự điền từ tên SRT (sửa được). Giúp AI hiểu chủ đề → prompt hợp ngữ cảnh. |
| **📁 Thư mục lưu prompt** *(tùy chọn)* | Chọn thư mục riêng cho video này → prompt + bảng cảnh không đè nhau. Để TRỐNG = lưu ở gốc. |
| **Style Profile** | Chọn phong cách hình ảnh của kênh. |
| **🎭 Tên nhân vật chính** | Nếu có 1 nhân vật xuyên suốt thì nhập tên; không có để trống. |
| **Số giây mỗi cảnh** | Mỗi cảnh ~bao nhiêu giây (mặc định 8). |
| **Kiểu sản xuất video** | 3 lựa chọn (Mục 6). |
| **Áp style ở đâu** | 3 chế độ (Mục 6). |
| **🤖 TẠO PROMPT** | Bấm để AI viết prompt → lưu `veo_prompts.txt`. |
| **📄 Mở veo_prompts.txt** | Mở file prompt vừa tạo. |

`[📷 HÌNH 6 — Cận cảnh ô "File SRT" + "Tiêu đề video" + "Thư mục lưu prompt" (3 ô đầu)]`

`[📷 HÌNH 7 — Cận cảnh nhóm "Kiểu sản xuất video" (3 ô chọn) và "Áp STYLE ở đâu" (3 ô chọn)]`

`[📷 HÌNH 8 — Khung Nhật ký lúc đang chạy TẠO PROMPT, thấy dòng tiến độ ...x/y]`

---

## 5. TRANG 🎬 RENDER VIDEO (ghép thành video)

`[📷 HÌNH 9 — Toàn bộ trang Render Video]`

| Ô / Nút | Ý nghĩa |
|---|---|
| **File PHỤ ĐỀ (SRT)** | SRT của video (phải khớp prompt đã tạo). |
| **Thư mục ẢNH/CLIP** | Thư mục chứa ảnh `01, 02...`. |
| **File VOICEOVER** | File giọng đọc. |
| **Xuất ra MP4** | Đường dẫn + tên file kết quả. |
| **Ken Burns** | Zoom nhẹ ảnh tĩnh cho đỡ nhàm. |
| **Chèn phụ đề** | Ghi chữ phụ đề lên video. |
| **Crossfade ảnh** | Mờ chuyển cảnh giữa các ảnh tĩnh. |
| **▶ RENDER VIDEO** | Bắt đầu ghép. |
| **➕ Thêm vào Hàng đợi** | Lưu video vào hàng đợi render hàng loạt. |
| **📂 Mở thư mục xuất** | Mở thư mục chứa video. |

`[📷 HÌNH 10 — Cận cảnh 3 ô tick: Ken Burns / Chèn phụ đề / Crossfade ảnh]`

`[📷 HÌNH 11 — Ví dụ thư mục ảnh đặt tên đúng: 01.jpg, 02.jpg, 03.jpg... để minh hoạ quy tắc đặt tên]`

---

## 6. STYLE PROFILE — Phong cách hình ảnh của kênh

### 6.1. (Cơ bản) Cách dùng
Vào tab **Cài đặt** → phần **Style Profile** → **➕ Thêm** → đặt tên kênh → dán nội dung phong cách → **💾 Lưu** → quay lại trang Tạo Prompt chọn đúng profile.

`[📷 HÌNH 12 — Tab Cài đặt, phần Style Profile: danh sách profile bên trái + ô nội dung bên phải + nút Lưu]`

### 6.2. (Nâng cao) Viết Style Profile dạng JSON
Viết dạng **JSON** với các trường (tool tự tách thông minh):

| Trường | Tool dùng để | Ví dụ |
|---|---|---|
| `art_style` | Ghép vào MỌI prompt (nét cố định) | "Simple 2D stick figure, flat 2D NOT 3D" |
| `line_work` | Kiểu viền | "thick black marker outlines" |
| `shading_lighting` | Đổ bóng/sáng | "flat lighting, minimal shadows" |
| `characters` | AI tả đúng nhân vật theo cảnh | `{"modern_human": "...", "ancient_human": "..."}` |
| `scene_modes` | AI chọn MÀU/BỐI CẢNH theo cảnh | `{"night": {"when":"...","background":"...","palette":"...","lighting":"..."}}` |
| `variety` | Đa dạng góc máy | "vary shot type: wide, close-up, POV..." |
| `mood` | Tông cảm xúc chung | "tense, curious, satirical" |

**Lưu ý nâng cao:**
- `art_style/line_work/shading_lighting` = NÉT cố định (dính mọi prompt).
- `scene_modes/characters` = thay đổi theo cảnh (AI quyết) — đừng ép cứng vào nét.
- Đừng nhét "góc máy/màu cố định" vào `art_style` nếu video đổi bối cảnh — sẽ làm cứng hình.
- Tool đọc được **mọi cấu trúc JSON** (kể cả lồng nhau / tên lạ — tự gom lại), nhưng viết đúng các trường trên cho kết quả tốt nhất.

### 6.3. (Quan trọng) Phụ thuộc công cụ tạo ảnh
Tool chỉ **viết prompt chữ**. Ảnh đúng phong cách hay không **phụ thuộc công cụ tạo ảnh** (vd Veo). Muốn nhân vật/nét đồng nhất tuyệt đối → dùng **Style Lock / ảnh tham chiếu** trên công cụ tạo ảnh.

`[📷 HÌNH 13 — (Tùy chọn) Ví dụ 1 ảnh kết quả ĐÚNG phong cách vs 1 ảnh SAI, để user thấy khác biệt]`

---

## 7. 3 KIỂU SẢN XUẤT + 3 CHẾ ĐỘ ÁP STYLE

**Kiểu sản xuất (chọn 1):**
1. **🖼️ Ảnh tĩnh + Ken Burns** — 1 prompt ẢNH/cảnh → tạo ảnh → render zoom nhẹ.
2. **🎬 Clip video trực tiếp** — 1 prompt VIDEO/cảnh → tạo clip.
3. **⭐ Clip từ ảnh (image-to-video)** — 2 bộ prompt (ảnh + chuyển động) → nhân vật đồng nhất cao nhất.

**Áp style ở đâu (chọn 1):**
1. **① Trong prompt — kèm style** (TẮT Style Lock ở công cụ tạo ảnh).
2. **⭐ Lock lo NÉT + AI lo MÀU** (BẬT Style Lock chỉ nét) — *khuyên dùng*.
3. **② Lock lo TẤT CẢ style** (AI chỉ viết nội dung).

---

## 8. KHÁI NIỆM QUAN TRỌNG — Bảng cảnh (scenes.csv) & chống đè file

- Bấm TẠO PROMPT → tool tạo **`scenes.csv`** (bảng phân cảnh: giờ bắt đầu–kết thúc + prompt từng cảnh).
- RENDER → tool đọc `scenes.csv` để **khoá ảnh thứ i vào đúng khung giờ cảnh i** → ảnh khớp tiếng.
- **SRT và scenes.csv là 1 CẶP** — đổi SRT thì phải tạo lại prompt, nếu không render lệch.
- **Số ảnh = số cảnh**: scenes.csv có 99 cảnh → đặt đúng 99 ảnh (`01`→`99`).
- **Render KHÔNG tốn tiền API** — chỉ TẠO PROMPT mới gọi AI.
- Muốn giữ nhiều video song song → dùng **📁 Thư mục lưu prompt** riêng mỗi video.

**Cách kiểm render có khớp:** nhìn dòng `• Rải ảnh:` trong Nhật ký — *"theo bảng cảnh (...khóa timestamp SRT)"* là đúng.

`[📷 HÌNH 14 — Khung Nhật ký lúc render, khoanh đỏ dòng "• Rải ảnh: theo bảng cảnh ... khóa timestamp SRT"]`

---

## 9. CÀI ĐẶT API (nâng cao)

`[📷 HÌNH 15 — Tab Cài đặt phần API: ô Nhà cung cấp, Model, API Key, nút Kiểm tra kết nối]`

- 3 nhà cung cấp: Gemini / OpenAI / Claude. User tự nhập **API key của mình**.
- Lấy key: Gemini `aistudio.google.com` · OpenAI `platform.openai.com/api-keys` · Claude `console.anthropic.com`.
- Giá tham khảo (200 prompt ≈ 1 video): OpenAI nano/mini rất rẻ; Claude đắt hơn nhưng bám yêu cầu chặt hơn (hợp video nhiều nhân vật).
- Báo hết hạn mức (429) → chờ ít phút / bật billing / đổi nhà cung cấp.

---

## 10. MẸO & LỖI THƯỜNG GẶP (mục "Xử lý sự cố")

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Render báo "filename too long" | Đường dẫn quá 260 ký tự | Bật Long Path Windows, hoặc để file ở thư mục ngắn hơn |
| Crossfade báo lỗi với video nhiều ảnh | (Đã vá bản mới) dòng lệnh quá dài | Chạy `update.bat` lấy bản mới; hoặc tạm tắt Crossfade |
| Ảnh ra sai phong cách (ra người thật) | Công cụ tạo ảnh không bám caption | Dùng Style Lock / ảnh tham chiếu |
| Clip ghép lệch tiếng | scenes.csv không khớp SRT | Tạo lại prompt cho đúng video trước khi render |
| Render dùng nhầm bảng cảnh video khác | scenes.csv bị đè | Dùng "Thư mục lưu prompt" riêng, hoặc Hàng đợi |
| Prompt không có phong cách | Profile trống / sai | Kiểm tra đã chọn đúng profile + profile có nội dung |

`[📷 HÌNH 16 — (Tùy chọn) Ảnh ví dụ thông báo lỗi đỏ trong app, để user nhận diện]`

---

## 11. BẢNG THUẬT NGỮ (cho người mới)

| Thuật ngữ | Nghĩa |
|---|---|
| **SRT** | File phụ đề có mốc thời gian. |
| **Voiceover** | Giọng đọc thuyết minh. |
| **Cảnh (scene)** | Đoạn ~8 giây, gồm 1 hoặc vài câu phụ đề gộp; ứng 1 ảnh/clip. |
| **scenes.csv** | Bảng phân cảnh tool tạo, dùng khớp ảnh theo thời gian. |
| **Prompt** | Câu lệnh mô tả để AI tạo ảnh/clip. |
| **Style Profile** | Mô tả phong cách hình ảnh cố định của kênh. |
| **Style Lock** | Tính năng công cụ tạo ảnh khoá phong cách bằng ảnh mẫu. |
| **Ken Burns** | Hiệu ứng zoom/lia chậm trên ảnh tĩnh. |
| **Render** | Ghép ảnh + tiếng + phụ đề thành video MP4. |
| **Faceless** | Kênh YouTube không lộ mặt. |

---

## 12. DANH SÁCH ẢNH CẦN CHỤP (gửi kèm cho Cowork)

> **Boss chụp các ảnh sau, đặt tên đúng số, đưa Cowork chèn vào đúng `[📷 HÌNH N]`.**

| Số | Tên file gợi ý | Chụp gì |
|---|---|---|
| 1 | `hinh01_giao-dien.png` | Toàn cảnh app mới mở (sidebar 4 mục + nội dung + Nhật ký) |
| 2 | `hinh02_thu-muc.png` | Thư mục tool, thấy install/run/update.bat |
| 3 | `hinh03_mat-khau.png` | Hộp thoại nhập mật khẩu |
| 4 | `hinh04_so-do.png` | (Cowork tự vẽ sơ đồ 4 bước) |
| 5 | `hinh05_trang-prompt.png` | Toàn bộ trang Tạo Prompt |
| 6 | `hinh06_3-o-dau.png` | Cận cảnh ô SRT + Tiêu đề + Thư mục lưu prompt |
| 7 | `hinh07_kieu-style.png` | Cận cảnh "Kiểu sản xuất" + "Áp style" |
| 8 | `hinh08_nhat-ky-prompt.png` | Nhật ký lúc đang tạo prompt |
| 9 | `hinh09_trang-render.png` | Toàn bộ trang Render Video |
| 10 | `hinh10_o-tick.png` | Cận cảnh 3 ô Ken Burns / Phụ đề / Crossfade |
| 11 | `hinh11_dat-ten-anh.png` | Thư mục ảnh đặt tên 01, 02, 03... |
| 12 | `hinh12_style-profile.png` | Tab Cài đặt phần Style Profile |
| 13 | `hinh13_dung-sai.png` | (Tùy chọn) Ảnh kết quả đúng vs sai phong cách |
| 14 | `hinh14_nhat-ky-render.png` | Nhật ký render, khoanh dòng "• Rải ảnh: theo bảng cảnh" |
| 15 | `hinh15_cai-dat-api.png` | Tab Cài đặt phần API (nhà cung cấp/model/key) |
| 16 | `hinh16_loi.png` | (Tùy chọn) Ảnh thông báo lỗi đỏ |

---

## 13. GHI CHÚ KỸ THUẬT (nếu Cowork cần chính xác)

- Output prompt: `veo_prompts.txt` (ảnh/video) hoặc `image_prompts.txt` + `motion_prompts.txt` (image-to-video).
- Bảng cảnh: `scenes.csv` (cột: scene, start, end, dur, veo_sec, speed, text, prompt[, motion]).
- Render: FFmpeg, mặc định 1920×1080, 30fps; chế độ khớp clip (cut/speed/loop); crossfade chia cụm ≤20 ảnh.
- Mật khẩu lưu dạng mã băm (không lưu mật khẩu thật, không lưu API key trong file chia sẻ). App nhớ đăng nhập 30 ngày/máy.
