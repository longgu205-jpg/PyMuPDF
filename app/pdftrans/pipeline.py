import os

import pymupdf

from .layout import extract_blocks, font_for_lang, int_to_rgb, needs_translation
from .translators import TranslationCancelled


class ProgressInfo:
    def __init__(self, total_blocks, page_count):
        self.total_blocks = total_blocks
        self.page_count = page_count
        self.done_blocks = 0
        self.current_page = 0
        self.failed_blocks = 0

    @property
    def percent(self):
        if self.total_blocks == 0:
            return 100.0
        return round(100.0 * self.done_blocks / self.total_blocks, 1)


def translate_pdf(
    pdf_path,
    out_path=None,
    translator=None,
    src="en",
    dst="zh-TW",
    progress_cb=None,
    dump_text=None,
    abort=None,
):
    pdf_path = str(pdf_path)
    if out_path is None:
        root, _ext = os.path.splitext(pdf_path)
        out_path = root + "_translated.pdf"
    out_path = str(out_path)

    doc = pymupdf.open(pdf_path)
    pending = []
    unique = {}
    info = ProgressInfo(0, doc.page_count)

    for pno in range(doc.page_count):
        tasks = [
            b
            for b in extract_blocks(doc[pno])
            if needs_translation(b["text"])
        ]
        pending.append((pno, tasks))
        for b in tasks:
            unique[b["text"]] = None
    info.total_blocks = len(unique)

    if progress_cb:
        progress_cb(info, "start")

    if dump_text:
        _dump_stages_text(pending, dump_text)

    texts = list(unique)
    if texts:

        def batch_progress(done, _total):
            info.done_blocks = done
            if progress_cb:
                progress_cb(info, None)

        translations = translator.translate_many(
            texts, src=src, dst=dst, progress=batch_progress, abort=abort
        )
        for t, r in zip(texts, translations):
            unique[t] = r
    info.done_blocks = info.total_blocks
    info.failed_blocks = sum(1 for v in unique.values() if v is None)

    results = []
    try:
        for pno, tasks in pending:
            page = doc[pno]
            for b in tasks:
                if unique.get(b["text"]):
                    b["zh"] = unique[b["text"]]
                    page.add_redact_annot(b["bbox"], fill=(1, 1, 1))
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)
            for b in tasks:
                if not unique.get(b["text"]):
                    continue
                try:
                    _insert_translation(page, b, dst)
                except Exception as e:
                    info.failed_blocks += 1
                    print(f"[warn] page {pno + 1} block insert skipped ({e})")
            if progress_cb:
                progress_cb(info, f"writing page {pno + 1}/{doc.page_count}")
    except (KeyboardInterrupt, TranslationCancelled):
        doc.close()
        raise

    doc.save(out_path, garbage=3, deflate=True)
    doc.close()
    if progress_cb:
        progress_cb(info, "done")
    return out_path, info


def _dump_stages_text(pending, dump_path):
    with open(dump_path, "w", encoding="utf-8") as f:
        for pno, tasks in pending:
            f.write(f"===== page {pno + 1} =====\n")
            for b in tasks:
                f.write(f"[{b['bbox']}] {b['text']}\n")


def _insert_translation(page, block, dst):
    font = font_for_lang(dst)
    rect = pymupdf.Rect(block["bbox"])
    margin = 2.0
    avail = pymupdf.Rect(
        max(rect.x0 - margin, 0),
        max(rect.y0 - margin, 0),
        min(rect.x1 + rect.width * 0.25, page.rect.x1 - margin),
        min(rect.y1 + rect.height * 0.75, page.rect.y1 - margin),
    )
    color = int_to_rgb(block.get("color", 0))
    size = min(max(block["size"], 6.0), 24.0)
    smallest = 4.0
    while size >= smallest:
        rc = page.insert_textbox(
            avail,
            block["zh"],
            fontname=font,
            fontsize=size,
            align=pymupdf.TEXT_ALIGN_LEFT,
            color=color,
        )
        if rc >= 0:
            return True
        size -= 0.5
    return False


def translate_path(input_path, out_path=None, **kwargs):
    input_path = str(input_path)
    if os.path.isdir(input_path):
        out_dir = out_path or input_path.rstrip("/\\") + "_translated"
        os.makedirs(out_dir, exist_ok=True)
        results = []
        for name in sorted(os.listdir(input_path)):
            if not name.lower().endswith(".pdf"):
                continue
            src_file = os.path.join(input_path, name)
            dst_file = os.path.join(out_dir, os.path.splitext(name)[0] + "_translated.pdf")
            results.append(translate_pdf(src_file, dst_file, **kwargs))
        return results
    return [translate_pdf(input_path, out_path, **kwargs)]
