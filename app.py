#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto Edit Video — Giao diện (GUI).
  • Tab "Làm video": up SRT + chọn Style -> [Tạo Prompt] (tự tạo cảnh + viết prompt
    bằng Gemini) -> tạo clip Veo -> [Render Video].
  • Tab "Cài đặt": nhập Gemini API key (có nút kiểm tra kết nối) + quản lý Style Profile.

Chạy: double-click run.bat  hoặc  python app.py
"""
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import i18n
from i18n import tr

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

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
        "produce": "video",                         # image | video | i2v | chain (kiểu sản xuất)
        "style_mode": "in_prompt",
        # ⚠️ load_config CHỈ GIỮ key có trong default này — key mới PHẢI khai ở đây,
        # không là "lưu xong mở lại mất" (đã dính với lang + sub_font/sub_mode...)
        "lang": "",                                 # "" = lần đầu -> tự nhận theo locale
        "aspect": "16:9",                           # khung hình render: 16:9 | 9:16
        "clip_audio": False,                        # giữ âm thanh gốc của clip
        "clip_volume": "0.25",
        "logo": "",                                 # thương hiệu: watermark + tiêu đề + i/o + sfx
        "logo_pos": "br",
        "logo_opacity": "0.85",
        "title_on": False,
        "title_sec": "4",
        "intro": "",
        "outro": "",
        "sfx": "",
        "sfx_volume": "0.5",
        "channels": {},                             # hồ sơ KÊNH: {tên: snapshot cài đặt}
        "active_channel": "",
        "kara_color": "#FFFF00",
        "sub_font": "Arial Black",
        "sub_mode": "word",
        "sub_outline": "#000000",
        "sleep_item_sec": "20",
        "main_character": "",
        "prompt_dir": "",                           # thư mục lưu prompt+scenes (trống=gốc)
        "queue": [],
        "render_history": [],                       # lịch sử video đã render
    }


def _config_path():
    """Đường dẫn config.local.json (API key + profiles + hàng đợi + lịch sử...).
    ⚠️ Bản .exe (Nuitka onefile): __file__ nằm trong thư mục TEMP giải nén — thư mục này ĐỔI
    tên mỗi lần chạy và bị XÓA khi thoát app. Lưu config ở đó = mất sạch khi mở lại (đây là
    bug 'lưu style xong tắt/mở lại là mất'). Nên bản .exe lưu ở DATA_DIR (%APPDATA%\\AutoEditVideo),
    CÙNG chỗ license.json — ổn định + luôn ghi được. Bản dev (.py) giữ nguyên cạnh app.py."""
    if _is_frozen():
        try:
            import config
            os.makedirs(config.DATA_DIR, exist_ok=True)
            return os.path.join(config.DATA_DIR, "config.local.json")
        except Exception:
            pass
    return os.path.join(HERE, "config.local.json")


def load_config():
    cfg = default_config()
    try:
        with open(_config_path(), encoding="utf-8-sig") as f:
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
        with open(_config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:  # noqa
        print("Loi luu config:", e)


# (Đã GỠ hệ thống mật khẩu cũ — thay bằng LICENSE; xem license_gate bên dưới.)


# ============================ LICENSE GATE ============================
# Thay mật khẩu bằng kích hoạt bản quyền (hybrid Ed25519, dùng chung server với tool khác).
# Chỉ chạy khi config.LICENSE_ENABLED = True (bản BÁN); dev để False -> vào tự do.
def license_gate(root):
    """Cổng license khi mở app. True = được vào; False = thoát.
    refresh() best-effort (gia hạn + bắt revoke) -> check() offline -> nếu chưa hợp lệ thì
    mở hộp thoại kích hoạt (hiện Machine ID cho khách gửi người bán + ô dán key)."""
    import license_client as lic
    try:
        lic.refresh()                       # offline thì tự bỏ qua, giữ token (grace)
    except Exception:
        pass
    st = lic.check()
    if st.get("status") in ("VALID", "GRACE"):
        return True
    return _activate_dialog(root, lic, st)


def _activate_dialog(root, lic, st):
    """Hộp thoại kích hoạt. Trả True nếu activate thành công + license VALID/GRACE."""
    win = tk.Toplevel(root)
    win.title(tr("Kích hoạt bản quyền — PeiPei Auto Edit Video"))
    win.resizable(False, False)
    win.grab_set()
    result = {"ok": False}
    mid = lic.get_machine_id()

    frm = ttk.Frame(win, padding=16)
    frm.pack(fill="both", expand=True)
    ttk.Label(frm, text=tr("Phần mềm cần kích hoạt bản quyền để sử dụng."),
              font=("Segoe UI", 10, "bold")).pack(anchor="w")
    if st.get("message"):
        ttk.Label(frm, text=st["message"], foreground="#a00").pack(anchor="w", pady=(2, 8))

    ttk.Label(frm, text=tr("Mã máy (gửi mã này cho người bán để lấy key):")).pack(anchor="w")
    midrow = ttk.Frame(frm)
    midrow.pack(fill="x", pady=(2, 10))
    ttk.Entry(midrow, textvariable=tk.StringVar(value=mid), width=34,
              state="readonly").pack(side="left")
    ttk.Button(midrow, text="Copy", width=7,
               command=lambda: (win.clipboard_clear(), win.clipboard_append(mid))).pack(
                   side="left", padx=6)

    ttk.Label(frm, text=tr("Dán license key:")).pack(anchor="w")
    kvar = tk.StringVar()
    ttk.Entry(frm, textvariable=kvar, width=46).pack(fill="x", pady=(2, 6))
    status = ttk.Label(frm, text="", foreground="#a00")
    status.pack(anchor="w")

    def _do_activate():
        key = kvar.get().strip()
        if not key:
            status.config(text=tr("Hãy dán license key."), foreground="#a00")
            return
        status.config(text=tr("Đang kích hoạt..."), foreground="#333")
        win.update()
        ok, msg = lic.activate(key)
        if ok and lic.check().get("status") in ("VALID", "GRACE"):
            result["ok"] = True
            win.destroy()
        else:
            status.config(text=msg or tr("Kích hoạt thất bại."), foreground="#a00")

    btns = ttk.Frame(frm)
    btns.pack(fill="x", pady=(10, 0))
    ttk.Button(btns, text=tr("Kích hoạt"), command=_do_activate).pack(side="left")
    ttk.Button(btns, text=tr("Thoát"), command=win.destroy).pack(side="right")

    win.protocol("WM_DELETE_WINDOW", win.destroy)
    win.wait_window()
    return result["ok"]


def dflt(*parts):
    return os.path.join(HERE, *parts)


def _is_frozen():
    """True khi đang chạy dạng .exe đóng gói (Nuitka đặt __compiled__; PyInstaller đặt frozen)."""
    return getattr(sys, "frozen", False) or ("__compiled__" in globals())


def _self_exe():
    """Đường dẫn .exe THẬT để tự gọi lại render. ⚠️ Nuitka onefile đặt sys.executable =
    một python.exe ẢO trong thư mục temp (KHÔNG tồn tại) -> KHÔNG dùng được cho subprocess.
    Đường dẫn .exe thật khách chạy nằm ở sys.argv[0] (hoặc env NUITKA_ONEFILE_BINARY)."""
    return os.environ.get("NUITKA_ONEFILE_BINARY") or os.path.abspath(sys.argv[0])


def script_cmd(script):
    """Lệnh gọi ENGINE phụ (auto_edit/sleep_video).
    - Dev (.py): [python, <đường dẫn script>].
    - Bản .exe: KHÔNG còn python + .py riêng -> gọi LẠI chính .exe (đường dẫn THẬT, không
      phải sys.executable ảo) kèm cờ route -> vào auto_edit.main()/sleep_video.main()."""
    if _is_frozen():
        flag = "--run-sleep-video" if "sleep" in script else "--run-auto-edit"
        return [_self_exe(), flag]
    return [PY, dflt(script)]


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
        # Ngôn ngữ: theo config; LẦN ĐẦU (chưa lưu) -> theo locale Windows (máy nước
        # ngoài mặc định English để khách Tây đọc được ngay)
        i18n.set_lang(self.cfg.get("lang") or i18n.detect_default())
        self.q = queue.Queue()
        try:
            import config
            self.app_ver = str(getattr(config, "APP_VERSION", "")).strip()
        except Exception:
            self.app_ver = ""
        _vtag = f" {self.app_ver}" if self.app_ver else ""
        root.title(f"PeiPei Auto Edit Video{_vtag} 🎬")
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
        self.aspect = tk.StringVar(value=self.cfg.get("aspect", "16:9"))
        self.subs = tk.BooleanVar(value=True)
        self.kara_color = tk.StringVar(value=self.cfg.get("kara_color", "#FFFF00"))
        # Phụ đề: phông chữ + cách hiển thị + màu viền (mặc định = như cũ)
        self.sub_font = tk.StringVar(value=self.cfg.get("sub_font", "Arial Black"))
        self.sub_mode = tk.StringVar(value=self.cfg.get("sub_mode", "word"))
        self.sub_outline = tk.StringVar(value=self.cfg.get("sub_outline", "#000000"))
        self.crossfade = tk.BooleanVar(value=False)
        self.transition = tk.StringVar(value="fade")   # kiểu chuyển cảnh khi bật Crossfade (#2)
        self.color = tk.StringVar(value="none")        # màu phim (#3)
        self.vignette = tk.BooleanVar(value=False)
        self.grain = tk.BooleanVar(value=False)
        self.clip_audio = tk.BooleanVar(value=bool(self.cfg.get("clip_audio", False)))
        self.clip_volume = tk.StringVar(value=str(self.cfg.get("clip_volume", "0.25")))
        # Thương hiệu kênh: logo/watermark + tiêu đề mở video + intro/outro + SFX
        self.logo = tk.StringVar(value=self.cfg.get("logo", ""))
        self.logo_pos = tk.StringVar(value=self.cfg.get("logo_pos", "br"))
        self.logo_opacity = tk.StringVar(value=str(self.cfg.get("logo_opacity", "0.85")))
        self.title_on = tk.BooleanVar(value=bool(self.cfg.get("title_on", False)))
        self.title_sec = tk.StringVar(value=str(self.cfg.get("title_sec", "4")))
        self.intro = tk.StringVar(value=self.cfg.get("intro", ""))
        self.outro = tk.StringVar(value=self.cfg.get("outro", ""))
        self.sfx = tk.StringVar(value=self.cfg.get("sfx", ""))
        self.sfx_volume = tk.StringVar(value=str(self.cfg.get("sfx_volume", "0.5")))
        self.channel_var = tk.StringVar(value=self.cfg.get("active_channel", ""))
        self.bgm = tk.StringVar(value="")              # file nhạc nền (#4)
        self.bgm_volume = tk.StringVar(value="0.18")
        self.duck = tk.BooleanVar(value=True)          # tự hạ nhạc khi có lời (ducking)
        # --- Video ngủ (clip/ảnh nền + audio dài) ---
        self.sleep_bg = tk.StringVar(value="")
        self.sleep_audio = tk.StringVar(value="")
        self.sleep_out = tk.StringVar(value=dflt("output", "sleep.mp4"))
        self.sleep_effect = tk.StringVar(value="none")
        self.sleep_intensity = tk.StringVar(value="vua")
        self.sleep_fade = tk.StringVar(value="4")
        self.sleep_viz = tk.StringVar(value="none")    # visualizer âm thanh
        self.sleep_ambient = tk.StringVar(value="")    # âm thanh nền phụ (mưa/gió/tuyết)
        self.sleep_ambient_vol = tk.StringVar(value="0.25")
        self.sleep_item_sec = tk.StringVar(value=str(self.cfg.get("sleep_item_sec", "20")))
        # Thư mục lưu prompt + scenes.csv (TÙY CHỌN). Trống = lưu ở gốc dự án (đè như cũ).
        self.prompt_dir = tk.StringVar(value=self.cfg.get("prompt_dir", ""))
        # File bảng cảnh scenes.csv CHỌN TAY (TÙY CHỌN). Trống = tự tìm. Chọn để chắc
        # render ĐÚNG bảng cảnh của video (tránh dùng nhầm bảng cảnh video khác).
        self.scenes_file = tk.StringVar(value="")

        # Tự cập nhật tiêu đề khi Boss chọn file SRT khác
        self.srt.trace_add("write", self._on_srt_change)

        # Thanh TRÊN CÙNG (ngay dưới tiêu đề): license (gói + hạn còn lại) trái +
        # hỗ trợ Zalo (xanh lá) phải
        header = ttk.Frame(root)
        header.pack(fill="x", side="top", padx=8, pady=(4, 0))
        self.lic_status = tk.StringVar(value="")
        ttk.Label(header, textvariable=self.lic_status, anchor="w").pack(side="left")
        tk.Label(header, text="Hỗ trợ Zalo : 0827298265", fg="#1aa64b",
                 font=("", 9, "bold")).pack(side="right")
        if self.app_ver:                       # số phiên bản cho user dễ nhận biết
            tk.Label(header, text=f"Phiên bản {self.app_ver}", fg="#888",
                     font=("", 9)).pack(side="right", padx=(0, 12))

        # Khung trên: SIDEBAR trái + nội dung phải
        top = ttk.Frame(root)
        top.pack(fill="both", expand=True, padx=6, pady=6)
        side = ttk.Frame(top, width=165)
        side.pack(side="left", fill="y", padx=(0, 6))
        side.pack_propagate(False)
        content = ttk.Frame(top)
        content.pack(side="left", fill="both", expand=True)

        # 4 trang nội dung
        self.pages = {n: ttk.Frame(content)
                      for n in ("prompt", "render", "sleep", "queue", "settings")}
        self._build_prompt(self.pages["prompt"])
        self._build_render(self.pages["render"])
        self._build_sleep(self.pages["sleep"])
        self._build_queue(self.pages["queue"])
        self._build_settings(self.pages["settings"])

        # Nút điều hướng sidebar
        self._side_btns = {}
        for name, label in (("prompt", "✍️  Tạo Prompt"), ("render", "🎬  Render Video"),
                            ("sleep", "🌙  Video ngủ"),
                            ("queue", "📋  Hàng đợi"), ("settings", "⚙️  Cài đặt")):
            b = tk.Button(side, text=label, anchor="w", relief="flat", bd=0,
                          padx=12, pady=11, font=("", 10),
                          command=lambda n=name: self._show_page(n))
            b.pack(fill="x", pady=1)
            self._side_btns[name] = b

        # Log + status (dùng chung)
        # Thanh TIẾN ĐỘ render + ước tính thời gian còn lại (đọc từ log engine)
        prow = ttk.Frame(root)
        prow.pack(fill="x", padx=6, pady=(0, 2))
        self.pbar = ttk.Progressbar(prow, maximum=100)
        self.pbar.pack(side="left", fill="x", expand=True)
        self.eta_var = tk.StringVar(value="")
        ttk.Label(prow, textvariable=self.eta_var, width=24,
                  anchor="e").pack(side="left", padx=(6, 0))
        self._prog_t0 = None

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

        self._refresh_license_label()
        self._show_page("prompt")
        i18n.translate_tree(root)         # áp ngôn ngữ đã chọn lên toàn bộ giao diện
        self.root.after(100, self._drain)
        self._check_update_async()          # tự hỏi server có bản mới không (nền)

        # Theo dõi tiến trình render để bảo vệ khi đóng app giữa chừng (#8)
        self.render_procs = []          # các subprocess render đang chạy
        self.rendering = False
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        """Đóng app: nếu đang render thì hỏi xác nhận + dừng sạch tiến trình."""
        if self.rendering:
            if not messagebox.askyesno(
                    "Đang render",
                    "Đang render dở. Thoát bây giờ sẽ HỦY render (video chưa hoàn chỉnh, "
                    "phải làm lại từ đầu).\n\nVẫn thoát?"):
                return
            for p in list(self.render_procs):
                try:
                    p.kill()
                except Exception:  # noqa
                    pass
        self.root.destroy()

    def _show_page(self, name):
        for p in self.pages.values():
            p.pack_forget()
        self.pages[name].pack(fill="both", expand=True)
        for n, b in self._side_btns.items():
            b.configure(bg=("#cfe2ff" if n == name else "#f0f0f0"))

    def _refresh_license_label(self):
        """Hiện gói + số ngày còn lại của license (chỉ khi bản BÁN bật license; dev thì ẩn)."""
        try:
            import config
            if getattr(config, "LICENSE_ENABLED", False):
                import license_client as lic
                self.lic_status.set(tr(lic.status_text()))
            else:
                self.lic_status.set("")
        except Exception:
            self.lic_status.set("")

    def _check_update_async(self):
        """Hỏi server có bản mới không (chạy NỀN để không chặn khởi động). Chỉ chạy ở bản
        BÁN (LICENSE_ENABLED). Có bản mới -> thông báo + mở link tải (khách tự cập nhật)."""
        try:
            import config
            if not getattr(config, "LICENSE_ENABLED", False):
                return
        except Exception:
            return

        def worker():
            try:
                import license_client as lic
                info = lic.check_update()          # None nếu không có bản mới / offline
            except Exception:
                info = None
            if info:
                self.root.after(0, lambda: self._show_update(info))

        threading.Thread(target=worker, daemon=True).start()

    def _on_lang_pick(self, _e=None):
        """Đổi ngôn ngữ Việt/Anh: dịch SỐNG toàn bộ giao diện + lưu nhớ."""
        code = "en" if self.lang_var.get() == "English" else "vi"
        i18n.set_lang(code)
        os.environ["AEV_LANG"] = code       # engine subprocess (render/sleep) dịch log theo
        self.cfg["lang"] = code
        save_config(self.cfg)
        i18n.translate_tree(self.root)
        # Nhãn ĐỘNG gắn qua biến (textvariable) không nằm trong cây dịch -> set lại tay
        self.q_count.set(tr(f"{len(self.cfg.get('queue', []))} video trong hàng đợi"))
        self._refresh_license_label()
        self._update_key_hint()
        self.status.set(tr("Sẵn sàng."))

    def _check_update_now(self):
        """User CHỦ ĐỘNG bấm kiểm tra bản mới (tab Cài đặt) — chạy NỀN để không đơ UI.
        Có bản mới -> dùng chung popup _show_update (bản .exe tự tải + thay + restart). Không có
        -> báo đang dùng bản mới nhất. Lỗi mạng -> báo kiểm tra kết nối."""
        self.status.set("Đang kiểm tra cập nhật...")

        def worker():
            import config
            cur = str(getattr(config, "APP_VERSION", "")).strip()
            info, err = None, None
            try:
                import license_client as lic
                import requests
                r = requests.get(config.LICENSE_SERVER_URL.rstrip("/") + "/version", timeout=10)
                r.raise_for_status()
                d = r.json()
                latest = (d.get("latest_version") or "").strip()
                if latest and lic._ver_tuple(latest) > lic._ver_tuple(cur):
                    info = {"latest": latest, "url": (d.get("download_url") or "").strip(),
                            "message": (d.get("message") or "").strip()}
            except Exception as e:  # noqa
                err = str(e)

            def show():
                if info:
                    self._show_update(info)
                elif err:
                    messagebox.showwarning(
                        tr("Kiểm tra cập nhật"),
                        tr("Chưa kiểm tra được bản mới — hãy kiểm tra kết nối mạng.") + "\n\n" + err)
                else:
                    messagebox.showinfo(
                        tr("Kiểm tra cập nhật"),
                        tr(f"Bạn đang dùng phiên bản mới nhất ({cur})."))
                self.status.set(tr("Sẵn sàng."))
            self.root.after(0, show)

        threading.Thread(target=worker, daemon=True).start()

    def _show_update(self, info):
        """Thông báo có bản mới. Bản .exe (frozen) -> hỏi CẬP NHẬT NGAY (tự tải + tự thay +
        khởi động lại). Dev / không có link -> chỉ mở trang tải."""
        latest = info.get("latest", "?")
        url = (info.get("url") or "").strip()
        note = (info.get("message") or "").strip()
        text = tr(f"Đã có phiên bản mới: {latest}.")
        if note:
            text += f"\n{note}"
        if url and _is_frozen():
            text += "\n\n" + tr("CẬP NHẬT NGAY? (app tự tải + tự cài + khởi động lại — bạn không cần làm gì)")
            if messagebox.askyesno(tr("🔔 Có bản cập nhật mới"), text):
                self._do_self_update(url)
        elif url:
            text += "\n\n" + tr("Mở trang tải bản mới ngay?")
            if messagebox.askyesno(tr("🔔 Có bản cập nhật mới"), text):
                try:
                    import webbrowser
                    webbrowser.open(url)
                except Exception:
                    pass
        else:
            messagebox.showinfo("🔔 Có bản cập nhật mới", text)

    def _do_self_update(self, url):
        """FULL-AUTO update (chỉ bản .exe): tải .exe mới -> đổi tên bản đang chạy thành .old
        -> đặt bản mới vào đúng tên (Windows cho RENAME file .exe đang chạy) -> mở bản mới ->
        thoát bản cũ. File .old sẽ được dọn ở lần mở app kế tiếp."""
        exe = _self_exe()
        newexe, oldexe = exe + ".new", exe + ".old"
        self._busy(True)
        self.rendering = True                     # chặn đóng app giữa chừng
        self.log.delete("1.0", "end")
        self._log("$ đang tải bản cập nhật...\n\n")
        self.status.set("Đang tải bản cập nhật...")

        def worker():
            try:
                import requests
                with requests.get(url, stream=True, timeout=120) as r:
                    r.raise_for_status()
                    total = int(r.headers.get("content-length", 0))
                    got = 0
                    with open(newexe, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1 << 20):
                            if not chunk:
                                continue
                            f.write(chunk)
                            got += len(chunk)
                            if total:
                                self.q.put(("line", f"   ...tải {got * 100 // total}%\n"))
                if os.path.getsize(newexe) < 200_000:      # .exe thật ~12MB; quá nhỏ = lỗi
                    raise RuntimeError("File tải về không hợp lệ (quá nhỏ).")
                if os.path.exists(oldexe):
                    try:
                        os.remove(oldexe)
                    except OSError:
                        pass
                os.rename(exe, oldexe)             # đổi tên file ĐANG CHẠY (Windows cho phép)
                try:
                    os.rename(newexe, exe)         # đặt bản mới vào đúng tên
                except Exception:
                    os.rename(oldexe, exe)         # lỗi -> khôi phục bản cũ
                    raise
                subprocess.Popen([exe], cwd=os.path.dirname(exe) or None)   # mở bản mới
                self.q.put(("selfupdate_done", None))                       # -> thoát bản cũ
            except Exception as e:  # noqa
                try:
                    if os.path.exists(newexe):
                        os.remove(newexe)
                except OSError:
                    pass
                self.q.put(("done", f"Cập nhật thất bại: {e}"))

        threading.Thread(target=worker, daemon=True).start()

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

        pdir = ttk.Frame(f1)
        pdir.pack(fill="x", padx=8, pady=3)
        ttk.Label(pdir, text="📁 Thư mục lưu prompt:", width=18).pack(side="left")
        ttk.Entry(pdir, textvariable=self.prompt_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(pdir, text="Chọn...", command=self._pick_prompt_dir, width=8).pack(side="left", padx=4)
        ttk.Label(f1, foreground="#888", wraplength=640,
                  text="(Tùy chọn) Mỗi video 1 thư mục riêng → prompt + scenes.csv không đè nhau, "
                       "render lại khỏi tốn API. Để TRỐNG = lưu ở gốc (đè như cũ).").pack(
            fill="x", padx=12, pady=(0, 2))

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
        ttk.Entry(linec, textvariable=self.main_char, width=24).pack(side="left", padx=6)
        ttk.Label(linec, foreground="#888",
                  text="(TRỐNG nếu không có; NHIỀU nhân vật cách nhau dấu phẩy: Kha, Thảo)"
                  ).pack(side="left")

        f2 = ttk.LabelFrame(parent, text="Tùy chọn prompt")
        f2.pack(fill="x", padx=8, pady=6)
        line = ttk.Frame(f2)
        line.pack(fill="x", padx=10, pady=6)
        ttk.Label(line, text="Số giây mỗi cảnh:").pack(side="left")
        # to=3600 chỉ giới hạn nút ▲▼; gõ tay vẫn nhập số bất kỳ. Cảnh DÀI (>10s) -> ẢNH TĨNH
        # (Ken Burns kéo đủ giờ) cho video ngủ / video chậm, KHÔNG cần khớp clip Veo.
        ttk.Spinbox(line, from_=2, to=3600, width=6, textvariable=self.secs).pack(side="left", padx=6)
        ttk.Label(line, text="(2–10s: hợp clip Veo  ·  >10s: ẢNH TĨNH kéo dài — cho video ngủ)",
                  foreground="#888").pack(side="left")

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
        ttk.Radiobutton(
            fp, variable=self.produce, value="chain", command=self._save_produce,
            text="🎞️  Ảnh đầu→cuối (chuỗi gối đầu) — N+1 ẢNH + N CHUYỂN ĐỘNG  (Veo Frames-to-Video, video liền mạch)"
        ).pack(anchor="w", padx=8, pady=1)

        fstyle = ttk.LabelFrame(
            f2, text="Phong cách (Style) để AI hay ẢNH MẪU lo? — chọn đúng 1, chọn cả 2 nơi sẽ chọi nhau")
        fstyle.pack(fill="x", padx=10, pady=(0, 6))
        self.style_mode = tk.StringVar(value=self.cfg.get("style_mode", "in_prompt"))
        ttk.Radiobutton(
            fstyle, variable=self.style_mode, value="in_prompt", command=self._save_stylemode,
            text="①  AI viết STYLE ngay trong prompt — chọn khi bạn KHÔNG dùng ảnh mẫu ở tool tạo video"
        ).pack(anchor="w", padx=8, pady=1)
        ttk.Radiobutton(
            fstyle, variable=self.style_mode, value="lock_art", command=self._save_stylemode,
            text="⭐  Ảnh mẫu lo NÉT VẼ — AI lo màu sắc + bối cảnh — chọn khi CÓ dùng ảnh mẫu (khuyên dùng)"
        ).pack(anchor="w", padx=8, pady=1)
        ttk.Radiobutton(
            fstyle, variable=self.style_mode, value="lock_all", command=self._save_stylemode,
            text="②  Ảnh mẫu lo TOÀN BỘ phong cách — AI chỉ viết nội dung cảnh (không tả màu, không tả style)"
        ).pack(anchor="w", padx=8, pady=1)
        ttk.Label(fstyle, foreground="#888",
                  text="Ảnh mẫu = ảnh khóa phong cách (Style Lock / ảnh tham chiếu) bạn đưa vào tool tạo video như Veo/Flow."
                  ).pack(anchor="w", padx=8, pady=(0, 4))

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
        # ---- HỒ SƠ KÊNH: 1 click áp trọn bộ cài đặt (style, sub, khung hình, nhạc...) ----
        chrow = ttk.Frame(parent)
        chrow.pack(fill="x", padx=8, pady=(6, 0))
        ttk.Label(chrow, text="📺 Hồ sơ kênh:").pack(side="left")
        self.cmb_channel = ttk.Combobox(chrow, textvariable=self.channel_var,
                                        state="readonly", width=22,
                                        values=list(self.cfg.get("channels", {}).keys()))
        self.cmb_channel.pack(side="left", padx=6)
        self.cmb_channel.bind("<<ComboboxSelected>>", self._on_channel_pick)
        ttk.Button(chrow, text="💾 Lưu kênh...", width=12,
                   command=self._channel_save_as).pack(side="left", padx=2)
        ttk.Button(chrow, text="🗑", width=3,
                   command=self._channel_delete).pack(side="left")
        ttk.Label(chrow, foreground="#888",
                  text="(lưu/áp trọn bộ: khung hình, phụ đề, màu, nhạc, logo, intro...)"
                  ).pack(side="left", padx=8)

        f1 = ttk.LabelFrame(parent, text="Nguyên liệu")
        f1.pack(fill="x", padx=8, pady=6)
        self._row(f1, "File PHỤ ĐỀ (SRT):", self.srt, lambda: self._pick_file(
            self.srt, [("SRT", "*.srt"), ("Tất cả", "*.*")]))
        self._row(f1, "Thư mục ẢNH/CLIP:", self.images, self._pick_dir)
        self._row(f1, "File VOICEOVER:", self.voice, lambda: self._pick_file(
            self.voice, [("Audio", "*.mp3 *.wav *.m4a *.aac"), ("Tất cả", "*.*")]))
        self._row(f1, "📋 File bảng cảnh:", self.scenes_file, self._pick_scenes_file)
        self._row(f1, "Xuất ra MP4:", self.out, self._pick_save)
        ttk.Label(f1, foreground="#888", wraplength=640,
                  text="📋 File bảng cảnh (scenes.csv): để TRỐNG = tự tìm. NÊN CHỌN đúng "
                       "scenes.csv của video này để render khớp tiếng (tránh dùng nhầm bảng "
                       "cảnh video khác → cảnh lệch audio).").pack(fill="x", padx=12, pady=(0, 2))

        f2 = ttk.LabelFrame(parent, text="Tùy chọn ghép")
        f2.pack(fill="x", padx=8, pady=6)
        linea = ttk.Frame(f2)
        linea.pack(fill="x", padx=10, pady=(8, 0))
        ttk.Label(linea, text="📐 Khung hình:").pack(side="left")
        ttk.Radiobutton(linea, text="16:9 ngang (YouTube)", value="16:9",
                        variable=self.aspect, command=self._save_aspect
                        ).pack(side="left", padx=(8, 0))
        ttk.Radiobutton(linea, text="9:16 dọc (Shorts/TikTok)", value="9:16",
                        variable=self.aspect, command=self._save_aspect
                        ).pack(side="left", padx=(8, 0))
        line = ttk.Frame(f2)
        line.pack(fill="x", padx=10, pady=8)
        ttk.Checkbutton(line, text="Ken Burns (zoom ảnh tĩnh)",
                        variable=self.kenburns).pack(side="left")
        ttk.Checkbutton(line, text="Chèn phụ đề", variable=self.subs).pack(side="left", padx=14)
        ttk.Checkbutton(line, text="Crossfade ảnh", variable=self.crossfade).pack(side="left")
        ttk.Label(line, text="kiểu:").pack(side="left", padx=(10, 2))
        ttk.Combobox(line, width=11, state="readonly", textvariable=self.transition,
                     values=["fade", "fadeblack", "dissolve", "slideleft", "slideright",
                             "slideup", "wipeleft", "wiperight", "circleopen", "radial",
                             "zoomin", "pixelize"]).pack(side="left")

        # ---- PHỤ ĐỀ: phông chữ + màu chữ/viền + cách hiển thị + preset màu ----
        linek = ttk.Frame(f2)
        linek.pack(fill="x", padx=10, pady=(0, 2))
        ttk.Label(linek, text="🖍 Phụ đề — Phông chữ:").pack(side="left")
        try:                                   # chỉ liệt kê font CÓ THẬT trên máy
            import tkinter.font as tkfont
            avail = set(tkfont.families())
        except Exception:
            avail = set()
        curated = ["Arial Black", "Arial", "Impact", "Segoe UI Black", "Segoe UI",
                   "Tahoma", "Verdana", "Bahnschrift", "Calibri", "Cambria", "Georgia",
                   "Times New Roman", "Comic Sans MS", "Consolas", "Montserrat", "Roboto"]
        fonts = [f for f in curated if not avail or f in avail] or curated
        cbf = ttk.Combobox(linek, width=18, textvariable=self.sub_font, values=fonts)
        cbf.pack(side="left", padx=6)
        cbf.bind("<<ComboboxSelected>>", lambda e: self._save_subopts())
        cbf.bind("<FocusOut>", lambda e: self._save_subopts())
        ttk.Label(linek, text="Màu chữ:").pack(side="left", padx=(10, 0))
        self.kara_swatch = tk.Label(linek, width=3, relief="ridge",
                                    bg=self._safe_bg(self.kara_color.get()))
        self.kara_swatch.pack(side="left", padx=4)
        ttk.Button(linek, text="Đổi", width=5,
                   command=self._pick_kara_color).pack(side="left")
        ttk.Label(linek, text="Màu viền:").pack(side="left", padx=(10, 0))
        self.outline_swatch = tk.Label(linek, width=3, relief="ridge",
                                       bg=self._safe_bg(self.sub_outline.get()))
        self.outline_swatch.pack(side="left", padx=4)
        ttk.Button(linek, text="Đổi", width=5,
                   command=self._pick_sub_outline).pack(side="left")

        linem = ttk.Frame(f2)
        linem.pack(fill="x", padx=10, pady=(0, 2))
        ttk.Label(linem, text="Cách hiện sub:").pack(side="left")
        for val, lbl in (("word", "1 TỪ nhảy theo voice (mặc định)"),
                         ("line", "Cả câu"),
                         ("kara", "Cả câu + tô màu từ đang đọc")):
            ttk.Radiobutton(linem, text=lbl, value=val, variable=self.sub_mode,
                            command=self._save_subopts).pack(side="left", padx=(8, 0))

        # Preset màu phụ đề (bấm chọn mẫu — đặt màu chữ + màu viền)
        SUB_PRESETS = [
            ("Neon", "#00FFF7", "#006E7A"), ("Classic", "#FFFFFF", "#000000"),
            ("Minimal", "#FFFFFF", "#2B2B2B"), ("Bold", "#FFE600", "#000000"),
            ("Mint", "#7CFFC4", "#0B5C3D"), ("Rose", "#FF7CA8", "#651232"),
            ("Sky", "#7CD9FF", "#0C4A6E"), ("Sunset", "#FFB25C", "#7A3A00"),
            ("Lavender", "#C9A8FF", "#3B2A66"), ("Lemon", "#FFF75C", "#6B6000"),
            ("Coral", "#FF8C7C", "#7A1F10"), ("Teal", "#5CE8E0", "#0B5C58"),
        ]
        linep = ttk.Frame(f2)
        linep.pack(fill="x", padx=10, pady=(2, 8))
        ttk.Label(linep, text="Preset màu (bấm chọn):").pack(side="left")
        for name, fg, oc in SUB_PRESETS:
            tk.Button(linep, text=name, fg=fg, bg="#181818",
                      activeforeground=fg, activebackground="#2A2A2A",
                      relief="groove", bd=1, padx=6, font=("", 8, "bold"),
                      command=lambda f=fg, o=oc, n=name: self._apply_sub_preset(n, f, o)
                      ).pack(side="left", padx=2)

        # Màu phim + vignette + hạt phim (#3)
        line2 = ttk.Frame(f2)
        line2.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Label(line2, text="🎨 Màu phim:").pack(side="left")
        ttk.Combobox(line2, width=11, state="readonly", textvariable=self.color,
                     values=["none", "cinematic", "cold", "warm", "bw"]).pack(side="left", padx=(2, 12))
        ttk.Checkbutton(line2, text="Vignette (tối góc)", variable=self.vignette).pack(side="left")
        ttk.Checkbutton(line2, text="Hạt phim", variable=self.grain).pack(side="left", padx=12)

        # Nhạc nền + ducking (#4)
        line3 = ttk.Frame(f2)
        line3.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Label(line3, text="🎵 Nhạc nền:").pack(side="left")
        ttk.Entry(line3, textvariable=self.bgm, width=28).pack(side="left", padx=(2, 4))
        ttk.Button(line3, text="Chọn...", width=8, command=self._pick_bgm).pack(side="left")
        # FOLDER nhạc -> playlist nhiều bài tự nối (video dài không lặp mãi 1 bài)
        ttk.Button(line3, text="📁", width=3,
                   command=lambda: self._pick_dir(self.bgm)).pack(side="left", padx=2)
        ttk.Label(line3, text="Âm lượng:").pack(side="left", padx=(12, 2))
        ttk.Spinbox(line3, from_=0.0, to=1.0, increment=0.02, width=5,
                    textvariable=self.bgm_volume).pack(side="left")
        ttk.Checkbutton(line3, text="Tự hạ nhạc khi có lời",
                        variable=self.duck).pack(side="left", padx=12)

        # Âm thanh GỐC của clip Veo (mặc định TẮT tiếng như cũ; bật -> trộn dưới voice)
        line3b = ttk.Frame(f2)
        line3b.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Checkbutton(line3b, text="🔉 Giữ âm thanh gốc của clip (mặc định tắt tiếng)",
                        variable=self.clip_audio,
                        command=self._save_clip_audio).pack(side="left")
        ttk.Label(line3b, text="Âm lượng tiếng clip:").pack(side="left", padx=(12, 2))
        ttk.Spinbox(line3b, from_=0.0, to=1.0, increment=0.05, width=5,
                    textvariable=self.clip_volume).pack(side="left")

        # ---- THƯƠNG HIỆU: logo + tiêu đề mở video + intro/outro + SFX chuyển cảnh ----
        fb = ttk.LabelFrame(parent, text="Thương hiệu kênh (tùy chọn — bỏ trống = như cũ)")
        fb.pack(fill="x", padx=8, pady=(0, 6))
        rb1 = ttk.Frame(fb)
        rb1.pack(fill="x", padx=10, pady=(6, 2))
        ttk.Label(rb1, text="🖼 Logo/watermark:").pack(side="left")
        ttk.Entry(rb1, textvariable=self.logo, width=26).pack(side="left", padx=(2, 4))
        ttk.Button(rb1, text="Chọn...", width=8, command=lambda: self._pick_file(
            self.logo, [("Ảnh PNG", "*.png"), ("Ảnh", "*.png *.jpg *.jpeg *.webp"),
                        ("Tất cả", "*.*")])).pack(side="left")
        ttk.Label(rb1, text="Góc:").pack(side="left", padx=(10, 2))
        ttk.Combobox(rb1, width=4, state="readonly", textvariable=self.logo_pos,
                     values=["br", "bl", "tr", "tl"]).pack(side="left")
        ttk.Label(rb1, text="Độ mờ:").pack(side="left", padx=(10, 2))
        ttk.Spinbox(rb1, from_=0.1, to=1.0, increment=0.05, width=5,
                    textvariable=self.logo_opacity).pack(side="left")
        rb2 = ttk.Frame(fb)
        rb2.pack(fill="x", padx=10, pady=2)
        ttk.Checkbutton(rb2, text="🅣 Chèn TIÊU ĐỀ mở video (lấy từ ô 📌 Tiêu đề, chữ to + fade)",
                        variable=self.title_on,
                        command=self._save_brand).pack(side="left")
        ttk.Label(rb2, text="giây:").pack(side="left", padx=(10, 2))
        ttk.Spinbox(rb2, from_=2, to=15, width=4,
                    textvariable=self.title_sec).pack(side="left")
        rb3 = ttk.Frame(fb)
        rb3.pack(fill="x", padx=10, pady=2)
        ttk.Label(rb3, text="🎬 Intro:").pack(side="left")
        ttk.Entry(rb3, textvariable=self.intro, width=22).pack(side="left", padx=(2, 2))
        ttk.Button(rb3, text="Chọn...", width=8, command=lambda: self._pick_file(
            self.intro, [("Video", "*.mp4 *.mov *.mkv"), ("Tất cả", "*.*")])).pack(side="left")
        ttk.Label(rb3, text="Outro:").pack(side="left", padx=(12, 2))
        ttk.Entry(rb3, textvariable=self.outro, width=22).pack(side="left", padx=(0, 2))
        ttk.Button(rb3, text="Chọn...", width=8, command=lambda: self._pick_file(
            self.outro, [("Video", "*.mp4 *.mov *.mkv"), ("Tất cả", "*.*")])).pack(side="left")
        rb4 = ttk.Frame(fb)
        rb4.pack(fill="x", padx=10, pady=(2, 6))
        ttk.Label(rb4, text="💥 SFX chuyển cảnh:").pack(side="left")
        ttk.Entry(rb4, textvariable=self.sfx, width=26).pack(side="left", padx=(2, 2))
        ttk.Button(rb4, text="Chọn...", width=8, command=lambda: self._pick_file(
            self.sfx, [("Audio", "*.mp3 *.wav *.m4a *.ogg"), ("Tất cả", "*.*")])).pack(side="left")
        ttk.Label(rb4, text="Âm lượng:").pack(side="left", padx=(10, 2))
        ttk.Spinbox(rb4, from_=0.0, to=1.0, increment=0.05, width=5,
                    textvariable=self.sfx_volume).pack(side="left")

        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=8, pady=8)
        self.btn_render = ttk.Button(bar, text="▶  RENDER VIDEO", command=self.run_render)
        self.btn_render.pack(side="left", padx=4)
        ttk.Button(bar, text="👁️ Xem trước",
                   command=self.run_preview).pack(side="left", padx=4)
        ttk.Button(bar, text="➕ Thêm vào Hàng đợi",
                   command=self.add_to_queue).pack(side="left", padx=4)
        self.btn_qc = ttk.Button(bar, text="🔍 Kiểm tra khớp nghĩa",
                                 command=self.run_qc_match)
        self.btn_qc.pack(side="left", padx=4)
        ttk.Button(bar, text="📂 Mở thư mục xuất",
                   command=self.open_out).pack(side="right", padx=4)
        ttk.Button(bar, text="🖼 Frame thumbnail",
                   command=self._export_thumb_frames).pack(side="right", padx=2)
        ttk.Button(bar, text="📑 Chapters",
                   command=self._export_chapters).pack(side="right", padx=2)

        ttk.Label(parent, wraplength=640, foreground="#555",
                  text="Đặt clip Veo tên 01,02,... trong thư mục clip. Render dùng scenes.csv "
                       "(sinh ở trang Tạo Prompt) để khớp clip theo đúng timestamp.").pack(
            fill="x", padx=12, pady=(0, 4))

    # ============================ TRANG VIDEO NGỦ ============================
    def _build_sleep(self, parent):
        f1 = ttk.LabelFrame(parent, text="Video ngủ dài (clip/ảnh nền + audio dài → 3-4 tiếng)")
        f1.pack(fill="x", padx=8, pady=6)
        rbg = self._row(f1, "🎬 NỀN (clip / ảnh):", self.sleep_bg, lambda: self._pick_file(
            self.sleep_bg, [("Clip / Ảnh", "*.mp4 *.mov *.mkv *.webm *.jpg *.jpeg *.png"),
                            ("Tất cả", "*.*")]))
        # Chọn FOLDER nhiều ảnh/clip -> nền XOAY VÒNG liền mạch (crossfade giữa các mục)
        ttk.Button(rbg, text="📁 Folder", width=9,
                   command=lambda: self._pick_dir(self.sleep_bg)).pack(side="left")
        self._row(f1, "🎵 AUDIO dài (kịch bản):", self.sleep_audio, lambda: self._pick_file(
            self.sleep_audio, [("Audio", "*.mp3 *.wav *.m4a *.aac"), ("Tất cả", "*.*")]))
        self._row(f1, "🌧️ Âm thanh NỀN (mưa/gió/tuyết — tùy chọn):", self.sleep_ambient,
                  lambda: self._pick_file(self.sleep_ambient,
                  [("Audio", "*.mp3 *.wav *.m4a *.aac *.ogg"), ("Tất cả", "*.*")]))
        self._row(f1, "Xuất ra MP4:", self.sleep_out, self._pick_sleep_out)
        ttk.Label(f1, foreground="#888", wraplength=640,
                  text="Nền = 1 FILE (clip ngắn tự LOOP LIỀN MẠCH — render vài phút) hoặc 1 FOLDER "
                       "nhiều ảnh/clip (nút 📁 Folder — tự XOAY VÒNG + crossfade theo tên file, "
                       "dựng đoạn loop lâu hơn chút).").pack(
            fill="x", padx=12, pady=(0, 2))

        f2 = ttk.LabelFrame(parent, text="Tùy chọn")
        f2.pack(fill="x", padx=8, pady=6)
        line = ttk.Frame(f2)
        line.pack(fill="x", padx=10, pady=8)
        ttk.Label(line, text="✨ Hiệu ứng (cho nền ẢNH tĩnh):").pack(side="left")
        ttk.Combobox(line, width=8, state="readonly", textvariable=self.sleep_effect,
                     values=["none", "rain", "snow", "fog", "bokeh"]).pack(side="left", padx=(2, 6))
        ttk.Combobox(line, width=6, state="readonly", textvariable=self.sleep_intensity,
                     values=["nhe", "vua", "nang"]).pack(side="left")
        ttk.Label(line, text="Fade tiếng (s):").pack(side="left", padx=(16, 2))
        ttk.Spinbox(line, from_=0, to=15, width=5, textvariable=self.sleep_fade).pack(side="left")
        ttk.Label(line, text="🎵 Visualizer:").pack(side="left", padx=(16, 2))
        ttk.Combobox(line, width=7, state="readonly", textvariable=self.sleep_viz,
                     values=["none", "bars", "waves"]).pack(side="left")
        line2 = ttk.Frame(f2)
        line2.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(line2, text="🔊 Âm lượng âm thanh nền:").pack(side="left")
        ttk.Spinbox(line2, from_=0.0, to=1.0, increment=0.05, width=5,
                    textvariable=self.sleep_ambient_vol).pack(side="left", padx=(4, 0))
        ttk.Label(line2, text="⏱ Giây mỗi mục (folder):").pack(side="left", padx=(16, 2))
        ttk.Spinbox(line2, from_=4, to=3600, width=6,
                    textvariable=self.sleep_item_sec).pack(side="left")
        ttk.Label(line2, foreground="#888",
                  text="(0.15 = rất nhẹ · 0.25 = nhẹ · 0.5 = rõ). Chỉ áp dụng khi có chọn "
                       "file âm thanh nền ở trên.").pack(side="left", padx=8)
        ttk.Label(f2, foreground="#888", wraplength=640,
                  text="Để hiệu ứng 'none' nếu nền đã đẹp (vd clip cảnh có sẵn). Hiệu ứng tự tạo "
                       "(mưa/tuyết/sương/bokeh) chỉ cho nền ẢNH TĨNH. ⚠️ Visualizer (bars/waves) "
                       "bật → render LÂU hơn nhiều (vẽ theo audio, không loop-copy được).").pack(
            fill="x", padx=12, pady=(0, 4))

        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=8, pady=8)
        self.btn_sleep = ttk.Button(bar, text="🌙  TẠO VIDEO NGỦ", command=self.run_sleep)
        self.btn_sleep.pack(side="left", padx=4)
        ttk.Button(bar, text="👁️ Xem trước (20s)",
                   command=lambda: self.run_sleep(preview=True)).pack(side="left", padx=4)
        ttk.Button(bar, text="📂 Mở thư mục xuất",
                   command=self._open_sleep_dir).pack(side="right", padx=4)

    def _pick_sleep_out(self):
        p = filedialog.asksaveasfilename(defaultextension=".mp4",
                                         filetypes=[("MP4", "*.mp4"), ("Tất cả", "*.*")])
        if p:
            self.sleep_out.set(p)

    def _open_sleep_dir(self):
        d = os.path.dirname(os.path.abspath(self.sleep_out.get() or dflt("output", "sleep.mp4")))
        if os.path.isdir(d):
            os.startfile(d)
        else:
            messagebox.showinfo("Chưa có", "Chưa có thư mục xuất — tạo video ngủ trước.")

    def run_sleep(self, preview=False):
        bg = (self.sleep_bg.get() or "").strip()
        audio = (self.sleep_audio.get() or "").strip()
        if not (os.path.isfile(bg) or os.path.isdir(bg)):   # nhận cả FOLDER nhiều ảnh/clip
            messagebox.showwarning(tr("Thiếu"),
                                   tr("Chưa chọn nền (1 file clip/ảnh, hoặc 1 folder nhiều ảnh/clip)."))
            return
        if not os.path.isfile(audio):
            messagebox.showwarning("Thiếu", "Chưa chọn file audio dài.")
            return
        out = (self.sleep_out.get() or "").strip() or dflt("output", "sleep.mp4")
        if preview:                                   # xem trước -> file RIÊNG, không đè bản chính
            out = os.path.splitext(out)[0] + "_preview.mp4"
        try:
            fv = float(self.sleep_fade.get())
        except (TypeError, ValueError):
            fv = 4.0
        cmd = script_cmd("sleep_video.py") + [
               "--bg", bg, "--audio", audio, "--out", out,
               "--effect", self.sleep_effect.get(), "--intensity", self.sleep_intensity.get(),
               "--fade", f"{fv}", "--viz", self.sleep_viz.get()]
        if os.path.isdir(bg):                         # folder nhiều ảnh/clip -> giây mỗi mục
            try:
                isec = float(self.sleep_item_sec.get())
            except (TypeError, ValueError):
                isec = 20.0
            if not (4 <= isec <= 3600):              # >120s engine tự chuyển CHẾ ĐỘ MỤC DÀI
                isec = min(max(isec, 4), 3600)       # (lặp COPY) nên nhận tới 3600
                self.sleep_item_sec.set(f"{isec:g}")
                self.status.set(tr("Giây mỗi mục chỉ nhận 4–3600s — đã tự chỉnh lại."))
            cmd += ["--item-sec", f"{isec:g}"]
            self.cfg["sleep_item_sec"] = self.sleep_item_sec.get()
            save_config(self.cfg)
        amb = (self.sleep_ambient.get() or "").strip()
        if amb and os.path.isfile(amb):
            cmd += ["--ambient", amb,
                    "--ambient-volume", (self.sleep_ambient_vol.get() or "0.25").strip()]
        if preview:
            cmd += ["--max-seconds", "20"]            # chỉ render 20s để xem/nghe thử

        self.log.delete("1.0", "end")
        self._log("$ xem trước video ngủ (20 giây)...\n\n" if preview else "$ tạo video ngủ...\n\n")
        self._busy(True)
        self.rendering = True
        self.status.set("Đang tạo bản xem trước..." if preview else "Đang tạo video ngủ...")

        def worker():
            try:
                env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
                           PYTHONUNBUFFERED="1")      # log engine hiện NGAY (không buffer)
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                p = subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True,
                                     encoding="utf-8", errors="replace", env=env,
                                     creationflags=flags)
                self.render_procs.append(p)
                for line in p.stdout:
                    self.q.put(("line", line))
                p.wait()
                ok = (p.returncode == 0)
                if not preview:
                    self._add_history(out, ok)
                self.q.put(("queue_finished", None))
                if ok and preview:
                    try:
                        os.startfile(out)                 # tự mở bản xem trước cho xem/nghe
                    except Exception:  # noqa
                        pass
                    self.q.put(("done", f"✅ Xem trước xong (20s): {out}"))
                elif ok:
                    self.q.put(("done", f"✅ Video ngủ xong: {out}"))
                else:
                    self.q.put(("done", f"Tạo video ngủ thất bại (mã {p.returncode}). Xem nhật ký."))
            except Exception as e:  # noqa
                self.q.put(("done", f"Lỗi: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def _open_prompts(self):
        p = self._out_path("veo_prompts.txt")
        if not os.path.isfile(p):
            p = dflt("veo_prompts.txt")          # fallback bản ở gốc
        if os.path.isfile(p):
            os.startfile(p)
        else:
            messagebox.showinfo("Chưa có", "Chưa có veo_prompts.txt — bấm TẠO PROMPT trước.")

    # ============================ TAB CÀI ĐẶT ============================
    def _build_settings(self, parent):
        # --- Phần mềm: phiên bản + nút KIỂM TRA CẬP NHẬT (user chủ động, khỏi đợi mở lại app) ---
        fu = ttk.LabelFrame(parent, text="Phần mềm")
        fu.pack(fill="x", padx=8, pady=6)
        ru = ttk.Frame(fu)
        ru.pack(fill="x", padx=8, pady=6)
        ttk.Label(ru, text=f"Phiên bản hiện tại: {self.app_ver or '?'}").pack(side="left")
        ttk.Button(ru, text="🔄 Kiểm tra cập nhật",
                   command=self._check_update_now).pack(side="right")
        # Ngôn ngữ / Language — đổi SỐNG toàn bộ giao diện, lưu nhớ
        self.lang_var = tk.StringVar(
            value="English" if i18n.get_lang() == "en" else "Tiếng Việt")
        cbl = ttk.Combobox(ru, width=10, state="readonly", textvariable=self.lang_var,
                           values=["Tiếng Việt", "English"])
        cbl.pack(side="right", padx=(0, 12))
        cbl.bind("<<ComboboxSelected>>", self._on_lang_pick)
        ttk.Label(ru, text="🌐 Ngôn ngữ / Language:").pack(side="right", padx=(0, 4))
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
        brow = ttk.Frame(right)
        brow.pack(anchor="e", pady=4)
        ttk.Button(brow, text="👁️ Xem trước style",
                   command=self._preview_style).pack(side="left", padx=4)
        ttk.Button(brow, text="💾 Lưu profile này",
                   command=self._profile_save).pack(side="left")

        self._refresh_profile_list()

    def _preview_style(self):
        """Hiện câu NÉT tool sẽ ghép vào mỗi prompt + cảnh báo nếu profile sai cấu trúc.
        Giúp bạn bè TỰ kiểm JSON mà không cần render thử (#10)."""
        import ai_prompts
        style = self.txt_style.get("1.0", "end").strip()
        if not style:
            messagebox.showinfo(tr("Xem trước style"), tr("Profile đang trống."))
            return
        cap = ai_prompts._style_caption(style)
        if not cap.strip():
            messagebox.showwarning(
                "Xem trước style",
                "⚠️ Profile này KHÔNG sinh được câu NÉT nào!\n\n"
                "Prompt sẽ thiếu phong cách. Kiểm tra lại — nên có các trường: "
                "art_style, line_work, shading_lighting, mood (và scene_modes, characters).")
            return
        ai = ai_prompts._style_for_ai(style)
        messagebox.showinfo(
            "Xem trước style",
            "✅ Câu NÉT sẽ tự ghép vào MỌI prompt:\n\n"
            + (cap[:650] + ("..." if len(cap) > 650 else ""))
            + "\n\n──────────\nPhần gửi AI (màu / nhân vật / bối cảnh):\n"
            + (ai[:350] + ("..." if len(ai) > 350 else "")))

    # ---------- tiện ích UI chung ----------
    def _row(self, parent, label, var, cmd):
        f = ttk.Frame(parent)
        f.pack(fill="x", padx=8, pady=3)
        ttk.Label(f, text=label, width=18).pack(side="left")
        ttk.Entry(f, textvariable=var).pack(side="left", fill="x", expand=True)
        ttk.Button(f, text="Chọn...", command=cmd, width=8).pack(side="left", padx=4)
        return f

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

    def _prompt_base(self):
        """Thư mục lưu prompt + scenes.csv. User chọn thư mục hợp lệ -> dùng nó (mỗi
        video 1 thư mục riêng, không đè nhau). Trống/không hợp lệ -> gốc dự án (đè như cũ)."""
        d = (self.prompt_dir.get() or "").strip()
        if d and os.path.isdir(d):
            return d
        return HERE

    def _out_path(self, name):
        """Đường dẫn file output (prompt/scenes) theo thư mục lưu đã chọn."""
        return os.path.join(self._prompt_base(), name)

    def _save_prompt_dir(self):
        self.cfg["prompt_dir"] = self.prompt_dir.get().strip()
        save_config(self.cfg)

    def _pick_prompt_dir(self):
        d = filedialog.askdirectory(initialdir=self._prompt_base())
        if d:
            self.prompt_dir.set(d)
            self._save_prompt_dir()

    def _scenes_path(self):
        """File scenes.csv để render + kiểm tra. Ưu tiên: ① file CHỌN TAY → ② cùng THƯ MỤC
        CLIP (mỗi video 1 thư mục clip+scenes) → ③ thư mục lưu prompt đặt riêng → ④ gốc dự án.
        Đặt thư mục clip TRƯỚC gốc → KHÔNG đọc nhầm scenes.csv cũ còn sót ở gốc."""
        f = (self.scenes_file.get() or "").strip()
        if f and os.path.isfile(f):
            return f
        img = (self.images.get() or "").strip()          # ② cùng thư mục clip đang chọn
        if img and os.path.isfile(os.path.join(img, "scenes.csv")):
            return os.path.join(img, "scenes.csv")
        d = (self.prompt_dir.get() or "").strip()         # ③ thư mục lưu prompt (nếu đặt riêng)
        if d and os.path.isdir(d) and os.path.isfile(os.path.join(d, "scenes.csv")):
            return os.path.join(d, "scenes.csv")
        g = dflt("scenes.csv")                            # ④ gốc dự án (cuối cùng)
        return g if os.path.isfile(g) else ""

    def _pick_scenes_file(self):
        f = filedialog.askopenfilename(
            initialdir=self._prompt_base(),
            filetypes=[("Bảng cảnh", "*.csv"), ("Tất cả", "*.*")])
        if f:
            self.scenes_file.set(f)

    def _pick_dir(self, var=None):
        """Chọn thư mục -> đặt vào var; không truyền var = ô Thư mục ẢNH/CLIP (trang Render).
        ⚠️ TRÁNH định nghĩa trùng tên lần 2 — bản sau ĐÈ bản trước làm nút cũ câm lặng."""
        d = filedialog.askdirectory(initialdir=HERE)
        if d:
            (var if var is not None else self.images).set(d)

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
            messagebox.showinfo(tr("Chọn profile"), tr("Hãy chọn 1 profile bên trái (hoặc bấm Thêm)."))
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
            messagebox.showinfo(tr("Không thể xoá"), tr("Phải giữ ít nhất 1 profile."))
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
        self.key_hint.set(tr(hints.get(self.provider_var.get(), "")))

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

    # ---------- log/queue ----------
    def _busy(self, on):
        if on:                                   # bắt đầu việc mới -> reset thanh tiến độ
            self.pbar["value"] = 0
            self.eta_var.set("")
            self._prog_t0 = None
        st = "disabled" if on else "normal"
        self.btn_prompt["state"] = st
        self.btn_render["state"] = st
        if hasattr(self, "btn_qc"):
            self.btn_qc["state"] = st
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
                    try:
                        self._progress_line(data)
                    except Exception:  # noqa — tiến độ chỉ là trang trí, không được chặn log
                        pass
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
                elif kind == "scenes_done":
                    # Tạo prompt xong -> tự điền file bảng cảnh vừa tạo (liền mạch render)
                    if data and os.path.isfile(data):
                        self.scenes_file.set(data)
                elif kind == "queue_finished":
                    self._refresh_queue()        # cập nhật hàng đợi (đã xóa job xong)
                    self._refresh_history()      # cập nhật lịch sử render
                elif kind == "preview_done":
                    self._busy(False)
                    self.rendering = False
                    self.render_procs.clear()
                    path, msg = data
                    self.status.set(msg)
                    if path and os.path.isfile(path):
                        try:
                            os.startfile(path)
                        except Exception:  # noqa
                            pass
                elif kind == "selfupdate_done":
                    self.rendering = False
                    self.root.destroy()          # bản mới đã mở -> thoát bản cũ
                    return
                elif kind == "done":
                    self._busy(False)
                    self.rendering = False           # hết render -> cho đóng app tự do
                    self.render_procs.clear()
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
            messagebox.showwarning(tr("Thiếu"), tr("Chưa chọn file SRT hợp lệ."))
            return
        name = self.profile_var.get()
        style = self.cfg["profiles"].get(name, "")
        prov = self.cfg.get("provider", "gemini")
        key = self.cfg.get("keys", {}).get(prov, "")
        smode = self.style_mode.get()
        character = self.main_char.get().strip()
        title = self.video_title.get().strip()
        base_dir = self._prompt_base()          # thư mục lưu prompt + scenes.csv
        self._save_prompt_dir()
        self.cfg["main_character"] = character
        save_config(self.cfg)
        if not key.strip():
            messagebox.showwarning(tr("Thiếu API key"),
                                   tr(f"Vào tab Cài đặt nhập API key cho '{prov}' trước nhé."))
            return
        if smode != "lock_all" and not style.strip():
            messagebox.showwarning(tr("Thiếu style"),
                                   tr("Style profile đang trống. Vào tab Cài đặt để dán nội dung, "
                                      "hoặc chọn chế độ '② Lock lo TẤT CẢ style'."))
            return
        try:
            target = float(self.secs.get())
        except ValueError:
            target = 8.0

        # ⚠️ CẢNH BÁO ĐÈ FILE: chưa chọn thư mục lưu prompt riêng -> lưu ở GỐC, ghi đè
        # scenes.csv + prompt của video làm trước (mất nếu video đó chưa render xong).
        # Chỉ cảnh báo khi THẬT SỰ có file sắp bị đè (gốc đã có scenes.csv) -> tránh phiền.
        pd = (self.prompt_dir.get() or "").strip()
        if (not pd or not os.path.isdir(pd)) and os.path.isfile(os.path.join(HERE, "scenes.csv")):
            ans = messagebox.askyesnocancel(
                "⚠️ Có thể ĐÈ prompt của video trước",
                "Bạn CHƯA chọn '📁 Thư mục lưu prompt' riêng cho video này.\n\n"
                "→ scenes.csv + prompt sẽ lưu ở thư mục GỐC và GHI ĐÈ lên file của video "
                "làm trước đó (mất prompt cũ nếu video đó chưa render xong).\n\n"
                "[Yes / Có]      = Chọn thư mục riêng ngay (khuyên dùng)\n"
                "[No / Không]   = Vẫn lưu ở gốc và ghi đè\n"
                "[Cancel / Hủy] = Dừng lại")
            if ans is None:                       # Cancel -> dừng
                self.status.set("Đã hủy tạo prompt.")
                return
            if ans:                               # Yes -> chọn thư mục riêng
                self._pick_prompt_dir()
                d2 = (self.prompt_dir.get() or "").strip()
                if not (d2 and os.path.isdir(d2)):
                    self.status.set("Chưa chọn thư mục — đã dừng tạo prompt.")
                    return
                base_dir = self._prompt_base()    # cập nhật lại nơi lưu (thư mục riêng)
            # No -> giữ nguyên, cố ý ghi đè ở gốc

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
                    sc = os.path.join(base_dir, "scenes.csv")
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
                        texts, key, image_prompts=img_prompts, model=model, progress=prog,
                        provider=prov, character=character, title=title)
                    ip = os.path.join(base_dir, "image_prompts.txt")
                    mp = os.path.join(base_dir, "motion_prompts.txt")
                    with open(ip, "w", encoding="utf-8") as f:
                        f.write("\n".join(p.replace("\n", " ").strip() for p in img_prompts) + "\n")
                    with open(mp, "w", encoding="utf-8") as f:
                        f.write("\n".join(p.replace("\n", " ").strip() for p in motion) + "\n")
                    sc = write_scenes(img_prompts, motion)
                    self.q.put(("scenes_done", sc))
                    self.q.put(("line", f"\n• Đã ghi:\n   {ip}\n   {mp}\n   {sc}\n"))
                    self.q.put(("done", f"✅ Xong (Image-to-video)! {len(img_prompts)} cảnh × 2 prompt. "
                                        "Dùng image_prompts.txt tạo keyframe → motion_prompts.txt cho i2v."))
                elif produce == "chain":
                    self.q.put(("line", f"• {len(scenes)} cảnh → chuỗi {len(scenes) + 1} ẢNH gối đầu "
                                        f"(ảnh đầu→cuối cho Veo Frames-to-Video) gọi {prov}...\n"))
                    self.q.put(("line", "• (1/2) Viết chuỗi prompt ẢNH liên hoàn...\n"))
                    img_prompts, motion = ai_prompts.generate_chain_prompts(
                        texts, style, key, model=model, progress=prog,
                        style_mode=smode, provider=prov, character=character, title=title)
                    self.q.put(("line", "• (2/2) Viết prompt CHUYỂN ĐỘNG từng clip...\n"))
                    ip = os.path.join(base_dir, "image_prompts.txt")
                    mp = os.path.join(base_dir, "motion_prompts.txt")
                    with open(ip, "w", encoding="utf-8") as f:
                        f.write("\n".join(p.replace("\n", " ").strip() for p in img_prompts) + "\n")
                    with open(mp, "w", encoding="utf-8") as f:
                        f.write("\n".join(p.replace("\n", " ").strip() for p in motion) + "\n")
                    pair = [f"ảnh {i + 1} → ảnh {i + 2}" for i in range(len(scenes))]
                    sc = write_scenes(pair, motion)
                    self.q.put(("scenes_done", sc))
                    self.q.put(("line", f"\n• Đã ghi:\n   {ip}  ({len(img_prompts)} ảnh gối đầu)\n"
                                        f"   {mp}  ({len(motion)} clip)\n   {sc}\n"))
                    self.q.put(("done", f"✅ Xong (Ảnh đầu→cuối)! {len(img_prompts)} ảnh × {len(motion)} clip. "
                                        "Tạo ảnh 1..N+1 (dùng ref giữ nhân vật) → mỗi clip Veo dùng ảnh i + ảnh "
                                        "i+1 + dòng tương ứng trong motion_prompts.txt."))
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
                    vp = os.path.join(base_dir, "veo_prompts.txt")
                    with open(vp, "w", encoding="utf-8") as f:
                        f.write("\n".join(p.replace("\n", " ").strip() for p in prompts) + "\n")
                    sc = write_scenes(prompts)
                    self.q.put(("scenes_done", sc))
                    self.q.put(("line", f"\n• Đã ghi {len(prompts)} prompt vào:\n   {vp}\n   {sc}\n"))
                    self.q.put(("done", f"✅ Xong! Đã viết {len(prompts)} prompt. "
                                        "Mở veo_prompts.txt để dán vào Veo."))
            except Exception as e:  # noqa
                self.q.put(("done", f"Lỗi: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    # ---------- Kiểm clip hỏng trước khi render (#7) ----------
    def _broken_clips(self, images):
        """Quét thư mục, trả danh sách clip VIDEO hỏng (ffprobe lỗi hoặc chỉ ~1 frame).
        Clip hỏng sẽ làm video bị HỤT thời lượng -> cảnh lệch khỏi audio."""
        try:
            import auto_edit as ae
            files = ae.collect_media(images)
        except Exception:  # noqa
            return []
        bad = []
        for f in files:
            if f.lower().endswith(ae.VIDEO_EXTS):
                d = ae.probe_duration(f)
                if d is None or d < 0.25:        # 1 frame ~0.04s
                    bad.append(os.path.basename(f))
        return bad

    def _confirm_broken(self, images):
        """True = cho render tiếp. Nếu có clip hỏng -> hỏi xác nhận."""
        bad = self._broken_clips(images)
        if not bad:
            return True
        lst = ", ".join(bad[:15]) + ("..." if len(bad) > 15 else "")
        return messagebox.askyesno(
            "⚠️ Clip hỏng",
            f"Phát hiện {len(bad)} clip VIDEO hỏng (lỗi/chỉ 1 khung hình):\n\n{lst}\n\n"
            "Các clip này sẽ làm video BỊ HỤT thời lượng → cảnh lệch khỏi tiếng.\n"
            "Nên thay bằng clip tốt hoặc ảnh tĩnh (.jpg) trước.\n\nVẫn render?")

    # ---------- RENDER (gọi auto_edit.py) ----------
    def run_render(self):
        if not os.path.isfile(self.srt.get()):
            messagebox.showwarning("Thiếu", "Chưa chọn file SRT.")
            return
        if not os.path.isdir(self.images.get()):
            messagebox.showwarning(tr("Thiếu"), tr("Chưa chọn thư mục ảnh/clip."))
            return
        if not self._confirm_broken(self.images.get()):
            return
        job = self._current_job()
        warn = self._scenes_voice_mismatch(job.get("scenes", ""), job.get("voice", ""))
        if warn and not messagebox.askyesno("⚠️ Bảng cảnh không khớp", warn + "\n\nVẫn render?"):
            return
        cmd = self._job_cmd(job)

        self.log.delete("1.0", "end")
        self._log("$ render...\n\n")
        self._busy(True)
        self.rendering = True
        self.status.set("Đang render...")

        def worker():
            try:
                env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
                           PYTHONUNBUFFERED="1")      # log engine hiện NGAY (không buffer)
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                p = subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True,
                                     encoding="utf-8", errors="replace", env=env,
                                     creationflags=flags)
                self.render_procs.append(p)
                for line in p.stdout:
                    self.q.put(("line", line))
                p.wait()
                ok = (p.returncode == 0)
                self._add_history(job.get("out", ""), ok)          # lưu lịch sử
                self.q.put(("queue_finished", None))               # refresh list lịch sử
                if ok:
                    self.q.put(("done", f"✅ Render xong: {self.out.get()}"))
                else:
                    self.q.put(("done", f"Render thất bại (mã {p.returncode}). Xem nhật ký."))
            except Exception as e:  # noqa
                self.q.put(("done", f"Lỗi: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    # ---------- XEM TRƯỚC nhanh (render vài cảnh đầu với hiệu ứng đang chọn) ----------
    def run_preview(self):
        if not os.path.isfile(self.srt.get()):
            messagebox.showwarning("Thiếu", "Chưa chọn file SRT.")
            return
        if not os.path.isdir(self.images.get()):
            messagebox.showwarning(tr("Thiếu"), tr("Chưa chọn thư mục ảnh/clip."))
            return
        prev = os.path.join(tempfile.gettempdir(), "aev_preview.mp4")
        job = dict(self._current_job(), out=prev)
        cmd = self._job_cmd(job, preview=True)

        self.log.delete("1.0", "end")
        self._log("$ xem trước (render vài cảnh đầu với hiệu ứng đang chọn)...\n\n")
        self._busy(True)
        self.rendering = True
        self.status.set("Đang tạo xem trước...")

        def worker():
            try:
                env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
                           PYTHONUNBUFFERED="1")      # log engine hiện NGAY (không buffer)
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                p = subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True,
                                     encoding="utf-8", errors="replace", env=env,
                                     creationflags=flags)
                self.render_procs.append(p)
                for line in p.stdout:
                    self.q.put(("line", line))
                p.wait()
                if p.returncode == 0:
                    self.q.put(("preview_done", (prev, "✅ Xem trước xong (đã mở video).")))
                else:
                    self.q.put(("done", f"Xem trước thất bại (mã {p.returncode}). Xem nhật ký."))
            except Exception as e:  # noqa
                self.q.put(("done", f"Lỗi: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    # ---------- QC khớp nghĩa: clip có đúng ý lời thoại không (#9) ----------
    def run_qc_match(self):
        sc = self._scenes_path()      # ĐỌC ĐÚNG bảng cảnh đang chọn (như khi render) — KHÔNG lấy nhầm file ở gốc
        if not sc or not os.path.isfile(sc):
            messagebox.showwarning("Thiếu", "Chưa có scenes.csv — chọn ô '📋 File bảng cảnh' "
                                            "(trang Render) hoặc bấm TẠO PROMPT trước.")
            return
        prov = self.cfg.get("provider", "gemini")
        key = self.cfg.get("keys", {}).get(prov, "")
        if not key.strip():
            messagebox.showwarning(tr("Thiếu API key"), tr(f"Vào Cài đặt nhập key cho '{prov}'."))
            return
        model = self.cfg.get("models", {}).get(prov)
        import csv
        rows = list(csv.DictReader(open(sc, encoding="utf-8-sig")))
        scenes = [{"scene": r.get("scene"), "text": r.get("text", ""),
                   "prompt": r.get("prompt", "")} for r in rows]

        self.log.delete("1.0", "end")
        self._busy(True)
        self.status.set("Đang kiểm khớp nghĩa (clip vs lời thoại)...")
        self.q.put(("line", f"• Kiểm {len(scenes)} cảnh bằng {prov}...\n"))

        def worker():
            try:
                import ai_prompts
                def prog(d, t):
                    self.q.put(("line", f"   ...đã kiểm {d}/{t}\n"))
                res = ai_prompts.qc_scene_match(scenes, key, model=model,
                                                provider=prov, progress=prog)
                good = [d for d in res if d.get("verdict") == "good"]
                weak = [d for d in res if d.get("verdict") == "weak"]
                off = [d for d in res if d.get("verdict") == "off"]
                self.q.put(("line", f"\n===== KẾT QUẢ: ✅{len(good)} khớp | 🟡{len(weak)} yếu | "
                                    f"❌{len(off)} lệch =====\n"))
                for d in off:
                    self.q.put(("line", f"  ❌ Cảnh {d.get('scene')}: {d.get('reason')}\n"))
                for d in weak:
                    self.q.put(("line", f"  🟡 Cảnh {d.get('scene')}: {d.get('reason')}\n"))
                self.q.put(("done", f"✅ QC xong: {len(good)} khớp, {len(weak)} yếu, "
                                    f"{len(off)} lệch nghĩa (chi tiết ở nhật ký)."))
            except Exception as e:  # noqa
                self.q.put(("done", f"Lỗi QC: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def _pick_bgm(self):
        p = filedialog.askopenfilename(
            title="Chọn nhạc nền",
            filetypes=[("Âm thanh", "*.mp3 *.wav *.m4a *.aac *.ogg"), ("Tất cả", "*.*")])
        if p:
            self.bgm.set(p)

    def _safe_bg(self, hexcol):
        """Trả hex hợp lệ (#RRGGBB) để đặt nền swatch; sai -> vàng."""
        import re
        return hexcol if re.match(r"^#[0-9A-Fa-f]{6}$", str(hexcol or "")) else "#FFFF00"

    def _pick_kara_color(self):
        """Mở bảng chọn màu -> đặt màu chữ chạy karaoke, lưu nhớ."""
        from tkinter import colorchooser
        _, hx = colorchooser.askcolor(color=self._safe_bg(self.kara_color.get()),
                                      title="Màu chữ chạy theo voice (karaoke)")
        if hx:
            self.kara_color.set(hx)
            try:
                self.kara_swatch.configure(bg=hx)
            except Exception:
                pass
            self.cfg["kara_color"] = hx
            save_config(self.cfg)

    def _pick_sub_outline(self):
        """Mở bảng chọn màu -> đặt màu VIỀN chữ phụ đề, lưu nhớ."""
        from tkinter import colorchooser
        _, hx = colorchooser.askcolor(color=self._safe_bg(self.sub_outline.get()),
                                      title="Màu viền chữ phụ đề")
        if hx:
            self.sub_outline.set(hx)
            self.outline_swatch.config(bg=self._safe_bg(hx))
            self._save_subopts()

    def _apply_sub_preset(self, name, fg, outline):
        """Bấm preset -> đặt màu chữ + màu viền phụ đề theo mẫu, lưu nhớ."""
        self.kara_color.set(fg)
        self.sub_outline.set(outline)
        self.kara_swatch.config(bg=self._safe_bg(fg))
        self.outline_swatch.config(bg=self._safe_bg(outline))
        self._save_subopts()
        self.status.set(f"Đã áp preset phụ đề '{name}' (chữ {fg}, viền {outline}).")

    def _save_aspect(self):
        self.cfg["aspect"] = self.aspect.get()
        save_config(self.cfg)

    def _save_brand(self):
        """Lưu nhóm cài đặt THƯƠNG HIỆU (logo/tiêu đề/intro-outro/sfx) vào config."""
        for k, v in (("logo", self.logo.get().strip()),
                     ("logo_pos", self.logo_pos.get()),
                     ("logo_opacity", self.logo_opacity.get().strip()),
                     ("title_on", bool(self.title_on.get())),
                     ("title_sec", self.title_sec.get().strip()),
                     ("intro", self.intro.get().strip()),
                     ("outro", self.outro.get().strip()),
                     ("sfx", self.sfx.get().strip()),
                     ("sfx_volume", self.sfx_volume.get().strip())):
            self.cfg[k] = v
        save_config(self.cfg)

    # ---------- HỒ SƠ KÊNH: lưu/áp trọn bộ cài đặt cho từng kênh ----------
    _CHANNEL_KEYS = ("aspect", "sub_font", "sub_mode", "sub_outline", "kara_color",
                     "clip_audio", "clip_volume", "logo", "logo_pos", "logo_opacity",
                     "title_on", "title_sec", "intro", "outro", "sfx", "sfx_volume",
                     "bgm", "bgm_volume", "duck", "transition", "crossfade", "kenburns",
                     "color", "vignette", "grain", "active_profile", "main_character")

    def _channel_snapshot(self):
        return {
            "aspect": self.aspect.get(), "sub_font": self.sub_font.get(),
            "sub_mode": self.sub_mode.get(), "sub_outline": self.sub_outline.get(),
            "kara_color": self.kara_color.get(),
            "clip_audio": bool(self.clip_audio.get()),
            "clip_volume": self.clip_volume.get(),
            "logo": self.logo.get(), "logo_pos": self.logo_pos.get(),
            "logo_opacity": self.logo_opacity.get(),
            "title_on": bool(self.title_on.get()), "title_sec": self.title_sec.get(),
            "intro": self.intro.get(), "outro": self.outro.get(),
            "sfx": self.sfx.get(), "sfx_volume": self.sfx_volume.get(),
            "bgm": self.bgm.get(), "bgm_volume": self.bgm_volume.get(),
            "duck": bool(self.duck.get()), "transition": self.transition.get(),
            "crossfade": bool(self.crossfade.get()),
            "kenburns": bool(self.kenburns.get()), "color": self.color.get(),
            "vignette": bool(self.vignette.get()), "grain": bool(self.grain.get()),
            "active_profile": self.profile_var.get(),
            "main_character": self.main_char.get(),
        }

    def _channel_apply(self, d):
        self.aspect.set(d.get("aspect", "16:9"))
        self.sub_font.set(d.get("sub_font", "Arial Black"))
        self.sub_mode.set(d.get("sub_mode", "word"))
        self.sub_outline.set(d.get("sub_outline", "#000000"))
        self.kara_color.set(d.get("kara_color", "#FFFF00"))
        self.clip_audio.set(bool(d.get("clip_audio", False)))
        self.clip_volume.set(str(d.get("clip_volume", "0.25")))
        self.logo.set(d.get("logo", "")); self.logo_pos.set(d.get("logo_pos", "br"))
        self.logo_opacity.set(str(d.get("logo_opacity", "0.85")))
        self.title_on.set(bool(d.get("title_on", False)))
        self.title_sec.set(str(d.get("title_sec", "4")))
        self.intro.set(d.get("intro", "")); self.outro.set(d.get("outro", ""))
        self.sfx.set(d.get("sfx", "")); self.sfx_volume.set(str(d.get("sfx_volume", "0.5")))
        self.bgm.set(d.get("bgm", "")); self.bgm_volume.set(str(d.get("bgm_volume", "0.18")))
        self.duck.set(bool(d.get("duck", True)))
        self.transition.set(d.get("transition", "fade"))
        self.crossfade.set(bool(d.get("crossfade", False)))
        self.kenburns.set(bool(d.get("kenburns", True)))
        self.color.set(d.get("color", "none"))
        self.vignette.set(bool(d.get("vignette", False)))
        self.grain.set(bool(d.get("grain", False)))
        if d.get("active_profile") in self.cfg.get("profiles", {}):
            self.profile_var.set(d["active_profile"])
            self.cfg["active_profile"] = d["active_profile"]
        self.main_char.set(d.get("main_character", ""))
        # đồng bộ ô màu + lưu các nhóm
        self.kara_swatch.config(bg=self._safe_bg(self.kara_color.get()))
        self.outline_swatch.config(bg=self._safe_bg(self.sub_outline.get()))
        self._save_subopts(); self._save_aspect(); self._save_clip_audio()
        self._save_brand()

    def _on_channel_pick(self, _e=None):
        name = self.channel_var.get()
        d = self.cfg.get("channels", {}).get(name)
        if not d:
            return
        self._channel_apply(d)
        self.cfg["active_channel"] = name
        save_config(self.cfg)
        self.status.set(tr(f"Đã áp hồ sơ kênh '{name}'."))

    def _channel_save_as(self):
        name = simpledialog.askstring(tr("Lưu hồ sơ kênh"),
                                      tr("Tên kênh (vd: Stickman, Quân sự...):"),
                                      initialvalue=self.channel_var.get() or "")
        if not name or not name.strip():
            return
        name = name.strip()
        self.cfg.setdefault("channels", {})[name] = self._channel_snapshot()
        self.cfg["active_channel"] = name
        save_config(self.cfg)
        self.channel_var.set(name)
        self.cmb_channel["values"] = list(self.cfg["channels"].keys())
        self.status.set(tr(f"Đã lưu hồ sơ kênh '{name}'."))

    def _channel_delete(self):
        name = self.channel_var.get()
        if not name or name not in self.cfg.get("channels", {}):
            return
        if not messagebox.askyesno(tr("Xoá"), tr(f"Xoá hồ sơ kênh '{name}'?")):
            return
        self.cfg["channels"].pop(name, None)
        self.cfg["active_channel"] = ""
        save_config(self.cfg)
        self.channel_var.set("")
        self.cmb_channel["values"] = list(self.cfg["channels"].keys())

    # ---------- Chapters + frame thumbnail ----------
    def _export_chapters(self):
        """scenes.csv -> chapters.txt kiểu YouTube (m:ss + câu đầu cảnh) cạnh file xuất."""
        import csv as _csv
        import re as _re
        sc = self._scenes_path()
        if not (sc and os.path.isfile(sc)):
            messagebox.showwarning(tr("Thiếu"), tr("Chưa thấy file bảng cảnh (scenes.csv)."))
            return
        rows = []
        with open(sc, encoding="utf-8-sig", newline="") as f:
            for r in _csv.reader(f):
                if len(r) >= 7 and r[0].strip().isdigit():
                    m = _re.findall(r"\d+", r[1])
                    if len(m) >= 3:
                        secs = int(m[0]) * 3600 + int(m[1]) * 60 + int(m[2])
                        rows.append((secs, " ".join(r[6].split())[:60]))
        if not rows:
            messagebox.showwarning(tr("Lỗi"), tr("Không đọc được bảng cảnh."))
            return
        out = os.path.splitext(self.out.get().strip() or dflt("output", "final.mp4"))[0] \
            + "_chapters.txt"
        with open(out, "w", encoding="utf-8") as f:
            for secs, txt in rows:
                f.write(f"{secs // 60}:{secs % 60:02d} {txt}\n")
        self.status.set(tr(f"Đã xuất chapters: {os.path.basename(out)}"))
        try:
            os.startfile(out)
        except OSError:
            pass

    def _export_thumb_frames(self):
        """Trích 6 frame rải đều từ video đã render -> làm nền thumbnail."""
        out = (self.out.get() or "").strip()
        if not os.path.isfile(out):
            messagebox.showwarning(tr("Thiếu"), tr("Chưa thấy file video xuất — render trước đã."))
            return
        import auto_edit as ae
        dur = ae.probe_duration(out) or 0
        if dur < 2:
            messagebox.showwarning(tr("Lỗi"), tr("Video quá ngắn / không đọc được."))
            return
        folder = os.path.splitext(out)[0] + "_thumbs"
        os.makedirs(folder, exist_ok=True)
        for i in range(6):
            t = dur * (i + 0.5) / 6
            subprocess.run([ae.FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                            "-ss", f"{t:.2f}", "-i", out, "-frames:v", "1",
                            os.path.join(folder, f"thumb_{i + 1}.jpg")],
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.status.set(tr("Đã trích 6 frame thumbnail."))
        try:
            os.startfile(folder)
        except OSError:
            pass

    # ---------- Thanh tiến độ: đọc log engine -> % + ETA ----------
    def _progress_line(self, s):
        import re as _re
        import time as _time
        m = _re.search(r"\[(\d+)/(\d+)\]", s)
        if m:
            done, total = int(m.group(1)), int(m.group(2))
            if self._prog_t0 is None:
                self._prog_t0 = _time.time()
            if total > 0 and done > 0:
                self.pbar["value"] = min(88.0, done * 88.0 / total)
                left = (_time.time() - self._prog_t0) / done * (total - done)
                self.eta_var.set(tr(f"còn ~{int(left // 60)}p{int(left % 60):02d}s")
                                 if left > 3 else "")
            return
        if "(1/2)" in s:
            self.pbar["value"] = 25
        elif "(2/2)" in s:
            self.pbar["value"] = 70
        elif "bản cuối" in s or "final pass" in s:
            self.pbar["value"] = 92
            self.eta_var.set(tr("đang ghép bản cuối..."))
        elif "intro/outro" in s:
            self.pbar["value"] = 96
        elif "✅" in s:
            self.pbar["value"] = 100
            self.eta_var.set("")

    def _save_clip_audio(self):
        self.cfg["clip_audio"] = bool(self.clip_audio.get())
        self.cfg["clip_volume"] = self.clip_volume.get().strip()
        save_config(self.cfg)

    def _save_subopts(self):
        """Lưu tùy chọn phụ đề (font + cách hiện + màu) vào config."""
        self.cfg["sub_font"] = self.sub_font.get().strip()
        self.cfg["sub_mode"] = self.sub_mode.get()
        self.cfg["sub_outline"] = self.sub_outline.get().strip()
        self.cfg["kara_color"] = self.kara_color.get().strip()
        save_config(self.cfg)

    # ============================ HÀNG ĐỢI ============================
    def _current_job(self):
        """Gói nguyên liệu đang chọn ở tab Làm video thành 1 'job' để render."""
        return {
            "out": self.out.get(), "srt": self.srt.get(),
            "images": self.images.get(), "voice": self.voice.get(),
            "scenes": self._scenes_path(), "secs": self.secs.get(),
            "kenburns": self.kenburns.get(), "subs": self.subs.get(),
            "aspect": self.aspect.get(),
            "clip_audio": self.clip_audio.get(), "clip_volume": self.clip_volume.get(),
            "logo": self.logo.get(), "logo_pos": self.logo_pos.get(),
            "logo_opacity": self.logo_opacity.get(),
            "title_on": self.title_on.get(), "title_sec": self.title_sec.get(),
            "title_text": self.video_title.get(),
            "intro": self.intro.get(), "outro": self.outro.get(),
            "sfx": self.sfx.get(), "sfx_volume": self.sfx_volume.get(),
            "crossfade": self.crossfade.get(), "transition": self.transition.get(),
            "color": self.color.get(), "vignette": self.vignette.get(),
            "grain": self.grain.get(), "bgm": self.bgm.get(),
            "bgm_volume": self.bgm_volume.get(), "duck": self.duck.get(),
            "kara_color": self.kara_color.get(),
            "sub_font": self.sub_font.get(), "sub_mode": self.sub_mode.get(),
            "sub_outline": self.sub_outline.get(),
        }

    def _job_cmd(self, job, preview=False):
        """Dựng lệnh gọi auto_edit.py cho 1 job (render đơn + hàng đợi + xem trước)."""
        cmd = script_cmd("auto_edit.py") + [
            "--images", job["images"], "--srt", job["srt"], "--out", job["out"]]
        if (job.get("voice") or "").strip():
            cmd += ["--voice", job["voice"]]
        if job.get("scenes") and os.path.isfile(job["scenes"]):
            cmd += ["--scenes", job["scenes"]]
        else:
            cmd += ["--seconds-per-image", str(job.get("secs", "8"))]
        if (job.get("aspect") or "16:9") == "9:16":   # job cũ không có key -> 16:9 như xưa
            cmd += ["--aspect", "9:16"]
        if job.get("clip_audio"):                      # giữ âm thanh gốc của clip
            try:
                cv = float(job.get("clip_volume", "0.25"))
            except (TypeError, ValueError):
                cv = 0.25
            cmd += ["--keep-clip-audio", "--clip-volume", f"{min(max(cv, 0.0), 1.0):g}"]
        lg = (job.get("logo") or "").strip()           # thương hiệu: logo + tiêu đề + i/o + sfx
        if lg and os.path.isfile(lg):
            cmd += ["--logo", lg, "--logo-pos", job.get("logo_pos") or "br",
                    "--logo-opacity", str(job.get("logo_opacity") or "0.85")]
        if job.get("title_on") and (job.get("title_text") or "").strip():
            cmd += ["--title-text", job["title_text"].strip(),
                    "--title-sec", str(job.get("title_sec") or "4")]
        for k, flag in (("intro", "--intro"), ("outro", "--outro")):
            p = (job.get(k) or "").strip()
            if p and os.path.isfile(p):
                cmd += [flag, p]
        sf = (job.get("sfx") or "").strip()
        if sf and os.path.isfile(sf):
            cmd += ["--sfx", sf, "--sfx-volume", str(job.get("sfx_volume") or "0.5")]
        if not job.get("kenburns", True):
            cmd += ["--no-kenburns"]
        if not job.get("subs", True):
            cmd += ["--no-subtitles"]
        else:
            kc = (job.get("kara_color") or "").strip()
            if kc:
                cmd += ["--karaoke-color", kc]
            sf = (job.get("sub_font") or "").strip()
            if sf and sf != "Arial Black":              # khác mặc định mới cần truyền
                cmd += ["--sub-font", sf]
            sm = (job.get("sub_mode") or "word").strip()
            if sm in ("line", "kara"):
                cmd += ["--sub-mode", sm]
            so = (job.get("sub_outline") or "").strip()
            if so and so.lower() not in ("#000000", "black"):
                cmd += ["--sub-outline-color", so]
        if job.get("crossfade", False):
            cmd += ["--transition", job.get("transition") or "fade"]
        if job.get("color") and job["color"] != "none":
            cmd += ["--color", job["color"]]
        if job.get("vignette"):
            cmd += ["--vignette"]
        if job.get("grain"):
            cmd += ["--grain"]
        bgm = (job.get("bgm") or "").strip()
        if bgm and (os.path.isfile(bgm) or os.path.isdir(bgm)):   # file đơn hoặc FOLDER playlist
            try:
                bv = float(job.get("bgm_volume", "0.18"))
            except (TypeError, ValueError):
                bv = 0.18
            cmd += ["--bgm", bgm, "--bgm-volume", f"{bv}"]
            if not job.get("duck", True):
                cmd += ["--no-duck"]
        if preview:
            cmd += ["--max-scenes", "3"]      # xem trước: chỉ vài cảnh đầu cho nhanh
        return cmd

    def add_to_queue(self):
        if not os.path.isfile(self.srt.get()):
            messagebox.showwarning(tr("Thiếu"), tr("Chưa chọn file SRT hợp lệ."))
            return
        if not os.path.isdir(self.images.get()):
            messagebox.showwarning(tr("Thiếu"), tr("Chưa chọn thư mục ảnh/clip."))
            return
        job = self._current_job()
        # CẢNH BÁO nếu bảng cảnh không khớp voice (dễ là dùng nhầm scenes video khác)
        warn = self._scenes_voice_mismatch(job.get("scenes", ""), job.get("voice", ""))
        if warn and not messagebox.askyesno("⚠️ Bảng cảnh không khớp", warn + "\n\nVẫn thêm?"):
            return
        # Lưu BẢN SAO scenes.csv ĐÃ CHỌN (snapshot) -> tránh bị ghi đè khi tạo prompt video khác
        sc = job.get("scenes", "")
        if sc and os.path.isfile(sc):
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

    def _scenes_voice_mismatch(self, scenes, voice):
        """Trả chuỗi cảnh báo nếu tổng thời lượng scenes lệch voice >10% (dễ là nhầm
        bảng cảnh video khác). Trả None nếu khớp / thiếu dữ liệu."""
        if not (scenes and os.path.isfile(scenes) and voice and os.path.isfile(voice)):
            return None
        try:
            import auto_edit as ae, csv
            rows = list(csv.DictReader(open(scenes, encoding="utf-8-sig")))
            tot = sum(float(r.get("dur", 0)) for r in rows)
            vd = ae.probe_duration(voice) or 0
            if vd and tot and abs(tot - vd) / vd > 0.10:
                return (f"Bảng cảnh: {len(rows)} cảnh = {tot:.0f}s ({tot/60:.1f}′)\n"
                        f"Voice    : {vd:.0f}s ({vd/60:.1f}′)\n\n"
                        f"Lệch {abs(tot-vd):.0f}s — có thể đang dùng NHẦM bảng cảnh của video khác!\n"
                        f"Nên chọn đúng scenes.csv của video này (ô '📋 File bảng cảnh').")
        except Exception:  # noqa
            pass
        return None

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

        # --- 📜 Lịch sử render (video đã render xong) ---
        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=10, pady=(8, 2))
        htop = ttk.Frame(parent)
        htop.pack(fill="x", padx=10, pady=(2, 2))
        ttk.Label(htop, text="📜 Lịch sử render", font=("", 10, "bold")).pack(side="left")
        ttk.Label(htop, foreground="#777", text="(các video đã render xong)").pack(side="left", padx=6)
        hmid = ttk.Frame(parent)
        hmid.pack(fill="both", expand=True, padx=10, pady=2)
        self.hlist = tk.Listbox(hmid, height=7)
        self.hlist.pack(side="left", fill="both", expand=True)
        self.hlist.bind("<Double-Button-1>", self._history_open)
        hsb = ttk.Scrollbar(hmid, command=self.hlist.yview)
        hsb.pack(side="right", fill="y")
        self.hlist["yscrollcommand"] = hsb.set
        hbar = ttk.Frame(parent)
        hbar.pack(fill="x", padx=10, pady=(2, 8))
        ttk.Button(hbar, text="📂 Mở thư mục video", command=self._history_open).pack(side="left", padx=2)
        ttk.Button(hbar, text="🧹 Xoá lịch sử", command=self._history_clear).pack(side="left", padx=2)
        ttk.Label(hbar, foreground="#888", text="(nháy đúp 1 dòng = mở thư mục video)").pack(side="left", padx=6)

        self._refresh_queue()
        self._refresh_history()

    def _add_history(self, out, ok):
        """Ghi 1 mục vào lịch sử render (mới nhất lên đầu, giữ tối đa 100 mục)."""
        import time as _t
        hist = self.cfg.setdefault("render_history", [])
        hist.insert(0, {"out": out, "time": _t.strftime("%Y-%m-%d %H:%M"), "ok": bool(ok)})
        del hist[100:]
        save_config(self.cfg)

    def _refresh_history(self):
        if not hasattr(self, "hlist"):
            return
        self.hlist.delete(0, "end")
        for h in self.cfg.get("render_history", []):
            icon = "✅" if h.get("ok") else "❌"
            self.hlist.insert("end", f"{icon} {h.get('time','')}   {os.path.basename(h.get('out','?'))}")
        if not self.cfg.get("render_history"):
            self.hlist.insert("end", "(chưa có video nào được render)")

    def _history_open(self, _e=None):
        hist = self.cfg.get("render_history", [])
        sel = self.hlist.curselection()
        idx = sel[0] if sel else 0
        if 0 <= idx < len(hist):
            d = os.path.dirname(hist[idx].get("out", "")) or HERE
            if os.path.isdir(d):
                os.startfile(d)

    def _history_clear(self):
        if self.cfg.get("render_history") and messagebox.askyesno(
                "Xoá lịch sử", "Xoá toàn bộ lịch sử render? (không xoá file video)"):
            self.cfg["render_history"] = []
            save_config(self.cfg)
            self._refresh_history()

    def _refresh_queue(self):
        self.qlist.delete(0, "end")
        for i, j in enumerate(self.cfg.get("queue", []), 1):
            out = os.path.basename(j.get("out", "?"))
            srt = os.path.basename(j.get("srt", "?"))
            imgs = os.path.basename((j.get("images", "?") or "").rstrip("/\\"))
            self.qlist.insert("end", f"{i}.  {out}   ←  {srt}   |  clip: {imgs}")
        n = len(self.cfg.get("queue", []))
        self.q_count.set(tr(f"{n} video trong hàng đợi"))

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
            messagebox.showinfo(tr("Hàng đợi trống"), tr("Chưa có video nào trong hàng đợi."))
            return
        # Kiểm clip hỏng cho toàn hàng đợi (#7)
        allbad = [(os.path.basename(j.get("out", "?")), self._broken_clips(j.get("images", "")))
                  for j in jobs]
        allbad = [(n, b) for n, b in allbad if b]
        if allbad:
            detail = "\n".join(f"  • {n}: {', '.join(b[:8])}" for n, b in allbad)
            if not messagebox.askyesno(
                    "⚠️ Clip hỏng trong hàng đợi",
                    f"Có clip hỏng (lỗi/1 frame) làm video hụt:\n\n{detail}\n\nVẫn render cả hàng đợi?"):
                return
        self.log.delete("1.0", "end")
        self._busy(True)
        self.rendering = True
        self.status.set(f"Đang render hàng đợi (0/{len(jobs)})...")

        def worker():
            ok_count, fail, done_outs = 0, [], []
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
                    self.render_procs.append(p)
                    for line in p.stdout:
                        self.q.put(("line", line))
                    p.wait()
                    if p.returncode == 0:
                        ok_count += 1
                        done_outs.append(job.get("out", ""))
                        self._add_history(job.get("out", ""), True)   # lưu lịch sử
                        self.q.put(("line", f"✅ Xong: {job.get('out')}\n"))
                    else:
                        fail.append(name)
                        self._add_history(job.get("out", ""), False)
                        self.q.put(("line", f"❌ Lỗi (mã {p.returncode}): {name}\n"))
                except Exception as e:  # noqa
                    fail.append(name)
                    self.q.put(("line", f"❌ Lỗi: {e}\n"))
            # Xóa các job ĐÃ render thành công khỏi hàng đợi (giữ lại job lỗi để thử lại)
            self.cfg["queue"] = [j for j in self.cfg.get("queue", [])
                                 if j.get("out", "") not in done_outs]
            save_config(self.cfg)
            msg = f"✅ Hàng đợi xong: {ok_count}/{len(jobs)} video"
            if fail:
                msg += f" ({len(fail)} lỗi giữ lại để thử lại: {', '.join(fail)})"
            self.q.put(("queue_finished", None))
            self.q.put(("done", msg))

        threading.Thread(target=worker, daemon=True).start()


def _cleanup_old_exe():
    """Dọn file .exe.old còn sót sau lần TỰ CẬP NHẬT (best-effort, không lỗi nếu thất bại)."""
    try:
        if _is_frozen():
            old = _self_exe() + ".old"
            if os.path.exists(old):
                os.remove(old)
    except Exception:  # noqa
        pass


def main():
    selftest = "--selftest" in sys.argv
    _cleanup_old_exe()
    # Nạp ngôn ngữ TRƯỚC license gate (hộp kích hoạt là thứ đầu tiên khách thấy)
    i18n.set_lang(load_config().get("lang") or i18n.detect_default())
    os.environ["AEV_LANG"] = i18n.get_lang()   # engine subprocess đọc để dịch log
    root = tk.Tk()
    if not selftest:
        try:
            import config
            license_on = bool(getattr(config, "LICENSE_ENABLED", False))
        except Exception:
            license_on = False
        if license_on:                        # bản BÁN: thay mật khẩu bằng kích hoạt LICENSE
            root.withdraw()
            if not license_gate(root):
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
    # Chẩn đoán: in nơi ĐANG lưu config.local.json + nội dung đọc được (KHÔNG in API key).
    if len(sys.argv) > 1 and sys.argv[1] == "--where-config":
        try:                                  # tên profile có dấu -> tránh lỗi charmap cp1252
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa
            pass
        p = _config_path()
        print("config_path :", p)
        print("exists      :", os.path.exists(p))
        try:
            c = load_config()
            print("profiles    :", list(c.get("profiles", {}).keys()))
            print("active      :", c.get("active_profile"))
        except Exception as e:  # noqa
            print("load_err    :", e)
        sys.exit(0)
    # Bản .exe tự gọi lại CHÍNH NÓ để chạy engine (vì không còn python + .py riêng).
    # Xem script_cmd(): khi frozen, render/sleep gọi [exe, --run-auto-edit/--run-sleep-video, ...].
    if len(sys.argv) > 1 and sys.argv[1] in ("--run-auto-edit", "--run-sleep-video"):
        _which = sys.argv.pop(1)              # bỏ cờ route -> argparse của engine đọc đúng
        if _which == "--run-auto-edit":
            import auto_edit
            sys.exit(auto_edit.main())
        import sleep_video
        sys.exit(sleep_video.main())
    try:
        main()
    except Exception as e:  # noqa
        try:
            messagebox.showerror("Không mở được app", str(e))
        except Exception:
            print("Loi:", e)
        raise
