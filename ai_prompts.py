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
- Chooses a camera framing (wide / medium / close-up) and varies it across scenes.
- COLOUR / ERA: a style profile JSON with "scene_modes" is given below. Pick the scene_mode whose "when" best matches this scene's era/topic and apply ONLY its background, palette and lighting (the colours and setting). You MAY name a character's identifying features (e.g. round glasses, messy brown hair) so the right character appears, but do NOT describe the drawing style itself.
- NEVER write a scene_mode KEY name (such as "ancient_day", "night", "concept", "modern") in the text; describe the colours in plain words instead.
- Do NOT begin with a label like "MODERN:".

STYLE PROFILE (use ONLY scene_modes for colour/era; the art style is added separately):
---
{style}
---

Return ONLY a JSON array of strings: exactly one line per scene, in the SAME ORDER as given. No commentary, no extra keys."""

SYSTEM_SPLIT_IMAGE = """You write the CONTENT of STILL-IMAGE prompts for AI generators (such as Veo's image mode) for faceless narrated videos. The ART-STYLE (line work, shading, how characters are drawn) is controlled separately — by a fixed style caption or a visual style lock — so you MUST NOT describe the art style, line work, rendering, textures, or how things are drawn. Focus on WHAT appears and the COLOUR / ERA setting.

You will receive a numbered list of scenes; each scene has the NARRATION spoken during it.
For EACH scene, write ONE concise English line that:
- Visually conveys the MEANING of the narration (not a literal word-for-word transcription).
- Describes a SINGLE STILL moment (subject, setting, framing). Do NOT describe motion or camera movement — one frozen frame held still.
- Chooses a camera framing (wide / medium / close-up) and varies it across scenes.
- COLOUR / ERA: a style profile JSON with "scene_modes" is given below. Pick the scene_mode whose "when" best matches this scene's era/topic and apply ONLY its background, palette and lighting (the colours and setting). You MAY name a character's identifying features (e.g. round glasses, messy brown hair) so the right character appears, but do NOT describe the drawing style itself.
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
- A camera framing (wide / medium / close-up).
Keep it to ONE concise sentence. Do NOT describe style, colors, or how it is drawn/rendered.

Return ONLY a JSON array of strings, exactly one per scene, in the SAME ORDER. No commentary, no extra keys."""

SYSTEM_CONTENT_IMAGE = """You describe ONLY the visual CONTENT of each scene for an image generator (faceless narrated videos). A separate visual-style system already controls the art style, so you MUST NOT mention any art style, rendering, colors, line work, textures, or visual aesthetics.

For EACH scene (you get its NARRATION), write ONE short English line describing:
- WHO / WHAT appears and a minimal setting (a single STILL moment — no motion, no camera movement).
- A camera framing (wide / medium / close-up).
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
                arr = [str(x).replace("\n", " ").strip() for x in arr if str(x).strip()]
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
                arr = [str(x).replace("\n", " ").strip() for x in arr if str(x).strip()]
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


def _style_caption(style):
    """Câu ART-STYLE CỐ ĐỊNH (text tự nhiên) để TOOL tự ghép vào MỌI prompt.

    - Profile JSON: ghép art_style + line_work + shading_lighting + mood.
      KHÔNG lấy "characters" và "scene_modes": characters để Gemini nêu theo từng
      cảnh (chỉ nhân vật xuất hiện), scene_modes để Gemini lo MÀU/ERA. Nhờ vậy
      art-style đồng nhất 100% mọi cảnh mà không bắt nhầm cả nhân vật không có mặt.
    - Profile text thuần: dùng nguyên văn cả khối làm style.
    """
    s = (style or "").strip()
    if not s:
        return ""
    d = _as_json(s)
    if d is None:
        return s
    parts = []
    for k in ("art_style", "line_work", "shading_lighting"):
        v = d.get(k)
        if v and str(v).strip():
            parts.append(str(v).strip())
    mood = d.get("mood")
    if mood and str(mood).strip():
        parts.append("overall mood: " + str(mood).strip())
    parts = [p.rstrip(" .") for p in parts]
    parts = [(p[:1].upper() + p[1:]) for p in parts if p]   # viết hoa đầu mỗi vế
    cap = ". ".join(parts)
    return (cap + ".") if cap else ""


def _style_for_ai(style):
    """Style RÚT GỌN gửi cho AI ở chế độ SPLIT: BỎ các field ART-STYLE mà AI bị CẤM
    mô tả (art_style / line_work / shading_lighting) -> tiết kiệm token input, không
    mất gì (art-style do TOOL ghép caption / Lock lo). Giữ scene_modes (màu/era),
    characters, variety, mood. Profile text thuần -> giữ nguyên."""
    d = _as_json(style)
    if d is None:
        return (style or "").strip()
    keep = {k: d[k] for k in ("scene_modes", "characters", "variety", "mood") if k in d}
    return json.dumps(keep, ensure_ascii=False) if keep else (style or "").strip()


def _strip_mode_keys(text, keys):
    """Nếu Gemini lỡ in nguyên tên KEY scene_mode (vd 'ancient_day') vào câu thì
    đổi gạch dưới thành khoảng trắng cho đọc được ('ancient day'). Chỉ xử lý key
    CÓ dấu '_' để khỏi đụng các từ thường (night / concept / modern)."""
    for k in keys:
        if "_" in k:
            text = re.sub(r"\b" + re.escape(k) + r"\b", k.replace("_", " "), text)
    return text


def _character_directive(name):
    """Chỉ thị cho AI khi video có NHÂN VẬT CHÍNH (tool video đã có ảnh tham chiếu).
    Bắt AI: gọi nhân vật bằng TÊN (để tool áp ảnh ref), KHÔNG tả ngoại hình (ref lo),
    chỉ tả HÀNH ĐỘNG + BIỂU CẢM + TƯ THẾ + góc máy, và ĐA DẠNG hoá qua các cảnh."""
    n = name.strip()
    return (
        f'MAIN CHARACTER: the recurring main character is named "{n}". In EVERY scene where '
        f'this character appears, refer to them BY THE NAME "{n}" (e.g. "{n} leans forward and '
        f'listens") so the tool can apply the reference image. Do NOT describe {n}\'s fixed '
        f"appearance (face, hair, clothes, body) — a reference image controls that. INSTEAD, "
        f"for each such scene clearly state {n}'s ACTION, facial EXPRESSION/emotion, body "
        f"POSE/gesture and camera framing, and VARY them across scenes (avoid repeating the "
        f"same standing pose or the same expression). Scenes without {n} simply omit the name."
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
        txt, last = None, None
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
            if txt is not None:
                break
            chosen = None
            time.sleep(2 * (attempt + 1))
        if txt is None:
            raise RuntimeError(_friendly(last))
        out.extend(_parse_array(txt, len(chunk)))
        if progress:
            progress(min(start + batch, n), n)
    return out


def generate_prompts(scenes_text, style, api_key, model=None,
                     batch=None, progress=None, mode="video", embed_style=True,
                     style_mode=None, provider="gemini", character=""):
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
    out = _run_batches(system, scenes_text, api_key, model, batch, progress, provider)

    # Hậu xử lý: dọn tên key rò rỉ + ghép câu ART-STYLE cố định vào đầu mỗi prompt.
    result = []
    for p in out:
        p = _strip_mode_keys((p or "").strip(), mode_keys)
        if caption and p:
            p = f"{caption} {p}"
        result.append(p)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# IMAGE-TO-VIDEO: prompt CHUYỂN ĐỘNG (áp lên ảnh keyframe đã tạo sẵn).
# Ảnh đã chứa nhân vật + bối cảnh + màu + style -> motion CHỈ tả camera + hành động.
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_MOTION = """You write IMAGE-TO-VIDEO motion prompts. Each scene ALREADY has a finished keyframe image (the character, setting, colours and art style are fixed in that image). For EACH scene you receive its NARRATION; write ONE short English line describing ONLY:
- the CAMERA movement (e.g. slow push-in, gentle pan left, slow zoom out, static, slight handheld), and
- the ONGOING action / motion to animate (what moves and how, matching the narration).
You MUST NOT describe appearance, the character's looks, clothes, art style, colours, lighting or the background — they are already in the image. Keep it to ONE short line (about 8-16 words). {char}
Return ONLY a JSON array of strings, exactly one per scene, in the SAME ORDER. No commentary, no extra keys."""


def generate_motion_prompts(scenes_text, api_key, model=None, batch=None,
                            progress=None, provider="gemini", character=""):
    """Sinh prompt CHUYỂN ĐỘNG cho image-to-video (1 dòng/cảnh, chỉ camera + hành động)."""
    if not api_key or not api_key.strip():
        raise RuntimeError("Chưa nhập API key (vào tab Cài đặt).")
    if batch is None:
        batch = DEFAULT_BATCH.get(provider, 12)
    api_key = api_key.strip()
    char = (f'If the main character "{character.strip()}" appears, you may use the name in '
            f"the action.") if (character and character.strip()) else ""
    system = SYSTEM_MOTION.format(char=char)
    out = _run_batches(system, scenes_text, api_key, model, batch, progress, provider)
    return [(p or "").strip() for p in out]
