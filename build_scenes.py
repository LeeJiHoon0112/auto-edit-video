#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_scenes.py — Gom SRT (nhiều đoạn vụn) thành các CẢNH có timestamp.

Mục đích: tạo "xương sống thời gian" để mỗi prompt/ảnh gắn cứng vào một mốc
[start - end] lấy từ voiceover -> ảnh khớp lời cả NỘI DUNG lẫn THỜI GIAN.

Xuất ra scenes.csv với các cột:
    scene | start | end | dur | text(lời trong cảnh) | prompt(để trống cho Boss/AI điền)

Cách chạy:
    python build_scenes.py                       # gom mỗi cảnh ~8 giây
    python build_scenes.py --target 6            # mỗi cảnh ~6 giây (nhiều ảnh hơn)
    python build_scenes.py --srt input/subtitle.srt --out scenes.csv
"""
import argparse
import csv
import os

import auto_edit as ae   # tái dùng parse_srt

VEO_LEVELS = [4, 6, 8, 10]   # các mức độ dài clip Veo chọn được


def nearest_veo(dur):
    """Chọn mức Veo gần nhất + % phải đổi tốc độ để khít cảnh."""
    level = min(VEO_LEVELS, key=lambda L: abs(L - dur))
    pct = (dur / level - 1) * 100         # >0: clip phải chậm lại ; <0: nhanh lên
    if abs(pct) < 1:
        txt = "khít"
    else:
        txt = f"{abs(pct):.0f}% {'chậm' if pct > 0 else 'nhanh'}"
    return level, pct, txt


def fmt(t):
    h = int(t // 3600); m = int(t % 3600 // 60)
    s = int(t % 60); ms = int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def group_scenes(segs, target):
    """Gom các đoạn liền nhau cho tới khi đạt ~target giây thì chốt 1 cảnh."""
    scenes = []
    cur = None
    for s in segs:
        if cur is None:
            cur = {"start": s["start"], "end": s["end"], "texts": [s["text"]]}
            continue
        # nếu thêm đoạn này mà cảnh vẫn chưa quá dài -> gộp tiếp
        if s["end"] - cur["start"] <= target:
            cur["end"] = s["end"]
            cur["texts"].append(s["text"])
        else:
            scenes.append(cur)
            cur = {"start": s["start"], "end": s["end"], "texts": [s["text"]]}
    if cur:
        scenes.append(cur)
    # nối liền mạch: end của cảnh = start của cảnh kế
    for i in range(len(scenes) - 1):
        scenes[i]["end"] = scenes[i + 1]["start"]
    return scenes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--srt", default="input/subtitle.srt")
    ap.add_argument("--target", type=float, default=8.0, help="thời lượng mỗi cảnh (giây)")
    ap.add_argument("--out", default="scenes.csv")
    args = ap.parse_args()

    segs = ae.parse_srt(args.srt)
    scenes = group_scenes(segs, args.target)

    rows = []
    for i, sc in enumerate(scenes, 1):
        text = " ".join(t.strip() for t in sc["texts"]).strip()
        dur = round(sc["end"] - sc["start"], 2)
        veo, pct, speed_txt = nearest_veo(dur)
        rows.append({
            "scene": i,
            "start": fmt(sc["start"]),
            "end": fmt(sc["end"]),
            "dur": dur,
            "veo_sec": veo,           # mức Veo nên tạo cho cảnh này
            "speed": speed_txt,       # tool sẽ đổi tốc độ chừng này để khít
            "text": text,
            "prompt": "",             # để trống cho Boss/AI điền prompt khớp lời
        })

    fields = ["scene", "start", "end", "dur", "veo_sec", "speed", "text", "prompt"]
    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    total = scenes[-1]["end"] - scenes[0]["start"]
    pcts = [abs((r["dur"] / r["veo_sec"] - 1) * 100) for r in rows]
    within15 = sum(1 for p in pcts if p <= 15)
    print(f"• {len(segs)} đoạn SRT  ->  {len(rows)} CẢNH (mỗi cảnh ~{args.target:g}s) "
          f"| tổng {total:.1f}s")
    print(f"• Đã ghi: {os.path.abspath(args.out)}")
    print(f"• Đổi tốc độ: trung bình {sum(pcts)/len(pcts):.1f}% | "
          f"cao nhất {max(pcts):.1f}% | "
          f"{within15}/{len(rows)} cảnh dưới 15% (gần như vô hình)")
    print("\n--- 8 cảnh đầu (kèm mức Veo nên dùng) ---")
    for r in rows[:8]:
        print(f"  Cảnh {r['scene']:>2} | {r['dur']:>5}s → Veo {r['veo_sec']}s "
              f"({r['speed']:>9}) | {r['text'][:45]}")


if __name__ == "__main__":
    main()
