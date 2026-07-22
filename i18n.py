# -*- coding: utf-8 -*-
"""Song ngữ Việt ↔ Anh cho PeiPei Auto Edit Video.

Cách hoạt động:
- Từ điển EN: chuỗi TIẾNG VIỆT (đúng nguyên văn trong code) -> tiếng Anh.
  Thiếu bản dịch -> giữ nguyên tiếng Việt (không bao giờ vỡ UI).
- tr(s): dịch 1 chuỗi theo ngôn ngữ hiện tại (dùng cho popup/status/chuỗi động).
- translate_tree(root): quét CÂY widget, dịch mọi nhãn tĩnh tại chỗ -> đổi ngôn ngữ
  SỐNG không cần mở lại app; lưu chuỗi gốc trên widget nên đổi qua lại vô hạn lần.
- RULES: mẫu regex cho nhãn ĐỘNG có số/ngày (phiên bản, hàng đợi, license...).
- detect_default(): máy Windows không phải tiếng Việt -> mặc định English
  (khách nước ngoài mở app lần đầu đọc được ngay).
"""
import re

_lang = "vi"                      # "vi" | "en"


def set_lang(code):
    global _lang
    _lang = "en" if str(code).lower().startswith("en") else "vi"


def get_lang():
    return _lang


def detect_default():
    """Ngôn ngữ mặc định cho LẦN CHẠY ĐẦU (chưa có trong config): theo locale Windows."""
    try:
        import ctypes
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return "vi" if (lang_id & 0xFF) == 0x2A else "en"   # 0x2A = Vietnamese
    except Exception:
        return "vi"


