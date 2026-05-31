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
KENBURNS_AMOUNT = 0.12   # mức zoom Ken Burns (0.12 = phóng to thêm 12%)
IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm")
AUDIO_NAMES = ("voice.mp3", "voice.wav", "voice.m4a", "voiceover.mp3", "voiceover.wav")

# Style phụ đề (cú pháp ASS force_style). &HAABBGGRR (AA=alpha, 00=đục).
SUB_STYLE = (
    "FontName=Arial,Fontsize=22,Bold=1,"
    "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,"
    "Outline=2,Shadow=1,Alignment=2,MarginV=60"
)


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


def run(cmd, cwd=None):
    """Chạy lệnh, in lỗi gọn nếu fail."""
    res = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, encoding="utf-8",
                         errors="replace")
    if res.returncode != 0:
        sys.stderr.write("\n[FFmpeg lỗi]\n" + (res.stderr or "")[-1500:] + "\n")
        raise SystemExit(f"Lệnh thất bại: {' '.join(cmd[:3])} ...")
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


# ----------------------------------------------------------------------------
# Tạo từng cảnh (ảnh -> clip mp4) với Ken Burns + fade
# ----------------------------------------------------------------------------
def build_clip(media, duration, out_path, kenburns=True, index=0, clip_fit="auto"):
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
            if 0.8 <= ratio <= 1.25:
                mode = "speed"           # lệch ít -> đổi tốc độ, giữ trọn nội dung
            elif ratio < 0.8:
                mode = "cut"             # clip dài hơn nhiều -> cắt lấy phần đầu
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
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20", out_path]
        run(cmd)
        return

    # Ảnh tĩnh
    if kenburns:
        rate = KENBURNS_AMOUNT / frames           # tăng zoom mỗi frame
        zmax = 1.0 + KENBURNS_AMOUNT
        # scale lên lớn để zoompan mượt, crop đúng tỉ lệ 16:9 trước
        vf = (
            f"scale={WIDTH*2}:{HEIGHT*2}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH*2}:{HEIGHT*2},"
            f"zoompan=z='min(zoom+{rate:.6f},{zmax:.3f})':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS},"
        )
    else:
        vf = (f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
              f"crop={WIDTH}:{HEIGHT},fps={FPS},")

    # fade in/out nếu cảnh đủ dài
    if duration > 2 * FADE + 0.1:
        vf += (f"fade=t=in:st=0:d={FADE},"
               f"fade=t=out:st={duration - FADE:.3f}:d={FADE},")
    vf += "setsar=1,format=yuv420p"

    cmd = [FFMPEG, "-y", "-loop", "1", "-i", media, "-t", f"{duration:.3f}",
           "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "20",
           out_path]
    run(cmd)


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
    ap.add_argument("--no-kenburns", action="store_true")
    ap.add_argument("--no-subtitles", action="store_true")
    ap.add_argument("--keep-temp", action="store_true")
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
        # 1) Render từng cảnh
        clips = []
        for i, (src, dur) in enumerate(scenes):
            clip = os.path.join(tmp, f"clip_{i:04d}.mp4")
            print(f"  [{i+1}/{len(scenes)}] {os.path.basename(src)}  ({dur:.2f}s)")
            build_clip(src, dur, clip, kenburns=not args.no_kenburns, index=i,
                       clip_fit=args.clip_fit)
            clips.append(clip)

        # 2) Nối các cảnh (copy, không re-encode)
        listfile = os.path.join(tmp, "concat.txt")
        with open(listfile, "w", encoding="utf-8") as f:
            for c in clips:
                f.write(f"file '{c.replace(chr(92), '/')}'\n")
        silent = os.path.join(tmp, "video_silent.mp4")
        run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", listfile,
             "-c", "copy", silent])

        # 3) Pass cuối: burn phụ đề + ghép voice
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        out_abs = os.path.abspath(args.out)

        cmd = [FFMPEG, "-y", "-i", silent]
        if voice:
            cmd += ["-i", os.path.abspath(voice)]

        vf = None
        cwd = None
        if not args.no_subtitles:
            # Copy SRT vào temp tên ascii để tránh lỗi escape path trên Windows
            subs = os.path.join(tmp, "subs.srt")
            shutil.copyfile(args.srt, subs)
            cwd = tmp                       # chạy ffmpeg trong temp -> path tương đối
            vf = f"subtitles=subs.srt:charenc=UTF-8:force_style='{SUB_STYLE}'"

        if vf:
            cmd += ["-vf", vf]
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-pix_fmt", "yuv420p"]
        if voice:
            cmd += ["-c:a", "aac", "-b:a", "192k", "-map", "0:v:0", "-map", "1:a:0",
                    "-shortest"]
        else:
            cmd += ["-map", "0:v:0"]
        cmd += [out_abs]

        # silent là absolute -> để subtitles dùng path tương đối, đưa -i silent
        # vẫn dùng absolute path (ffmpeg input không bị ảnh hưởng bởi filter escaping)
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
