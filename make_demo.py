#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_demo.py — Dựng video DEMO ngắn để kiểm chứng phụ đề KHỚP tiếng + liền mạch.

Cách hoạt động (mô phỏng đúng cơ chế thật):
  • Đọc SRT thật của Boss, lấy các đoạn trong N giây đầu.
  • Với mỗi đoạn, dùng giọng đọc máy (Windows TTS) đọc đúng câu đó,
    rồi ĐẶT vào đúng mốc thời gian start của đoạn (adelay) -> voiceover khớp timestamp.
  • Tạo vài ảnh đánh số để thấy rõ ảnh đổi cảnh.
  • Gọi auto_edit.py render ra demo.mp4.

Kết quả: nghe câu nào thì thấy đúng phụ đề câu đó -> chứng minh khớp.
"""
import os
import subprocess
import sys

import auto_edit as ae   # tái dùng parse_srt + đường dẫn FFMPEG

LIMIT = 30.0             # số giây demo
HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.join(HERE, "demo")
IMGDIR = os.path.join(DEMO, "images")
FONT = r"C\:/Windows/Fonts/arialbd.ttf"   # đường dẫn font cho drawtext (đã escape)


def tts(text, wav_path, rate=2):
    """Đọc text -> file wav bằng Windows System.Speech (tránh lỗi escape: truyền qua file)."""
    txt_file = wav_path + ".txt"
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write(text)
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        f"$t=[IO.File]::ReadAllText('{txt_file}',[Text.Encoding]::UTF8); "
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Rate={rate}; "
        f"$s.SetOutputToWaveFile('{wav_path}'); $s.Speak($t); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    os.remove(txt_file)


def make_image(path, label, color):
    # Ảnh nền màu trơn (mỗi cảnh 1 màu để thấy rõ chuyển cảnh)
    subprocess.run([ae.FFMPEG, "-y", "-f", "lavfi", "-i",
                    f"color=c={color}:s=1920x1080", "-frames:v", "1", path],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


def main():
    os.makedirs(IMGDIR, exist_ok=True)
    segs = [s for s in ae.parse_srt(os.path.join(HERE, "input", "subtitle.srt"))
            if s["start"] < LIMIT]
    print(f"• Demo {LIMIT:.0f}s đầu: {len(segs)} câu phụ đề")

    # 1) TTS từng câu rồi đặt vào đúng timestamp
    tmp_wavs, filters, labels = [], [], []
    for i, s in enumerate(segs):
        w = os.path.join(DEMO, f"seg_{i:02d}.wav")
        tts(s["text"], w)
        tmp_wavs.append(w)
        delay = int(s["start"] * 1000)
        filters.append(f"[{i}:a]adelay={delay}|{delay}[a{i}]")
        labels.append(f"[a{i}]")
        print(f"   {s['start']:5.2f}s  «{s['text'][:48]}»")

    # 2) Trộn thành 1 voiceover khớp timestamp
    voice = os.path.join(DEMO, "voice.mp3")
    fc = ";".join(filters) + ";" + "".join(labels) + \
        f"amix=inputs={len(labels)}:normalize=0[out]"
    cmd = [ae.FFMPEG, "-y"]
    for w in tmp_wavs:
        cmd += ["-i", w]
    cmd += ["-filter_complex", fc, "-map", "[out]", "-t", f"{LIMIT}", voice]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    for w in tmp_wavs:
        os.remove(w)

    # 3) Trimmed SRT (đánh số lại, trong LIMIT giây)
    srt = os.path.join(DEMO, "subtitle.srt")
    with open(srt, "w", encoding="utf-8") as f:
        for i, s in enumerate(segs, 1):
            def ts(t):
                h = int(t // 3600); m = int(t % 3600 // 60)
                sec = int(t % 60); ms = int(round((t - int(t)) * 1000))
                return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"
            end = min(s["end"], LIMIT)
            f.write(f"{i}\n{ts(s['start'])} --> {ts(end)}\n{s['text']}\n\n")

    # 4) Ảnh đánh số
    palette = ["0x1b3a5b", "0x5b1b2e", "0x1b5b34", "0x5b4a1b", "0x3a1b5b"]
    for i in range(5):
        make_image(os.path.join(IMGDIR, f"{i+1:02d}.png"),
                   f"ANH {i+1}", palette[i])

    # 5) Render demo bằng auto_edit (đổi ảnh mỗi 6s)
    out = os.path.join(HERE, "output", "demo.mp4")
    subprocess.run([sys.executable, os.path.join(HERE, "auto_edit.py"),
                    "--srt", srt, "--images", IMGDIR, "--voice", voice,
                    "--out", out, "--seconds-per-image", "6"], check=True)
    print(f"\n✅ DEMO: {out}")


if __name__ == "__main__":
    main()
