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
    return pymupdf.sRGB_to_rgb(color)
