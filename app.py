#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto Edit Video — Giao diện (GUI).
  • Tab "Làm video": up SRT + chọn Style -> [Tạo Prompt] (tự tạo cảnh + viết prompt
    bằng Gemini) -> tạo clip Veo -> [Render Video].
  • Tab "Cài đặt": nhập Gemini API key (có nút kiểm tra kết nối) + quản lý Style Profile.

Chạy: double-click run.bat  hoặc  python app.py
"""
import hashlib
import json
import os
import queue
import secrets
import time
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
CONFIG_PATH = os.path.join(HERE, "config.local.json")
ACCESS_PATH = os.path.join(HERE, "access.json")      # CHỈ chứa mã băm (commit được)
SESSION_PATH = os.path.join(HERE, "session.local.json")  # token ghi nhớ máy này (gitignored)
PBKDF2_ITERS = 200000
SESSION_DAYS = 30     # ghi nhớ bao nhiêu ngày trước khi hỏi lại

DEFAULT_STYLE = (
    "Flat 2D educational illustration. White OR pure black background — never mixed. "
    "Black line art, maximum 3 colors. No shadows, no depth, no environments. "
    "Subjects isolated in negative space. Cosmic objects rendered with soft radial glow on "
    "black. Stick figure mascot (round glasses, hand-drawn) appears in explainer/comparison "
    "scenes. Text overlays in bold black (on white) or bold white (on black). Iconic, minimal "
    "detail."
)


def default_config():
    return {
        "provider": "gemini",                       # gemini | openai | claude
        "keys": {"gemini": "", "openai": "", "claude": ""},
        "models": {},                               # model đang dùng theo provider
        "model_cache": {},                          # danh sách model TỰ lấy từ API theo provider
        "profiles": {"Người que": DEFAULT_STYLE},
        "active_profile": "Người que",
        "produce": "video",                         # image | video | i2v (kiểu sản xuất)
        "style_mode": "in_prompt",
        "main_character": "",
        "queue": [],
    }


def load_config():
    cfg = default_config()
    try:
        with open(CONFIG_PATH, encoding="utf-8-sig") as f:
            data = json.load(f)
        cfg.update({k: data[k] for k in cfg if k in data})
        # Di trú ô tick cũ "tool_style" -> "style_mode"
        if "style_mode" not in data and "tool_style" in data:
            cfg["style_mode"] = "lock_all" if data.get("tool_style") else "in_prompt"
        # Di trú key/model Gemini cũ -> cấu trúc đa nhà cung cấp
        if not cfg["keys"].get("gemini") and data.get("gemini_key"):
            cfg["keys"]["gemini"] = data["gemini_key"]
        if not cfg["models"].get("gemini") and data.get("model"):
            cfg["models"]["gemini"] = data["model"]
        # Di trú "prompt_mode" + "workflow" cũ -> 1 lựa chọn "produce"
        if "produce" not in data:
            if data.get("workflow") == "i2v":
                cfg["produce"] = "i2v"
            elif data.get("prompt_mode") == "image":
                cfg["produce"] = "image"
        if not cfg["profiles"]:
            cfg["profiles"] = {"Người que": DEFAULT_STYLE}
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:  # noqa
        print("Loi luu config:", e)


# ----------------------------- Mật khẩu mở app -----------------------------
def _pw_hash(pw, salt, iters=PBKDF2_ITERS):
    return hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"),
                               bytes.fromhex(salt), iters).hex()


def load_access():
    try:
        with open(ACCESS_PATH, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None


def has_password():
    a = load_access()
    return bool(a and a.get("hash") and a.get("salt"))


def set_password(pw):
    salt = secrets.token_hex(16)
    data = {"algo": "pbkdf2_sha256", "iterations": PBKDF2_ITERS,
            "salt": salt, "hash": _pw_hash(pw, salt)}
    with open(ACCESS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def clear_password():
    try:
        os.remove(ACCESS_PATH)
    except OSError:
        pass


def verify_password(pw):
    a = load_access()
    if not a:
        return True
    try:
        return _pw_hash(pw, a["salt"], a.get("iterations", PBKDF2_ITERS)) == a["hash"]
    except Exception:
        return False


def _session_token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def save_session():
    """Lưu token ghi nhớ đăng nhập cho MÁY NÀY (session.local.json — gitignored)."""
    token = secrets.token_hex(32)
    data = {"token_hash": _session_token_hash(token),
            "expires": time.time() + SESSION_DAYS * 86400}
    with open(SESSION_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return token


def has_valid_session():
    """Kiểm tra máy này đã đăng nhập và còn trong thời hạn chưa."""
    try:
        with open(SESSION_PATH, encoding="utf-8") as f:
            d = json.load(f)
        if time.time() > d.get("expires", 0):
            os.remove(SESSION_PATH)     # hết hạn -> xoá
            return False
        return bool(d.get("token_hash"))
    except Exception:
        return False


def clear_session():
    try:
        os.remove(SESSION_PATH)
    except OSError:
        pass


def password_gate(root):
    """Hỏi mật khẩu khi mở app. True = đúng/không cần; False = sai/huỷ."""
    # Kiểm tra session còn hạn -> tự đăng nhập, không hỏi
    if has_valid_session():
        return True

    for _ in range(3):
        pw = simpledialog.askstring(
            "Mật khẩu",
            f"Nhập mật khẩu mở Auto Edit Video:\n(Ghi nhớ {SESSION_DAYS} ngày trên máy này)",
            show="*", parent=root)
        if pw is None:
            return False                 # bấm Huỷ
        if verify_password(pw):
            save_session()               # đúng -> lưu session để lần sau tự vào
            return True
        messagebox.showerror("Sai mật khẩu", "Mật khẩu không đúng. Thử lại.")
    return False


def dflt(*parts):
    return os.path.join(HERE, *parts)


def _extract_title_from_srt(path):
    """Lấy tiêu đề video từ tên file SRT.
    Xử lý: bỏ timestamp, bỏ hậu tố thừa (_Script/_Final/...), đổi _ thành dấu cách."""
    import re
    name = os.path.splitext(os.path.basename(path or ""))[0]
    # 1) Bỏ timestamp _YYYYMMDD_HHMMSS ở cuối (Clone Voice tự thêm)
    name = re.sub(r'[_\s]*\d{8}[_\s]*\d{6}$', '', name).strip()
    # 2) Bỏ hậu tố thường gặp không thuộc tiêu đề (không phân biệt hoa/thường)
    name = re.sub(r'[\s_]*(Script|Final|Draft|Edit|v\d+|SRT)$', '', name, flags=re.IGNORECASE).strip()
    # 3) Thay _ bằng dấu cách (tên file kiểu Why_You_Cant_Stop)
    name = name.replace('_', ' ').strip()
    return name


class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.q = queue.Queue()
        root.title("Auto Edit Video 🎬")
        root.geometry("880x720")
        root.minsize(780, 640)

        # Biến nguyên liệu DÙNG CHUNG giữa các trang (SRT dùng cho cả Prompt lẫn Render)
        self.srt = tk.StringVar(value=dflt("input", "subtitle.srt"))
        self.video_title = tk.StringVar(value=_extract_title_from_srt(dflt("input", "subtitle.srt")))
        self.images = tk.StringVar(value=dflt("input", "images"))
        self.voice = tk.StringVar(value=self._auto_voice())
        self.out = tk.StringVar(value=dflt("output", "final.mp4"))
        self.secs = tk.StringVar(value="8")
        self.kenburns = tk.BooleanVar(value=True)
        self.subs = tk.BooleanVar(value=True)
        self.crossfade = tk.BooleanVar(value=False)

        # Tự cập nhật tiêu đề khi Boss chọn file SRT khác
        self.srt.trace_add("write", self._on_srt_change)

        # Khung trên: SIDEBAR trái + nội dung phải
        top = ttk.Frame(root)
        top.pack(fill="both", expand=True, padx=6, pady=6)
        side = ttk.Frame(top, width=165)
        side.pack(side="left", fill="y", padx=(0, 6))
        side.pack_propagate(False)
        content = ttk.Frame(top)
        content.pack(side="left", fill="both", expand=True)

        # 4 trang nội dung
        self.pages = {n: ttk.Frame(content) for n in ("prompt", "render", "queue", "settings")}
        self._build_prompt(self.pages["prompt"])
        self._build_render(self.pages["render"])
        self._build_queue(self.pages["queue"])
        self._build_settings(self.pages["settings"])

        # Nút điều hướng sidebar
        self._side_btns = {}
        for name, label in (("prompt", "✍️  Tạo Prompt"), ("render", "🎬  Render Video"),
                            ("queue", "📋  Hàng đợi"), ("settings", "⚙️  Cài đặt")):
            b = tk.Button(side, text=label, anchor="w", relief="flat", bd=0,
                          padx=12, pady=11, font=("", 10),
                          command=lambda n=name: self._show_page(n))
            b.pack(fill="x", pady=1)
            self._side_btns[name] = b

        # Log + status (dùng chung)
        box = ttk.LabelFrame(root, text="Nhật ký")
        box.pack(fill="both", expand=False, padx=6, pady=(0, 4))
        self.log = tk.Text(box, height=8, wrap="word", bg="#1e1e1e",
                           fg="#d4d4d4", insertbackground="white")
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(box, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log["yscrollcommand"] = sb.set

        self.status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(root, textvariable=self.status, anchor="w",
                  relief="sunken").pack(fill="x", side="bottom")

        self._show_page("prompt")
        self.root.after(100, self._drain)

    def _show_page(self, name):
        for p in self.pages.values():
            p.pack_forget()
        self.pages[name].pack(fill="both", expand=True)
        for n, b in self._side_btns.items():
            b.configure(bg=("#cfe2ff" if n == name else "#f0f0f0"))

    # ============================ TRANG TẠO PROMPT ============================
    def _build_prompt(self, parent):
        f1 = ttk.LabelFrame(parent, text="Nguyên liệu")
        f1.pack(fill="x", padx=8, pady=6)
        self._row(f1, "File PHỤ ĐỀ (SRT):", self.srt, lambda: self._pick_file(
            self.srt, [("SRT", "*.srt"), ("Tất cả", "*.*")]))

        title_row = ttk.Frame(f1)
        title_row.pack(fill="x", padx=8, pady=3)
        ttk.Label(title_row, text="📌 Tiêu đề video:", width=18).pack(side="left")
        ttk.Entry(title_row, textvariable=self.video_title).pack(side="left", fill="x", expand=True)
        ttk.Label(title_row, foreground="#888",
                  text="(tự điền từ tên SRT — có thể sửa)").pack(side="left", padx=6)

        sf = ttk.Frame(f1)
        sf.pack(fill="x", padx=8, pady=3)
        ttk.Label(sf, text="Style Profile:", width=18).pack(side="left")
        self.profile_var = tk.StringVar(value=self.cfg.get("active_profile", ""))
        self.cmb_profile = ttk.Combobox(sf, textvariable=self.profile_var,
                                        values=list(self.cfg["profiles"].keys()),
                                        state="readonly")
        self.cmb_profile.pack(side="left", fill="x", expand=True)
        self.cmb_profile.bind("<<ComboboxSelected>>", self._on_profile_pick)
        ttk.Label(sf, text="(quản lý ở Cài đặt)", foreground="#888").pack(side="left", padx=6)

        linec = ttk.Frame(f1)
        linec.pack(fill="x", padx=8, pady=3)
        ttk.Label(linec, text="🎭 Tên nhân vật chính:", width=18).pack(side="left")
        self.main_char = tk.StringVar(value=self.cfg.get("main_character", ""))
        ttk.Entry(linec, textvariable=self.main_char, width=18).pack(side="left", padx=6)
        ttk.Label(linec, foreground="#888",
                  text="(để TRỐNG nếu không có nhân vật chính)").pack(side="left")

        f2 = ttk.LabelFrame(parent, text="Tùy chọn prompt")
        f2.pack(fill="x", padx=8, pady=6)
        line = ttk.Frame(f2)
        line.pack(fill="x", padx=10, pady=6)
        ttk.Label(line, text="Số giây mỗi cảnh:").pack(side="left")
        ttk.Spinbox(line, from_=2, to=30, width=5, textvariable=self.secs).pack(side="left", padx=6)

        fp = ttk.LabelFrame(f2, text="Kiểu sản xuất video")
        fp.pack(fill="x", padx=10, pady=(0, 6))
        self.produce = tk.StringVar(value=self.cfg.get("produce", "video"))
        ttk.Radiobutton(
            fp, variable=self.produce, value="image", command=self._save_produce,
            text="🖼️  Ảnh tĩnh + Ken Burns — 1 prompt ẢNH  (kênh ảnh tĩnh, dùng zoom)"
        ).pack(anchor="w", padx=8, pady=1)
        ttk.Radiobutton(
            fp, variable=self.produce, value="video", command=self._save_produce,
            text="🎬  Clip video trực tiếp — 1 prompt VIDEO  (Veo text-to-video)"
        ).pack(anchor="w", padx=8, pady=1)
        ttk.Radiobutton(
            fp, variable=self.produce, value="i2v", command=self._save_produce,
            text="⭐  Clip từ ảnh — 2 prompt: ẢNH + CHUYỂN ĐỘNG  (có nhân vật chính, đồng nhất cao)"
        ).pack(anchor="w", padx=8, pady=1)

        fstyle = ttk.LabelFrame(f2, text="Áp STYLE ở đâu? (chỉ 1 nơi — tránh chọi style)")
        fstyle.pack(fill="x", padx=10, pady=(0, 6))
        self.style_mode = tk.StringVar(value=self.cfg.get("style_mode", "in_prompt"))
        ttk.Radiobutton(
            fstyle, variable=self.style_mode, value="in_prompt", command=self._save_stylemode,
            text="①  Trong prompt — kèm style  (TẮT Style Lock ở tool video)"
        ).pack(anchor="w", padx=8, pady=1)
        ttk.Radiobutton(
            fstyle, variable=self.style_mode, value="lock_art", command=self._save_stylemode,
            text="⭐  Lock lo NÉT + AI lo MÀU/ERA  (BẬT Style Lock chỉ nét) — khuyên dùng"
        ).pack(anchor="w", padx=8, pady=1)
        ttk.Radiobutton(
            fstyle, variable=self.style_mode, value="lock_all", command=self._save_stylemode,
            text="②  Lock lo TẤT CẢ style — AI chỉ viết nội dung  (BẬT Style Lock đầy đủ)"
        ).pack(anchor="w", padx=8, pady=1)

        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=8, pady=8)
        self.btn_prompt = ttk.Button(bar, text="🤖  TẠO PROMPT (AI)",
                                     command=self.run_make_prompts)
        self.btn_prompt.pack(side="left", padx=4)
        ttk.Button(bar, text="📄 Mở veo_prompts.txt",
                   command=self._open_prompts).pack(side="left", padx=4)

        ttk.Label(parent, wraplength=640, foreground="#555",
                  text="①  Bấm TẠO PROMPT → ra prompt  →  ②  tạo ảnh/clip (đặt tên 01,02...) "
                       "bỏ vào thư mục clip  →  ③  sang trang 🎬 Render.").pack(
            fill="x", padx=12, pady=(0, 4))

    # ============================ TRANG RENDER ============================
    def _build_render(self, parent):
        f1 = ttk.LabelFrame(parent, text="Nguyên liệu")
        f1.pack(fill="x", padx=8, pady=6)
        self._row(f1, "File PHỤ ĐỀ (SRT):", self.srt, lambda: self._pick_file(
            self.srt, [("SRT", "*.srt"), ("Tất cả", "*.*")]))
        self._row(f1, "Thư mục ẢNH/CLIP:", self.images, self._pick_dir)
        self._row(f1, "File VOICEOVER:", self.voice, lambda: self._pick_file(
            self.voice, [("Audio", "*.mp3 *.wav *.m4a *.aac"), ("Tất cả", "*.*")]))
        self._row(f1, "Xuất ra MP4:", self.out, self._pick_save)

        f2 = ttk.LabelFrame(parent, text="Tùy chọn ghép")
        f2.pack(fill="x", padx=8, pady=6)
        line = ttk.Frame(f2)
        line.pack(fill="x", padx=10, pady=8)
        ttk.Checkbutton(line, text="Ken Burns (zoom ảnh tĩnh)",
                        variable=self.kenburns).pack(side="left")
        ttk.Checkbutton(line, text="Chèn phụ đề", variable=self.subs).pack(side="left", padx=14)
        ttk.Checkbutton(line, text="Crossfade ảnh", variable=self.crossfade).pack(side="left")

        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=8, pady=8)
        self.btn_render = ttk.Button(bar, text="▶  RENDER VIDEO", command=self.run_render)
        self.btn_render.pack(side="left", padx=4)
        ttk.Button(bar, text="➕ Thêm vào Hàng đợi",
                   command=self.add_to_queue).pack(side="left", padx=4)
        ttk.Button(bar, text="📂 Mở thư mục xuất",
                   command=self.open_out).pack(side="right", padx=4)

        ttk.Label(parent, wraplength=640, foreground="#555",
                  text="Đặt clip Veo tên 01,02,... trong thư mục clip. Render dùng scenes.csv "
                       "(sinh ở trang Tạo Prompt) để khớp clip theo đúng timestamp.").pack(
            fill="x", padx=12, pady=(0, 4))

    def _open_prompts(self):
        p = dflt("veo_prompts.txt")
        if os.path.isfile(p):
            os.startfile(p)
        else:
            messagebox.showinfo("Chưa có", "Chưa có veo_prompts.txt — bấm TẠO PROMPT trước.")

    # ============================ TAB CÀI ĐẶT ============================
    def _build_settings(self, parent):
        # --- Nhà cung cấp AI + API key (mỗi nhà cung cấp 1 key riêng) ---
        fa = ttk.LabelFrame(parent, text="API viết prompt — chọn nhà cung cấp")
        fa.pack(fill="x", padx=8, pady=6)
        rp = ttk.Frame(fa)
        rp.pack(fill="x", padx=8, pady=(6, 2))
        ttk.Label(rp, text="Nhà cung cấp:", width=12).pack(side="left")
        self.provider_var = tk.StringVar(value=self.cfg.get("provider", "gemini"))
        self.cmb_provider = ttk.Combobox(rp, textvariable=self.provider_var, state="readonly",
                                         width=10, values=["gemini", "openai", "claude"])
        self.cmb_provider.pack(side="left")
        self.cmb_provider.bind("<<ComboboxSelected>>", self._on_provider_pick)
        self.key_hint = tk.StringVar()
        ttk.Label(rp, textvariable=self.key_hint, foreground="#888").pack(side="left", padx=8)
        rm = ttk.Frame(fa)
        rm.pack(fill="x", padx=8, pady=(0, 2))
        ttk.Label(rm, text="Model:", width=12).pack(side="left")
        self.model_var = tk.StringVar()
        self.cmb_model = ttk.Combobox(rm, textvariable=self.model_var, state="readonly", width=30)
        self.cmb_model.pack(side="left")
        self.cmb_model.bind("<<ComboboxSelected>>", self._on_model_pick)
        ttk.Button(rm, text="🔄", width=3, command=self._fetch_models).pack(side="left", padx=4)
        ttk.Label(rm, text="(tự cập nhật từ API; model đầu = mặc định rẻ)",
                  foreground="#888").pack(side="left", padx=6)
        r = ttk.Frame(fa)
        r.pack(fill="x", padx=8, pady=6)
        ttk.Label(r, text="API Key:", width=12).pack(side="left")
        self.key_var = tk.StringVar(value=self._provider_key())
        self.key_entry = ttk.Entry(r, textvariable=self.key_var, show="*")
        self.key_entry.pack(side="left", fill="x", expand=True)
        self.show_key = tk.BooleanVar(value=False)
        ttk.Checkbutton(r, text="Hiện", variable=self.show_key,
                        command=self._toggle_key).pack(side="left", padx=4)
        r2 = ttk.Frame(fa)
        r2.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(r2, text="💾 Lưu key", command=self._save_key).pack(side="left")
        ttk.Button(r2, text="🔌 Kiểm tra kết nối", command=self.check_api).pack(
            side="left", padx=6)
        self._refresh_models()
        self._update_key_hint()
        self._fetch_models()        # nền: tự cập nhật danh sách model lúc mở (nếu có key)

        # --- Mật khẩu mở app ---
        fpw = ttk.LabelFrame(parent, text="🔒 Mật khẩu mở app (chặn người ngoài)")
        fpw.pack(fill="x", padx=8, pady=6)
        rw = ttk.Frame(fpw)
        rw.pack(fill="x", padx=8, pady=6)
        self.pw_status = tk.StringVar()
        ttk.Label(rw, textvariable=self.pw_status).pack(side="left")
        ttk.Button(rw, text="🔑 Đặt / Đổi mật khẩu",
                   command=self._set_app_password).pack(side="right", padx=2)
        ttk.Button(rw, text="Tắt", command=self._clear_app_password).pack(side="right", padx=2)
        rw2 = ttk.Frame(fpw)
        rw2.pack(fill="x", padx=8, pady=(0, 4))
        self.session_status = tk.StringVar()
        ttk.Label(rw2, textvariable=self.session_status).pack(side="left")
        ttk.Button(rw2, text="🚪 Đăng xuất máy này",
                   command=self._logout).pack(side="right", padx=2)
        ttk.Label(fpw, foreground="#888", wraplength=720,
                  text=f"Nhập đúng mật khẩu → tự ghi nhớ {SESSION_DAYS} ngày trên máy này. "
                       "Đặt xong nhớ ĐẨY LÊN GITHUB (file access.json — chỉ chứa mã băm, "
                       "KHÔNG có API key) để bạn bè pull về cũng bị hỏi mật khẩu.").pack(
            fill="x", padx=10, pady=(0, 4))
        self._refresh_pw_status()

        # --- Style profiles ---
        fp = ttk.LabelFrame(parent, text="Style Visual Profile (cho từng kênh)")
        fp.pack(fill="both", expand=True, padx=8, pady=6)
        left = ttk.Frame(fp)
        left.pack(side="left", fill="y", padx=6, pady=6)
        ttk.Label(left, text="Danh sách:").pack(anchor="w")
        self.lb = tk.Listbox(left, width=22, height=12, exportselection=False)
        self.lb.pack(fill="y", expand=True)
        self.lb.bind("<<ListboxSelect>>", self._on_lb_select)
        bb = ttk.Frame(left)
        bb.pack(fill="x", pady=4)
        ttk.Button(bb, text="➕ Thêm", width=8, command=self._profile_add).pack(side="left")
        ttk.Button(bb, text="🗑 Xoá", width=8, command=self._profile_del).pack(side="left", padx=2)

        right = ttk.Frame(fp)
        right.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        ttk.Label(right, text="Nội dung style (dán mô tả phong cách kênh):").pack(anchor="w")
        self.txt_style = tk.Text(right, wrap="word", height=12)
        self.txt_style.pack(fill="both", expand=True)
        ttk.Button(right, text="💾 Lưu profile này",
                   command=self._profile_save).pack(anchor="e", pady=4)

        self._refresh_profile_list()

    # ---------- tiện ích UI chung ----------
    def _row(self, parent, label, var, cmd):
        f = ttk.Frame(parent)
        f.pack(fill="x", padx=8, pady=3)
        ttk.Label(f, text=label, width=18).pack(side="left")
        ttk.Entry(f, textvariable=var).pack(side="left", fill="x", expand=True)
        ttk.Button(f, text="Chọn...", command=cmd, width=8).pack(side="left", padx=4)

    def _auto_voice(self):
        for n in ("voice.mp3", "voice.wav", "voice.m4a"):
            p = dflt("input", n)
            if os.path.isfile(p):
                return p
        return ""

    def _on_srt_change(self, *_):
        """Tự điền tiêu đề từ tên file SRT khi Boss chọn file mới."""
        path = self.srt.get()
        t = _extract_title_from_srt(path)
        if t:
            self.video_title.set(t)

    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=HERE)
        if d:
            self.images.set(d)

    def _pick_file(self, var, types):
        f = filedialog.askopenfilename(initialdir=HERE, filetypes=types)
        if f:
            var.set(f)

    def _pick_save(self):
        f = filedialog.asksaveasfilename(initialdir=dflt("output"),
                                         defaultextension=".mp4",
                                         filetypes=[("MP4", "*.mp4")])
        if f:
            self.out.set(f)

    def open_out(self):
        d = os.path.dirname(self.out.get()) or HERE
        os.makedirs(d, exist_ok=True)
        os.startfile(d)

    # ---------- profile handlers ----------
    def _on_profile_pick(self, _e=None):
        self.cfg["active_profile"] = self.profile_var.get()
        save_config(self.cfg)

    def _refresh_profile_list(self):
        self.lb.delete(0, "end")
        for name in self.cfg["profiles"]:
            self.lb.insert("end", name)
        self.cmb_profile["values"] = list(self.cfg["profiles"].keys())

    def _on_lb_select(self, _e=None):
        sel = self.lb.curselection()
        if not sel:
            return
        name = self.lb.get(sel[0])
        self.txt_style.delete("1.0", "end")
        self.txt_style.insert("1.0", self.cfg["profiles"].get(name, ""))

    def _profile_add(self):
        name = simpledialog.askstring("Thêm Style Profile", "Tên kênh/phong cách:")
        if not name:
            return
        self.cfg["profiles"][name] = ""
        self.cfg["active_profile"] = name
        save_config(self.cfg)
        self._refresh_profile_list()
        self.profile_var.set(name)
        idx = list(self.cfg["profiles"]).index(name)
        self.lb.selection_clear(0, "end")
        self.lb.selection_set(idx)
        self._on_lb_select()

    def _profile_save(self):
        sel = self.lb.curselection()
        if not sel:
            messagebox.showinfo("Chọn profile", "Hãy chọn 1 profile bên trái (hoặc bấm Thêm).")
            return
        name = self.lb.get(sel[0])
        self.cfg["profiles"][name] = self.txt_style.get("1.0", "end").strip()
        save_config(self.cfg)
        self.status.set(f"Đã lưu style '{name}'.")
        self._refresh_profile_list()

    def _profile_del(self):
        sel = self.lb.curselection()
        if not sel:
            return
        name = self.lb.get(sel[0])
        if len(self.cfg["profiles"]) <= 1:
            messagebox.showinfo("Không thể xoá", "Phải giữ ít nhất 1 profile.")
            return
        if messagebox.askyesno("Xoá", f"Xoá style profile '{name}'?"):
            self.cfg["profiles"].pop(name, None)
            self.cfg["active_profile"] = next(iter(self.cfg["profiles"]))
            save_config(self.cfg)
            self.profile_var.set(self.cfg["active_profile"])
            self.txt_style.delete("1.0", "end")
            self._refresh_profile_list()

    # ---------- API key handlers ----------
    def _toggle_key(self):
        self.key_entry["show"] = "" if self.show_key.get() else "*"

    def _provider_key(self):
        return self.cfg.get("keys", {}).get(self.provider_var.get(), "")

    def _update_key_hint(self):
        hints = {"gemini": "Key tại aistudio.google.com",
                 "openai": "Key tại platform.openai.com/api-keys",
                 "claude": "Key tại console.anthropic.com → Get API key"}
        self.key_hint.set(hints.get(self.provider_var.get(), ""))

    def _on_provider_pick(self, _e=None):
        self.cfg["provider"] = self.provider_var.get()
        save_config(self.cfg)
        self.key_var.set(self._provider_key())     # nạp key của nhà cung cấp đã chọn
        self._update_key_hint()
        self._refresh_models()                     # nạp danh sách model (cache/cứng)
        self._fetch_models()                       # nền: tự cập nhật từ API

    def _model_options(self, prov):
        """Danh sách model cho combobox: model TUYỂN CHỌN (mặc định rẻ) lên đầu, rồi
        các model khác TỰ lấy từ API. Bỏ model tuyển chọn nào không còn tồn tại."""
        import ai_prompts
        hard = list(ai_prompts.MODELS.get(prov, []))
        fetched = self.cfg.get("model_cache", {}).get(prov, [])
        if not fetched:
            return hard                            # chưa fetch -> dùng danh sách cứng
        curated = [m for m in hard if m in fetched]
        others = [m for m in fetched if m not in curated]
        return (curated + others) or hard

    def _refresh_models(self):
        prov = self.provider_var.get()
        vals = self._model_options(prov)
        self.cmb_model["values"] = vals
        cur = self.cfg.get("models", {}).get(prov)
        if cur not in vals:                       # model cũ/không hợp lệ -> về mặc định
            cur = vals[0] if vals else ""
            if cur:
                self.cfg.setdefault("models", {})[prov] = cur
                save_config(self.cfg)
        self.model_var.set(cur)

    def _fetch_models(self, prov=None):
        """Lấy danh sách model THẬT từ API (nền) rồi cập nhật combobox + cache config."""
        prov = prov or self.provider_var.get()
        key = self.cfg.get("keys", {}).get(prov, "")
        if not key.strip():
            return

        def worker():
            try:
                import ai_prompts
                models = ai_prompts.list_chat_models(prov, key)
            except Exception:  # noqa
                models = []
            if models:
                self.q.put(("models", (prov, models)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_model_pick(self, _e=None):
        self.cfg.setdefault("models", {})[self.provider_var.get()] = self.model_var.get()
        save_config(self.cfg)
        self.status.set(f"Đã chọn model: {self.model_var.get()}")

    def _save_key(self):
        self.cfg.setdefault("keys", {})[self.provider_var.get()] = self.key_var.get().strip()
        save_config(self.cfg)
        self.status.set(f"Đã lưu API key ({self.provider_var.get()}).")

    def _save_produce(self):
        self.cfg["produce"] = self.produce.get()
        save_config(self.cfg)

    def _save_stylemode(self):
        self.cfg["style_mode"] = self.style_mode.get()
        save_config(self.cfg)

    def check_api(self):
        self._save_key()
        prov = self.provider_var.get()
        key = self.cfg.get("keys", {}).get(prov, "")
        self.status.set(f"Đang kiểm tra kết nối {prov}...")
        self._log(f"• Kiểm tra kết nối {prov}...\n")

        def worker():
            try:
                import ai_prompts
                ok, msg, model = ai_prompts.check_connection(
                    prov, key, self.cfg.get("models", {}).get(prov))
                # chỉ tự đặt model khi user CHƯA chọn (tôn trọng lựa chọn tay)
                if ok and model and not self.cfg.get("models", {}).get(prov):
                    self.cfg.setdefault("models", {})[prov] = model
                    save_config(self.cfg)
            except Exception as e:  # noqa
                ok, msg = False, str(e)
            self.q.put(("apiresult", (ok, msg)))

        threading.Thread(target=worker, daemon=True).start()
        self._fetch_models(prov)        # tiện thể cập nhật danh sách model từ API

    # ---------- mật khẩu mở app ----------
    def _refresh_pw_status(self):
        self.pw_status.set("Đang BẬT — cần mật khẩu để mở ✓" if has_password()
                           else "Chưa đặt — ai cũng mở được")
        if has_valid_session():
            exp = time.time()
            try:
                d = json.load(open(SESSION_PATH, encoding="utf-8"))
                days_left = max(0, int((d["expires"] - exp) / 86400) + 1)
                self.session_status.set(f"Máy này đã đăng nhập — còn {days_left} ngày")
            except Exception:
                self.session_status.set("Máy này đã đăng nhập")
        else:
            self.session_status.set("Máy này chưa đăng nhập / đã hết hạn")

    def _set_app_password(self):
        pw1 = simpledialog.askstring("Đặt mật khẩu", "Mật khẩu mới:",
                                     show="*", parent=self.root)
        if not pw1:
            return
        pw2 = simpledialog.askstring("Đặt mật khẩu", "Nhập lại mật khẩu:",
                                     show="*", parent=self.root)
        if pw1 != pw2:
            messagebox.showerror("Lỗi", "Hai lần nhập không khớp.")
            return
        set_password(pw1)
        self._refresh_pw_status()
        messagebox.showinfo("Xong", "Đã đặt mật khẩu mở app.\nNhớ đẩy file access.json "
                                    "lên GitHub để bạn bè cũng bị hỏi mật khẩu.")

    def _clear_app_password(self):
        if not has_password():
            return
        if messagebox.askyesno("Tắt mật khẩu", "Bỏ mật khẩu mở app?"):
            clear_password()
            clear_session()
            self._refresh_pw_status()

    def _logout(self):
        clear_session()
        self._refresh_pw_status()
        self.status.set("Đã đăng xuất — lần mở app sau cần nhập lại mật khẩu.")

    # ---------- log/queue ----------
    def _busy(self, on):
        st = "disabled" if on else "normal"
        self.btn_prompt["state"] = st
        self.btn_render["state"] = st
        if hasattr(self, "btn_render_queue"):
            self.btn_render_queue["state"] = st

    def _log(self, txt):
        self.log.insert("end", txt)
        self.log.see("end")

    def _drain(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "line":
                    self._log(data)
                elif kind == "apiresult":
                    ok, msg = data
                    self._log(("✓ " if ok else "✗ ") + msg + "\n")
                    self.status.set(msg)
                    (messagebox.showinfo if ok else messagebox.showerror)(
                        "Kiểm tra kết nối", msg)
                elif kind == "models":
                    prov, models = data
                    self.cfg.setdefault("model_cache", {})[prov] = models
                    save_config(self.cfg)
                    if prov == self.provider_var.get():
                        self._refresh_models()
                    self.status.set(f"Đã cập nhật {len(models)} model ({prov}).")
                elif kind == "done":
                    self._busy(False)
                    self.status.set(data)
                    if data.startswith("✅"):
                        messagebox.showinfo("Xong", data)
                    else:
                        messagebox.showerror("Lỗi", data)
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    # ---------- TẠO PROMPT (cảnh + AI) ----------
    def run_make_prompts(self):
        srt = self.srt.get()
        if not os.path.isfile(srt):
            messagebox.showwarning("Thiếu", "Chưa chọn file SRT hợp lệ.")
            return
        name = self.profile_var.get()
        style = self.cfg["profiles"].get(name, "")
        prov = self.cfg.get("provider", "gemini")
        key = self.cfg.get("keys", {}).get(prov, "")
        smode = self.style_mode.get()
        character = self.main_char.get().strip()
        title = self.video_title.get().strip()
        self.cfg["main_character"] = character
        save_config(self.cfg)
        if not key.strip():
            messagebox.showwarning("Thiếu API key",
                                   f"Vào tab Cài đặt nhập API key cho '{prov}' trước nhé.")
            return
        if smode != "lock_all" and not style.strip():
            messagebox.showwarning("Thiếu style",
                                   "Style profile đang trống. Vào tab Cài đặt để dán nội dung, "
                                   "hoặc chọn chế độ '② Lock lo TẤT CẢ style'.")
            return
        try:
            target = float(self.secs.get())
        except ValueError:
            target = 8.0

        self.log.delete("1.0", "end")
        self._busy(True)
        self.status.set("Đang tạo cảnh + viết prompt...")

        def worker():
            try:
                import auto_edit as ae
                import build_scenes as bs
                import ai_prompts
                self.q.put(("line", f"• Đọc SRT, gom cảnh (~{target:g}s)...\n"))
                segs = ae.parse_srt(srt)
                scenes = bs.group_scenes(segs, target)
                texts = [" ".join(t.strip() for t in s["texts"]).strip() for s in scenes]
                import csv
                produce = self.produce.get()
                model = self.cfg.get("models", {}).get(prov)

                def prog(done, total):
                    self.q.put(("line", f"   ...{done}/{total}\n"))

                def write_scenes(img_prompts, motion=None):
                    sc = dflt("scenes.csv")
                    cols = ["scene", "start", "end", "dur", "veo_sec", "speed", "text", "prompt"]
                    if motion is not None:
                        cols.append("motion")
                    with open(sc, "w", newline="", encoding="utf-8-sig") as f:
                        w = csv.writer(f)
                        w.writerow(cols)
                        for i, s in enumerate(scenes):
                            dur = round(s["end"] - s["start"], 2)
                            veo, _pct, speed = bs.nearest_veo(dur)
                            row = [i + 1, bs.fmt(s["start"]), bs.fmt(s["end"]), dur, veo, speed,
                                   texts[i], (img_prompts[i] if i < len(img_prompts) else "")]
                            if motion is not None:
                                row.append(motion[i] if i < len(motion) else "")
                            w.writerow(row)
                    return sc

                if produce == "i2v":
                    self.q.put(("line", f"• {len(segs)} đoạn → {len(scenes)} cảnh. "
                                        f"[Image-to-video] gọi {prov}...\n"))
                    self.q.put(("line", "• (1/2) Viết prompt ẢNH keyframe...\n"))
                    img_prompts = ai_prompts.generate_prompts(
                        texts, style, key, model=model, progress=prog, mode="image",
                        style_mode=smode, provider=prov, character=character, title=title)
                    self.q.put(("line", "• (2/2) Viết prompt CHUYỂN ĐỘNG...\n"))
                    motion = ai_prompts.generate_motion_prompts(
                        texts, key, model=model, progress=prog, provider=prov,
                        character=character, title=title)
                    ip, mp = dflt("image_prompts.txt"), dflt("motion_prompts.txt")
                    with open(ip, "w", encoding="utf-8") as f:
                        f.write("\n".join(p.replace("\n", " ").strip() for p in img_prompts) + "\n")
                    with open(mp, "w", encoding="utf-8") as f:
                        f.write("\n".join(p.replace("\n", " ").strip() for p in motion) + "\n")
                    sc = write_scenes(img_prompts, motion)
                    self.q.put(("line", f"\n• Đã ghi:\n   {ip}\n   {mp}\n   {sc}\n"))
                    self.q.put(("done", f"✅ Xong (Image-to-video)! {len(img_prompts)} cảnh × 2 prompt. "
                                        "Dùng image_prompts.txt tạo keyframe → motion_prompts.txt cho i2v."))
                else:
                    mode = "image" if produce == "image" else "video"
                    loai = "ẢNH tĩnh" if mode == "image" else "VIDEO"
                    kieu = {"in_prompt": "kèm style trong prompt",
                            "lock_art": "Lock nét + AI lo màu/era",
                            "lock_all": "chỉ nội dung (Lock lo style)"}.get(smode, smode)
                    self.q.put(("line", f"• {len(segs)} đoạn → {len(scenes)} cảnh. "
                                        f"Gọi {prov} viết prompt {loai} [{kieu}]...\n"))
                    prompts = ai_prompts.generate_prompts(
                        texts, style, key, model=model, progress=prog, mode=mode,
                        style_mode=smode, provider=prov, character=character, title=title)
                    vp = dflt("veo_prompts.txt")
                    with open(vp, "w", encoding="utf-8") as f:
                        f.write("\n".join(p.replace("\n", " ").strip() for p in prompts) + "\n")
                    sc = write_scenes(prompts)
                    self.q.put(("line", f"\n• Đã ghi {len(prompts)} prompt vào:\n   {vp}\n   {sc}\n"))
                    self.q.put(("done", f"✅ Xong! Đã viết {len(prompts)} prompt. "
                                        "Mở veo_prompts.txt để dán vào Veo."))
            except Exception as e:  # noqa
                self.q.put(("done", f"Lỗi: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    # ---------- RENDER (gọi auto_edit.py) ----------
    def run_render(self):
        if not os.path.isfile(self.srt.get()):
            messagebox.showwarning("Thiếu", "Chưa chọn file SRT.")
            return
        if not os.path.isdir(self.images.get()):
            messagebox.showwarning("Thiếu", "Chưa chọn thư mục ảnh/clip.")
            return
        job = self._current_job()
        sc = dflt("scenes.csv")
        if os.path.isfile(sc):
            job["scenes"] = sc
        cmd = self._job_cmd(job)

        self.log.delete("1.0", "end")
        self._log("$ render...\n\n")
        self._busy(True)
        self.status.set("Đang render...")

        def worker():
            try:
                env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                p = subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True,
                                     encoding="utf-8", errors="replace", env=env,
                                     creationflags=flags)
                for line in p.stdout:
                    self.q.put(("line", line))
                p.wait()
                if p.returncode == 0:
                    self.q.put(("done", f"✅ Render xong: {self.out.get()}"))
                else:
                    self.q.put(("done", f"Render thất bại (mã {p.returncode}). Xem nhật ký."))
            except Exception as e:  # noqa
                self.q.put(("done", f"Lỗi: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    # ============================ HÀNG ĐỢI ============================
    def _current_job(self):
        """Gói nguyên liệu đang chọn ở tab Làm video thành 1 'job' để render."""
        return {
            "out": self.out.get(), "srt": self.srt.get(),
            "images": self.images.get(), "voice": self.voice.get(),
            "scenes": "", "secs": self.secs.get(),
            "kenburns": self.kenburns.get(), "subs": self.subs.get(),
            "crossfade": self.crossfade.get(),
        }

    def _job_cmd(self, job):
        """Dựng lệnh gọi auto_edit.py cho 1 job (dùng chung render đơn + hàng đợi)."""
        cmd = [PY, dflt("auto_edit.py"),
               "--images", job["images"], "--srt", job["srt"], "--out", job["out"]]
        if (job.get("voice") or "").strip():
            cmd += ["--voice", job["voice"]]
        if job.get("scenes") and os.path.isfile(job["scenes"]):
            cmd += ["--scenes", job["scenes"]]
        else:
            cmd += ["--seconds-per-image", str(job.get("secs", "8"))]
        if not job.get("kenburns", True):
            cmd += ["--no-kenburns"]
        if not job.get("subs", True):
            cmd += ["--no-subtitles"]
        if job.get("crossfade", False):
            cmd += ["--transition", "fade"]
        return cmd

    def add_to_queue(self):
        if not os.path.isfile(self.srt.get()):
            messagebox.showwarning("Thiếu", "Chưa chọn file SRT hợp lệ.")
            return
        if not os.path.isdir(self.images.get()):
            messagebox.showwarning("Thiếu", "Chưa chọn thư mục ảnh/clip.")
            return
        job = self._current_job()
        # Lưu BẢN SAO scenes.csv hiện tại (nếu có) -> tránh bị ghi đè khi tạo prompt video khác
        sc = dflt("scenes.csv")
        if os.path.isfile(sc):
            qdir = dflt("queue")
            os.makedirs(qdir, exist_ok=True)
            base = os.path.splitext(os.path.basename(job["out"]))[0] or "job"
            dst = os.path.join(qdir, f"scenes_{len(self.cfg.get('queue', []))+1}_{base}.csv")
            try:
                shutil.copyfile(sc, dst)
                job["scenes"] = dst
            except Exception:  # noqa
                pass
        self.cfg.setdefault("queue", []).append(job)
        save_config(self.cfg)
        self._refresh_queue()
        self.status.set(f"Đã thêm vào hàng đợi ({len(self.cfg['queue'])} video).")

    def _build_queue(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=10, pady=(8, 2))
        self.q_count = tk.StringVar(value="0 video trong hàng đợi")
        ttk.Label(top, textvariable=self.q_count, font=("", 10, "bold")).pack(side="left")
        ttk.Label(parent, wraplength=720, foreground="#777",
                  text="Mẹo: ở tab '🎬 Làm video' set SRT + thư mục clip + voice + tên file ra, "
                       "rồi bấm '➕ Hàng đợi'. Mỗi video nên để clip ở THƯ MỤC RIÊNG và đặt "
                       "TÊN FILE RA khác nhau (tránh ghi đè).").pack(fill="x", padx=10, pady=(0, 4))
        mid = ttk.Frame(parent)
        mid.pack(fill="both", expand=True, padx=10, pady=4)
        self.qlist = tk.Listbox(mid, height=10)
        self.qlist.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(mid, command=self.qlist.yview)
        sb.pack(side="right", fill="y")
        self.qlist["yscrollcommand"] = sb.set
        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=10, pady=6)
        ttk.Button(bar, text="🗑 Xoá mục chọn", command=self._queue_del).pack(side="left", padx=2)
        ttk.Button(bar, text="🧹 Xoá hết", command=self._queue_clear).pack(side="left", padx=2)
        self.btn_render_queue = ttk.Button(bar, text="▶  RENDER CẢ HÀNG ĐỢI",
                                           command=self.run_render_queue)
        self.btn_render_queue.pack(side="right", padx=4)
        self._refresh_queue()

    def _refresh_queue(self):
        self.qlist.delete(0, "end")
        for i, j in enumerate(self.cfg.get("queue", []), 1):
            out = os.path.basename(j.get("out", "?"))
            srt = os.path.basename(j.get("srt", "?"))
            imgs = os.path.basename((j.get("images", "?") or "").rstrip("/\\"))
            self.qlist.insert("end", f"{i}.  {out}   ←  {srt}   |  clip: {imgs}")
        n = len(self.cfg.get("queue", []))
        self.q_count.set(f"{n} video trong hàng đợi")

    def _queue_del(self):
        sel = self.qlist.curselection()
        if not sel:
            return
        self.cfg.get("queue", []).pop(sel[0])
        save_config(self.cfg)
        self._refresh_queue()

    def _queue_clear(self):
        if self.cfg.get("queue") and messagebox.askyesno("Xoá hết", "Xoá toàn bộ hàng đợi?"):
            self.cfg["queue"] = []
            save_config(self.cfg)
            self._refresh_queue()

    def run_render_queue(self):
        jobs = list(self.cfg.get("queue", []))
        if not jobs:
            messagebox.showinfo("Hàng đợi trống", "Chưa có video nào trong hàng đợi.")
            return
        self.log.delete("1.0", "end")
        self._busy(True)
        self.status.set(f"Đang render hàng đợi (0/{len(jobs)})...")

        def worker():
            ok_count, fail = 0, []
            env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            for idx, job in enumerate(jobs, 1):
                name = os.path.basename(job.get("out", "?"))
                self.q.put(("line", f"\n===== VIDEO {idx}/{len(jobs)}: {name} =====\n"))
                try:
                    p = subprocess.Popen(self._job_cmd(job), cwd=HERE,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         text=True, encoding="utf-8", errors="replace",
                                         env=env, creationflags=flags)
                    for line in p.stdout:
                        self.q.put(("line", line))
                    p.wait()
                    if p.returncode == 0:
                        ok_count += 1
                        self.q.put(("line", f"✅ Xong: {job.get('out')}\n"))
                    else:
                        fail.append(name)
                        self.q.put(("line", f"❌ Lỗi (mã {p.returncode}): {name}\n"))
                except Exception as e:  # noqa
                    fail.append(name)
                    self.q.put(("line", f"❌ Lỗi: {e}\n"))
            msg = f"✅ Hàng đợi xong: {ok_count}/{len(jobs)} video"
            if fail:
                msg += f" ({len(fail)} lỗi: {', '.join(fail)})"
            self.q.put(("done", msg))

        threading.Thread(target=worker, daemon=True).start()


def main():
    selftest = "--selftest" in sys.argv
    root = tk.Tk()
    if not selftest and has_password():       # hỏi mật khẩu trước khi vào (nếu đã đặt)
        root.withdraw()
        if not password_gate(root):
            root.destroy()
            return
        root.deiconify()
    App(root)
    if selftest:
        root.update()
        root.destroy()
        print("selftest OK")
        return
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa
        try:
            messagebox.showerror("Không mở được app", str(e))
        except Exception:
            print("Loi:", e)
        raise
