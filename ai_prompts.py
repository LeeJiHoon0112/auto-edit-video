#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai_prompts.py — Gọi Google Gemini để tự viết PROMPT VIDEO cho từng cảnh.

Gọi REST API trực tiếp bằng thư viện chuẩn (urllib) -> KHÔNG cần cài package.
Lấy API key miễn phí tại: https://aistudio.google.com  (Get API key)

Tự động chọn model còn hạn mức: nếu model đầu bị 429/404 sẽ thử model kế tiếp.
"""
import json
import urllib.request
import urllib.error

# Thứ tự ưu tiên model (cái nào còn free + chạy được thì dùng)
PREFERRED_MODELS = [
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
]
GEMINI_MODEL = PREFERRED_MODELS[0]
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


class GeminiError(Exception):
    def __init__(self, code, detail=""):
        self.code = code
        self.detail = detail
        super().__init__(f"HTTP {code}: {detail[:200]}")


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
        raise GeminiError(e.code, e.read().decode("utf-8", "replace"))
    except urllib.error.URLError as e:
        raise GeminiError(0, str(e.reason))
    cands = data.get("candidates", [])
    if not cands:
        raise GeminiError(599, "Gemini không trả về kết quả (nội dung có thể bị chặn).")
    parts = cands[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts)


def _friendly(err):
    if isinstance(err, GeminiError):
        if err.code in (400, 403):
            return "API key sai hoặc bị từ chối (kiểm tra lại key)."
        if err.code == 429:
            return ("Hết hạn mức miễn phí của Gemini (HTTP 429) trên mọi model thử được. "
                    "Chờ ít phút rồi thử lại, hoặc bật billing trong Google AI Studio.")
        if err.code == 404:
            return "Không tìm thấy model hợp lệ cho key này."
        if err.code == 0:
            return f"Không kết nối được Internet/Gemini: {err.detail}"
        return f"Lỗi Gemini: {err.detail[:200]}"
    return str(err)


def find_working_model(api_key, models=None):
    """Trả về model đầu tiên còn dùng được, hoặc raise GeminiError."""
    last = None
    for m in (models or PREFERRED_MODELS):
        try:
            _call(api_key, m, "Reply with the single word OK.", "Say OK", timeout=30)
            return m
        except GeminiError as e:
            last = e
            if e.code in (404, 429):
                continue
            raise
    raise last or GeminiError(0, "no model")


def check_connection(api_key, model=None):
    """Trả về (ok: bool, message: str, model: str|None)."""
    if not api_key or not api_key.strip():
        return False, "Chưa nhập API key.", None
    try:
        m = find_working_model(api_key.strip())
        return True, f"Kết nối Gemini THÀNH CÔNG ✓ (model: {m})", m
    except Exception as e:  # noqa
        return False, _friendly(e), None


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


def generate_prompts(scenes_text, style, api_key, model=None,
                     batch=20, progress=None):
    """
    scenes_text : list[str] — lời nói của từng cảnh, theo thứ tự.
    style       : str       — Visual Style Profile của kênh.
    Trả về list[str] prompt, cùng độ dài scenes_text. Tự đổi model nếu 429/404.
    """
    if not api_key or not api_key.strip():
        raise RuntimeError("Chưa nhập API key (vào tab Cài đặt).")
    if not style or not style.strip():
        raise RuntimeError("Chưa có Style Profile (vào tab Cài đặt để thêm/chọn).")

    api_key = api_key.strip()
    system = SYSTEM_TEMPLATE.format(style=style.strip())
    order = ([model] if model else []) + [m for m in PREFERRED_MODELS if m != model]
    chosen = None
    out = []
    n = len(scenes_text)

    for start in range(0, n, batch):
        chunk = scenes_text[start:start + batch]
        listing = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(chunk))
        user = (f"Here are {len(chunk)} scenes. Write one video prompt for each, "
                f"returning a JSON array of exactly {len(chunk)} strings, in order.\n\n{listing}")

        models_try = ([chosen] if chosen else []) + [m for m in order if m != chosen]
        txt, last = None, None
        for m in models_try:
            try:
                txt = _call(api_key, m, system, user)
                chosen = m
                break
            except GeminiError as e:
                last = e
                if e.code in (404, 429):
                    continue
                raise RuntimeError(_friendly(e))
        if txt is None:
            raise RuntimeError(_friendly(last))

        out.extend(_parse_array(txt, len(chunk)))
        if progress:
            progress(min(start + batch, n), n)
    return out
