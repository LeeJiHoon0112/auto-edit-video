#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto Edit Video — tự động ghép ảnh khớp phụ đề SRT + voiceover -> MP4 (FFmpeg)

Quy ước input (mặc định):
    input/images/      ảnh theo thứ tự: 01.png, 02.png, ... (1 ảnh <-> 1 đoạn SRT)
    input/subtitle.srt phụ đề có timestamp
    input/voice.mp3    voiceover (hoặc .wav/.m4a)
    output/final.mp4   kết quả

Cách chạy:
    python auto_edit.py
    python auto_edit.py --images input/images --srt input/subtitle.srt --voice input/voice.mp3 --out output/final.mp4
    python auto_edit.py --no-kenburns        # tắt zoom Ken Burns
    python auto_edit.py --no-subtitles       # không burn phụ đề vào video

Không cần cài thư viện Python ngoài — chỉ dùng FFmpeg + thư viện chuẩn.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor

# Ép stdout/stderr sang UTF-8 để in được tiếng Việt trên console Windows (cp1252)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# ----------------------------------------------------------------------------
# Cấu hình mặc định (Boss có thể chỉnh)
# ----------------------------------------------------------------------------
WIDTH = 1920
HEIGHT = 1080
FPS = 30
FADE = 0.4               # thời gian fade in/out mỗi cảnh (giây)
KENBURNS_AMOUNT = 0.16   # mức zoom Ken Burns (0.16 = phóng to thêm 16%)
KENBURNS_SS = 1.5        # phóng to nội bộ khử rung zoompan rồi thu về 1080p (1.0=tắt, 2.0=mượt nhất/chậm)
IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm")
AUDIO_NAMES = ("voice.mp3", "voice.wav", "voice.m4a", "voiceover.mp3", "voiceover.wav")

SRC_MAX = 6000          # ảnh nguồn lớn hơn cạnh này -> TỰ thu nhỏ (chống TREO khi decode + nhanh hơn)
SCENE_TIMEOUT = 600     # 1 cảnh render quá N giây -> coi như treo: kill + báo rõ cảnh nào (không đứng vô tận)

# Các kiểu chuyển cảnh (transition) của FFmpeg xfade — áp cho chuỗi ẢNH TĨNH liên tiếp.
# "none" = cắt thẳng (không hiệu ứng). Tất cả đều có sẵn trong FFmpeg, không cần gì thêm.
TRANSITIONS = ["none", "fade", "fadeblack", "fadewhite", "dissolve",
               "slideleft", "slideright", "slideup", "slidedown",
               "wipeleft", "wiperight", "wipeup", "wipedown",
               "smoothleft", "smoothright", "smoothup", "smoothdown",
               "circleopen", "circleclose", "radial", "pixelize",
               "zoomin", "diagtl", "diagbr"]

# Phụ đề: tạo file ASS có PlayResX/Y = đúng kích thước video -> mọi giá trị tính bằng
# PIXEL THẬT (không bị libass scale theo thang 288 gây phụ đề trôi lên giữa màn hình).
# Kiểu "quân sự/tài liệu": IN HOA, chữ trắng to đậm khối, viền đen DÀY + bóng.
SUB_FONT = "Arial Black"   # font đậm khối; nếu máy không có sẽ tự về Arial
SUB_SIZE = 52              # cỡ chữ (pixel thật trên video 1080p)
SUB_OUTLINE = 4            # độ dày viền đen (px)
SUB_SHADOW = 2             # độ đổ bóng (px)
SUB_MARGIN_V = 70          # khoảng cách từ ĐÁY lên (px) — số NHỎ = sát đáy hơn
SUB_UPPERCASE = True       # IN HOA toàn bộ phụ đề (False = giữ hoa/thường)


def _ass_time(t):
    """Giây -> 'H:MM:SS.cc' (centisecond) cho file ASS."""
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{int(s):02d}.{int(round((s - int(s)) * 100)):02d}"


