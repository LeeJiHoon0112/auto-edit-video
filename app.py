#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto Edit Video — Giao diện (GUI) cho tool ghép ảnh/video theo SRT + voice -> MP4.

Chạy: double-click "Auto Edit Video.bat"  hoặc  python app.py
Không cần cài thư viện ngoài (Tkinter có sẵn trong Python).
"""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def dflt(*parts):
    return os.path.join(HERE, *parts)


class App:
    def __init__(self, root):
        self.root = root
        self.proc = None
        self.q = queue.Queue()
        root.title("Auto Edit Video 🎬")
        root.geometry("760x640")
        root.minsize(680, 560)

        pad = {"padx": 8, "pady": 4}

        # ---- Khu vực chọn nguyên liệu ----
        box = ttk.LabelFrame(root, text="1. Nguyên liệu")
        box.pack(fill="x", **pad)

        self.images = tk.StringVar(value=dflt("input", "images"))
        self.voice = tk.StringVar(value=self._auto_voice())
        self.srt = tk.StringVar(value=dflt("input", "subtitle.srt"))
        self.out = tk.StringVar(value=dflt("output", "final.mp4"))

        self._row(box, "Thư mục ẢNH/VIDEO:", self.images, self._pick_dir)
        self._row(box, "File VOICEOVER:", self.voice, lambda: self._pick_file(
            self.voice, [("Audio", "*.mp3 *.wav *.m4a *.aac"), ("Tất cả", "*.*")]))
        self._row(box, "File PHỤ ĐỀ (SRT):", self.srt, lambda: self._pick_file(
            self.srt, [("SRT", "*.srt"), ("Tất cả", "*.*")]))
        self._row(box, "Xuất ra MP4:", self.out, self._pick_save)

        # ---- Khu vực chế độ ----
        box2 = ttk.LabelFrame(root, text="2. Cách ghép ảnh")
        box2.pack(fill="x", **pad)

        self.mode = tk.StringVar(value="scenes")
        modes = [
            ("scenes", "Khớp lời (theo bảng cảnh scenes.csv) — nên dùng"),
            ("spi", "Đổi ảnh mỗi N giây (ảnh nền chung)"),
            ("spread", "Rải đều toàn bộ ảnh theo thời lượng"),
            ("srt", "1 ảnh / 1 đoạn phụ đề"),
        ]
        for val, label in modes:
            ttk.Radiobutton(box2, text=label, variable=self.mode,
                            value=val).pack(anchor="w", padx=10)

        line = ttk.Frame(box2)
        line.pack(fill="x", padx=10, pady=6)
        ttk.Label(line, text="Số giây mỗi cảnh/ảnh:").pack(side="left")
        self.secs = tk.StringVar(value="8")
        ttk.Spinbox(line, from_=2, to=30, width=5, textvariable=self.secs).pack(
            side="left", padx=6)

        self.kenburns = tk.BooleanVar(value=True)
        self.subs = tk.BooleanVar(value=True)
        ttk.Checkbutton(line, text="Hiệu ứng Ken Burns (zoom)",
                        variable=self.kenburns).pack(side="left", padx=12)
        ttk.Checkbutton(line, text="Chèn phụ đề",
                        variable=self.subs).pack(side="left")

        # ---- Nút hành động ----
        bar = ttk.Frame(root)
        bar.pack(fill="x", **pad)
        self.btn_scene = ttk.Button(bar, text="① Tạo bảng cảnh",
                                    command=self.run_scenes)
        self.btn_scene.pack(side="left", padx=4)
        self.btn_prev = ttk.Button(bar, text="② Xem trước (nhanh)",
                                   command=lambda: self.run_render(preview=True))
        self.btn_prev.pack(side="left", padx=4)
        self.btn_render = ttk.Button(bar, text="③ RENDER VIDEO ▶",
                                     command=lambda: self.run_render(preview=False))
        self.btn_render.pack(side="left", padx=4)
        ttk.Button(bar, text="📂 Mở thư mục xuất",
                   command=self.open_out).pack(side="right", padx=4)

        # ---- Log ----
        box3 = ttk.LabelFrame(root, text="Nhật ký")
        box3.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(box3, wrap="word", height=12, bg="#1e1e1e",
                           fg="#d4d4d4", insertbackground="white")
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(box3, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log["yscrollcommand"] = sb.set

        self.status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(root, textvariable=self.status, anchor="w",
                  relief="sunken").pack(fill="x", side="bottom")

        self.root.after(100, self._drain)

    # ---------- tiện ích UI ----------
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

    # ---------- chạy lệnh ----------
    def _busy(self, on):
        state = "disabled" if on else "normal"
        for b in (self.btn_scene, self.btn_prev, self.btn_render):
            b["state"] = state

    def _write(self, txt):
        self.log.insert("end", txt)
        self.log.see("end")

    def _drain(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "line":
                    self._write(data)
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

    def _spawn(self, cmd, ok_msg):
        self.log.delete("1.0", "end")
        self._write("$ " + " ".join(f'"{c}"' if " " in c else c for c in cmd) + "\n\n")
        self._busy(True)
        self.status.set("Đang chạy...")

        def worker():
            try:
                env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
                p = subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True,
                                     encoding="utf-8", errors="replace", env=env)
                self.proc = p
                for line in p.stdout:
                    self.q.put(("line", line))
                p.wait()
                if p.returncode == 0:
                    self.q.put(("done", ok_msg))
                else:
                    self.q.put(("done", f"Thất bại (mã {p.returncode}). Xem nhật ký."))
            except Exception as e:  # noqa
                self.q.put(("done", f"Lỗi: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def _check_inputs(self):
        if not os.path.isfile(self.srt.get()):
            messagebox.showwarning("Thiếu", "Chưa chọn file SRT hợp lệ.")
            return False
        if not os.path.isdir(self.images.get()):
            messagebox.showwarning("Thiếu", "Chưa chọn thư mục ảnh/video.")
            return False
        return True

    def run_scenes(self):
        if not os.path.isfile(self.srt.get()):
            messagebox.showwarning("Thiếu", "Chưa chọn file SRT.")
            return
        cmd = [PY, dflt("build_scenes.py"), "--srt", self.srt.get(),
               "--target", self.secs.get(), "--out", dflt("scenes.csv")]
        self._spawn(cmd, "✅ Đã tạo bảng cảnh: scenes.csv")

    def run_render(self, preview):
        if not self._check_inputs():
            return
        cmd = [PY, dflt("auto_edit.py"),
               "--images", self.images.get(),
               "--srt", self.srt.get(),
               "--out", self.out.get()]
        if self.voice.get().strip():
            cmd += ["--voice", self.voice.get()]

        m = self.mode.get()
        if m == "scenes":
            sc = dflt("scenes.csv")
            if not os.path.isfile(sc):
                messagebox.showwarning(
                    "Thiếu bảng cảnh",
                    "Chưa có scenes.csv. Bấm '① Tạo bảng cảnh' trước nhé.")
                return
            cmd += ["--scenes", sc]
        elif m == "spi":
            cmd += ["--seconds-per-image", self.secs.get()]
        else:
            cmd += ["--image-mode", m]

        if not self.kenburns.get():
            cmd += ["--no-kenburns"]
        if not self.subs.get():
            cmd += ["--no-subtitles"]
        if preview:
            cmd += ["--dry-run"]

        msg = "✅ Xem trước xong (chưa render)." if preview \
            else f"✅ Render xong: {self.out.get()}"
        self._spawn(cmd, msg)


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
            print("Lỗi:", e)
        raise
