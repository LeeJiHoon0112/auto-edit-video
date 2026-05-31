#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai_prompts.py — Gọi Google Gemini để tự viết PROMPT VIDEO cho từng cảnh.

Gọi REST API trực tiếp bằng thư viện chuẩn (urllib) -> KHÔNG cần cài package.
Lấy API key miễn phí tại: https://aistudio.google.com  (Get API key)
"""
import json
import urllib.request
import urllib.error

GEMINI_MODEL = "gemini-2.0-flash"
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

SYSTEM_TEMPLATE = """You are an expert at writing VIDEO-generation prompts (for tools like Google Veo) for faceless narrated videos.

You will receive a numbered list of scenes; each scene has the NARRATION spoken during it.
For EACH scene, write ONE concise English video prompt that:
- Visually conveys the MEANING of that scene's narration (not a literal word-for-word transcription).
- Describes MOTION / action (these are short moving video clips, not still images): use action verbs.
- STRICTLY follows this VISUAL STYLE PROFILE, applied to every prompt, keeping the character/style consistent across all scenes:
---
{style}
---
- Is concise and iconic (about 1-2 sentences), written in English.

Return ONLY a JSON array of strings: exactly one prompt per scene, in the SAME ORDER as given. No commentary, no extra keys."""


def _call(api_key, model, system, user, timeout=120):
    url = f"{API_BASE}/{model}:generateContent?key={api_key}"
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0.85, "responseMimeType": "application/json"},
    }
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        if e.code in (400, 403):
            raise RuntimeError(f"API key sai hoặc bị từ chối (HTTP {e.code}).")
        if e.code == 429:
            raise RuntimeError("Vượt giới hạn miễn phí (HTTP 429). Chờ một lát rồi thử lại.")
        raise RuntimeError(f"Lỗi HTTP {e.code}: {detail[:200]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Không kết nối được Internet/Gemini: {e.reason}")
    cands = data.get("candidates", [])
    if not cands:
        raise RuntimeError("Gemini không trả về kết quả (có thể nội dung bị chặn).")
    parts = cands[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts)


def check_connection(api_key, model=GEMINI_MODEL):
    """Kiểm tra key + kết nối. Trả về (ok: bool, message: str)."""
    if not api_key or not api_key.strip():
        return False, "Chưa nhập API key."
    try:
        _call(api_key.strip(), model, "Reply with the single word OK.", "Say OK", timeout=30)
        return True, "Kết nối Gemini THÀNH CÔNG ✓"
    except Exception as e:  # noqa
        return False, str(e)


def _parse_array(txt, expected):
    txt = (txt or "").strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        nl = txt.find("\n")
        if nl != -1 and len(txt[:nl]) < 12:
            txt = txt[nl + 1:]
    try:
        arr = json.loads(txt)
        if isinstance(arr, list):
            arr = [str(x).replace("\n", " ").strip() for x in arr]
            if len(arr) < expected:
                arr += [""] * (expected - len(arr))
            return arr[:expected]
    except Exception:
        pass
    lines = [ln.strip(" -\t\"").strip() for ln in txt.splitlines() if ln.strip()]
    if len(lines) < expected:
        lines += [""] * (expected - len(lines))
    return lines[:expected]


def generate_prompts(scenes_text, style, api_key, model=GEMINI_MODEL,
                     batch=20, progress=None):
    """
    scenes_text : list[str] — lời nói (narration) của từng cảnh, theo thứ tự.
    style       : str       — Visual Style Profile của kênh.
    Trả về list[str] prompt, cùng độ dài với scenes_text.
    """
    if not api_key or not api_key.strip():
        raise RuntimeError("Chưa nhập API key (vào tab Cài đặt).")
    if not style or not style.strip():
        raise RuntimeError("Chưa có Style Profile (vào tab Cài đặt để thêm/chọn).")

    api_key = api_key.strip()
    system = SYSTEM_TEMPLATE.format(style=style.strip())
    out = []
    n = len(scenes_text)
    for start in range(0, n, batch):
        chunk = scenes_text[start:start + batch]
        listing = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(chunk))
        user = (f"Here are {len(chunk)} scenes. Write one video prompt for each, "
                f"returning a JSON array of exactly {len(chunk)} strings, in order.\n\n{listing}")
        txt = _call(api_key, model, system, user)
        out.extend(_parse_array(txt, len(chunk)))
        if progress:
            progress(min(start + batch, n), n)
    return out