def _write_ass(srt_path, ass_path, width, height):
    """Chuyển SRT -> ASS với PlayResX/Y = kích thước video (pixel thật).
    Phụ đề canh GIỮA-DƯỚI, IN HOA (nếu bật), chữ trắng viền đen dày + bóng."""
    segs = parse_srt(srt_path)
    bold = -1
    style = (f"Style: Default,{SUB_FONT},{SUB_SIZE},"
             f"&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
             f"{bold},0,0,0,100,100,0,0,1,{SUB_OUTLINE},{SUB_SHADOW},"
             f"2,60,60,{SUB_MARGIN_V},1")
    head = (
        "[Script Info]\nScriptType: v4.00+\nWrapStyle: 0\n"
        f"PlayResX: {width}\nPlayResY: {height}\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n" + style + "\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )
    lines = [head]
    for s in segs:
        txt = " ".join(s["text"].split())            # gộp về 1 dòng, bỏ xuống dòng
        if SUB_UPPERCASE:
            txt = txt.upper()
        lines.append(f"Dialogue: 0,{_ass_time(s['start'])},{_ass_time(s['end'])},"
                     f"Default,,0,0,0,,{txt}\n")
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write("".join(lines))


# ----------------------------------------------------------------------------
# Tìm FFmpeg / FFprobe (PATH hoặc thư mục cài WinGet)
# ----------------------------------------------------------------------------
def find_tool(name):
    p = shutil.which(name)
    if p:
        return p
    # Dò trong thư mục WinGet (PATH có thể chưa refresh sau khi cài)
    roots = [
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"),
        os.path.expandvars(r"%PROGRAMFILES%\ffmpeg"),
        r"C:\ffmpeg",
    ]
    exe = name + (".exe" if os.name == "nt" else "")
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            if exe in files:
                return os.path.join(dirpath, exe)
    return None


FFMPEG = find_tool("ffmpeg")
FFPROBE = find_tool("ffprobe")


def run(cmd, cwd=None, timeout=None):
    """Chạy lệnh, in lỗi gọn nếu fail. Ẩn cửa sổ console FFmpeg trên Windows.
    timeout (giây): quá hạn -> kill + báo lỗi (chống TREO vô tận khi gặp ảnh khổng lồ/lỗi)."""
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        res = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, encoding="utf-8",
                             errors="replace", creationflags=flags, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SystemExit(f"QUÁ {timeout}s chưa xong (treo?) — {' '.join(str(c) for c in cmd[:3])} ...")
    if res.returncode != 0:
        sys.stderr.write("\n[FFmpeg lỗi]\n" + (res.stderr or "")[-1500:] + "\n")
        raise SystemExit(f"Lệnh thất bại: {' '.join(str(c) for c in cmd[:3])} ...")
    return res


# ----------------------------------------------------------------------------
# Parse SRT
# ----------------------------------------------------------------------------
def srt_time_to_sec(t):
    # 00:00:01,500 -> 1.5
    h, m, rest = t.split(":")
    s, ms = rest.replace(".", ",").split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_srt(path):
    """Trả về list [{'start','end','text'}] theo thứ tự thời gian."""
    with open(path, "r", encoding="utf-8-sig") as f:
        raw = f.read()
    raw = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    blocks = re.split(r"\n\s*\n", raw)
    time_re = re.compile(
        r"(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})"
    )
    segs = []
    for b in blocks:
        m = time_re.search(b)
        if not m:
            continue
        lines = b.split("\n")
        # bỏ dòng số thứ tự và dòng timestamp -> còn lại là text
        text_lines = [ln for ln in lines if not time_re.search(ln)
                      and not ln.strip().isdigit()]
        text = " ".join(ln.strip() for ln in text_lines).strip()
        segs.append({
            "start": srt_time_to_sec(m.group(1)),
            "end": srt_time_to_sec(m.group(2)),
            "text": text,
        })
    segs.sort(key=lambda s: s["start"])
    return segs


# ----------------------------------------------------------------------------
# Thu thập ảnh / video (sort tự nhiên: 2 trước 10)
# ----------------------------------------------------------------------------
def natural_key(s):
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", s)]


def collect_media(folder):
    if not os.path.isdir(folder):
        raise SystemExit(f"Không thấy thư mục ảnh: {folder}")
    files = [f for f in os.listdir(folder)
             if f.lower().endswith(IMG_EXTS + VIDEO_EXTS)]
    files.sort(key=natural_key)
    return [os.path.join(folder, f) for f in files]


def find_voice(input_dir, explicit):
    if explicit:
        if not os.path.isfile(explicit):
            raise SystemExit(f"Không thấy file voice: {explicit}")
        return explicit
    for name in AUDIO_NAMES:
        p = os.path.join(input_dir, name)
        if os.path.isfile(p):
            return p
    # bất kỳ file audio nào trong input/
    for f in os.listdir(input_dir):
        if f.lower().endswith((".mp3", ".wav", ".m4a", ".aac")):
            return os.path.join(input_dir, f)
    return None


def probe_duration(path):
    if not FFPROBE:
        return None
    res = run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", path])
    try:
        return float(res.stdout.strip())
    except ValueError:
        return None


def probe_fps(path):
    """FPS thật của 1 clip video (avg_frame_rate). Veo thường 24. None nếu không đọc được."""
    if not FFPROBE:
        return None
    res = run([FFPROBE, "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=avg_frame_rate",
               "-of", "default=noprint_wrappers=1:nokey=1", path])
    s = (res.stdout or "").strip()
    try:
        if "/" in s:
            a, b = s.split("/")
            return float(a) / float(b) if float(b) else None
        return float(s)
    except (ValueError, ZeroDivisionError):
        return None


def color_grade_filter(name):
    """Trả chuỗi filter FFmpeg cho 'màu phim' theo preset, hoặc None nếu 'none'."""
    presets = {
        "cinematic": ("eq=contrast=1.08:saturation=1.10,"
                      "colorbalance=rs=0.03:rm=0.02:rh=0.05:bs=-0.04:bm=-0.03:bh=-0.05"),
        "cold": ("eq=contrast=1.10:saturation=0.88,"
                 "colorbalance=bs=0.06:bm=0.04:bh=0.05:rs=-0.03:rh=-0.03"),
        "warm": ("eq=contrast=1.03:saturation=1.06,"
                 "colorbalance=rs=0.06:rm=0.05:rh=0.06:bs=-0.05:bh=-0.05"),
        "bw": "hue=s=0,eq=contrast=1.12",
    }
    return presets.get(name)


# ----------------------------------------------------------------------------
# Encoder phần cứng (GPU) — tự dò cái CHẠY ĐƯỢC trên máy, fallback libx264
# ----------------------------------------------------------------------------
_ENC = None             # cache: (tên, [flags]) — chỉ dò 1 lần mỗi lần chạy

# Encoder video tốc độ cao, ưu tiên GPU. cq/global_quality ~ chất lượng crf 23.
_GPU_ENCODERS = [
    ("h264_nvenc", ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "23", "-b:v", "0"]),
    ("h264_qsv",   ["-c:v", "h264_qsv", "-global_quality", "23", "-preset", "medium"]),
    ("h264_amf",   ["-c:v", "h264_amf", "-quality", "balanced", "-rc", "cqp", "-qp_i", "23", "-qp_p", "23"]),
]
_CPU_ENCODER = ("libx264", ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"])


def _test_encoder(flags):
    """Encode thử 5 frame testsrc -> True nếu encoder CHẠY ĐƯỢC THẬT trên máy này
    (vd máy không iGPU thì h264_qsv có trong build nhưng test sẽ fail -> bị loại)."""
    win = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        r = subprocess.run(
            [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
             "-i", "testsrc2=size=256x256:rate=30", "-frames:v", "5"]
            + flags + ["-f", "null", "-"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=win, timeout=30)
        return r.returncode == 0
    except Exception:  # noqa
        return False


def detect_encoder(pref="auto"):
    """Chọn encoder video NHANH NHẤT chạy được: ưu tiên GPU (nvenc/qsv/amf),
    fallback libx264 veryfast. Cache lại. pref='cpu' -> ép libx264."""
    global _ENC
    if _ENC is not None:
        return _ENC
    if pref != "cpu":
        for name, flags in _GPU_ENCODERS:
            if _test_encoder(flags):
                _ENC = (name, flags)
                return _ENC
    _ENC = _CPU_ENCODER
    return _ENC


def enc_name():
    return (_ENC or detect_encoder())[0]


def enc_args(image=False):
    """Flags encoder video. image=True -> libx264 veryfast (file ẢNH nhỏ, encode tĩnh đủ
    nhanh, vì nút thắt của ảnh là FILTER không phải encode). Còn lại -> GPU đã dò."""
    if image:
        return list(_CPU_ENCODER[1])
    return list((_ENC or detect_encoder())[1])


def _probe_size(path):
    """(width, height) của ảnh/video, hoặc (None, None)."""
    if not FFPROBE:
        return None, None
    try:
        r = run([FFPROBE, "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", path],
                timeout=30)
        w, h = (r.stdout or "").strip().split("x")[:2]
        return int(w), int(h)
    except Exception:  # noqa
        return None, None


def _maybe_shrink_image(media, tmp_dir):
    """Ảnh nguồn khổng lồ (cạnh > SRC_MAX) -> thu nhỏ về SRC_MAX trước khi Ken Burns.
    Chống TREO (decode ảnh vài chục–trăm MP ngốn RAM) + render nhanh hơn. Trả đường dẫn dùng."""
    w, h = _probe_size(media)
    if not w or not h or max(w, h) <= SRC_MAX:
        return media
    small = os.path.join(tmp_dir, "shrink_" + re.sub(r"[^\w.]", "_", os.path.basename(media)) + ".png")
    try:
        run([FFMPEG, "-y", "-i", media, "-vf",
             f"scale='if(gt(iw,ih),{SRC_MAX},-1)':'if(gt(iw,ih),-1,{SRC_MAX})':flags=lanczos",
             small], timeout=180)
        print(f"     (ảnh lớn {w}x{h} -> thu nhỏ {SRC_MAX}px cho nhanh & khỏi treo)")
        return small if os.path.isfile(small) else media
    except SystemExit:
        print(f"     (CẢNH BÁO: ảnh {w}x{h} quá lớn, không thu nhỏ được — thử render thẳng)")
        return media


# ----------------------------------------------------------------------------
# Tạo từng cảnh (ảnh -> clip mp4) với Ken Burns + fade
# ----------------------------------------------------------------------------
def build_clip(media, duration, out_path, kenburns=True, index=0, clip_fit="auto",
               edge_fade=True):
    frames = max(1, round(duration * FPS))
    is_video = media.lower().endswith(VIDEO_EXTS)

    if is_video:
        # Khớp clip Veo (độ dài cố định) vào đúng độ dài cảnh
        clip_len = probe_duration(media) or duration
        base = (f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={WIDTH}:{HEIGHT},setsar=1")
        ratio = duration / clip_len      # >1: phải kéo dài (chậm) | <1: rút ngắn

        mode = clip_fit
        if mode == "auto":
            # Ưu tiên 'cut' khi clip ĐỦ DÀI (>= ~96% cảnh): giữ NGUYÊN frame gốc của Veo
            # -> KHÔNG đổi tốc độ, KHÔNG nhân frame -> hết rung (judder). Chỉ làm chậm khi
            # clip NGẮN HƠN cảnh và lệch ít; lệch nhiều thì lặp.
            if ratio <= 1.04:
                mode = "cut"             # clip >= cảnh -> cắt lấy phần đầu (mượt nhất)
            elif ratio <= 1.25:
                mode = "speed"           # clip ngắn hơn chút -> làm chậm nhẹ cho khớp
            else:
                mode = "loop"            # clip ngắn hơn nhiều -> lặp cho đủ

        if mode == "speed":
            vf = f"setpts={ratio:.4f}*PTS,{base},fps={FPS},format=yuv420p"
            cmd = [FFMPEG, "-y", "-an", "-i", media, "-vf", vf, "-t", f"{duration:.3f}"]
        elif mode == "loop":
            vf = f"{base},fps={FPS},format=yuv420p"
            cmd = [FFMPEG, "-y", "-an", "-stream_loop", "-1", "-i", media,
                   "-t", f"{duration:.3f}", "-vf", vf]
        else:  # cut
            vf = f"{base},fps={FPS},format=yuv420p"
            cmd = [FFMPEG, "-y", "-an", "-i", media, "-t", f"{duration:.3f}", "-vf", vf]
        cmd += enc_args() + ["-pix_fmt", "yuv420p", out_path]
        run(cmd, timeout=SCENE_TIMEOUT)
        return

    # Ảnh tĩnh — ảnh khổng lồ thì TỰ thu nhỏ trước (chống treo + nhanh hơn)
    media = _maybe_shrink_image(media, os.path.dirname(out_path))
    if kenburns:
        amt = KENBURNS_AMOUNT
        zmax = 1.0 + amt
        fr = frames
        # Chống RUNG của zoompan: render Ken Burns ở khung phóng to (KENBURNS_SS lần)
        # rồi THU về 1080p (lanczos). Làm tròn pixel ở độ phân giải cao -> "mịn dưới
        # pixel" khi co lại -> zoom/pan hết giật. File xuất ra VẪN là 1080p.
        zw, zh = int(WIDTH * KENBURNS_SS) // 2 * 2, int(HEIGHT * KENBURNS_SS) // 2 * 2
        pw, ph = zw * 2, zh * 2          # pre-scale = 2x khung zoompan (đủ dư cho zoom)
        pre = (f"scale={pw}:{ph}:force_original_aspect_ratio=increase,crop={pw}:{ph}")
        cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        v = index % 4
        if v == 0:        # zoom in, giữa
            z, x, y = f"1+{amt}*on/{fr}", cx, cy
        elif v == 1:      # zoom out, giữa
            z, x, y = f"{zmax:.3f}-{amt}*on/{fr}", cx, cy
        elif v == 2:      # zoom in + lia trái -> phải
            z, x, y = f"1+{amt}*on/{fr}", f"(iw-iw/zoom)*on/{fr}", cy
        else:             # zoom in + lia phải -> trái
            z, x, y = f"1+{amt}*on/{fr}", f"(iw-iw/zoom)*(1-on/{fr})", cy
        vf = (f"{pre},zoompan=z='{z}':x='{x}':y='{y}':"
              f"d={fr}:s={zw}x{zh}:fps={FPS},"
              f"scale={WIDTH}:{HEIGHT}:flags=lanczos,")
    else:
        vf = (f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
              f"crop={WIDTH}:{HEIGHT},fps={FPS},")

    # fade in/out viền (tắt khi dùng crossfade vì xfade lo chuyển cảnh)
    if edge_fade and duration > 2 * FADE + 0.1:
        vf += (f"fade=t=in:st=0:d={FADE},"
               f"fade=t=out:st={duration - FADE:.3f}:d={FADE},")
    vf += "setsar=1,format=yuv420p"

    cmd = ([FFMPEG, "-y", "-loop", "1", "-i", media, "-t", f"{duration:.3f}",
            "-vf", vf] + enc_args(image=True) + ["-pix_fmt", "yuv420p", out_path])
    run(cmd, timeout=SCENE_TIMEOUT)


# ----------------------------------------------------------------------------
# Crossfade (chỉ giữa các ẢNH liên tiếp) + nối các đoạn
# ----------------------------------------------------------------------------
# Số ảnh tối đa mỗi lệnh xfade. Nhóm lớn hơn -> chia cụm để dòng lệnh ffmpeg KHÔNG
# vượt giới hạn ~32K ký tự của Windows (gây WinError 206 khi render video toàn ảnh tĩnh).
XFADE_CHUNK = 20
_XF_SEQ = [0]            # bộ đếm tạo tên file segment xfade DUY NHẤT (tránh trùng khi đệ quy)


def _xfade_chain(clip_paths, lens, dur, out_path, transition="fade"):
    """Crossfade 1 cụm NHỎ (<= XFADE_CHUNK ảnh) trong đúng 1 lệnh ffmpeg."""
    inputs = []
    for p in clip_paths:
        inputs += ["-i", p]
    fc = []
    prev = "[0:v]"
    cum = lens[0]
    for j in range(1, len(clip_paths)):
        off = cum - dur
        lbl = f"[x{j}]"
        fc.append(f"{prev}[{j}:v]xfade=transition={transition}:"
                  f"duration={dur:.3f}:offset={off:.3f}{lbl}")
        prev = lbl
        cum = cum + lens[j] - dur
    cmd = ([FFMPEG, "-y"] + inputs + ["-filter_complex", ";".join(fc),
           "-map", prev, "-r", str(int(FPS))] + enc_args()
           + ["-pix_fmt", "yuv420p", out_path])
    run(cmd, timeout=SCENE_TIMEOUT)


def xfade_group(clip_paths, lens, dur, out_path, transition="fade"):
    """Nối 1 nhóm ảnh bằng crossfade. Nhóm LỚN -> chia thành các cụm <= XFADE_CHUNK,
    crossfade từng cụm ra segment (mỗi segment giữ phần "đuôi" thừa để crossfade tiếp),
    rồi crossfade CÁC SEGMENT với nhau -> liền mạch, không lệch thời lượng, không vượt
    giới hạn dòng lệnh Windows. lens = độ dài render mỗi clip."""
    n = len(clip_paths)
    if n <= XFADE_CHUNK:
        _xfade_chain(clip_paths, lens, dur, out_path, transition)
        return
    tmpd = os.path.dirname(out_path)
    segs, seg_lens, i = [], [], 0
    while i < n:
        j = min(i + XFADE_CHUNK, n)
        seg = os.path.join(tmpd, f"xfseg_{_XF_SEQ[0]:05d}.mp4")
        _XF_SEQ[0] += 1
        if j - i == 1:
            shutil.copyfile(clip_paths[i], seg)
            seg_lens.append(lens[i])
        else:
            _xfade_chain(clip_paths[i:j], lens[i:j], dur, seg, transition)
            seg_lens.append(sum(lens[i:j]) - (j - i - 1) * dur)
        segs.append(seg)
        i = j
    # Crossfade các segment với nhau (số segment nhỏ -> đệ quy 1 lần là đủ)
    xfade_group(segs, seg_lens, dur, out_path, transition)


def concat_copy(paths, out_path, tmp):
    lst = os.path.join(tmp, "concat_seg.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for p in paths:
            f.write(f"file '{p.replace(chr(92), '/')}'\n")
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out_path])


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Auto ghép ảnh theo SRT + voice -> MP4")
    ap.add_argument("--images", default="input/images")
    ap.add_argument("--srt", default="input/subtitle.srt")
    ap.add_argument("--voice", default=None)
    ap.add_argument("--input-dir", default="input")
    ap.add_argument("--out", default="output/final.mp4")
    ap.add_argument("--image-mode", choices=["auto", "spread", "srt"], default="auto",
                    help="auto: tự chọn | spread: rải đều N ảnh theo thời lượng | "
                         "srt: 1 ảnh mỗi đoạn phụ đề")
    ap.add_argument("--scenes", default=None,
                    help="File scenes.csv (từ build_scenes.py): ghép ảnh theo ĐÚNG "
                         "khung giờ từng cảnh -> ảnh khớp lời cả nội dung lẫn thời gian. "
                         "Ảnh đặt tên 01,02,... theo thứ tự cảnh.")
    ap.add_argument("--seconds-per-image", type=float, default=None,
                    help="Cố định mỗi ảnh hiển thị N giây, lặp vòng ảnh nếu thiếu "
                         "(vd 6 = đổi ảnh mỗi 6s). Ưu tiên hơn --image-mode.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Chỉ in kế hoạch phân cảnh, KHÔNG render (xem trước cho nhanh)")
    ap.add_argument("--clip-fit", choices=["auto", "speed", "cut", "loop"], default="auto",
                    help="Khớp clip video vào cảnh: auto (khuyên) | speed: đổi tốc độ | "
                         "cut: cắt lấy đầu | loop: lặp cho đủ")
    ap.add_argument("--transition", choices=TRANSITIONS, default="none",
                    help="Kiểu chuyển cảnh giữa các ẢNH TĨNH: none=cắt thẳng | fade | "
                         "dissolve | slideleft/right/up/down | wipeleft/... | "
                         "circleopen | radial | zoomin ... (danh sách TRANSITIONS)")
    ap.add_argument("--xfade-duration", type=float, default=0.5,
                    help="Thời gian crossfade giữa 2 ảnh (giây)")
    ap.add_argument("--fps", type=int, default=None,
                    help="FPS video ra. Bỏ trống = TỰ ĐỘNG: khớp clip video (Veo 24fps) "
                         "nếu có clip -> hết rung; 30 nếu toàn ảnh tĩnh (Ken Burns mượt).")
    ap.add_argument("--no-kenburns", action="store_true")
    ap.add_argument("--no-subtitles", action="store_true")
    # --- Màu phim (#3) ---
    ap.add_argument("--color", choices=["none", "cinematic", "cold", "warm", "bw"],
                    default="none",
                    help="Màu phim: none | cinematic (điện ảnh) | cold (lạnh/quân sự) | "
                         "warm (ấm hoài niệm) | bw (đen trắng tài liệu)")
    ap.add_argument("--vignette", action="store_true", help="Tối nhẹ 4 góc (điện ảnh)")
    ap.add_argument("--grain", action="store_true", help="Thêm hạt phim nhẹ")
    # --- Nhạc nền (#4) ---
    ap.add_argument("--bgm", default=None,
                    help="File nhạc nền (mp3/wav). Tự lặp cho đủ dài + fade nhỏ ở cuối.")
    ap.add_argument("--bgm-volume", type=float, default=0.18,
                    help="Âm lượng nhạc nền 0..1 (mặc định 0.18 = nhỏ, nền cho lời thoại)")
    ap.add_argument("--no-duck", action="store_true",
                    help="TẮT tự hạ nhạc khi có lời (mặc định BẬT: nhạc tự nhỏ lúc đọc)")
    ap.add_argument("--keep-temp", action="store_true")
    ap.add_argument("--max-scenes", type=int, default=None,
                    help="Chỉ render N cảnh ĐẦU — dùng cho XEM TRƯỚC nhanh hiệu ứng.")
    ap.add_argument("--encoder", choices=["auto", "cpu"], default="auto",
                    help="auto: ưu tiên GPU (nvenc/qsv/amf) cho NHANH; cpu: libx264 (mọi máy).")
    ap.add_argument("--jobs", type=int, default=None,
                    help="Số cảnh render SONG SONG cùng lúc. Bỏ trống = tự động theo CPU.")
    args = ap.parse_args()

    if not FFMPEG:
        raise SystemExit("Không tìm thấy ffmpeg. Hãy cài rồi thử lại.")

    if not os.path.isfile(args.srt):
        raise SystemExit(f"Không thấy file SRT: {args.srt}")

    segs = parse_srt(args.srt)
    if not segs:
        raise SystemExit("File SRT không có đoạn nào hợp lệ.")
    media = collect_media(args.images)
    if not media:
        raise SystemExit(f"Thư mục {args.images} chưa có ảnh/video nào.")
    voice = find_voice(args.input_dir, args.voice)

    n_seg, n_img = len(segs), len(media)

    # Tổng thời lượng video = max(cuối SRT, độ dài voiceover) -> luôn phủ hết tiếng
    audio_dur = probe_duration(voice) if voice else None
    total_end = segs[-1]["end"]
    if audio_dur:
        total_end = max(total_end, audio_dur)

    # ---- Quyết định cách rải ảnh (ĐỘC LẬP với số đoạn phụ đề) ----
    spi = args.seconds_per_image
    mode = args.image_mode
    if mode == "auto" and not spi and not args.scenes:
        mode = "srt" if n_img == n_seg else "spread"

    if args.scenes:
        # Ghép theo bảng cảnh: ảnh thứ i khóa vào đúng [start-end] của cảnh i
        import csv
        scenes = []
        with open(args.scenes, encoding="utf-8-sig") as f:
            for i, row in enumerate(csv.DictReader(f)):
                st = srt_time_to_sec(row["start"])
                en = srt_time_to_sec(row["end"])
                scenes.append((media[min(i, n_img - 1)], max(0.4, en - st)))
        mode_label = f"theo bảng cảnh ({len(scenes)} cảnh, khóa timestamp SRT)"
    elif spi:
        n_scenes = max(1, round(total_end / spi))
        scenes = []
        for i in range(n_scenes):
            d = spi if i < n_scenes - 1 else max(0.4, total_end - spi * (n_scenes - 1))
            scenes.append((media[i % n_img], d))          # lặp vòng ảnh nếu thiếu
        mode_label = f"mỗi ảnh ~{spi:g}s (lặp vòng {n_img} ảnh)"
    elif mode == "srt":
        boundaries = [0.0] + [segs[i]["start"] for i in range(1, n_seg)] + [total_end]
        scenes = [(media[min(i, n_img - 1)], max(0.4, boundaries[i + 1] - boundaries[i]))
                  for i in range(n_seg)]
        mode_label = "1 ảnh / 1 đoạn phụ đề"
    else:  # spread
        per = total_end / n_img
        scenes = [(media[i], per) for i in range(n_img)]
        mode_label = f"rải đều {n_img} ảnh"

    # ---- XEM TRƯỚC: chỉ giữ N cảnh đầu cho render nhanh ----
    if args.max_scenes and args.max_scenes > 0 and len(scenes) > args.max_scenes:
        scenes = scenes[:args.max_scenes]
        total_end = sum(d for _, d in scenes)
        mode_label += f" | XEM TRƯỚC {len(scenes)} cảnh đầu"

    # ---- Chọn FPS: khớp clip Veo để HẾT RUNG ----
    # Clip Veo thường 24fps. Ép lên 30fps phải nhân bản frame KHÔNG đều -> giật (judder).
    # Có clip video -> dùng FPS = fps clip (24). Toàn ảnh tĩnh -> 30 (Ken Burns mượt hơn).
    has_video = any(src.lower().endswith(VIDEO_EXTS) for src, _ in scenes)
    if args.fps:
        fps_use, fps_why = args.fps, "theo --fps"
    elif has_video:
        vsrc = next(src for src, _ in scenes if src.lower().endswith(VIDEO_EXTS))
        f = probe_fps(vsrc)
        fps_use = int(round(f)) if f else 24
        fps_why = "khớp clip video -> hết rung"
    else:
        fps_use, fps_why = 30, "toàn ảnh tĩnh -> Ken Burns mượt"
    globals()["FPS"] = max(1, fps_use)
    print(f"• FPS: {FPS} ({fps_why})")

    # ---- Encoder (ưu tiên GPU) + số luồng render song song ----
    enc = detect_encoder(args.encoder)[0]
    cpu = os.cpu_count() or 4
    auto_jobs = max(1, min(4, cpu // 2))
    if enc != "libx264":
        auto_jobs = min(auto_jobs, 3)          # encoder GPU: cap session đồng thời cho an toàn
    jobs = args.jobs if (args.jobs and args.jobs > 0) else auto_jobs
    print(f"• Encoder: {enc} | Render song song: {jobs} cảnh/lúc")

    voice_name = os.path.basename(voice) if voice else "KHÔNG"
    dur_txt = f"{audio_dur:.1f}s" if audio_dur else "theo SRT"
    print(f"• Phụ đề: {n_seg} đoạn (tự khớp voiceover theo timestamp) | "
          f"Ảnh: {n_img} | Voice: {voice_name} ({dur_txt})")
    print(f"• Rải ảnh: {mode_label} → {len(scenes)} cảnh | tổng video {total_end:.1f}s")

    if args.dry_run:
        for i, (src, d) in enumerate(scenes):
            print(f"   cảnh {i+1:>3}: {os.path.basename(src):<22} {d:6.2f}s")
        print(f"   → TỔNG {sum(d for _, d in scenes):.1f}s "
              f"(khớp voice/SRT {total_end:.1f}s)")
        return

    tmp = tempfile.mkdtemp(prefix="autoedit_")
    try:
        # 1) Render từng cảnh (ảnh nằm giữa 2 ảnh -> render dài thêm để crossfade)
        is_img = [not s.lower().endswith(VIDEO_EXTS) for s, _ in scenes]
        use_xf = (args.transition != "none")
        D = max(0.15, min(args.xfade_duration, 1.5)) if use_xf else 0.0

        n_sc = len(scenes)
        clips = [os.path.join(tmp, f"clip_{i:04d}.mp4") for i in range(n_sc)]
        rlen = []
        jobtasks = []
        for i, (src, dur) in enumerate(scenes):
            extra = D if (use_xf and is_img[i] and i + 1 < n_sc and is_img[i + 1]) else 0.0
            rlen.append(dur + extra)
            jobtasks.append((i, src, dur + extra))

        done = [0]
        plock = threading.Lock()

        def _render_scene(t):
            i, src, d = t
            try:
                build_clip(src, d, clips[i], kenburns=not args.no_kenburns, index=i,
                           clip_fit=args.clip_fit, edge_fade=not use_xf)
            except SystemExit as e:
                raise SystemExit(f"Cảnh {i+1} ({os.path.basename(src)}): {e}")
            with plock:
                done[0] += 1
                print(f"  [{done[0]}/{n_sc}] {os.path.basename(src)}  ({d:.2f}s)")

        # Render SONG SONG nhiều cảnh -> tận dụng đa nhân (jobs=1 thì tuần tự như cũ)
        if jobs <= 1:
            for t in jobtasks:
                _render_scene(t)
        else:
            with ThreadPoolExecutor(max_workers=jobs) as ex:
                for _ in ex.map(_render_scene, jobtasks):
                    pass

        # 2) Ghép các cảnh
        silent = os.path.join(tmp, "video_silent.mp4")
        if not use_xf:
            listfile = os.path.join(tmp, "concat.txt")
            with open(listfile, "w", encoding="utf-8") as f:
                for c in clips:
                    f.write(f"file '{c.replace(chr(92), '/')}'\n")
            run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", listfile,
                 "-c", "copy", silent])
        else:
            print("• Áp crossfade cho các ảnh tĩnh...")
            segments, i, n = [], 0, len(clips)
            while i < n:
                if is_img[i]:
                    j = i
                    while j < n and is_img[j]:
                        j += 1
                    if j - i == 1:
                        segments.append(clips[i])
                    else:
                        seg = os.path.join(tmp, f"seg_{i:04d}.mp4")
                        xfade_group(clips[i:j], rlen[i:j], D, seg, args.transition)
                        segments.append(seg)
                    i = j
                else:
                    segments.append(clips[i])
                    i += 1
            concat_copy(segments, silent, tmp)

        # 3) Pass cuối: màu phim + vignette + hạt phim + phụ đề + voice + NHẠC NỀN
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        out_abs = os.path.abspath(args.out)
        bgm = os.path.abspath(args.bgm) if (args.bgm and os.path.isfile(args.bgm)) else None
        vid_dur = probe_duration(silent) or total_end

        # Chuỗi filter VIDEO (#3): màu -> vignette -> hạt phim -> phụ đề
        # (phụ đề để CUỐI chuỗi -> chữ vẽ trên cùng, không bị ám màu/tối góc che).
        vchain = []
        cg = color_grade_filter(args.color)
        if cg:
            vchain.append(cg)
        if args.vignette:
            vchain.append("vignette=angle=PI/5")
        if args.grain:
            vchain.append("noise=alls=6:allf=t")
        cwd = None
        if not args.no_subtitles:
            # ASS (tên ascii, trong temp) PlayResX/Y = kích thước video -> phụ đề đúng pixel thật.
            subs = os.path.join(tmp, "subs.ass")
            _write_ass(args.srt, subs, WIDTH, HEIGHT)
            cwd = tmp                       # chạy ffmpeg trong temp -> path phụ đề tương đối
            vchain.append("subtitles=subs.ass")

        cmd = [FFMPEG, "-y", "-i", silent]
        if voice:
            cmd += ["-i", os.path.abspath(voice)]
        if bgm:
            cmd += ["-stream_loop", "-1", "-i", bgm]   # lặp nhạc cho đủ dài video

        if bgm:
            # Có nhạc nền -> gộp tất cả vào -filter_complex (video + trộn audio)
            bidx = 2 if voice else 1
            fc = []
            if vchain:
                fc.append(f"[0:v]{','.join(vchain)}[v]")
                vmap = "[v]"
            else:
                vmap = "0:v:0"
            bvol = max(0.0, min(2.0, args.bgm_volume))
            fo = max(0.0, vid_dur - 2.0)                # nhạc fade nhỏ 2s cuối
            fc.append(f"[{bidx}:a]volume={bvol:.3f},"
                      f"afade=t=out:st={fo:.2f}:d=2,atrim=0:{vid_dur:.3f}[bgm]")
            if voice:
                if not args.no_duck:
                    # ducking: nhạc TỰ NHỎ lại khi có lời (voice làm sidechain)
                    fc.append("[1:a]asplit=2[vmix][vsc]")
                    fc.append("[bgm][vsc]sidechaincompress=threshold=0.05:ratio=8:"
                              "attack=15:release=300[bgd]")
                    fc.append("[bgd][vmix]amix=inputs=2:normalize=0[aout]")
                else:
                    fc.append("[bgm][1:a]amix=inputs=2:normalize=0[aout]")
            else:
                fc.append("[bgm]anull[aout]")
            cmd += (["-filter_complex", ";".join(fc), "-map", vmap, "-map", "[aout]"]
                    + enc_args() + ["-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-t", f"{vid_dur:.3f}", out_abs])
            print("• Đang render bản cuối (màu + phụ đề + voice + nhạc nền)...")
        else:
            # Không nhạc nền -> dùng -vf cho video như cũ
            if vchain:
                cmd += ["-vf", ",".join(vchain)]
            cmd += enc_args() + ["-pix_fmt", "yuv420p"]
            if voice:
                cmd += ["-c:a", "aac", "-b:a", "192k", "-map", "0:v:0", "-map", "1:a:0",
                        "-shortest"]
            else:
                cmd += ["-map", "0:v:0"]
            cmd += [out_abs]
            print("• Đang render bản cuối (phụ đề + voice)...")

        run(cmd, cwd=cwd)

        print(f"\n✅ XONG: {out_abs}")
        if audio_dur and segs[-1]['end'] < audio_dur - 0.5:
            print(f"  (Voice dài {audio_dur:.1f}s > SRT {segs[-1]['end']:.1f}s — "
                  "ảnh cuối đã được kéo dài để phủ hết tiếng.)")
    finally:
        if args.keep_temp:
            print(f"• Temp giữ lại tại: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
