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
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
CONFIG_PATH = os.path.join(HERE, "config.local.json")

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
        "gemini_key": "",
        "model": "gemini-3.5-flash",
        "profiles": {"Người que": DEFAULT_STYLE},
        "active_profile": "Người que",
        "prompt_mode": "video",
    }


def load_config():
    cfg = default_config()
    try:
        with open(CONFIG_PATH, encoding="utf-8-sig") as f:
            data = json.load(f)
        cfg.update({k: data[k] for k in cfg if k in data})
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


def dflt(*parts):
    return os.path.join(HERE, *parts)


class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.q = queue.Queue()
        root.title("Auto Edit Video 🎬")
        root.geometry("780x680")
        root.minsize(700, 600)

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=6, pady=6)
        self.tab_make = ttk.Frame(nb)
        self.tab_set = ttk.Frame(nb)
        nb.add(self.tab_make, text="  🎬 Làm video  ")
        nb.add(self.tab_set, text="  ⚙️ Cài đặt  ")

        self._build_make(self.tab_make)
        self._build_settings(self.tab_set)

        # Log + status (dùng chung)
        box = ttk.LabelFrame(root, text="Nhật ký")
        box.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        self.log = tk.Text(box, height=9, wrap="word", bg="#1e1e1e",
                           fg="#d4d4d4", insertbackground="white")
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(box, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log["yscrollcommand"] = sb.set

        self.status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(root, textvariable=self.status, anchor="w",
                  relief="sunken").pack(fill="x", side="bottom")
        self.root.after(100, self._drain)

    # ============================ TAB LÀM VIDEO ============================
    def _build_make(self, parent):
        f1 = ttk.LabelFrame(parent, text="1. Nguyên liệu")
        f1.pack(fill="x", padx=8, pady=6)

        self.srt = tk.StringVar(value=dflt("input", "subtitle.srt"))
        self.images = tk.StringVar(value=dflt("input", "images"))
        self.voice = tk.StringVar(value=self._auto_voice())
        self.out = tk.StringVar(value=dflt("output", "final.mp4"))

        self._row(f1, "File PHỤ ĐỀ (SRT):", self.srt, lambda: self._pick_file(
            self.srt, [("SRT", "*.srt"), ("Tất cả", "*.*")]))

        # Style profile chooser
        sf = ttk.Frame(f1)
        sf.pack(fill="x", padx=8, pady=3)
        ttk.Label(sf, text="Style Profile:", width=18).pack(side="left")
        self.profile_var = tk.StringVar(value=self.cfg.get("active_profile", ""))
        self.cmb_profile = ttk.Combobox(sf, textvariable=self.profile_var,
                                        values=list(self.cfg["profiles"].keys()),
                                        state="readonly")
        self.cmb_profile.pack(side="left", fill="x", expand=True)
        self.cmb_profile.bind("<<ComboboxSelected>>", self._on_profile_pick)
        ttk.Label(sf, text="(quản lý ở tab Cài đặt)", foreground="#888").pack(
            side="left", padx=6)

        self._row(f1, "Thư mục ẢNH/CLIP:", self.images, self._pick_dir)
        self._row(f1, "File VOICEOVER:", self.voice, lambda: self._pick_file(
            self.voice, [("Audio", "*.mp3 *.wav *.m4a *.aac"), ("Tất cả", "*.*")]))
        self._row(f1, "Xuất ra MP4:", self.out, self._pick_save)

        f2 = ttk.LabelFrame(parent, text="2. Tùy chọn ghép")
        f2.pack(fill="x", padx=8, pady=6)
        line = ttk.Frame(f2)
        line.pack(fill="x", padx=10, pady=6)
        ttk.Label(line, text="Số giây mỗi cảnh:").pack(side="left")
        self.secs = tk.StringVar(value="8")
        ttk.Spinbox(line, from_=2, to=30, width=5, textvariable=self.secs).pack(
            side="left", padx=6)
        self.kenburns = tk.BooleanVar(value=True)
        self.subs = tk.BooleanVar(value=True)
        ttk.Checkbutton(line, text="Ken Burns (zoom ảnh tĩnh)",
                        variable=self.kenburns).pack(side="left", padx=12)
        ttk.Checkbutton(line, text="Chèn phụ đề", variable=self.subs).pack(side="left")

        line2 = ttk.Frame(f2)
        line2.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(line2, text="Loại prompt AI:").pack(side="left")
        self.prompt_mode = tk.StringVar(value=self.cfg.get("prompt_mode", "video"))
        ttk.Radiobutton(line2, text="🎬 Video (có chuyển động)", variable=self.prompt_mode,
                        value="video", command=self._save_mode).pack(side="left", padx=8)
        ttk.Radiobutton(line2, text="🖼️ Ảnh tĩnh", variable=self.prompt_mode,
                        value="image", command=self._save_mode).pack(side="left", padx=8)

        # Buttons
        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=8, pady=8)
        self.btn_prompt = ttk.Button(bar, text="🤖  TẠO PROMPT (AI)",
                                     command=self.run_make_prompts)
        self.btn_prompt.pack(side="left", padx=4)
        self.btn_render = ttk.Button(bar, text="▶  RENDER VIDEO",
                                     command=self.run_render)
        self.btn_render.pack(side="left", padx=4)
        ttk.Button(bar, text="📂 Mở thư mục xuất", command=self.open_out).pack(
            side="right", padx=4)

        hint = ("Quy trình: ①  bấm 'TẠO PROMPT' → ra veo_prompts.txt   →   "
                "② tạo clip Veo, đặt tên 01,02... bỏ vào thư mục ảnh/clip   →   "
                "③ bấm 'RENDER VIDEO'.")
        ttk.Label(parent, text=hint, wraplength=720, foreground="#555").pack(
            fill="x", padx=12, pady=(0, 4))

    # ============================ TAB CÀI ĐẶT ============================
    def _build_settings(self, parent):
        # --- API key ---
        fa = ttk.LabelFrame(parent, text="Gemini API")
        fa.pack(fill="x", padx=8, pady=6)
        r = ttk.Frame(fa)
        r.pack(fill="x", padx=8, pady=6)
        ttk.Label(r, text="API Key:", width=10).pack(side="left")
        self.key_var = tk.StringVar(value=self.cfg.get("gemini_key", ""))
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
        ttk.Label(r2, text="Lấy key MIỄN PHÍ tại aistudio.google.com",
                  foreground="#888").pack(side="left", padx=8)

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

    def _save_key(self):
        self.cfg["gemini_key"] = self.key_var.get().strip()
        save_config(self.cfg)
        self.status.set("Đã lưu API key.")

    def _save_mode(self):
        self.cfg["prompt_mode"] = self.prompt_mode.get()
        save_config(self.cfg)

    def check_api(self):
        self._save_key()
        key = self.cfg["gemini_key"]
        self.status.set("Đang kiểm tra kết nối Gemini...")
        self._log("• Kiểm tra kết nối Gemini...\n")

        def worker():
            try:
                import ai_prompts
                ok, msg, model = ai_prompts.check_connection(key, self.cfg.get("model"))
                if ok and model:
                    self.cfg["model"] = model
                    save_config(self.cfg)
            except Exception as e:  # noqa
                ok, msg = False, str(e)
            self.q.put(("apiresult", (ok, msg)))

        threading.Thread(target=worker, daemon=True).start()

    # ---------- log/queue ----------
    def _busy(self, on):
        st = "disabled" if on else "normal"
        self.btn_prompt["state"] = st
        self.btn_render["state"] = st

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
                        "Kiểm tra Gemini", msg)
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
        key = self.cfg.get("gemini_key", "")
        if not key.strip():
            messagebox.showwarning("Thiếu API key",
                                   "Vào tab Cài đặt nhập Gemini API key trước nhé.")
            return
        if not style.strip():
            messagebox.showwarning("Thiếu style",
                                   "Style profile đang trống. Vào tab Cài đặt để dán nội dung.")
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
                mode = self.prompt_mode.get()
                loai = "ẢNH tĩnh" if mode == "image" else "VIDEO"
                self.q.put(("line", f"• {len(segs)} đoạn → {len(scenes)} cảnh. "
                                    f"Gọi Gemini viết prompt {loai}...\n"))

                def prog(done, total):
                    self.q.put(("line", f"   ...đã viết {done}/{total} prompt\n"))

                prompts = ai_prompts.generate_prompts(
                    texts, style, key, model=self.cfg.get("model"),
                    progress=prog, mode=mode)

                # Ghi veo_prompts.txt
                vp = dflt("veo_prompts.txt")
                with open(vp, "w", encoding="utf-8") as f:
                    f.write("\n".join(p.replace("\n", " ").strip() for p in prompts) + "\n")

                # Ghi scenes.csv (kèm prompt)
                import csv
                sc = dflt("scenes.csv")
                with open(sc, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f)
                    w.writerow(["scene", "start", "end", "dur", "veo_sec", "speed", "text", "prompt"])
                    for i, s in enumerate(scenes):
                        dur = round(s["end"] - s["start"], 2)
                        veo, _pct, speed = bs.nearest_veo(dur)
                        pr = prompts[i] if i < len(prompts) else ""
                        w.writerow([i + 1, bs.fmt(s["start"]), bs.fmt(s["end"]),
                                    dur, veo, speed, texts[i], pr])

                self.q.put(("line", f"\n• Đã ghi {len(prompts)} prompt vào:\n"
                                    f"   {vp}\n   {sc}\n"))
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
        scenes_csv = dflt("scenes.csv")
        cmd = [PY, dflt("auto_edit.py"),
               "--images", self.images.get(), "--srt", self.srt.get(),
               "--out", self.out.get()]
        if self.voice.get().strip():
            cmd += ["--voice", self.voice.get()]
        if os.path.isfile(scenes_csv):
            cmd += ["--scenes", scenes_csv]
        else:
            cmd += ["--seconds-per-image", self.secs.get()]
        if not self.kenburns.get():
            cmd += ["--no-kenburns"]
        if not self.subs.get():
            cmd += ["--no-subtitles"]

        self.log.delete("1.0", "end")
        self._log("$ render...\n\n")
        self._busy(True)
        self.status.set("Đang render...")

        def worker():
            try:
                env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
                p = subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True,
                                     encoding="utf-8", errors="replace", env=env)
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


def main():
    selftest = "--selftest" in sys.argv
    root = tk.Tk()
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
