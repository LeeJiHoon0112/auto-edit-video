# -*- coding: utf-8 -*-
"""PREFLIGHT — chạy TRƯỚC MỖI LẦN build/release: chặn các LỚP lỗi đã từng ship.

    python preflight.py        (exit 0 = PASS, khác 0 = có lỗi, CẤM build)

Kiểm tra:
 1. Cú pháp (py_compile) toàn bộ file .py.
 2. HÀM/METHOD TRÙNG TÊN (AST, cả module lẫn trong class) — lớp lỗi nút "Chọn..." câm 1.1.1.
 3. PERSISTENCE: mọi key GHI vào cfg[...] phải khai trong default_config —
    lớp lỗi "lưu xong mở lại mất" (lang/sub_font... 1.0.9-1.1.0).
 4. GUI smoke HEADLESS trên CONFIG TẠM (không đụng config thật của Boss):
    dựng App, đổi EN quét sót tiếng Việt, đổi lại VI, round-trip 1 key cấu hình.
 5. i18n: chuỗi tiếng Việt bọc tr("...") phải có trong từ điển EN hoặc khớp RULES.
 6. Engine dry-run nhanh (auto_edit --dry-run trên SRT+ảnh sinh tạm).
"""
import ast
import glob
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
FILES = ["app.py", "auto_edit.py", "sleep_video.py", "ai_prompts.py",
         "build_scenes.py", "i18n.py", "license_client.py", "config.py"]
FAILS, WARNS = [], []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILS.append(f"{name}: {detail}")


# ---------- 0) Bản BÁN phải bật license ----------
# (em build release bằng lệnh Nuitka trực tiếp, không qua build_release.bat -> chốt ở đây
#  luôn; quên bật lại sau khi dev = giao khách bản KHÔNG đòi key — gotcha #8)
print("0) License cho bản bán:")
import config  # noqa
check("config.LICENSE_ENABLED = True", bool(getattr(config, "LICENSE_ENABLED", False)),
      "đang False (chế độ dev) — đổi lại True rồi mới được build bản giao khách")

# ---------- 1) Cú pháp ----------
print("1) Cú pháp:")
for f in FILES:
    try:
        py_compile.compile(f, doraise=True)
        check(f, True)
    except Exception as e:
        check(f, False, str(e)[:120])

# ---------- 2) Trùng tên hàm/method ----------
print("2) Hàm/method trùng tên:")
for f in FILES:
    tree = ast.parse(open(f, encoding="utf-8").read())
    dups = []

    def scan(body, scope):
        seen = {}
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in seen:
                    dups.append(f"{scope}{node.name} (dòng {seen[node.name]} và {node.lineno})")
                seen[node.name] = node.lineno
            if isinstance(node, ast.ClassDef):
                scan(node.body, f"{node.name}.")
    scan(tree.body, "")
    check(f, not dups, "; ".join(dups))

# ---------- 3) Persistence: key ghi vào cfg phải có trong default_config ----------
print("3) Persistence (key cfg phải khai trong default_config):")
src = open("app.py", encoding="utf-8").read()
import app  # noqa  (sau khi compile OK)
defaults = set(app.default_config().keys())
written = set(re.findall(r"""(?:self\.)?cfg\[\s*["']([^"']+)["']\s*\]\s*=""", src))
missing = sorted(written - defaults)
check("app.py", not missing,
      f"key GHI nhưng THIẾU trong default_config (sẽ mất khi mở lại): {missing}")