# ───────────────────────── TỪ ĐIỂN: Việt -> Anh ─────────────────────────
EN = {
    # ----- Sidebar + khung chính -----
    "✍️  Tạo Prompt": "✍️  Create Prompts",
    "🎬  Render Video": "🎬  Render Video",
    "🌙  Video ngủ": "🌙  Sleep Video",
    "📋  Hàng đợi": "📋  Queue",
    "⚙️  Cài đặt": "⚙️  Settings",
    "Hỗ trợ Zalo : 0827298265": "Support Zalo : 0827298265",
    "Nhật ký": "Log",
    "Sẵn sàng.": "Ready.",
    # ----- Trang Tạo Prompt -----
    "Nguyên liệu": "Inputs",
    "File PHỤ ĐỀ (SRT):": "SUBTITLE file (SRT):",
    "Chọn...": "Browse...",
    "📌 Tiêu đề video:": "📌 Video title:",
    "(tự điền từ tên SRT — có thể sửa)": "(auto-filled from SRT name — editable)",
    "📁 Thư mục lưu prompt:": "📁 Prompt output folder:",
    "(Tùy chọn) Mỗi video 1 thư mục riêng → prompt + scenes.csv không đè nhau, render lại khỏi tốn API. Để TRỐNG = lưu ở gốc (đè như cũ).":
        "(Optional) One folder per video → prompts + scenes.csv never overwrite each other, re-render without paying API again. LEAVE EMPTY = save in app folder (overwrites).",
    "Style Profile:": "Style Profile:",
    "(quản lý ở Cài đặt)": "(manage in Settings)",
    "🎭 Tên nhân vật chính:": "🎭 Main character name(s):",
    "(TRỐNG nếu không có; NHIỀU nhân vật cách nhau dấu phẩy: Kha, Thảo)":
        "(EMPTY if none; separate MULTIPLE names with commas: Anna, Ben)",
    "Tùy chọn prompt": "Prompt options",
    "Số giây mỗi cảnh:": "Seconds per scene:",
    "(2–10s: hợp clip Veo  ·  >10s: ẢNH TĨNH kéo dài — cho video ngủ)":
        "(2–10s: fits Veo clips  ·  >10s: long STILL IMAGE — for sleep videos)",
    "Kiểu sản xuất video": "Production type",
    "🖼️  Ảnh tĩnh + Ken Burns — 1 prompt ẢNH  (kênh ảnh tĩnh, dùng zoom)":
        "🖼️  Still images + Ken Burns — 1 IMAGE prompt  (still-image channels, zoom effect)",
    "🎬  Clip video trực tiếp — 1 prompt VIDEO  (Veo text-to-video)":
        "🎬  Direct video clips — 1 VIDEO prompt  (Veo text-to-video)",
    "⭐  Clip từ ảnh — 2 prompt: ẢNH + CHUYỂN ĐỘNG  (có nhân vật chính, đồng nhất cao)":
        "⭐  Clips from images — 2 prompts: IMAGE + MOTION  (main character, high consistency)",
    "🎞️  Ảnh đầu→cuối (chuỗi gối đầu) — N+1 ẢNH + N CHUYỂN ĐỘNG  (Veo Frames-to-Video, video liền mạch)":
        "🎞️  First→last frame (chained) — N+1 IMAGES + N MOTIONS  (Veo Frames-to-Video, seamless story)",
    "Phong cách (Style) để AI hay ẢNH MẪU lo? — chọn đúng 1, chọn cả 2 nơi sẽ chọi nhau":
        "Who controls the STYLE — AI or a REFERENCE IMAGE? Pick exactly 1 (both = conflict)",
    "①  AI viết STYLE ngay trong prompt — chọn khi bạn KHÔNG dùng ảnh mẫu ở tool tạo video":
        "①  AI writes STYLE inside each prompt — pick this when you DON'T use a style reference image",
    "⭐  Ảnh mẫu lo NÉT VẼ — AI lo màu sắc + bối cảnh — chọn khi CÓ dùng ảnh mẫu (khuyên dùng)":
        "⭐  Reference image controls LINE ART — AI writes colors + setting — pick when you USE a reference (recommended)",
    "②  Ảnh mẫu lo TOÀN BỘ phong cách — AI chỉ viết nội dung cảnh (không tả màu, không tả style)":
        "②  Reference image controls the WHOLE style — AI writes scene content only (no colors, no style)",
    "Ảnh mẫu = ảnh khóa phong cách (Style Lock / ảnh tham chiếu) bạn đưa vào tool tạo video như Veo/Flow.":
        "Reference image = the style-lock image you give the video tool (Veo/Flow Style Lock).",
    "🤖  TẠO PROMPT (AI)": "🤖  CREATE PROMPTS (AI)",
    "📄 Mở veo_prompts.txt": "📄 Open veo_prompts.txt",
    "①  Bấm TẠO PROMPT → ra prompt  →  ②  tạo ảnh/clip (đặt tên 01,02...) bỏ vào thư mục clip  →  ③  sang trang 🎬 Render.":
        "①  Click CREATE PROMPTS  →  ②  generate images/clips (name them 01,02...) into the clip folder  →  ③  go to 🎬 Render.",
    # ----- Trang Render -----
    "Thư mục ẢNH/CLIP:": "IMAGE/CLIP folder:",
    "File VOICEOVER:": "VOICEOVER file:",
    "📋 File bảng cảnh:": "📋 Scene table file:",
    "Xuất ra MP4:": "Output MP4:",
    "📋 File bảng cảnh (scenes.csv): để TRỐNG = tự tìm. NÊN CHỌN đúng scenes.csv của video này để render khớp tiếng (tránh dùng nhầm bảng cảnh video khác → cảnh lệch audio).":
        "📋 Scene table (scenes.csv): EMPTY = auto-detect. SHOULD pick this video's own scenes.csv so render matches the audio (a wrong table = scenes out of sync).",
    "Tùy chọn ghép": "Assembly options",
    "📐 Khung hình:": "📐 Aspect ratio:",
    "16:9 ngang (YouTube)": "16:9 landscape (YouTube)",
    "9:16 dọc (Shorts/TikTok)": "9:16 portrait (Shorts/TikTok)",
    "• Khung hình: 9:16 DỌC (1080x1920 — Shorts/TikTok/Reels)":
        "• Aspect: 9:16 PORTRAIT (1080x1920 — Shorts/TikTok/Reels)",
    "Ken Burns (zoom ảnh tĩnh)": "Ken Burns (zoom stills)",
    "Chèn phụ đề": "Burn subtitles",
    "Crossfade ảnh": "Crossfade images",
    "kiểu:": "type:",
    "🖍 Phụ đề — Phông chữ:": "🖍 Subtitles — Font:",
    "Màu chữ:": "Text color:",
    "Đổi": "Pick",
    "Màu viền:": "Outline color:",
    "Cách hiện sub:": "Subtitle display:",
    "1 TỪ nhảy theo voice (mặc định)": "1 WORD synced to voice (default)",
    "Cả câu": "Full sentence",
    "Cả câu + tô màu từ đang đọc": "Full sentence + karaoke highlight",
    "Preset màu (bấm chọn):": "Color presets (click):",
    "🎨 Màu phim:": "🎨 Color grade:",
    "Vignette (tối góc)": "Vignette",
    "Hạt phim": "Film grain",
    "🎵 Nhạc nền:": "🎵 Background music:",
    "🔉 Giữ âm thanh gốc của clip (mặc định tắt tiếng)":
        "🔉 Keep the clips' original audio (muted by default)",
    "Âm lượng tiếng clip:": "Clip audio volume:",
    "• Tách âm thanh gốc của clip (khớp từng cảnh)...":
        "• Extracting the clips' original audio (scene-aligned)...",
    "  (không clip nào có âm thanh — bỏ qua)": "  (no clip has audio — skipped)",
    # ----- 1.2.0: hồ sơ kênh + thương hiệu + tiện ích -----
    "📺 Hồ sơ kênh:": "📺 Channel profile:",
    "💾 Lưu kênh...": "💾 Save channel...",
    "(lưu/áp trọn bộ: khung hình, phụ đề, màu, nhạc, logo, intro...)":
        "(saves/applies everything: aspect, subtitles, colors, music, logo, intro...)",
    "Lưu hồ sơ kênh": "Save channel profile",
    "Tên kênh (vd: Stickman, Quân sự...):": "Channel name (e.g. Stickman, Military...):",
    "Thương hiệu kênh (tùy chọn — bỏ trống = như cũ)":
        "Channel branding (optional — leave empty = same as before)",
    "🖼 Logo/watermark:": "🖼 Logo/watermark:",
    "Góc:": "Corner:",
    "Độ mờ:": "Opacity:",
    "🅣 Chèn TIÊU ĐỀ mở video (lấy từ ô 📌 Tiêu đề, chữ to + fade)":
        "🅣 Show the video TITLE at the start (from 📌 Title, large text + fade)",
    "giây:": "secs:",
    "🎬 Intro:": "🎬 Intro:",
    "Outro:": "Outro:",
    "💥 SFX chuyển cảnh:": "💥 Transition SFX:",
    "📑 Chapters": "📑 Chapters",
    "🖼 Frame thumbnail": "🖼 Thumbnail frames",
    "Chưa thấy file bảng cảnh (scenes.csv).": "Scene table (scenes.csv) not found.",
    "Không đọc được bảng cảnh.": "Could not read the scene table.",
    "Chưa thấy file video xuất — render trước đã.":
        "Output video not found — render first.",
    "Video quá ngắn / không đọc được.": "Video too short / unreadable.",
    "Đã trích 6 frame thumbnail.": "Extracted 6 thumbnail frames.",
    "đang ghép bản cuối...": "assembling final pass...",
    "• Dựng track SFX chuyển cảnh...": "• Building the transition SFX track...",
    "• Ghép intro/outro vào video...": "• Attaching intro/outro...",
    "  (concat copy lệch — re-encode lại toàn bộ cho chắc)":
        "  (copy concat mismatched — re-encoding the whole thing to be safe)",
    "  (folder nhạc nền không có file audio nào — bỏ qua nhạc)":
        "  (no audio files in the music folder — skipping music)",
    "Âm lượng:": "Volume:",
    "Tự hạ nhạc khi có lời": "Auto-duck music under voice",
    "▶  RENDER VIDEO": "▶  RENDER VIDEO",
    "👁️ Xem trước": "👁️ Preview",
    "➕ Thêm vào Hàng đợi": "➕ Add to Queue",
    "🔍 Kiểm tra khớp nghĩa": "🔍 Check scene match",
    "📂 Mở thư mục xuất": "📂 Open output folder",
    "Đặt clip Veo tên 01,02,... trong thư mục clip. Render dùng scenes.csv (sinh ở trang Tạo Prompt) để khớp clip theo đúng timestamp.":
        "Name your Veo clips 01,02,... in the clip folder. Render uses scenes.csv (from Create Prompts) to place each clip at its exact timestamp.",
    # ----- Trang Video ngủ -----
    "Video ngủ dài (clip/ảnh nền + audio dài → 3-4 tiếng)":
        "Long sleep video (background clip/image + long audio → 3-4 hours)",
    "🎬 NỀN (clip / ảnh):": "🎬 BACKGROUND (clip / image):",
    "🎵 AUDIO dài (kịch bản):": "🎵 LONG AUDIO (narration):",
    "🌧️ Âm thanh NỀN (mưa/gió/tuyết — tùy chọn):": "🌧️ AMBIENT sound (rain/wind/snow — optional):",
    "Clip nền ngắn (vd 10s) tự LOOP LIỀN MẠCH (crossfade) cho hết audio, GIỮ NGUYÊN cảnh. Render rất nhanh (loop-copy) — 4 tiếng cũng chỉ vài phút.":
        "A short background clip (e.g. 10s) loops SEAMLESSLY (crossfade) for the whole audio, scene unchanged. Very fast render (loop-copy) — even 4 hours takes minutes.",
    "Tùy chọn": "Options",
    "✨ Hiệu ứng (cho nền ẢNH tĩnh):": "✨ Effect (for STILL image background):",
    "Fade tiếng (s):": "Audio fade (s):",
    "🎵 Visualizer:": "🎵 Visualizer:",
    "🔊 Âm lượng âm thanh nền:": "🔊 Ambient volume:",
    "(0.15 = rất nhẹ · 0.25 = nhẹ · 0.5 = rõ). Chỉ áp dụng khi có chọn file âm thanh nền ở trên.":
        "(0.15 = very soft · 0.25 = soft · 0.5 = clear). Only applies when an ambient file is selected above.",
    "Để hiệu ứng 'none' nếu nền đã đẹp (vd clip cảnh có sẵn). Hiệu ứng tự tạo (mưa/tuyết/sương/bokeh) chỉ cho nền ẢNH TĨNH. ⚠️ Visualizer (bars/waves) bật → render LÂU hơn nhiều (vẽ theo audio, không loop-copy được).":
        "Keep effect 'none' if the background already looks good (e.g. a real scene clip). Generated effects (rain/snow/fog/bokeh) are for STILL image backgrounds only. ⚠️ Visualizer (bars/waves) makes render MUCH slower (drawn from audio, no loop-copy).",
    "🌙  TẠO VIDEO NGỦ": "🌙  CREATE SLEEP VIDEO",
    "👁️ Xem trước (20s)": "👁️ Preview (20s)",
    # ----- Trang Hàng đợi -----
    "Mẹo: ở tab '🎬 Làm video' set SRT + thư mục clip + voice + tên file ra, rồi bấm '➕ Hàng đợi'. Mỗi video nên để clip ở THƯ MỤC RIÊNG và đặt TÊN FILE RA khác nhau (tránh ghi đè).":
        "Tip: on the '🎬 Render' tab set SRT + clip folder + voice + output name, then click '➕ Add to Queue'. Give each video its OWN clip folder and a UNIQUE output name (avoid overwriting).",
    "🗑 Xoá mục chọn": "🗑 Remove selected",
    "🧹 Xoá hết": "🧹 Clear all",
    "▶  RENDER CẢ HÀNG ĐỢI": "▶  RENDER WHOLE QUEUE",
    "📜 Lịch sử render": "📜 Render history",
    "(các video đã render xong)": "(videos rendered so far)",
    "📂 Mở thư mục video": "📂 Open video folder",
    "🧹 Xoá lịch sử": "🧹 Clear history",
    "(nháy đúp 1 dòng = mở thư mục video)": "(double-click a row = open its folder)",
    # ----- Trang Cài đặt -----
    "Phần mềm": "Software",
    "🔄 Kiểm tra cập nhật": "🔄 Check for updates",
    "🌐 Ngôn ngữ / Language:": "🌐 Ngôn ngữ / Language:",
    "API viết prompt — chọn nhà cung cấp": "Prompt-writing API — pick a provider",
    "Nhà cung cấp:": "Provider:",
    "Model:": "Model:",
    "(tự cập nhật từ API; model đầu = mặc định rẻ)": "(auto-fetched from API; first = cheap default)",
    "API Key:": "API Key:",
    "Hiện": "Show",
    "💾 Lưu key": "💾 Save key",
    "🔌 Kiểm tra kết nối": "🔌 Test connection",
    "Style Visual Profile (cho từng kênh)": "Style Visual Profile (per channel)",
    "Danh sách:": "Profiles:",
    "➕ Thêm": "➕ Add",
    "🗑 Xoá": "🗑 Delete",
    "Nội dung style (dán mô tả phong cách kênh):": "Style content (paste your channel's style description):",
    "👁️ Xem trước style": "👁️ Preview style",
    "💾 Lưu profile này": "💾 Save this profile",
    "Key tại platform.openai.com/api-keys": "Get a key at platform.openai.com/api-keys",
    "Key tại aistudio.google.com": "Get a key at aistudio.google.com",
    "Key tại console.anthropic.com → Get API key":
        "Get a key at console.anthropic.com → Get API key",
    # ----- Popup dùng chung (tiêu đề + nội dung hay gặp) -----
    "Thiếu": "Missing",
    "Lỗi": "Error",
    "Xong": "Done",
    "Chưa có": "Nothing yet",
    "Hàng đợi trống": "Queue is empty",
    "Không thể xoá": "Cannot delete",
    "Chọn profile": "Pick a profile",
    "Xem trước style": "Style preview",
    "Thiếu API key": "Missing API key",
    "Thiếu style": "Missing style",
    "Xoá": "Delete",
    "Xoá hết": "Clear all",
    "🔔 Có bản cập nhật mới": "🔔 Update available",
    "Kiểm tra cập nhật": "Check for updates",
    "Không mở được app": "Cannot start app",
    "Chưa chọn file SRT hợp lệ.": "No valid SRT file selected.",
    "Chưa chọn thư mục ảnh/clip.": "No image/clip folder selected.",
    "Chưa nhập API key (vào tab Cài đặt).": "No API key yet (see Settings tab).",
    "Đang kiểm tra cập nhật...": "Checking for updates...",
    "Đang tải bản cập nhật...": "Downloading update...",
    "CẬP NHẬT NGAY? (app tự tải + tự cài + khởi động lại — bạn không cần làm gì)":
        "UPDATE NOW? (the app downloads, installs and restarts itself — nothing else to do)",
    "Mở trang tải bản mới ngay?": "Open the download page now?",
    "Chưa kiểm tra được bản mới — hãy kiểm tra kết nối mạng.":
        "Could not check for updates — please check your internet connection.",
    # ----- Trạng thái license (license_client.check trả tiếng Việt) -----
    "Chưa kích hoạt.": "Not activated.",
    "License không hợp lệ (chữ ký sai).": "Invalid license (bad signature).",
    "License này không dùng được trên máy hiện tại.": "This license is not valid on this machine.",
    "License này không dành cho phần mềm này.": "This license is for a different product.",
    "License đã hết hạn.": "License expired.",
    "Phản hồi server không hợp lệ.": "Invalid server response.",
    # ----- Hộp thoại kích hoạt license -----
    "Kích hoạt bản quyền — PeiPei Auto Edit Video":
        "Activate license — PeiPei Auto Edit Video",
    "Phần mềm cần kích hoạt bản quyền để sử dụng.":
        "This software needs a license to run.",
    "Mã máy (gửi mã này cho người bán để lấy key):":
        "Machine ID (send this code to the seller to get your key):",
    "Dán license key:": "Paste your license key:",
    "Hãy dán license key.": "Please paste a license key.",
    "Đang kích hoạt...": "Activating...",
    "Kích hoạt thất bại.": "Activation failed.",
    "Kích hoạt": "Activate",
    "Thoát": "Quit",
    # ----- Log engine (auto_edit.py / sleep_video.py) -----
    "theo --fps": "from --fps",
    "khớp clip video -> hết rung": "matches video clips -> no jitter",
    "toàn ảnh tĩnh -> Ken Burns mượt": "all still images -> smooth Ken Burns",
    "KHÔNG": "NONE",
    "theo SRT": "per SRT",
    "ảnh tĩnh": "still image",
    "• Áp crossfade cho các ảnh tĩnh...": "• Applying crossfade to still images...",
    "• Đang render bản cuối (màu + phụ đề + voice + nhạc nền)...":
        "• Rendering final pass (color + subtitles + voice + music)...",
    "• Đang render bản cuối (phụ đề + voice)...":
        "• Rendering final pass (subtitles + voice)...",
    "• (1/2) Dựng đoạn nền loop + hiệu ứng...":
        "• (1/2) Building background loop + effects...",
    "• (2/2) Render FULL + visualizer theo audio (lâu hơn vì vẽ theo nhạc)...":
        "• (2/2) FULL render + audio visualizer (slower — drawn from the music)...",
    "• (2/2) Lặp nền COPY + TRỘN âm thanh nền vào tiếng + fade...":
        "• (2/2) Loop-copy background + MIX ambient into audio + fade...",
    "• (2/2) Lặp nền cho hết audio + ghép tiếng + fade (video COPY -> nhanh)...":
        "• (2/2) Loop background over full audio + mux + fade (video COPY -> fast)...",
    "1 ảnh / 1 đoạn phụ đề": "1 image per subtitle segment",
    # ----- Video ngủ: FOLDER nhiều ảnh/clip -----
    "• Xem trước: rút gọn vòng xoay folder (mỗi mục ~6s) cho nhanh...":
        "• Preview: shortened folder rotation (~6s per item) for speed...",
    "Giây mỗi mục chỉ nhận 4–3600s — đã tự chỉnh lại.":
        "Seconds-per-item accepts 4–3600s — value adjusted.",
    "⏱ Giây mỗi mục (folder):": "⏱ Seconds per item (folder):",
    "Chưa chọn nền (1 file clip/ảnh, hoặc 1 folder nhiều ảnh/clip).":
        "No background selected (pick 1 clip/image file, or 1 folder of images/clips).",
    "Nền = 1 FILE (clip ngắn tự LOOP LIỀN MẠCH — render vài phút) hoặc 1 FOLDER "
    "nhiều ảnh/clip (nút 📁 Folder — tự XOAY VÒNG + crossfade theo tên file, "
    "dựng đoạn loop lâu hơn chút).":
        "Background = 1 FILE (a short clip loops SEAMLESSLY — renders in minutes) or 1 FOLDER "
        "of images/clips (📁 Folder button — auto-ROTATES + crossfades in filename order; "
        "building the loop takes a bit longer).",
    # ----- Popup còn lại hay gặp -----
    "Chưa có video nào trong hàng đợi.": "The queue has no videos yet.",
    "Phải giữ ít nhất 1 profile.": "At least 1 profile must remain.",
    "Hãy chọn 1 profile bên trái (hoặc bấm Thêm).": "Pick a profile on the left (or click Add).",
    "Profile đang trống.": "This profile is empty.",
    "Style profile đang trống. Vào tab Cài đặt để dán nội dung, hoặc chọn chế độ '② Lock lo TẤT CẢ style'.":
        "The style profile is empty. Paste content in Settings, or pick mode '② Reference image controls the WHOLE style'.",
}

