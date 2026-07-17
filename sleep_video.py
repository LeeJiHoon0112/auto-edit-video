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
# Song ngữ log theo AEV_LANG (như auto_edit.py); thiếu i18n.py -> giữ tiếng Việt
try:
    import i18n as _i18n
    from i18n import tr
    _i18n.set_lang(os.environ.get("AEV_LANG", "vi"))
except Exception:                                     # noqa
    def tr(s):
        return s

LOOP_SEC = 20.0          # độ dài đoạn nền loop (đủ dài để mắt không thấy lặp)
TEX_H = 2160             # cao texture; vstack đôi -> scroll dọc LIỀN MẠCH (không giật khi loop)

EFFECTS = ("none", "rain", "snow", "fog", "bokeh")
INTENSITIES = ("nhe", "vua", "nang")
VISUALIZERS = ("none", "bars", "waves")    # thanh nhạc / sóng âm (vẽ theo audio)

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


def _seamless_video_loop(clip, tmp, cap=LOOP_SEC, name="loopclip.mp4"):
    """Clip video nền -> bản LOOP LIỀN MẠCH: crossfade đuôi clip hòa vào đầu (frame cuối ≈
    frame đầu) -> lặp copy KHÔNG thấy điểm nối. Giữ NGUYÊN cảnh, không thêm gì.
    cap: cắt tối đa bấy nhiêu giây đầu (None = giữ NGUYÊN — dùng cho chuỗi FOLDER nhiều
    mục, cắt 20s sẽ mất các mục sau)."""
    d_full = ae.probe_duration(clip) or 10.0
    # CHỈ lấy tối đa LOOP_SEC giây ĐẦU clip để loop — KHÔNG re-encode cả clip. Clip nền dài
    # (vài phút) trên máy KHÔNG GPU (libx264): dựng cả clip -> vượt timeout 600s -> TREO
    # ("Tạo video ngủ thất bại mã 1"). Cắt còn ~LOOP_SEC: encode vài giây là xong, vẫn LOOP
    # LIỀN MẠCH + giữ nguyên cảnh (20s đầu clip là dư để mắt không thấy điểm lặp).
    d = min(d_full, float(cap)) if cap else d_full
    cf = min(1.2, max(0.4, d / 6.0))           # thời lượng crossfade (giây)
    out = os.path.join(tmp, name)
    # ĐỌC CLIP 2 LẦN (2 input) thay vì split: nhánh "đầu" và "đuôi" đọc ở vị trí lệch xa nhau
    # -> nếu dùng split, ffmpeg phải BUFFER cả clip trong RAM -> "Cannot allocate memory" với
    # clip dài / máy RAM thấp. 2 input decode ĐỘC LẬP -> không buffer -> nhẹ RAM, chạy máy yếu.
    scale = (f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
             f"crop={WIDTH}:{HEIGHT},fps={FPS},setsar=1")
    fc = (f"[0:v]{scale},trim=0:{d - cf:.3f},setpts=PTS-STARTPTS[b];"
          f"[1:v]{scale},trim=start={d - cf:.3f}:end={d:.3f},setpts=PTS-STARTPTS,format=yuva420p,"
          f"fade=t=out:st=0:d={cf:.3f}:alpha=1[t];"
          f"[b][t]overlay,format=yuv420p[out]")
    cmd = ([ae.FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", clip, "-i", clip,
            "-filter_complex", fc, "-map", "[out]", "-t", f"{d - cf:.3f}", "-r", str(FPS)]
           + ae.enc_args() + ["-pix_fmt", "yuv420p", out])
    ae.run(cmd, timeout=600)
    return out


IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def _norm_segment(src, idx, tmp, item_sec, effect, intensity):
    """Chuẩn hóa 1 mục trong FOLDER nền thành đoạn cùng kích thước/fps để ghép xoay vòng.
    Clip video -> lấy tối đa item_sec giây đầu; ảnh -> giữ item_sec giây (+hiệu ứng nếu chọn)."""
    out = os.path.join(tmp, f"seg{idx:02d}.mp4")
    scale = (f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
             f"crop={WIDTH}:{HEIGHT},fps={FPS},setsar=1")
    if src.lower().endswith(ae.VIDEO_EXTS):
        d = ae.probe_duration(src) or item_sec
        t = max(2.0, min(d, item_sec))
        cmd = ([ae.FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                "-vf", scale, "-t", f"{t:.3f}", "-an", "-r", str(FPS)]
               + ae.enc_args() + ["-pix_fmt", "yuv420p", out])
    else:
        if effect == "none":
            fc = f"[0:v]{scale}[out]"
            inputs = ["-loop", "1", "-i", src]
        else:
            tex = _make_texture(effect, intensity, tmp)
            fc = f"[0:v]{scale}[bg];" + _overlay(effect, intensity)
            inputs = ["-loop", "1", "-i", src, "-loop", "1", "-i", tex]
        cmd = ([ae.FFMPEG, "-y", "-hide_banner", "-loglevel", "error"] + inputs
               + ["-filter_complex", fc, "-map", "[out]", "-t", f"{item_sec:.3f}",
                  "-r", str(FPS)] + ae.enc_args() + ["-pix_fmt", "yuv420p", out])
    ae.run(cmd, timeout=600)
    return out


