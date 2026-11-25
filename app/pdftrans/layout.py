import re

import pymupdf

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
LETTER_RE = re.compile(r"[A-Za-z]")
HYPHEN_JOIN_RE = re.compile(r"([A-Za-z])-\s+([a-z])")


def extract_blocks(page):
    data = page.get_text("dict")
    blocks = []
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        line_texts = []
        sizes = []
        color = 0
        for line in block.get("lines", []):
            spans = [s["text"] for s in line.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            line_texts.append(" ".join(spans))
            for s in line.get("spans", []):
                if s.get("text", "").strip():
                    sizes.append(s.get("size", 10))
                    color = s.get("color", color)
        text = " ".join(line_texts)
        text = HYPHEN_JOIN_RE.sub(r"\1\2", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        blocks.append(
            {
                "text": text,
                "bbox": pymupdf.Rect(block["bbox"]),
                "size": max(sizes) if sizes else 10.0,
                "color": color,
            }
        )
    return blocks


def needs_translation(text):
    if not text or len(text) < 2:
        return False
    if not LETTER_RE.search(text):
        return False
    cjk = len(CJK_RE.findall(text))
    if cjk * 10 >= len(text):
        return False
    if re.fullmatch(r"[\d\s.,:%€$¥\-–—/()&+]+", text):
        return False
    return True


cjk_font_by_lang = {
    "zh-TW": "china-t",
    "zh-Hant": "china-t",
    "zh-HK": "china-t",
    "zh": "china-s",
    "zh-Hans": "china-s",
    "ja": "japan",
    "ko": "korea",
}


def font_for_lang(dst):
    return cjk_font_by_lang.get(dst, "china-s")


def int_to_rgb(color):
    if isinstance(color, (list, tuple)):
        try:
            vals = [float(v) for v in color]
        except (TypeError, ValueError):
            return (0.0, 0.0, 0.0)
        if len(vals) not in (1, 3, 4):
            return (0.0, 0.0, 0.0)
        if any(v < 0 or v > 1 for v in vals):
            if all(0 <= v <= 255 for v in vals):
                vals = [v / 255.0 for v in vals]
            else:
                return (0.0, 0.0, 0.0)
        return tuple(vals)
    if isinstance(color, bool) or not isinstance(color, (int, float)):
        return (0.0, 0.0, 0.0)
    c = int(color)
    if 0 <= c <= 0xFFFFFF:
        return ((c >> 16) & 255) / 255.0, ((c >> 8) & 255) / 255.0, (c & 255) / 255.0
    return (0.0, 0.0, 0.0)
