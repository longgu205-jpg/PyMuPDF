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


def _same_paragraph(para, entry):
    prev = para["last"]
    pb, eb = prev["bbox"], entry["bbox"]
    if eb.y0 < pb.y1 - 1:
        return False
    gap = eb.y0 - pb.y1
    h = max(pb.height, eb.height)
    if gap > 0.65 * h:
        return False
    pmin = min(pb.width, eb.width)
    if pmin <= 1:
        return False
    if min(pb.x1, eb.x1) - max(pb.x0, eb.x0) < 0.3 * pmin:
        return False
    if abs(pb.x0 - eb.x0) > max(3.0, 0.25 * pmin):
        return False
    ps, es = prev["size"], entry["size"]
    if min(ps, es) / max(ps, es) < 0.7:
        return False
    return True


def _merge_paragraph_lines(entries):
    items = sorted(entries, key=lambda e: (e["bbox"].y0, e["bbox"].x0))
    paragraphs = []
    for e in items:
        target = None
        for para in reversed(paragraphs[-6:]):
            if _same_paragraph(para, e):
                target = para
                break
        if target is None:
            paragraphs.append({"first": e, "last": e, "lines": [e]})
        else:
            target["lines"].append(e)
            target["last"] = e
    return [p["lines"] for p in paragraphs]


def _make_block(lines, cell_rect):
    lines = sorted(lines, key=lambda t: (round(t["bbox"].y0, 1), t["bbox"].x0))
    text = " ".join(t["text"] for t in lines)
    text = HYPHEN_JOIN_RE.sub(r"\1\2", text)
    text = re.sub(r"\s+", " ", text).strip()
    bbox = lines[0]["bbox"]
    for t in lines[1:]:
        bbox = bbox | t["bbox"]
    sizes = [t["size"] for t in lines]
    colors = [t["color"] for t in lines]
    return {
        "text": text,
        "bbox": bbox,
        "size": max(sizes) if sizes else 10.0,
        "color": colors[-1] if colors else 0,
        "cell": cell_rect,
    }


def extract_blocks(page, cells=None):
    data = page.get_text("dict")
    cells = cells if cells is not None else table_cells(page)
    in_cell = [None] * len(cells)
    for i, cell in enumerate(cells):
        if cell.is_valid and cell.width > 1 and cell.height > 1:
            in_cell[i] = cell

    entries = []
    for bno, block in enumerate(data.get("blocks", [])):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            line_bbox = pymupdf.Rect(line["bbox"])
            spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            cx = (line_bbox.x0 + line_bbox.x1) / 2
            cy = (line_bbox.y0 + line_bbox.y1) / 2
            cell_rect = None
            for i, cell in enumerate(in_cell):
                if cell and cell.contains(pymupdf.Point(cx, cy)):
                    cell_rect = cell
                    break
            entries.append(
                {
                    "bbox": line_bbox,
                    "text": " ".join(s["text"] for s in spans),
                    "size": max(s.get("size", 10) for s in spans),
                    "color": spans[-1].get("color", 0),
                    "cell": cell_rect,
                }
            )

    blocks = []
    cell_groups = {}
    para_entries = []
    for e in entries:
        if e["cell"] is not None:
            cell_groups.setdefault(id(e["cell"]), []).append(e)
        else:
            para_entries.append(e)

    for cell in cells:
        group = cell_groups.get(id(cell))
        if group:
            blocks.append(_make_block(group, cell))
    for lines in _merge_paragraph_lines(para_entries):
        if any(l["text"].strip() for l in lines):
            blocks.append(_make_block(lines, None))

    blocks = [b for b in blocks if b["text"]]
    blocks.sort(key=lambda b: (b["bbox"].y0, b["bbox"].x0))
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
