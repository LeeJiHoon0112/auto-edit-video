#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai_prompts.py — Gọi Google Gemini để tự viết PROMPT VIDEO cho từng cảnh.

Gọi REST API trực tiếp bằng thư viện chuẩn (urllib) -> KHÔNG cần cài package.
Lấy API key miễn phí tại: https://aistudio.google.com  (Get API key)

Tự động chọn model còn hạn mức: nếu model đầu bị 429/404 sẽ thử model kế tiếp.
"""
import json
import re
import sys
import time
import urllib.request
import urllib.error

# Model ưu tiên cho từng NHÀ CUNG CẤP (cái ĐẦU = rẻ/tốt mặc định, sau là dự phòng).
MODELS = {
    "gemini": ["gemini-3.5-flash", "gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash-lite"],
    "openai": ["gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.5"],
    "claude": ["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-8"],
}
PROVIDERS = list(MODELS.keys())
PROVIDER_LABEL = {"gemini": "Google Gemini", "openai": "OpenAI", "claude": "Anthropic Claude"}

# Số cảnh gửi mỗi lượt (batch). Claude/OpenAI tuân thủ JSON ổn định -> gửi nhiều để
# bớt lặp lại system prompt (tiết kiệm token input). Gemini hay lỗi JSON khi batch lớn
# -> giữ nhỏ. (đã test thật: Claude 24 cảnh/lượt sạch, không cắt cụt/lệch.)
DEFAULT_BATCH = {"gemini": 12, "openai": 24, "claude": 24}

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
# Tương thích tên cũ
PREFERRED_MODELS = MODELS["gemini"]
GEMINI_MODEL = PREFERRED_MODELS[0]
API_BASE = GEMINI_BASE

# ─────────────────────────────────────────────────────────────────────────────
# Chế độ "kèm style" (embed_style=True) khi profile là JSON có scene_modes:
#   Gemini CHỈ lo NỘI DUNG + MÀU/ERA (chọn scene_mode), KHÔNG mô tả art-style.
#   Câu ART-STYLE cố định do TOOL tự ghép (xem _style_caption) -> đồng nhất 100%.
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_SPLIT_VIDEO = """You write the CONTENT of VIDEO-generation prompts (for tools like Google Veo) for faceless narrated videos. The ART-STYLE (line work, shading, how characters are drawn) is controlled separately — by a fixed style caption or a visual style lock — so you MUST NOT describe the art style, line work, rendering, textures, or how things are drawn. Focus on WHAT happens and the COLOUR / ERA setting.

You will receive a numbered list of scenes; each scene has the NARRATION spoken during it.
For EACH scene, write ONE concise English line that:
- Visually conveys the MEANING of the narration (not a literal word-for-word transcription).
- Describes MOTION / action (a short moving clip): use action verbs.
- Keep each scene to ONE single action/moment; do NOT chain events with "then" / "transitions to" / "followed by" (each clip lasts only a few seconds).
- SHOT VARIETY & VISUAL HOOK: strongly VARY the shot type across scenes — wide establishing, medium, close-up, extreme close-up of eyes/hands/an object, over-the-shoulder, low or high angle, tilted/Dutch angle, framed through a foreground object or doorway, silhouette, reflection, or POV; compose with DEPTH and ONE clear eye-catching focal point. Do NOT repeat the same framing, and avoid a plain centred talking figure. For an ABSTRACT idea (an emotion, a concept, anything with no literal scene), show a striking visual METAPHOR or symbolic image instead of a person standing.
- NAME THE SHOT (MANDATORY): state the shot type and angle EXPLICITLY in every line (e.g. "Low-angle close-up of...", "Wide establishing shot of..."). Never give two consecutive scenes the same shot type.
- CAMERA MOVE (MANDATORY — this is a moving clip): give each scene exactly ONE camera movement — slow push-in, pull-back, pan, tilt, tracking/follow, slow orbit, gentle handheld sway, or locked-off static — VARY it from scene to scene and match its speed to the narration's energy (tense = faster, sharper; calm = slow, settling).
- NARRATIVE ARC (read the WHOLE list before writing): a scene that OPENS a new idea → wide establishing; scenes that BUILD the idea → medium framings; the most emotional or most important line of a section → close-up or extreme close-up; a small object or piece of evidence → detail insert; the FINAL scene → a settling wide or a slow pull-back. The result must feel like a film edited by a human, not a row of similar shots.
- CONCRETE DETAIL: fill the frame with SPECIFIC tangible detail — name the key objects/props and what sits in the foreground vs the background, and show the character's exact posture, gesture and gaze. Never settle for a generic "person with an expression"; make every frame specific and rich.
- COLOUR / ERA: a style profile JSON with "scene_modes" is given below. Pick the scene_mode whose "when" best matches this scene's era/topic and apply ONLY its background, palette and lighting (the colours and setting). Do NOT describe the drawing style itself.
- CHARACTER CONSISTENCY (MANDATORY): the "characters" field lists distinct character types with their visual traits. Every time a human appears in a scene, follow BOTH steps:
  STEP 1 — IDENTIFY the correct type from context: prehistoric / hunting / savannah / ancient era → use ancient_human traits. Present-day / technology / office / modern life → use modern_human traits. Other types (scientist, child, etc.) → match accordingly.
  STEP 2 — WRITE every key trait of that type explicitly (hair, clothing, build). Never write a vague "person", "human", "figure", or "character" alone — always attach the full visual description so the generator renders them correctly. Skipping even one trait causes visual inconsistency across clips.
- NEVER write a scene_mode KEY name (such as "ancient_day", "night", "concept", "modern") in the text; describe the colours in plain words instead.
- Do NOT begin with a label like "MODERN:".

STYLE PROFILE (scene_modes = colour/era; characters = who looks like what; art style added separately):
---
{style}
---