# ---------- 4) GUI smoke headless trên CONFIG TẠM ----------
print("4) GUI smoke (config tạm, không đụng config thật):")
tmpdir = tempfile.mkdtemp(prefix="preflight_")
try:
    real_cfg = os.path.join(HERE, "config.local.json")
    tmp_cfg = os.path.join(tmpdir, "config.local.json")
    if os.path.isfile(real_cfg):
        shutil.copy(real_cfg, tmp_cfg)
    app._config_path = lambda: tmp_cfg          # mọi save trong test chỉ chạm bản TẠM

    import re as _re
    import tkinter as tk
    VN = _re.compile(r"[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợ"
                     r"ùúủũụưứừửữựỳýỷỹỵđ]", _re.IGNORECASE)
    r = tk.Tk()
    a = app.App(r)

    def dump():
        out = []
        def walk(w):
            for c in w.winfo_children():
                try:
                    t = c.cget("text")
                    if isinstance(t, str) and t.strip():
                        out.append(t)
                except Exception:
                    pass
                walk(c)
        walk(r)
        return out

    a.lang_var.set("English"); a._on_lang_pick()
    left = [t for t in dump() if VN.search(t) and "Language" not in t]
    check("EN không sót tiếng Việt", not left, "; ".join(x[:40] for x in left[:5]))
    a.lang_var.set("Tiếng Việt"); a._on_lang_pick()
    check("đổi lại VI", any("Tạo Prompt" in t for t in dump()))
    a.sub_font.set("PreflightTestFont"); a._save_subopts()
    r.destroy()
    cfg2 = app.load_config.__wrapped__() if hasattr(app.load_config, "__wrapped__") else None
    saved = json.load(open(tmp_cfg, encoding="utf-8-sig"))
    check("round-trip cấu hình (save→load)",
          saved.get("sub_font") == "PreflightTestFont"
          and "sub_font" in defaults, f"sub_font={saved.get('sub_font')}")
    check("config THẬT không bị test chạm",
          not os.path.isfile(real_cfg)
          or json.load(open(real_cfg, encoding="utf-8-sig")).get("sub_font")
          != "PreflightTestFont")
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)

# ---------- 5) i18n: chuỗi Việt trong tr(...) phải dịch được ----------
print("5) i18n coverage cho tr(...):")
import i18n
i18n.set_lang("en")
VNchr = re.compile(r"[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]",
                   re.IGNORECASE)
untranslated = []
for f in ("app.py", "auto_edit.py", "sleep_video.py"):
    tree = ast.parse(open(f, encoding="utf-8").read())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "tr" and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            s = node.args[0].value
            if VNchr.search(s) and i18n.tr(s) == s:
                untranslated.append(f"{f}:{node.lineno} {s[:45]}")
if untranslated:
    WARNS.append(f"{len(untranslated)} chuỗi tr() chưa có bản dịch EN")
    for u in untranslated[:6]:
        print(f"  [WARN] {u}")
check("tr() literal có bản dịch", True,
      f"{len(untranslated)} cảnh báo (WARN, không chặn)" if untranslated else "đủ")

# ---------- 6) Engine dry-run ----------
print("6) Engine dry-run:")
td = tempfile.mkdtemp(prefix="preflight_eng_")
try:
    open(os.path.join(td, "t.srt"), "w", encoding="utf-8").write(
        "1\n00:00:00,000 --> 00:00:02,000\nxin chao\n\n")
    img_dir = os.path.join(td, "img"); os.makedirs(img_dir)
    import auto_edit as ae
    subprocess.run([ae.FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                    "-i", "color=c=black:size=640x360", "-frames:v", "1",
                    os.path.join(img_dir, "01.jpg")], check=True)
    p = subprocess.run([sys.executable, "auto_edit.py", "--images", img_dir,
                        "--srt", os.path.join(td, "t.srt"),
                        "--out", os.path.join(td, "o.mp4"),
                        "--seconds-per-image", "2", "--dry-run"],
                       capture_output=True, text=True, timeout=120,
                       encoding="utf-8", errors="replace")
    check("auto_edit --dry-run", p.returncode == 0, (p.stderr or "")[:120])
finally:
    shutil.rmtree(td, ignore_errors=True)

# ---------- Tổng kết ----------
print()
if FAILS:
    print(f"❌ PREFLIGHT FAIL ({len(FAILS)} lỗi) — CẤM build/release cho tới khi sửa xong:")
    for x in FAILS:
        print("   -", x)
    sys.exit(1)
print(f"✅ PREFLIGHT PASS" + (f" ({len(WARNS)} cảnh báo)" if WARNS else "") +
      " — được phép build/release.")
