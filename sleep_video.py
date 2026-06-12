#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VIDEO NGỦ dài (3-4 tiếng) — nền ảnh/clip + hiệu ứng TỰ TẠO (mưa/tuyết/sương/bokeh) + audio dài.

Tối ưu tốc độ: render 1 đoạn nền NGẮN (loop LIỀN MẠCH) rồi LẶP COPY (không re-encode) cho hết
audio + ghép tiếng + fade. Nhờ vậy video 4 tiếng vẫn ra trong vài phút, file nhẹ.

Dùng chung tiện ích của auto_edit (FFMPEG, run, enc_args, probe_duration, detect_encoder).

Cách chạy:
    python sleep_video.py --bg canh_dem.jpg --audio nhac_4h.wav --out output/sleep.mp4 --effect rain
"""
import argparse
import os
import sys
import tempfile
import shutil

import auto_edit as ae

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

WIDTH, HEIGHT = 1920, 1080
FPS = 30
LOOP_SEC = 20.0          # độ dài đoạn nền loop (đủ dài để mắt không thấy lặp)
TEX_H = 2160             # cao texture; vstack đôi -> scroll dọc LIỀN MẠCH (không giật khi loop)

EFFECTS = ("none", "rain", "snow", "fog", "bokeh")
INTENSITIES = ("nhe", "vua", "nang")

# cường độ -> (ngưỡng thưa geq: CAO = THƯA hạt, opacity blend gốc)
_INTENSITY = {
    "nhe":  (0.9930, 0.42),
    "vua":  (0.9880, 0.60),
    "nang": (0.9820, 0.78),
}


def _make_texture(effect, intensity, tmp):
    """Tạo 1 ảnh texture cho hiệu ứng (random hạt). Trả path, hoặc None nếu 'none'."""
    if effect == "none":
        return None
    thr, _op = _INTENSITY[intensity]
    out = os.path.join(tmp, f"tex_{effect}.png")
    if effect == "rain":
        src = f"color=black:s={WIDTH}x120"          # chấm thưa rồi kéo dọc -> vệt mưa dài
        vf = (f"geq=lum='255*gt(random(1),{thr:.4f})':cb=128:cr=128,"
              f"scale={WIDTH}:{TEX_H}:flags=bilinear,gblur=sigma=0.5")
    elif effect == "snow":
        src = f"color=black:s={WIDTH}x{TEX_H}"       # chấm TRÒN thưa hơn (tuyết)
        vf = f"geq=lum='255*gt(random(1),{thr + 0.004:.4f})':cb=128:cr=128,gblur=sigma=1.3"
    elif effect == "fog":
        src = "color=black:s=620x340"               # đám mờ lớn -> blur mạnh -> mây sương
        vf = f"geq=lum='random(1)*255':cb=128:cr=128,gblur=sigma=24,scale={WIDTH + 400}:{HEIGHT}"
    elif effect == "bokeh":
        src = "color=black:s=128x144"                # điểm thưa ở res THẤP -> phóng to -> đốm tròn lớn
        vf = (f"geq=lum='255*gt(random(1),0.93)':cb=128:cr=128,"
              f"scale={WIDTH}:{TEX_H}:flags=bilinear,gblur=sigma=9,"
              f"eq=brightness=0.06:contrast=2.6")
    else:
        return None
    ae.run([ae.FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
            "-i", src, "-vf", vf, "-frames:v", "1", out], timeout=120)
    return out


def _overlay(effect, intensity):
    """filter_complex (dùng [bg] = nền đã scale, [1] = texture) -> [out].
    Scroll LIỀN MẠCH trong LOOP_SEC: vstack/hstack đôi texture rồi mod khớp số vòng nguyên."""
    _thr, op = _INTENSITY[intensity]
    if effect == "fog":
        vx = WIDTH / LOOP_SEC                        # trôi NGANG 1 vòng/loop, opacity thấp
        return (f"[1]format=gray,split[t1][t2];[t1][t2]hstack[tt];"
                f"[tt]crop={WIDTH}:{HEIGHT}:'mod(t*{vx:.3f},{WIDTH})':0[fx];"
                f"[bg][fx]blend=all_mode=screen:all_opacity={op * 0.30:.3f}[out]")
    if effect == "bokeh":
        vy = TEX_H / LOOP_SEC                         # trôi DỌC chậm 1 vòng + lấp lánh
        return (f"[1]format=gray,split[t1][t2];[t1][t2]vstack[tt];"
                f"[tt]crop={WIDTH}:{HEIGHT}:0:'mod(t*{vy:.3f},{TEX_H})',"
                f"eq=brightness='0.05*sin(2*PI*t/{LOOP_SEC})'[fx];"
                f"[bg][fx]blend=all_mode=screen:all_opacity={op:.3f}[out]")
    # rain / snow: rơi DỌC (mưa nhanh 8 vòng/loop, tuyết chậm 2 vòng/loop)
    cyc = 8 if effect == "rain" else 2
    vy = cyc * TEX_H / LOOP_SEC
    return (f"[1]format=gray,split[t1][t2];[t1][t2]vstack[tt];"
            f"[tt]crop={WIDTH}:{HEIGHT}:0:'mod(t*{vy:.3f},{TEX_H})'[fx];"
            f"[bg][fx]blend=all_mode=screen:all_opacity={op:.3f}[out]")


def _seamless_video_loop(clip, tmp):
    """Clip video nền -> bản LOOP LIỀN MẠCH: crossfade đuôi clip hòa vào đầu (frame cuối ≈
    frame đầu) -> lặp copy KHÔNG thấy điểm nối. Giữ NGUYÊN cảnh, không thêm gì."""
    d = ae.probe_duration(clip) or 10.0
    cf = min(1.2, max(0.4, d / 6.0))           # thời lượng crossfade (giây)
    out = os.path.join(tmp, "loopclip.mp4")
    fc = (f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
          f"crop={WIDTH}:{HEIGHT},fps={FPS},setsar=1[v];"
          f"[v]split[base][tail];"
          f"[base]trim=0:{d - cf:.3f},setpts=PTS-STARTPTS[b];"
          f"[tail]trim=start={d - cf:.3f},setpts=PTS-STARTPTS,format=yuva420p,"
          f"fade=t=out:st=0:d={cf:.3f}:alpha=1[t];"
          f"[b][t]overlay,format=yuv420p[out]")
    cmd = ([ae.FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", clip,
            "-filter_complex", fc, "-map", "[out]", "-t", f"{d - cf:.3f}", "-r", str(FPS)]
           + ae.enc_args() + ["-pix_fmt", "yuv420p", out])
    ae.run(cmd, timeout=600)
    return out


def _build_loopclip(bg, effect, intensity, tmp):
    """Dựng đoạn nền NGẮN loop LIỀN MẠCH. Clip video -> crossfade seamless (giữ nguyên cảnh);
    ảnh tĩnh -> render LOOP_SEC + (hiệu ứng nếu chọn)."""
    if bg.lower().endswith(ae.VIDEO_EXTS):
        return _seamless_video_loop(bg, tmp)
    out = os.path.join(tmp, "loopclip.mp4")
    base = (f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},fps={FPS}")
    if effect == "none":
        fc = base + ",setsar=1[out]"
        inputs = ["-loop", "1", "-i", bg]
    else:
        tex = _make_texture(effect, intensity, tmp)
        inputs = ["-loop", "1", "-i", bg, "-loop", "1", "-i", tex]
        fc = base + "[bg];" + _overlay(effect, intensity)
    cmd = ([ae.FFMPEG, "-y", "-hide_banner", "-loglevel", "error"] + inputs
           + ["-filter_complex", fc, "-map", "[out]", "-t", f"{LOOP_SEC}", "-r", str(FPS)]
           + ae.enc_args() + ["-pix_fmt", "yuv420p", out])
    ae.run(cmd, timeout=600)
    return out


def make_sleep_video(bg, audio, out, effect="rain", intensity="vua", fade=4.0,
                     max_seconds=None, encoder="auto"):
    if not ae.FFMPEG:
        raise SystemExit("Không tìm thấy ffmpeg.")
    if not os.path.isfile(bg):
        raise SystemExit(f"Không thấy file nền: {bg}")
    if not os.path.isfile(audio):
        raise SystemExit(f"Không thấy file audio: {audio}")
    enc = ae.detect_encoder(encoder)[0]
    adur = ae.probe_duration(audio) or 0.0
    if max_seconds and max_seconds > 0:
        adur = min(adur, float(max_seconds))
    if adur < 1:
        raise SystemExit("Audio quá ngắn / không đọc được độ dài.")

    kind = "video loop" if bg.lower().endswith(ae.VIDEO_EXTS) else "ảnh tĩnh"
    print(f"• Nền: {os.path.basename(bg)} ({kind}) | Hiệu ứng: {effect}/{intensity} | "
          f"Encoder: {enc}")
    print(f"• Audio: {os.path.basename(audio)} | Video dài: {adur:.0f}s "
          f"({adur / 3600:.2f}h) | loop nền {LOOP_SEC:.0f}s")

    tmp = tempfile.mkdtemp(prefix="sleep_")
    try:
        print("• (1/2) Dựng đoạn nền loop + hiệu ứng...")
        loop = _build_loopclip(bg, effect, intensity, tmp)

        print("• (2/2) Lặp nền cho hết audio + ghép tiếng + fade (video COPY -> nhanh)...")
        os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
        fo = max(0.0, adur - fade)
        cmd = [ae.FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
               "-stream_loop", "-1", "-i", loop, "-i", os.path.abspath(audio),
               "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
               "-af", f"afade=t=in:st=0:d={min(2.0, fade):.2f},afade=t=out:st={fo:.2f}:d={fade:.2f}",
               "-c:a", "aac", "-b:a", "192k", "-t", f"{adur:.3f}",
               "-movflags", "+faststart", os.path.abspath(out)]
        ae.run(cmd, timeout=None)
        print(f"\n✅ XONG: {os.path.abspath(out)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description="Tạo video ngủ dài: nền + hiệu ứng + audio")
    ap.add_argument("--bg", required=True, help="Ảnh (.jpg/.png) hoặc video nền (.mp4)")
    ap.add_argument("--audio", required=True, help="File audio dài (mp3/wav/m4a)")
    ap.add_argument("--out", default="output/sleep.mp4")
    ap.add_argument("--effect", choices=EFFECTS, default="rain")
    ap.add_argument("--intensity", choices=INTENSITIES, default="vua")
    ap.add_argument("--fade", type=float, default=4.0, help="Fade tiếng đầu/cuối (giây)")
    ap.add_argument("--max-seconds", type=float, default=None,
                    help="Giới hạn độ dài (để TEST nhanh, vd 60). Bỏ trống = cả audio.")
    ap.add_argument("--encoder", choices=["auto", "cpu"], default="auto")
    args = ap.parse_args()
    make_sleep_video(args.bg, args.audio, args.out, effect=args.effect,
                     intensity=args.intensity, fade=args.fade,
                     max_seconds=args.max_seconds, encoder=args.encoder)


if __name__ == "__main__":
    main()
