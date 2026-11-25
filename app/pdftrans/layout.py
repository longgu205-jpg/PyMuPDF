import re

import pymupdf

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
LETTER_RE = re.compile(r"[A-Za-z]")
HYPHEN_JOIN_RE = re.compile(r"([A-Za-z])-\s+([a-z])")


def table_cells(page):
    cells = []
    try:
        finder = page.find_tables()
        for table in getattr(finder, "tables", []):
            for row in table.rows:
                for cell in row.cells:
                    if not cell:
                        continue
                    r = pymupdf.Rect(cell)
                    if r.width >= 10 and r.height >= 6:
                        cells.append(r)
    except Exception:
        return []
    unique = []
    for c in cells:
        if not any(c in u or u in c for u in unique):
            unique.append(c)
    return unique


def extract_blocks(page, cells=None):
    data = page.get_text("dict")
    cells = cells if cells is not None else table_cells(page)
    in_cell = [None] * len(cells)
    for i, cell in enumerate(cells):
        if cell.is_valid and cell.width > 1 and cell.height > 1:
            in_cell[i] = cell

    groups = {}

    def group_key(span_bbox, block_index):
        cx = (span_bbox.x0 + span_bbox.x1) / 2
        cy = (span_bbox.y0 + span_bbox.y1) / 2
        for i, cell in enumerate(in_cell):
            if cell and cell.contains(pymupdf.Point(cx, cy)):
                return ("cell", i)
        return ("block", block_index)

    for bno, block in enumerate(data.get("blocks", [])):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            line_bbox = pymupdf.Rect(line["bbox"])
            spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            key = group_key(line_bbox, bno)
            g = groups.setdefault(key, {"texts": [], "sizes": [], "color": 0, "bbox": None})
            g["texts"].append((line_bbox.y0, line_bbox.x0, " ".join(s["text"] for s in spans)))
            for s in spans:
                g["sizes"].append(s.get("size", 10))
                g["color"] = s.get("color", g["color"])
            span_rect = pymupdf.Rect(line["bbox"])
            g["bbox"] = span_rect if g["bbox"] is None else g["bbox"] | span_rect

    blocks = []
    for key, g in sorted(groups.items(), key=lambda kv: (kv[0][0], min(t[0] for t in kv[1]["texts"]), kv[0][1])):
        lines = sorted(g["texts"], key=lambda t: (round(t[0], 1), t[1]))
        text = " ".join(t[2] for t in lines)
        text = HYPHEN_JOIN_RE.sub(r"\1\2", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        cell_rect = in_cell[key[1]] if key[0] == "cell" else None
        blocks.append(
            {
                "text": text,
                "bbox": g["bbox"],
                "size": max(g["sizes"]) if g["sizes"] else 10.0,
                "color": g["color"],
                "cell": cell_rect,
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