# Nhãn ĐỘNG có số/ngày -> dịch bằng regex (giữ phần số)
RULES = [
    (re.compile(r"^Phiên bản hiện tại: (.+)$"), "Current version: {0}"),
    (re.compile(r"^Phiên bản (.+)$"), "Version {0}"),
    (re.compile(r"^(\d+) video trong hàng đợi$"), "{0} video(s) in queue"),
    (re.compile(r"^License: Thuê bao \| Hết hạn (.+) \(còn (\d+) ngày\)$"),
     "License: Subscription | Expires {0} ({1} days left)"),
    (re.compile(r"^License: Trọn đời(.*)$"), "License: Lifetime{0}"),
    (re.compile(r"^License: (.+)$"), "License: {0}"),   # msg lỗi việt -> tra tiếp từ điển
    (re.compile(r"^Đã có phiên bản mới: (.+)$"), "New version available: {0}"),
    (re.compile(r"^Bạn đang dùng phiên bản mới nhất \((.+)\)\.$"),
     "You are on the latest version ({0})."),
    # ----- Log engine (dòng có số liệu) -----
    (re.compile(r"^• Encoder: (.+) \| Render song song: (\d+) cảnh/lúc$"),
     "• Encoder: {0} | Parallel render: {1} scenes at once"),
    (re.compile(r"^• Phụ đề: (\d+) đoạn \(tự khớp voiceover theo timestamp\) \| Ảnh: (\d+) \| Voice: (.+) \((.+)\)$"),
     "• Subtitles: {0} segments (auto-synced to voiceover) | Images: {1} | Voice: {2} ({3})"),
    (re.compile(r"^• Rải ảnh: (.+) → (\d+) cảnh \| tổng video (.+)s$"),
     "• Layout: {0} → {1} scenes | total video {2}s"),
    (re.compile(r"^   cảnh +(\d+): (.+)$"), "   scene {0}: {1}"),
    (re.compile(r"^   → TỔNG (.+)s \(khớp voice/SRT (.+)s\)$"),
     "   → TOTAL {0}s (matches voice/SRT {1}s)"),
    (re.compile(r"^✅ XONG: (.+)$"), "✅ DONE: {0}"),
    (re.compile(r"^  \(Voice dài ([\d.]+)s > SRT ([\d.]+)s — .+\)$"),
     "  (Voice {0}s is longer than SRT {1}s — last image extended to cover the audio.)"),
    (re.compile(r"^• Temp giữ lại tại: (.+)$"), "• Temp kept at: {0}"),
    (re.compile(r"^     \(ảnh lớn (\d+)x(\d+) -> thu nhỏ (\d+)px cho nhanh & khỏi treo\)$"),
     "     (large image {0}x{1} -> shrunk to {2}px for speed & stability)"),
    (re.compile(r"^     \(CẢNH BÁO: ảnh (\d+)x(\d+) quá lớn.+\)$"),
     "     (WARNING: image {0}x{1} too large to shrink — rendering as-is)"),
    (re.compile(r"^QUÁ (\d+)s chưa xong \(treo\?\) — (.+)$"),
     "TIMED OUT after {0}s (stuck?) — {1}"),
    (re.compile(r"^• Nền: (.+) \((.+)\) \| Hiệu ứng: (.+) \| Encoder: (.+)$"),
     "• Background: {0} ({1}) | Effect: {2} | Encoder: {3}"),
    (re.compile(r"^• Audio: (.+) \| Video dài: (\d+)s \((.+)h\) \| loop nền (\d+)s$"),
     "• Audio: {0} | Video length: {1}s ({2}h) | background loop {3}s"),
    (re.compile(r"^• Âm thanh nền: (.+) \(âm lượng (.+)\)$"),
     "• Ambient: {0} (volume {1})"),
    (re.compile(r"^Vào tab Cài đặt nhập API key cho '(.+)' trước nhé\.$"),
     "Enter an API key for '{0}' in the Settings tab first."),
    (re.compile(r"^Vào Cài đặt nhập key cho '(.+)'\.$"),
     "Enter a key for '{0}' in Settings."),
    # 1.2.0
    (re.compile(r"^Đã áp hồ sơ kênh '(.+)'\.$"), "Applied channel profile '{0}'."),
    (re.compile(r"^Đã lưu hồ sơ kênh '(.+)'\.$"), "Saved channel profile '{0}'."),
    (re.compile(r"^Xoá hồ sơ kênh '(.+)'\?$"), "Delete channel profile '{0}'?"),
    (re.compile(r"^Đã xuất chapters: (.+)$"), "Chapters exported: {0}"),
    (re.compile(r"^còn ~(\d+)p(\d+)s$"), "~{0}m{1}s left"),
    (re.compile(r"^• Nhạc nền: playlist (\d+) bài \(nối theo tên file\)$"),
     "• Music: playlist of {0} tracks (joined by filename)"),
    (re.compile(r"^  ⚠️ Clip hỏng \(1 frame\): (.+) — đã dùng như ẢNH TĨNH \(Ken Burns\) thay thế$"),
     "  ⚠️ Broken clip (1 frame): {0} — used as a STILL IMAGE (Ken Burns) instead"),
    # Video ngủ: FOLDER nhiều ảnh/clip
    (re.compile(r"^• Chế độ mục DÀI: (\d+) mục × ~(.+)s \(lặp đoạn (.+)s bằng COPY, chỉ encode (\d+) đoạn \+ (\d+) mối nối\)\.\.\.$"),
     "• LONG-item mode: {0} items × ~{1}s (looping a {2}s segment by COPY — only {3} segments + {4} junctions encoded)..."),
    (re.compile(r"^  \(nhiều mục: dùng (\d+)/(\d+) mục đầu cho vòng xoay\)$"),
     "  (many items: using the first {0}/{1} for the rotation)"),
    (re.compile(r"^thư mục (\d+) mục$"), "folder ({0} items)"),
    (re.compile(r"^• Ghép (\d+) mục nền \(xoay vòng \+ crossfade, mỗi mục ≤(.+)s\)\.\.\.$"),
     "• Chaining {0} background items (rotation + crossfade, ≤{1}s each)..."),
    (re.compile(r"^  \(nhiều mục: dùng (\d+)/(\d+) mục đầu cho đoạn loop\)$"),
     "  (many items: using the first {0}/{1} for the loop)"),
    (re.compile(r"^Thư mục nền không có ảnh/clip nào: (.+)$"),
     "No images/clips found in background folder: {0}"),
    # mode_label (kiểu rải ảnh) trong dòng Layout
    (re.compile(r"^theo bảng cảnh \((\d+) cảnh, khóa timestamp SRT\)$"),
     "scene table ({0} scenes, locked to SRT timestamps)"),
    (re.compile(r"^mỗi ảnh ~(.+)s \(lặp vòng (\d+) ảnh\)$"),
     "~{0}s per image (cycling {1} images)"),
    (re.compile(r"^rải đều (\d+) ảnh$"), "{0} images spread evenly"),
]