def _folder_loop(folder, effect, intensity, tmp, item_sec):
    """FOLDER nhiều ảnh/clip -> 1 đoạn nền XOAY VÒNG liền mạch: chuẩn hóa từng mục (theo
    tên file) -> nối crossfade -> hòa đuôi về mục đầu (seamless) -> loop-copy như thường."""
    files = sorted(f for f in os.listdir(folder)
                   if f.lower().endswith(ae.VIDEO_EXTS + IMG_EXTS))
    paths = [os.path.join(folder, f) for f in files]
    if not paths:
        raise SystemExit(tr(f"Thư mục nền không có ảnh/clip nào: {folder}"))
    if len(paths) == 1:
        return _build_loopclip(paths[0], effect, intensity, tmp, item_sec)
    # Giới hạn TỔNG thời lượng đoạn loop (máy KHÔNG GPU encode chuỗi quá dài sẽ treo
    # timeout — bài học gotcha #10). Thừa mục -> chỉ dùng các mục đầu.
    MAX_TOTAL = 240.0
    max_items = max(2, int(MAX_TOTAL // max(4.0, float(item_sec))))
    if len(paths) > max_items:
        print(tr(f"  (nhiều mục: dùng {max_items}/{len(paths)} mục đầu cho đoạn loop)"))
        paths = paths[:max_items]
    print(tr(f"• Ghép {len(paths)} mục nền (xoay vòng + crossfade, mỗi mục ≤{item_sec:g}s)..."))
    segs, durs = [], []
    for i, p in enumerate(paths):
        s = _norm_segment(p, i, tmp, item_sec, effect, intensity)
        segs.append(s)
        durs.append(ae.probe_duration(s) or item_sec)
    # Nối chuỗi bằng xfade (cf giây mỗi mối), rồi hòa đuôi↔đầu bằng _seamless_video_loop
    # (cap=None để GIỮ NGUYÊN cả chuỗi — cắt 20s sẽ mất các mục sau)
    cf = 1.0
    inputs, fc, prev = [], [], "[0:v]"
    for s in segs:
        inputs += ["-i", s]
    run_len = durs[0]
    for i in range(1, len(segs)):
        lbl = f"[x{i}]"
        fc.append(f"{prev}[{i}:v]xfade=transition=fade:duration={cf}:"
                  f"offset={run_len - cf:.3f}{lbl}")
        prev = lbl
        run_len += durs[i] - cf
    chain = os.path.join(tmp, "chain.mp4")
    cmd = ([ae.FFMPEG, "-y", "-hide_banner", "-loglevel", "error"] + inputs
           + ["-filter_complex", ";".join(fc), "-map", prev, "-t", f"{run_len:.3f}",
              "-r", str(FPS)] + ae.enc_args() + ["-pix_fmt", "yuv420p", chain])
    ae.run(cmd, timeout=600)
    return _seamless_video_loop(chain, tmp, cap=None)


def _build_loopclip(bg, effect, intensity, tmp, item_sec=20.0):
    """Dựng đoạn nền NGẮN loop LIỀN MẠCH. FOLDER nhiều ảnh/clip -> xoay vòng; clip video ->
    crossfade seamless (giữ nguyên cảnh); ảnh tĩnh -> render LOOP_SEC + (hiệu ứng nếu chọn)."""
    if os.path.isdir(bg):
        return _folder_loop(bg, effect, intensity, tmp, item_sec)
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


def _viz_filter(viz):
    """Trả (chuỗi filter audio -> [viz], vị trí overlay y) cho visualizer; None nếu 'none'.
    Dùng [av] = nhánh audio (sau asplit). Nền đen của visualizer bị colorkey/alpha bỏ ->
    chỉ còn thanh/sóng overlay lên video nền. Vị trí ~65% chiều cao (cao hơn đáy), dải MỎNG."""
    if viz == "bars":
        # volume + ascale=cbrt -> bars hiện RÕ kể cả khi nhạc ngủ êm (biên độ nhỏ)
        f = ("[av]volume=7,showfreqs=s=1920x120:mode=bar:ascale=cbrt:fscale=log:win_size=2048:"
             "colors=0x7fb4ff,format=rgba,colorkey=0x000000:0.18:0.08[viz]")
        return f, "H*0.66"
    if viz == "waves":
        # Kiểu VẠCH DỌC đối xứng (giống music bars): waveform (showwaves cline) NHÂN với
        # 'lưới sọc' comb (geq tính 1 LẦN nhờ loop) -> cắt sóng thành các vạch mảnh, gap
        # trong suốt lộ video nền. alphamerge: trắng + alpha theo biên độ -> mềm, dịu mắt.
        f = ("[av]volume=2.5,aformat=channel_layouts=mono,showwaves=s=1920x100:mode=cline:"
             "colors=0xffffff:scale=cbrt:rate=30,format=gray[wav];"
             "color=black:s=1920x100:r=30,geq=lum='if(lt(mod(X,24),7),255,0)':cb=128:cr=128,"
             "format=gray,loop=loop=-1:size=1[comb];"
             "[wav][comb]blend=all_mode=multiply,format=gray[mask];"
             "color=0xffffff:s=1920x100:r=30[col];"
             "[col][mask]alphamerge[viz]")
        return f, "H*0.65"
    return None, None


def make_sleep_video(bg, audio, out, effect="rain", intensity="vua", fade=4.0,
                     max_seconds=None, encoder="auto", viz="none",
                     ambient=None, ambient_volume=0.25, item_sec=20.0):
    if not ae.FFMPEG:
        raise SystemExit("Không tìm thấy ffmpeg.")
    if not (os.path.isfile(bg) or os.path.isdir(bg)):     # nhận cả FOLDER nhiều ảnh/clip
        raise SystemExit(f"Không thấy file/thư mục nền: {bg}")
    if not os.path.isfile(audio):
        raise SystemExit(f"Không thấy file audio: {audio}")
    enc = ae.detect_encoder(encoder)[0]
    adur = ae.probe_duration(audio) or 0.0
    if max_seconds and max_seconds > 0:
        adur = min(adur, float(max_seconds))
    if adur < 1:
        raise SystemExit("Audio quá ngắn / không đọc được độ dài.")

    if os.path.isdir(bg):
        n_items = len([f for f in os.listdir(bg)
                       if f.lower().endswith(ae.VIDEO_EXTS + IMG_EXTS)])
        kind = tr(f"thư mục {n_items} mục")
    elif bg.lower().endswith(ae.VIDEO_EXTS):
        kind = tr("video loop")
    else:
        kind = tr("ảnh tĩnh")
    print(tr(f"• Nền: {os.path.basename(bg)} ({kind}) | Hiệu ứng: {effect}/{intensity} | "
             f"Encoder: {enc}"))
    print(tr(f"• Audio: {os.path.basename(audio)} | Video dài: {adur:.0f}s "
             f"({adur / 3600:.2f}h) | loop nền {LOOP_SEC:.0f}s"))

    tmp = tempfile.mkdtemp(prefix="sleep_")
    try:
        print(tr("• (1/2) Dựng đoạn nền loop + hiệu ứng..."))
        loop = _build_loopclip(bg, effect, intensity, tmp, item_sec)

        os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
        fo = max(0.0, adur - fade)
        afade = (f"afade=t=in:st=0:d={min(2.0, fade):.2f},"
                 f"afade=t=out:st={fo:.2f}:d={fade:.2f}")

        # Âm thanh NỀN phụ (mưa/gió/tuyết) — input [2], TỰ LẶP cho đủ dài, trộn amix vào tiếng.
        has_amb = bool(ambient and os.path.isfile(ambient))
        amb_in = (["-stream_loop", "-1", "-i", os.path.abspath(ambient)] if has_amb else [])
        if has_amb:
            print(tr(f"• Âm thanh nền: {os.path.basename(ambient)} (âm lượng {ambient_volume})"))

        def _mix_to_a(voice_lbl):
            """voice_lbl (nhãn nhánh tiếng chính) [+ ambient] -> afade -> [a]."""
            if has_amb:
                return (f"[2:a]volume={ambient_volume}[amb];"
                        f"[{voice_lbl}][amb]amix=inputs=2:duration=first:normalize=0,{afade}[a]")
            return f"[{voice_lbl}]{afade}[a]"

        vfilt, yoff = _viz_filter(viz)
        if vfilt:
            # CÓ visualizer -> render FULL theo audio (không loop-copy được) -> chậm hơn
            print(tr("• (2/2) Render FULL + visualizer theo audio (lâu hơn vì vẽ theo nhạc)..."))
            fc = (f"[1:a]asplit=2[av][ao];{vfilt};"
                  f"[0:v][viz]overlay=0:{yoff}:format=auto,format=yuv420p[v];"
                  f"{_mix_to_a('ao')}")
            cmd = ([ae.FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                    "-stream_loop", "-1", "-i", loop, "-i", os.path.abspath(audio)]
                   + amb_in
                   + ["-filter_complex", fc, "-map", "[v]", "-map", "[a]"]
                   + ae.enc_args() + ["-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                    "-t", f"{adur:.3f}", "-movflags", "+faststart", os.path.abspath(out)])
        elif has_amb:
            # KHÔNG visualizer nhưng CÓ ambient -> video COPY, nhưng phải trộn tiếng (filter)
            print(tr("• (2/2) Lặp nền COPY + TRỘN âm thanh nền vào tiếng + fade..."))
            cmd = ([ae.FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                    "-stream_loop", "-1", "-i", loop, "-i", os.path.abspath(audio)]
                   + amb_in
                   + ["-filter_complex", _mix_to_a("1:a"), "-map", "0:v:0", "-map", "[a]",
                      "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{adur:.3f}",
                      "-movflags", "+faststart", os.path.abspath(out)])
        else:
            # Không viz, không ambient -> lặp nền COPY cho hết audio (RẤT NHANH)
            print(tr("• (2/2) Lặp nền cho hết audio + ghép tiếng + fade (video COPY -> nhanh)..."))
            cmd = [ae.FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                   "-stream_loop", "-1", "-i", loop, "-i", os.path.abspath(audio),
                   "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-af", afade,
                   "-c:a", "aac", "-b:a", "192k", "-t", f"{adur:.3f}",
                   "-movflags", "+faststart", os.path.abspath(out)]
        ae.run(cmd, timeout=None)
        print("\n" + tr(f"✅ XONG: {os.path.abspath(out)}"))
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
    ap.add_argument("--viz", choices=VISUALIZERS, default="none",
                    help="Visualizer âm thanh: none | bars (thanh nhạc) | waves (sóng). "
                         "Bật -> render FULL theo audio (lâu hơn nhiều).")
    ap.add_argument("--ambient", default=None,
                    help="File âm thanh NỀN phụ (mưa/gió/tuyết...) trộn cùng voice; tự lặp cho đủ dài.")
    ap.add_argument("--ambient-volume", type=float, default=0.25,
                    help="Âm lượng âm thanh nền (0-1), mặc định 0.25 (nhẹ).")
    ap.add_argument("--item-sec", type=float, default=20.0,
                    help="Khi --bg là FOLDER nhiều ảnh/clip: số giây mỗi mục trong vòng xoay "
                         "(ảnh giữ đúng bấy nhiêu; clip lấy tối đa bấy nhiêu giây đầu).")
    args = ap.parse_args()
    make_sleep_video(args.bg, args.audio, args.out, effect=args.effect,
                     intensity=args.intensity, fade=args.fade,
                     max_seconds=args.max_seconds, encoder=args.encoder, viz=args.viz,
                     ambient=args.ambient, ambient_volume=args.ambient_volume,
                     item_sec=args.item_sec)


if __name__ == "__main__":
    main()