Return ONLY a JSON array of strings: exactly one line per scene, in the SAME ORDER as given. No commentary, no extra keys."""

SYSTEM_SPLIT_IMAGE = """You write the CONTENT of STILL-IMAGE prompts for AI generators (such as Veo's image mode) for faceless narrated videos. The ART-STYLE (line work, shading, how characters are drawn) is controlled separately — by a fixed style caption or a visual style lock — so you MUST NOT describe the art style, line work, rendering, textures, or how things are drawn. Focus on WHAT appears and the COLOUR / ERA setting.

You will receive a numbered list of scenes; each scene has the NARRATION spoken during it.
For EACH scene, write ONE concise English line that:
- Visually conveys the MEANING of the narration (not a literal word-for-word transcription).
- Describes a SINGLE STILL moment (subject, setting, framing). Do NOT describe motion or camera movement — one frozen frame held still.
- SHOT VARIETY & VISUAL HOOK: strongly VARY the shot type across scenes — wide establishing, medium, close-up, extreme close-up of eyes/hands/an object, over-the-shoulder, low or high angle, tilted/Dutch angle, framed through a foreground object or doorway, silhouette, reflection, or POV; compose with DEPTH and ONE clear eye-catching focal point. Do NOT repeat the same framing, and avoid a plain centred talking figure. For an ABSTRACT idea (an emotion, a concept, anything with no literal scene), show a striking visual METAPHOR or symbolic image instead of a person standing.
- NAME THE SHOT (MANDATORY): state the shot type and angle EXPLICITLY in every line (e.g. "Low-angle close-up of...", "Wide establishing shot of..."). Never give two consecutive scenes the same shot type.
- NARRATIVE ARC (read the WHOLE list before writing): a scene that OPENS a new idea → wide establishing; scenes that BUILD the idea → medium framings; the most emotional or most important line of a section → close-up or extreme close-up; a small object or piece of evidence → detail insert; the FINAL scene → a settling wide. The result must feel like a film edited by a human, not a row of similar shots.
- CONCRETE DETAIL: fill the frame with SPECIFIC tangible detail — name the key objects/props and what sits in the foreground vs the background, and show the character's exact posture, gesture and gaze. Never settle for a generic "person with an expression"; make every frame specific and rich.
- COLOUR / ERA: a style profile JSON with "scene_modes" is given below. Pick the scene_mode whose "when" best matches this scene's era/topic and apply ONLY its background, palette and lighting (the colours and setting). Do NOT describe the drawing style itself.
- CHARACTER CONSISTENCY (MANDATORY): the "characters" field lists distinct character types with their visual traits. Every time a human appears in a scene, follow BOTH steps:
  STEP 1 — IDENTIFY the correct type from context: prehistoric / hunting / savannah / ancient era → use ancient_human traits. Present-day / technology / office / modern life → use modern_human traits. Other types (scientist, child, etc.) → match accordingly.
  STEP 2 — WRITE every key trait of that type explicitly (hair, clothing, build). Never write a vague "person", "human", "figure", or "character" alone — always attach the full visual description so the generator renders them correctly. Skipping even one trait causes visual inconsistency across clips.
- NEVER write a scene_mode KEY name (such as "ancient_day", "night", "concept", "modern") in the text; describe the colours in plain words instead.
- Do NOT begin with a label like "MODERN:".

STYLE PROFILE (use ONLY scene_modes for colour/era; the art style is added separately):
---
{style}
---

Return ONLY a JSON array of strings: exactly one line per scene, in the SAME ORDER as given. No commentary, no extra keys."""


SYSTEM_CONTENT_VIDEO = """You describe ONLY the visual CONTENT of each scene for a video generator (faceless narrated videos). A separate visual-style system already controls the art style, so you MUST NOT mention any art style, rendering, colors, line work, textures, or visual aesthetics.

For EACH scene (you get its NARRATION), write ONE short English line describing:
- WHO / WHAT appears and a minimal setting.
- The ACTION / motion happening (use action verbs — it is a moving clip).
- SHOT VARIETY & VISUAL HOOK: strongly vary the shot type (wide, medium, close-up, extreme close-up of eyes/hands/an object, over-the-shoulder, low/high/tilted angle, foreground-framed, silhouette, reflection, POV); compose with depth and one eye-catching focal point; avoid repeating the same framing or a plain centred talking figure. For an abstract idea, use a striking visual metaphor instead of a person standing. Fill the frame with SPECIFIC tangible detail (key objects/props, foreground vs background, the character's exact posture/gesture/gaze); never settle for a generic "person with an expression".
- NAME THE SHOT + CAMERA MOVE (MANDATORY): every line states its shot type/angle explicitly AND exactly one camera movement (slow push-in, pull-back, pan, tilt, tracking/follow, slow orbit, gentle handheld, locked-off static) — never the same shot type or the same move in two consecutive scenes; movement speed matches the narration's energy (tense = faster, calm = slow).
- NARRATIVE ARC (read the whole list first): a scene opening a new idea → wide establishing; building scenes → medium; the emotional peak of a section → (extreme) close-up; a small object → detail insert; the final scene → settling wide or slow pull-back. The video must feel edited by a human, not a row of similar shots.
Keep it to ONE concise sentence. Do NOT describe style, colors, or how it is drawn/rendered.

Return ONLY a JSON array of strings, exactly one per scene, in the SAME ORDER. No commentary, no extra keys."""

SYSTEM_CONTENT_IMAGE = """You describe ONLY the visual CONTENT of each scene for an image generator (faceless narrated videos). A separate visual-style system already controls the art style, so you MUST NOT mention any art style, rendering, colors, line work, textures, or visual aesthetics.

For EACH scene (you get its NARRATION), write ONE short English line describing:
- WHO / WHAT appears and a minimal setting (a single STILL moment — no motion, no camera movement).
- SHOT VARIETY & VISUAL HOOK: strongly vary the shot type (wide, medium, close-up, extreme close-up of eyes/hands/an object, over-the-shoulder, low/high/tilted angle, foreground-framed, silhouette, reflection, POV); compose with depth and one eye-catching focal point; avoid repeating the same framing or a plain centred talking figure. For an abstract idea, use a striking visual metaphor instead of a person standing. Fill the frame with SPECIFIC tangible detail (key objects/props, foreground vs background, the character's exact posture/gesture/gaze); never settle for a generic "person with an expression".
- NAME THE SHOT (MANDATORY): every line states its shot type/angle explicitly (e.g. "Low-angle close-up of...") — never the same shot type in two consecutive scenes.
- NARRATIVE ARC (read the whole list first): a scene opening a new idea → wide establishing; building scenes → medium; the emotional peak of a section → (extreme) close-up; a small object → detail insert; the final scene → settling wide. The set must feel edited by a human, not a row of similar shots.
Keep it to ONE concise sentence. Do NOT describe style, colors, or how it is drawn/rendered.

Return ONLY a JSON array of strings, exactly one per scene, in the SAME ORDER. No commentary, no extra keys."""


class GeminiError(Exception):
    def __init__(self, code, detail=""):
        self.code = code
        self.detail = detail
        super().__init__(f"HTTP {code}: {detail[:200]}")


def _http(url, headers, data=None, timeout=120):
    """POST (data != None) hoặc GET (data == None). Trả JSON đã parse.
    Lỗi HTTP -> GeminiError(code, detail)."""
    method = "POST" if data is not None else "GET"
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise GeminiError(e.code, e.read().decode("utf-8", "replace"))
    except urllib.error.URLError as e:
        raise GeminiError(0, str(e.reason))


def _call_gemini(api_key, model, system, user, timeout=120):
    url = f"{GEMINI_BASE}/{model}:generateContent?key={api_key}"
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0.85, "responseMimeType": "application/json",
                             "maxOutputTokens": 8192},
    }
    data = _http(url, {"Content-Type": "application/json"},
                 json.dumps(body).encode("utf-8"), timeout)
    cands = data.get("candidates", [])
    if not cands:
        raise GeminiError(599, "Gemini không trả về kết quả (nội dung có thể bị chặn).")
    parts = cands[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts)


def _call_openai(api_key, model, system, user, timeout=120):
    # GPT-5.x: dùng 'max_completion_tokens' (KHÔNG dùng 'max_tokens') + KHÔNG gửi
    # 'temperature' (chỉ nhận mặc định). Để cao đủ chỗ cho reasoning + output.
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "max_completion_tokens": 16000,
    }
    data = _http("https://api.openai.com/v1/chat/completions",
                 {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                 json.dumps(body).encode("utf-8"), timeout)
    ch = data.get("choices", [])
    if not ch:
        raise GeminiError(599, "OpenAI không trả về kết quả.")
    return ch[0].get("message", {}).get("content", "") or ""


def _call_claude(api_key, model, system, user, timeout=120):
    body = {
        "model": model, "max_tokens": 8192, "temperature": 0.85,
        "system": system, "messages": [{"role": "user", "content": user}],
    }
    data = _http("https://api.anthropic.com/v1/messages",
                 {"Content-Type": "application/json", "x-api-key": api_key,
                  "anthropic-version": "2023-06-01"},
                 json.dumps(body).encode("utf-8"), timeout)
    blocks = data.get("content", [])
    if not blocks:
        raise GeminiError(599, "Claude không trả về kết quả.")
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


_CALLERS = {"gemini": _call_gemini, "openai": _call_openai, "claude": _call_claude}


def _call(provider, api_key, model, system, user, timeout=120):
    fn = _CALLERS.get(provider)
    if not fn:
        raise GeminiError(0, f"Nhà cung cấp không hỗ trợ: {provider}")
    return fn(api_key, model, system, user, timeout)


def _friendly(err):
    if isinstance(err, GeminiError):
        if err.code in (400, 401, 403):
            return "API key sai hoặc bị từ chối (kiểm tra lại key + nhà cung cấp)."
        if err.code == 429:
            return ("Hết hạn mức / quá nhiều yêu cầu (HTTP 429) trên mọi model thử được. "
                    "Chờ ít phút rồi thử lại, bật billing, hoặc đổi nhà cung cấp.")
        if err.code in (500, 502, 503):
            return ("Máy chủ AI quá tải tạm thời (HTTP %d). Đã tự thử lại vài lần không được. "
                    "Chờ một lát rồi bấm lại." % err.code)
        if err.code == 404:
            return "Không tìm thấy model hợp lệ cho key này."
        if err.code == 0:
            return f"Không kết nối được Internet/API: {err.detail}"
        return f"Lỗi API: {err.detail[:200]}"
    return str(err)


def list_models(provider, api_key, timeout=15):
    """Liệt kê model của 1 nhà cung cấp (1 GET, NHẸ, KHÔNG sinh nội dung -> nhanh +
    không tốn/đụng quota generate). Dùng để kiểm tra kết nối + xác thực key."""
    if provider == "gemini":
        data = _http(f"{GEMINI_BASE}?key={api_key}&pageSize=200", None, None, timeout)
        out = []
        for m in data.get("models", []):
            nm = m.get("name", "")
            if nm.startswith("models/"):
                nm = nm[len("models/"):]
            methods = m.get("supportedGenerationMethods", [])
            if nm and (not methods or "generateContent" in methods):
                out.append(nm)
        return out
    if provider == "openai":
        data = _http("https://api.openai.com/v1/models",
                     {"Authorization": f"Bearer {api_key}"}, None, timeout)
        return [m.get("id", "") for m in data.get("data", []) if m.get("id")]
    if provider == "claude":
        data = _http("https://api.anthropic.com/v1/models",
                     {"x-api-key": api_key, "anthropic-version": "2023-06-01"}, None, timeout)
        return [m.get("id", "") for m in data.get("data", []) if m.get("id")]
    return []


_OPENAI_SKIP = ("embed", "whisper", "tts", "dall", "image", "audio", "realtime",
                "transcribe", "moderation", "search", "codex", "babbage",
                "davinci", "instruct", "preview")


def list_chat_models(provider, api_key):
    """Danh sách model CHAT đã LỌC gọn để hiện trong ô Model (bỏ embedding/audio/ảnh/
    bản gắn ngày...), MỚI lên đầu. Lỗi -> trả []. Dùng cho ô Model TỰ cập nhật theo API."""
    try:
        ids = list_models(provider, api_key)
    except Exception:  # noqa
        return []
    if provider == "openai":
        out = [m for m in ids if m.startswith("gpt-")
               and not any(s in m for s in _OPENAI_SKIP)
               and not re.search(r"-\d{4}", m)]        # bỏ bản gắn ngày, giữ alias
    elif provider == "claude":
        out = [m for m in ids if m.startswith("claude-")]
    elif provider == "gemini":
        out = [m for m in ids if m.startswith("gemini-")]
    else:
        out = list(ids)
    return sorted(set(out), reverse=True)              # model mới (version cao) lên đầu


def check_connection(provider, api_key, model=None):
    """Trả về (ok, message, model). Kiểm tra NHANH bằng danh sách model (1 GET) ->
    không tốn quota generate. Chọn model TỐT NHẤT đang có cho nhà cung cấp đó."""
    if not api_key or not api_key.strip():
        return False, "Chưa nhập API key.", None
    try:
        available = list_models(provider, api_key.strip())
    except Exception as e:  # noqa
        return False, _friendly(e), None
    pref = MODELS.get(provider, [])
    avail = set(available)
    # Ưu tiên model ĐANG CHỌN (model truyền vào); nếu chưa chọn thì lấy model tốt nhất
    # theo thứ tự ưu tiên. (alias '-latest' của Claude có thể không liệt kê nhưng vẫn gọi được)
    chosen = model or (next((m for m in pref if m in avail), None)
                       or (pref[0] if pref else (available[0] if available else None)))
    if chosen:
        label = PROVIDER_LABEL.get(provider, provider)
        return True, f"Kết nối {label} THÀNH CÔNG ✓ (model: {chosen})", chosen
    return False, "Key hợp lệ nhưng không có model dùng được cho key này.", None


def _parse_array(txt, expected):
    txt = (txt or "").strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        nl = txt.find("\n")
        if nl != -1 and len(txt[:nl]) < 12:
            txt = txt[nl + 1:]
    txt = txt.strip()

    # 1) Thử JSON trực tiếp + vài cách "vá" khi bị cắt cụt
    candidates = [txt]
    fixed = txt.rstrip().rstrip(",")
    if fixed and not fixed.endswith("]"):
        # nếu thiếu ] cuối (có thể do bị cắt), thử thêm vào
        candidates += [fixed + "]", fixed + '"]']
    for cand in candidates:
        try:
            arr = json.loads(cand)
            if isinstance(arr, list) and arr:
                # KHÔNG lọc item rỗng (if str(x).strip()) để giữ đúng VỊ TRÍ từng cảnh.
                # Lọc sẽ gây LỆCH: ["A","","C"] -> ["A","C",""] -> cảnh 2 nhận prompt cảnh 3.
                arr = [str(x).replace("\n", " ").strip() for x in arr]
                if len(arr) < expected:
                    arr += [""] * (expected - len(arr))
                return arr[:expected]
        except Exception:
            pass

    # 1b) Model (OpenAI/Claude) có thể thêm lời dẫn -> rút mảng JSON nằm giữa [ ... ]
    i, jx = txt.find("["), txt.rfind("]")
    if i != -1 and jx > i:
        try:
            arr = json.loads(txt[i:jx + 1])
            if isinstance(arr, list) and arr:
                arr = [str(x).replace("\n", " ").strip() for x in arr]
                if len(arr) < expected:
                    arr += [""] * (expected - len(arr))
                return arr[:expected]
        except Exception:
            pass

    # 2) Fallback: tách dòng + dọn sạch [ ] " , ở 2 đầu
    lines = []
    for ln in txt.splitlines():
        s = ln.strip()
        if s in ("[", "]", "",):
            continue
        s = s.strip(",").strip().strip('"').strip().strip(",").strip()
        if s.startswith("- "):
            s = s[2:].strip()
        if s:
            lines.append(s)
    if len(lines) < expected:
        lines += [""] * (expected - len(lines))
    return lines[:expected]


def _as_json(style):
    """Thử đọc Style Profile dạng JSON dict; không phải JSON thì trả None."""
    try:
        d = json.loads(style)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def _scene_modes_present(style):
    d = _as_json(style)
    return bool(d and isinstance(d.get("scene_modes"), dict) and d["scene_modes"])


def _scene_mode_keys(style):
    d = _as_json(style)
    if d and isinstance(d.get("scene_modes"), dict):
        return list(d["scene_modes"].keys())
    return []


def _character_keys(style):
    """Tên KEY trong 'characters' (vd modern_human, ancient_human). AI đôi khi copy
    nguyên key có gạch dưới vào prompt -> cần đổi '_' thành khoảng trắng cho dễ đọc."""
    d = _as_json(style)
    if d and isinstance(d.get("characters"), dict):
        return list(d["characters"].keys())
    return []


# ─── Robust style parsing: ĐỌC ĐƯỢC MỌI cấu trúc JSON profile (kể cả lồng / tên lạ) ──
# Tên field NÉT (cho caption). So khớp substring sau khi chuẩn hoá -> nhận nhiều biến thể.
_CAPTION_FIELDS = ("art_style", "artstyle", "art_direction", "line_work", "linework",
                   "lineart", "outline", "shading_lighting", "shading", "rendering",
                   "render_style", "aesthetic", "full_prompt", "full_style_tag", "style_tag")
_MOOD_FIELDS = ("mood", "tone", "atmosphere")
# Tên field NỘI DUNG (gửi AI lo màu/bối cảnh/nhân vật/góc máy).
_AI_FIELDS = ("scene_mode", "scenes", "color_palette", "colour_palette", "colors",
              "colours", "palette", "characters", "character", "variety", "composition",
              "camera")


def _norm_key(k):
    return str(k).lower().replace("-", "_").replace(" ", "_")


def _to_text(obj):
    """Làm phẳng dict/list/scalar lồng nhau thành text đọc được (bỏ tên key cho gọn)."""
    if isinstance(obj, bool):
        return ""
    if isinstance(obj, str):
        return obj.strip()
    if isinstance(obj, (int, float)):
        return str(obj)
    if isinstance(obj, list):
        return ", ".join(t for t in (_to_text(x) for x in obj) if t)
    if isinstance(obj, dict):
        return "; ".join(t for t in (_to_text(v) for v in obj.values()) if t)
    return ""


def _deep_collect(obj, names):
    """Duyệt ĐỆ QUY: mỗi key khớp tên (substring sau norm) -> lấy text value 1 lần,
    không đi sâu vào key đã khớp. Nhờ vậy field lồng mấy lớp cũng moi ra được."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if any(n in _norm_key(k) for n in names):
                t = _to_text(v)
                if t:
                    out.append(t)
            else:
                out.extend(_deep_collect(v, names))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_deep_collect(v, names))
    return out


def _style_caption(style):
    """Câu ART-STYLE CỐ ĐỊNH (text) để TOOL tự ghép vào MỌI prompt.

    ROBUST: đọc được MỌI cấu trúc JSON — tìm sâu các field nét (kể cả lồng / tên lạ),
    và nếu không khớp tên nào thì FALLBACK làm phẳng cả JSON -> KHÔNG BAO GIỜ rỗng.
    Profile text thuần -> dùng nguyên văn.
    """
    s = (style or "").strip()
    if not s:
        return ""
    d = _as_json(s)
    if d is None:
        return s                                   # text thuần -> dùng nguyên
    parts = _deep_collect(d, _CAPTION_FIELDS)       # gom phần NÉT (tìm sâu)
    mood = _deep_collect(d, _MOOD_FIELDS)
    if mood:
        parts.append("overall mood: " + mood[0])
    if not parts:
        # FALLBACK: JSON cấu trúc lạ -> làm phẳng toàn bộ (bỏ phần động scene/character)
        skip = ("scene_mode", "scenes", "character")
        leftover = {k: v for k, v in d.items()
                    if not any(x in _norm_key(k) for x in skip)}
        flat = _to_text(leftover or d)
        return flat
    parts = [p.rstrip(" .") for p in parts if p.strip()]
    parts = [(p[:1].upper() + p[1:]) for p in parts]   # viết hoa đầu mỗi vế
    cap = ". ".join(parts)
    return (cap + ".") if cap else ""


def style_caption_is_empty(style):
    """True nếu profile KHÔNG sinh được caption nét nào (để UI cảnh báo người dùng)."""
    return not _style_caption(style).strip()


def _style_for_ai(style):
    """Style gửi cho AI: giữ field NỘI DUNG (scene_modes/characters/variety/màu...),
    bỏ field NÉT (AI bị cấm tả). ROBUST: nhận nhiều tên; nếu không khớp gì ->
    gửi NGUYÊN JSON để AI tự đọc (không bao giờ rỗng). Text thuần -> giữ nguyên."""
    d = _as_json(style)
    if d is None:
        return (style or "").strip()
    keep = {k: v for k, v in d.items()
            if any(n in _norm_key(k) for n in _AI_FIELDS)}
    return json.dumps(keep, ensure_ascii=False) if keep else (style or "").strip()


def _strip_mode_keys(text, keys):
    """Nếu Gemini lỡ in nguyên tên KEY scene_mode (vd 'ancient_day') vào câu thì
    đổi gạch dưới thành khoảng trắng cho đọc được ('ancient day'). Chỉ xử lý key
    CÓ dấu '_' để khỏi đụng các từ thường (night / concept / modern)."""
    for k in keys:
        if "_" in k:
            text = re.sub(r"\b" + re.escape(k) + r"\b", k.replace("_", " "), text)
    return text


def _title_context(title):
    """Câu ngữ cảnh tiêu đề video — ghép vào ĐẦU system prompt để AI hiểu chủ đề tổng thể.
    Giúp AI chọn ẩn dụ đúng, giữ nhất quán xuyên suốt video (quan trọng với kịch bản abstract)."""
    t = (title or "").strip()
    if not t:
        return ""
    return (f'VIDEO TITLE (overall context): "{t}"\n'
            f'This is the title of the video you are writing prompts for. '
            f'Use it to understand the overarching theme and narrative so every prompt '
            f'feels like it belongs to THIS specific story: consistent metaphors and '
            f'consistent emotional tone.\n'
            f'Also give THIS video ONE consistent atmosphere of its own (time of day, '
            f'weather, quality of light) where the narration and the style rules allow — '
            f'so different videos on the same channel do not all look identical.\n'
            f'CRITICAL: the title gives you the THEME ONLY. It must NEVER override the '
            f'era, setting or character type of an INDIVIDUAL scene. Each scene\'s own '
            f'narration decides whether it is prehistoric or modern (or any other setting). '
            f'A modern-sounding title (e.g. about phones) does NOT mean every scene is '
            f'modern: if a scene\'s narration is about ancestors, the savannah or hunting, '
            f'render it as that ancient setting with ancient characters. Always read each '
            f'scene on its own and pick its setting from that scene\'s words, not the title.\n\n')


def _parse_characters(text):
    """Tách danh sách TÊN nhân vật chính (phân cách bằng dấu phẩy / chấm phẩy / xuống dòng)."""
    import re as _re
    return [p.strip() for p in _re.split(r"[,;\n]+", text or "") if p.strip()]


def _character_directive(name):
    """Chỉ thị cho AI khi video có NHÂN VẬT CHÍNH (tool video đã có ảnh tham chiếu).
    Hỗ trợ 1 HOẶC NHIỀU nhân vật (nhập nhiều tên cách nhau bằng dấu phẩy).
    Bắt AI: gọi nhân vật bằng TÊN (để tool áp ảnh ref), KHÔNG tả ngoại hình (ref lo),
    chỉ tả HÀNH ĐỘNG + BIỂU CẢM + TƯ THẾ + góc máy, và ĐA DẠNG hoá qua các cảnh."""
    names = _parse_characters(name)
    if not names:
        return ""
    if len(names) == 1:
        n = names[0]
        return (
            f'MAIN CHARACTER: the recurring main character is named "{n}". In EVERY scene where '
            f'this character appears, refer to them BY THE NAME "{n}" (e.g. "{n} leans forward and '
            f'listens") so the tool can apply the reference image. Do NOT describe {n}\'s fixed '
            f"appearance (face, hair, clothes, body) — a reference image controls that. INSTEAD, "
            f"for each such scene clearly state {n}'s ACTION, facial EXPRESSION/emotion, body "
            f"POSE/gesture and camera framing, and VARY them across scenes (avoid repeating the "
            f"same standing pose or the same expression). Scenes without {n} simply omit the name."
        )
    # NHIỀU nhân vật chính: AI gọi đúng tên TỪNG người khi họ xuất hiện
    joined = ", ".join(f'"{n}"' for n in names)
    return (
        f"MAIN CHARACTERS: this video has {len(names)} recurring main characters named {joined}. "
        f"Each has its own reference image. In EVERY scene, refer to whichever of them appears "
        f"BY THEIR EXACT NAME (e.g. \"{names[0]} turns to {names[1]}\") so the tool maps the right "
        f"reference image to each. Do NOT describe their fixed appearance (face, hair, clothes, "
        f"body) — the reference images control that. INSTEAD, for each scene state each present "
        f"character's ACTION, facial EXPRESSION/emotion, body POSE/gesture and camera framing, and "
        f"VARY them across scenes. Only name the characters who actually appear in that scene; "
        f"scenes without any of them simply omit the names."
    )


def _inject_character(system, character):
    """Chèn chỉ thị nhân vật chính vào system prompt (ngay trước dòng yêu cầu JSON)."""
    if not character or not character.strip():
        return system
    block = _character_directive(character)
    idx = system.rfind("Return ONLY")
    if idx == -1:
        return system + "\n\n" + block
    return system[:idx] + block + "\n\n" + system[idx:]


def _run_batches(system, scenes_text, api_key, model, batch, progress, provider):
    """Gọi AI theo batch (tự retry/đổi model) + parse JSON -> list[str] thô.
    Dùng chung cho prompt nội dung lẫn prompt chuyển động (image-to-video)."""
    pref = MODELS.get(provider, MODELS["gemini"])
    order = ([model] if model else []) + [m for m in pref if m != model]
    chosen = None
    out = []
    n = len(scenes_text)
    for start in range(0, n, batch):
        chunk = scenes_text[start:start + batch]
        listing = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(chunk))
        user = (f"Here are {len(chunk)} scenes. Write one prompt for each, "
                f"returning a JSON array of exactly {len(chunk)} strings, in order.\n\n{listing}")
        if out:
            # CHỐNG LẶP QUA RANH GIỚI BATCH: cho AI thấy 2 prompt CUỐI của batch trước
            # để batch sau không mở đầu bằng đúng cỡ cảnh/chuyển động máy vừa dùng.
            tail = [p for p in out[-2:] if (p or "").strip()]
            if tail:
                prev = "\n".join(f"- {p}" for p in tail)
                user = (f"CONTEXT — the prompts for the scenes immediately BEFORE these "
                        f"(already written) were:\n{prev}\n"
                        f"Continue the variety: do NOT open with the same shot type or "
                        f"camera move as those.\n\n{user}")
        txt, last, parsed = None, None, None
        for attempt in range(4):     # tự thử lại khi lỗi tạm thời (429/500/503)
            models_try = ([chosen] if chosen else []) + [m for m in order if m != chosen]
            for m in models_try:
                try:
                    txt = _call(provider, api_key, m, system, user)
                    chosen = m
                    break
                except GeminiError as e:
                    last = e
                    if e.code in (404, 429, 500, 503):
                        continue
                    raise RuntimeError(_friendly(e))
            if txt is None:
                chosen = None
                time.sleep(2 * (attempt + 1))
                continue
            # Parse kết quả + kiểm tra prompt rỗng
            candidate = _parse_array(txt, len(chunk))
            empty_idx = [i + 1 for i, p in enumerate(candidate) if not p.strip()]
            if not empty_idx or attempt == 3:
                # Không có rỗng, hoặc đã hết lượt retry -> chấp nhận
                if empty_idx:
                    print(f"  ⚠️  Batch cảnh {start+1}–{start+len(chunk)}: "
                          f"prompt RỖNG tại vị trí {empty_idx} (hết retry)", file=sys.stderr)
                parsed = candidate
                break
            # Còn prompt rỗng + còn lượt retry -> thử lại batch này
            print(f"  ⚠️  Batch cảnh {start+1}–{start+len(chunk)}: "
                  f"prompt RỖNG tại vị trí {empty_idx}, retry ({attempt+1}/3)...", file=sys.stderr)
            time.sleep(2)
        if parsed is None:
            raise RuntimeError(_friendly(last) if last else "Không sinh được prompt.")
        out.extend(parsed)
        if progress:
            progress(min(start + batch, n), n)
    return out


def generate_prompts(scenes_text, style, api_key, model=None,
                     batch=None, progress=None, mode="video", embed_style=True,
                     style_mode=None, provider="gemini", character="", title=""):
    """
    scenes_text : list[str] — lời nói của từng cảnh, theo thứ tự.
    style       : str       — Visual Style Profile của kênh.
    provider    : "gemini" | "openai" | "claude" — nhà cung cấp API để gọi.
    mode        : "video" (có chuyển động) | "image" (ảnh tĩnh).
    style_mode  : "in_prompt" = TOOL ghép câu ART-STYLE cố định + Gemini lo nội dung+màu/era.
                  "lock_art"  = Lock của tool video lo NÉT; Gemini lo nội dung + MÀU/ERA
                                (KHÔNG ghép caption art-style).
                  "lock_all"  = Lock lo TẤT CẢ style; Gemini chỉ viết nội dung (không màu).
                  None -> suy ra từ embed_style (True->"in_prompt", False->"lock_all").
    embed_style : (giữ tương thích cũ) chỉ dùng khi style_mode=None.
    Trả về list[str] prompt, cùng độ dài scenes_text. Tự đổi model nếu 429/404.
    """
    if not api_key or not api_key.strip():
        raise RuntimeError("Chưa nhập API key (vào tab Cài đặt).")
    if batch is None:
        batch = DEFAULT_BATCH.get(provider, 12)

    if style_mode is None:                       # tương thích cách gọi cũ
        style_mode = "in_prompt" if embed_style else "lock_all"
    if style_mode == "in_prompt" and (not style or not style.strip()):
        raise RuntimeError("Chưa có Style Profile (vào tab Cài đặt để thêm/chọn).")

    api_key = api_key.strip()
    caption = ""
    mode_keys = _scene_mode_keys(style)
    has_modes = _scene_modes_present(style)
    if style_mode == "lock_all":
        # Lock của tool video lo TẤT CẢ style (kể cả màu) -> Gemini chỉ nội dung thuần.
        system = SYSTEM_CONTENT_IMAGE if mode == "image" else SYSTEM_CONTENT_VIDEO
    elif style_mode == "lock_art":
        # Lock lo NÉT; Gemini lo NỘI DUNG + MÀU/ERA (KHÔNG ghép caption art-style).
        if has_modes:
            template = SYSTEM_SPLIT_IMAGE if mode == "image" else SYSTEM_SPLIT_VIDEO
            system = template.format(style=_style_for_ai(style))
        else:
            system = SYSTEM_CONTENT_IMAGE if mode == "image" else SYSTEM_CONTENT_VIDEO
    else:  # "in_prompt": TOOL tự ghép art-style + Gemini lo nội dung + màu/era -> đồng nhất 100%.
        caption = _style_caption(style)
        if has_modes:
            template = SYSTEM_SPLIT_IMAGE if mode == "image" else SYSTEM_SPLIT_VIDEO
            system = template.format(style=_style_for_ai(style))
        else:
            system = SYSTEM_CONTENT_IMAGE if mode == "image" else SYSTEM_CONTENT_VIDEO
    system = _inject_character(system, character)   # nếu có nhân vật chính
    system = _title_context(title) + system         # tiêu đề video → ngữ cảnh tổng thể
    out = _run_batches(system, scenes_text, api_key, model, batch, progress, provider)

    # Hậu xử lý: dọn tên key rò rỉ (scene_mode + character) + ghép câu ART-STYLE.
    leak_keys = mode_keys + _character_keys(style)
    result = []
    for p in out:
        p = _strip_mode_keys((p or "").strip(), leak_keys)
        if caption and p:
            p = f"{caption} {p}"
        result.append(p)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# IMAGE-TO-VIDEO: prompt CHUYỂN ĐỘNG (áp lên ảnh keyframe đã tạo sẵn).
# Ảnh đã chứa nhân vật + bối cảnh + màu + style -> motion CHỈ tả camera + hành động.
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_MOTION = """You write IMAGE-TO-VIDEO motion prompts. For EACH scene you are given its NARRATION and a description of its KEYFRAME IMAGE that has ALREADY been drawn (the character, setting, objects, colours and art style are fixed in that image). Write ONE English line (about 10-20 words) describing how to ANIMATE THAT EXACT KEYFRAME: a CAMERA move PLUS a concrete VISIBLE motion.

CRITICAL — STAY INSIDE THE KEYFRAME (this is the most important rule):
- Only animate things that ACTUALLY EXIST in the KEYFRAME IMAGE. Read the keyframe description and animate what is literally in it.
- If the keyframe is a wall map, a chessboard, a portrait, a diagram or icons, animate THAT (camera pushing over the map, icons pulsing/blinking, a hand moving a piece, light sweeping across it) — do NOT invent real soldiers, crowds, smoke, launchers, vehicles or rooms that are NOT in the image.
- Use the NARRATION ONLY to set the ENERGY / mood / timing — NEVER to add objects, people or events that the keyframe does not contain.

VARIETY IS REQUIRED so the video does not feel repetitive:
- VARY the camera move across scenes — rotate through: slow push-in, pull-out / push-out, pan left, pan right, tilt up, tilt down, slow orbit / parallax, gentle handheld sway, rack focus, static hold. Do NOT use "push-in" in more than about one scene in four, and never repeat the same move many times in a row.
- MATCH the energy to the narration: tense / conflict / danger beats -> faster, sharper moves; calm / resolution beats -> slow, settling moves.
- Give a CONCRETE VISIBLE motion that is present in the image: a gesture, a head/eye turn, a hand movement, drifting particles, light flicker, steam, papers, fabric. AVOID vague phrases like "realization settles" and avoid over-using "subtle / slight / quiet".

You MUST NOT describe appearance, clothes, art style, colours, lighting or the background contents — they are already in the image. {char}
Return ONLY a JSON array of strings, exactly one per scene, in the SAME ORDER. No commentary, no extra keys."""


def generate_motion_prompts(scenes_text, api_key, image_prompts=None, model=None, batch=None,
                            progress=None, provider="gemini", character="", title=""):
    """Sinh prompt CHUYỂN ĐỘNG cho image-to-video (1 dòng/cảnh, camera + hành động).
    image_prompts: mô tả ẢNH keyframe đã sinh (mỗi cảnh 1) — GHÉP vào input để motion KHỚP
    đúng nội dung ảnh (không bịa vật thể/người không có trong ảnh, vd ảnh là bản đồ/bàn cờ mà
    motion lại tả lính/khói). None -> chỉ dùng narration (giữ tương thích cũ)."""
    if not api_key or not api_key.strip():
        raise RuntimeError("Chưa nhập API key (vào tab Cài đặt).")
    if batch is None:
        batch = DEFAULT_BATCH.get(provider, 12)
    api_key = api_key.strip()
    if image_prompts:                         # ghép mỗi cảnh = NARRATION + mô tả KEYFRAME
        feed = []
        for i, narr in enumerate(scenes_text):
            img = ((image_prompts[i] if i < len(image_prompts) else "") or "").strip()
            if img:
                feed.append(f"NARRATION: {narr}\n   KEYFRAME IMAGE (already drawn — animate THIS "
                            f"exact image, do not add anything not shown): {img}")
            else:
                feed.append(f"NARRATION: {narr}")
    else:
        feed = scenes_text
    char = (f'If the main character "{character.strip()}" appears, you may use the name in '
            f"the action.") if (character and character.strip()) else ""
    system = _title_context(title) + SYSTEM_MOTION.format(char=char)
    out = _run_batches(system, feed, api_key, model, batch, progress, provider)
    return [(p or "").strip() for p in out]


# ─────────────────────────────────────────────────────────────────────────────
# ẢNH ĐẦU→CUỐI (chuỗi GỐI ĐẦU) — cho Veo "Frames to Video".
# N cảnh -> N+1 prompt ẢNH liên hoàn (mốc mở đầu mỗi cảnh + 1 ảnh KẾT) + N prompt CHUYỂN ĐỘNG.
# Ảnh cuối clip i = ảnh đầu clip i+1 (gối đầu) -> video chảy liền mạch, cùng nhân vật xuyên suốt.
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_CHAIN_MOTION = """You write motion prompts for a FIRST-FRAME / LAST-FRAME video generator (e.g. Veo "Frames to Video"). For EACH clip you get the scene NARRATION plus a START FRAME description and an END FRAME description — both keyframes are ALREADY drawn, showing the SAME characters and setting at two moments. Write ONE English line (about 12-22 words) describing the MOTION that carries the shot from the START frame to the END frame: a CAMERA move PLUS the concrete action that transforms the start pose/state into the end pose/state.

RULES:
- Describe ONLY the transition BETWEEN the two given frames. Do NOT invent objects, characters or places that are not in either frame.
- Do NOT re-describe appearance, clothes, art style, colours or lighting — they are fixed in the frames.
- Keep the motion continuous and physically plausible so the interpolation is smooth (no teleport, no sudden new elements popping in).
- MATCH the energy to the narration (calm beats -> slow settling moves; tense / danger beats -> faster, sharper moves). {char}
Return ONLY a JSON array of strings, exactly one per clip, in the SAME ORDER. No commentary, no extra keys."""


def generate_chain_prompts(scenes_text, style, api_key, model=None, batch=None,
                           progress=None, style_mode=None, provider="gemini",
                           character="", title=""):
    """Chế độ ẢNH ĐẦU→CUỐI (chuỗi gối đầu) cho Veo Frames-to-Video.
    N cảnh -> N+1 prompt ẢNH liên hoàn (mỗi ảnh = mốc mở đầu 1 cảnh, + 1 ảnh KẾT) +
    N prompt CHUYỂN ĐỘNG (clip i nối ảnh i -> ảnh i+1). Ngoại hình nhân vật do ref lo nên
    prompt chỉ tả hành động/trạng thái/bối cảnh; cả chuỗi giữ cùng nhân vật + mạch truyện.
    Trả (image_prompts[N+1], motion_prompts[N])."""
    if not api_key or not api_key.strip():
        raise RuntimeError("Chưa nhập API key (vào tab Cài đặt).")
    n = len(scenes_text)
    if n == 0:
        return [], []
    if batch is None:
        batch = DEFAULT_BATCH.get(provider, 12)
    api_key = api_key.strip()

    # 1) Chuỗi N+1 prompt ẢNH: N mốc "mở đầu mỗi cảnh" + 1 mốc "kết". Nhúng ngữ cảnh LIÊN HOÀN
    #    vào từng mục để AI giữ cùng nhân vật/bối cảnh (tái dùng generate_prompts để lo style).
    feed_img = [f"[Keyframe in ONE continuous story — SAME characters and setting throughout. "
                f"OPENING moment of scene {i + 1} of {n}] {narr}"
                for i, narr in enumerate(scenes_text)]
    feed_img.append(f"[Keyframe in ONE continuous story — SAME characters and setting. FINAL "
                    f"closing moment, right after scene {n}] {scenes_text[-1]}")
    img_prompts = generate_prompts(feed_img, style, api_key, model=model, batch=batch,
                                   progress=progress, mode="image", style_mode=style_mode,
                                   provider=provider, character=character, title=title)

    # 2) N prompt CHUYỂN ĐỘNG: mỗi clip nhìn CẢ ảnh đầu (START) + ảnh cuối (END).
    char = (f'If the main character "{character.strip()}" appears, you may use the name in '
            f"the action.") if (character and character.strip()) else ""
    feed_motion = []
    for i in range(n):
        a = (img_prompts[i] if i < len(img_prompts) else "").strip()
        b = (img_prompts[i + 1] if i + 1 < len(img_prompts) else "").strip()
        feed_motion.append(f"NARRATION: {scenes_text[i]}\n   START FRAME: {a}\n   END FRAME: {b}")
    system = _title_context(title) + SYSTEM_CHAIN_MOTION.format(char=char)
    motion = _run_batches(system, feed_motion, api_key, model, batch, progress, provider)
    motion = [(p or "").strip() for p in motion]
    return img_prompts, motion


# ─────────────────────────────────────────────────────────────────────────────
# QC KHỚP NGHĨA: đối chiếu lời thoại từng cảnh ↔ mô tả cảnh -> tìm cảnh lệch nghĩa
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_QC = ("You are a video QC assistant. For each scene you get the NARRATION (what the "
"viewer HEARS) and the IMAGE description (what they SEE). Judge whether the image "
"MEANINGFULLY illustrates the narration so a viewer would understand. Return ONLY a JSON "
'array, one object per scene: {"scene": <int>, "verdict": "good|weak|off", '
'"reason": "<short reason in Vietnamese>"}. good=khớp rõ, weak=tạm/chung chung, off=lệch nghĩa.')


def qc_scene_match(scenes, api_key, model=None, provider="gemini", batch=25, progress=None):
    """Đối chiếu khớp nghĩa. scenes: list[{'scene','text','prompt'}].
    Trả list[{scene, verdict(good|weak|off), reason}]. Tự đổi model nếu 429/404."""
    if not api_key or not api_key.strip():
        raise RuntimeError("Chưa nhập API key (vào tab Cài đặt).")
    api_key = api_key.strip()
    pref = MODELS.get(provider, MODELS["gemini"])
    order = ([model] if model else []) + [m for m in pref if m != model]
    out, chosen, n = [], None, len(scenes)
    for start in range(0, n, batch):
        chunk = scenes[start:start + batch]
        listing = "\n".join(
            f'{s["scene"]}. NARRATION: {s["text"]}\n   IMAGE: {s["prompt"]}' for s in chunk)
        user = f"Judge these scenes:\n\n{listing}"
        txt, last = None, None
        models_try = ([chosen] if chosen else []) + [m for m in order if m != chosen]
        for m in models_try:
            try:
                txt = _call(provider, api_key, m, SYSTEM_QC, user)
                chosen = m
                break
            except GeminiError as e:
                last = e
                if e.code in (404, 429, 500, 503):
                    continue
                raise RuntimeError(_friendly(e))
        if txt is None:
            raise RuntimeError(_friendly(last) if last else "QC lỗi.")
        mt = re.search(r"\[.*\]", txt, re.S)
        if mt:
            try:
                out += json.loads(mt.group(0))
            except Exception:  # noqa
                pass
        if progress:
            progress(min(start + batch, n), n)
    return out