_REV = {v: k for k, v in EN.items()}          # Anh -> Việt (đổi ngược khi switch về vi)


def tr(s):
    """Dịch 1 chuỗi theo ngôn ngữ hiện tại. Không có bản dịch -> giữ nguyên.
    Nhóm bắt được trong RULES cũng được tra tiếp qua từ điển (vd 'License: <msg việt>')."""
    if not isinstance(s, str):
        return s
    if _lang == "en":
        if s in EN:
            return EN[s]
        for rx, tpl in RULES:
            m = rx.match(s)
            if m:
                return tpl.format(*(EN.get(g, g) for g in m.groups()))
        return s
    return _REV.get(s, s)                      # về vi: map ngược nếu đang là chuỗi Anh


def translate_tree(root):
    """Quét cây widget, dịch mọi nhãn tĩnh theo ngôn ngữ hiện tại (đổi qua lại được).
    Lưu chuỗi NGUỒN trên widget (w._i18n_src); nhãn bị code đổi text sau đó sẽ tự
    cập nhật nguồn mới ở lần quét kế (so với w._i18n_last)."""
    def walk(w):
        for c in w.winfo_children():
            try:
                cur = c.cget("text")
                if isinstance(cur, str) and cur.strip():
                    if getattr(c, "_i18n_last", None) != cur:
                        c._i18n_src = cur          # text mới do code đặt -> nguồn mới
                    out = tr(c._i18n_src) if _lang == "en" else _to_vi(c._i18n_src)
                    c.configure(text=out)
                    c._i18n_last = out
            except Exception:
                pass
            walk(c)
    walk(root)


def _to_vi(s):
    """Đưa chuỗi về tiếng Việt: nếu là chuỗi Anh đã dịch -> map ngược; regex rules ngược."""
    if s in _REV:
        return _REV[s]
    return s
