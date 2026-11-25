import os
import re
import subprocess
import sys
import tempfile
import unittest

import pymupdf

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)

from pdftrans.layout import extract_blocks, needs_translation
from pdftrans.pipeline import translate_pdf
from pdftrans.translators import MockTranslator, _split_chunks


def make_sample_pdf(path):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), "Quarterly Sales Report", fontsize=18)
    body = "This report summarizes the sales performance of the third quarter. " * 3
    page.insert_textbox(pymupdf.Rect(72, 130, 500, 260), body, fontsize=11)
    page.insert_text((72, 300), "2024-10-01", fontsize=10)
    doc.save(path)
    doc.close()
    return path


class TestLayout(unittest.TestCase):
    def test_extract_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = make_sample_pdf(os.path.join(tmp, "in.pdf"))
            doc = pymupdf.open(pdf)
            try:
                blocks = extract_blocks(doc[0])
            finally:
                doc.close()
            texts = [b["text"] for b in blocks]
            self.assertTrue(any("Quarterly Sales Report" in t for t in texts))
            self.assertTrue(any("sales performance" in t for t in texts))
            self.assertTrue(any("2024-10-01" in t for t in texts))

    def test_needs_translation(self):
        self.assertTrue(needs_translation("Hello, world! This is English text."))
        self.assertFalse(needs_translation("2024-10-01 12:30"))
        self.assertFalse(needs_translation("這已經是中文"))
        self.assertFalse(needs_translation(""))
        self.assertFalse(needs_translation("42"))


class TestSplitChunks(unittest.TestCase):
    def test_short_text_unchanged(self):
        self.assertEqual(_split_chunks("hello world", 100), ["hello world"])

    def test_long_text_split(self):
        text = "This is a sentence. " * 100
        joined = " ".join(_split_chunks(text, 200))
        self.assertEqual(joined.split(), text.strip().split())


class TestPipeline(unittest.TestCase):
    def test_translate_with_mock(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = make_sample_pdf(os.path.join(tmp, "in.pdf"))
            out = os.path.join(tmp, "out.pdf")
            out_path, info = translate_pdf(src, out, translator=MockTranslator())
            self.assertTrue(os.path.exists(out_path))
            self.assertEqual(info.failed_blocks, 0)
            result = pymupdf.open(out_path)
            spans = [
                (s["font"], s["text"])
                for b in result[0].get_text("dict")["blocks"] if b.get("type") == 0
                for l in b.get("lines", []) for s in l.get("spans", [])
            ]
            leftover_orig = [
                t for f, t in spans
                if f.startswith("Helvetica") and "2024-10-01" not in t
            ]
            self.assertEqual(leftover_orig, [])
            new_text = re.sub(r"\s+", "", " ".join(t for f, t in spans if not f.startswith("Helvetica")))
            self.assertIn("【中譯】QuarterlySalesReport", new_text)
            self.assertGreater(len(spans), 3)
            result.close()

    def test_cli_mock(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = make_sample_pdf(os.path.join(tmp, "in.pdf"))
            r = subprocess.run(
                [sys.executable, os.path.join(APP_DIR, "translate_cli.py"), src, "-o", os.path.join(tmp, "o.pdf"), "--engine", "mock"],
                capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(os.path.exists(os.path.join(tmp, "o.pdf")))


class TestGuiHelpers(unittest.TestCase):
    def test_label_mapping(self):
        from pdftrans.job import ENGINE_LABELS, engine_to_label, label_to_engine

        for name in ENGINE_LABELS:
            self.assertEqual(label_to_engine(engine_to_label(name)), name)

    def test_index_pdf_files_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_sample_pdf(os.path.join(tmp, "a.pdf"))
            make_sample_pdf(os.path.join(tmp, "b.pdf"))
            with open(os.path.join(tmp, "note.txt"), "w", encoding="utf-8") as f:
                f.write("x")
            files, out = index_pdf_files_helper(tmp)
            self.assertEqual(len(files), 2)
            self.assertTrue(out.endswith("_translated"))

    def test_index_pdf_files_single(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = make_sample_pdf(os.path.join(tmp, "a.pdf"))
            files, out = index_pdf_files_helper(pdf)
            self.assertEqual(files, [pdf])
            self.assertIsNone(out)

    def test_parse_key(self):
        from pdftrans.job import parse_key

        self.assertEqual(parse_key("mymemory", ""), {})
        self.assertEqual(parse_key("deepl", "ABC"), {"deepl_key": "ABC"})
        self.assertEqual(
            parse_key("openai", "https://x/v1|KEY|m"),
            {"openai_key": "KEY", "openai_base": "https://x/v1", "openai_model": "m"},
        )
        self.assertEqual(parse_key("openai", "KEY"), {"openai_key": "KEY", "openai_base": None, "openai_model": None})
        with self.assertRaises(ValueError):
            parse_key("deepl", "")

    def test_create_translator_key_aliases(self):
        from pdftrans.translators import DeepLTranslator, OpenAITranslator, create_translator, MockTranslator

        self.assertIsInstance(create_translator("mock"), MockTranslator)
        d = create_translator("deepl", deepl_key="abc:fx")
        self.assertEqual(d.host, "api-free.deepl.com")
        d2 = create_translator("deepl", api_key="abc")
        self.assertEqual(d2.host, "api.deepl.com")
        o = create_translator("openai", openai_key="K", openai_base="https://x/v1", openai_model="m")
        self.assertIsInstance(o, OpenAITranslator)
        self.assertEqual(o.model, "m")
        self.assertEqual(o.base_url, "https://x/v1")

    def test_gui_engine_wiring(self):
        from pdftrans.job import parse_key
        from pdftrans.translators import DeepLTranslator, OpenAITranslator, create_translator

        d = create_translator("deepl", **parse_key("deepl", "abc:fx"))
        self.assertIsInstance(d, DeepLTranslator)
        self.assertEqual(d.host, "api-free.deepl.com")
        o = create_translator("openai", **parse_key("openai", "https://x/v1|K|m"))
        self.assertIsInstance(o, OpenAITranslator)
        self.assertEqual(o.model, "m")
        self.assertEqual(o.base_url, "https://x/v1")

    def test_validate_input(self):
        from pdftrans.job import validate_input

        with self.assertRaises(ValueError):
            validate_input("")
        with self.assertRaises(ValueError):
            validate_input(os.path.join("", "not-exist-dir-xyz"))

    def test_color_normalization(self):
        from pdftrans.layout import int_to_rgb

        self.assertAlmostEqual(int_to_rgb(0xFF0000), (1.0, 0.0, 0.0))
        self.assertAlmostEqual(int_to_rgb(0), (0.0, 0.0, 0.0))
        self.assertEqual(int_to_rgb((0.5, 0.5, 0.5)), (0.5, 0.5, 0.5))
        self.assertEqual(int_to_rgb((128, 128, 128)), (128 / 255, 128 / 255, 128 / 255))
        self.assertEqual(int_to_rgb((0.5,)), (0.5,))
        for bad in [None, "red", -5, 0xFFFFFFFF, (1, 2), object(), True]:
            result = int_to_rgb(bad)
            self.assertEqual(result, (0.0, 0.0, 0.0), str(bad))


def index_pdf_files_helper(path):
    from pdftrans.job import index_pdf_files

    return index_pdf_files(path)


class TestBatchTranslate(unittest.TestCase):
    def test_translate_many_order(self):
        from pdftrans.translators import MockTranslator

        texts = ["one", "two", "three"]
        results = MockTranslator().translate_many(texts)
        self.assertEqual(results, ["【中譯】one", "【中譯】two", "【中譯】three"])

    def test_translate_many_empty(self):
        from pdftrans.translators import MockTranslator

        self.assertEqual(MockTranslator().translate_many([]), [])

    def test_translate_many_abort(self):
        import threading

        from pdftrans.translators import MockTranslator, TranslationCancelled

        t = MockTranslator()
        t.CONCURRENCY = 1
        event = threading.Event()
        event.set()
        with self.assertRaises(TranslationCancelled):
            t.translate_many(["a", "b"], abort=event)

    def test_pipeline_batch_and_abort(self):
        import threading

        from pdftrans.translators import MockTranslator, TranslationCancelled

        with tempfile.TemporaryDirectory() as tmp:
            src = make_sample_pdf(os.path.join(tmp, "in.pdf"))
            out = os.path.join(tmp, "out.pdf")
            out_path, info = translate_pdf(src, out, translator=MockTranslator())
            self.assertTrue(os.path.exists(out_path))
            self.assertEqual(info.failed_blocks, 0)

            doc = pymupdf.open(src)
            evt = threading.Event()
            evt.set()
            with self.assertRaises(TranslationCancelled):
                translate_pdf(src, os.path.join(tmp, "x.pdf"), translator=MockTranslator(), abort=evt)
            doc.close()


class TestGlossary(unittest.TestCase):
    def test_load_and_apply(self):
        from pdftrans.glossary import apply_glossary, load_glossary

        with tempfile.TemporaryDirectory() as tmp:
            g = os.path.join(tmp, "g.txt")
            with open(g, "w", encoding="utf-8") as f:
                f.write("# 註解\nHMI=人機介面\n\n")
            m = load_glossary(g)
            self.assertEqual(m, {"HMI": "人機介面"})
        self.assertEqual(apply_glossary("The HMI works.", m), "The 人機介面 works.")
        self.assertEqual(apply_glossary("nothing", m), "nothing")
        self.assertEqual(apply_glossary("x", {}), "x")

    def test_apply_case_insensitive(self):
        from pdftrans.glossary import apply_glossary

        m = {"batch": "批次"}
        self.assertEqual(apply_glossary("Batch data", m), "批次 data")


class TestTables(unittest.TestCase):
    def test_cell_grouping_splits_columns(self):
        from pdftrans.layout import extract_blocks

        with tempfile.TemporaryDirectory() as tmp:
            pdf = os.path.join(tmp, "t.pdf")
            doc = pymupdf.open()
            page = doc.new_page(width=595, height=300)
            page.insert_text((80, 100), "Cell one content", fontsize=10)
            page.insert_text((270, 100), "Cell two content", fontsize=10)
            doc.save(pdf)
            doc.close()
            d2 = pymupdf.open(pdf)
            try:
                cells = [pymupdf.Rect(72, 60, 250, 120), pymupdf.Rect(250, 60, 500, 120)]
                blocks = extract_blocks(d2[0], cells=cells)
                self.assertEqual(
                    {b["text"] for b in blocks}, {"Cell one content", "Cell two content"}
                )
            finally:
                d2.close()

    def test_find_tables_smoke(self):
        from pdftrans.layout import table_cells

        with tempfile.TemporaryDirectory() as tmp:
            pdf = os.path.join(tmp, "t.pdf")
            doc = pymupdf.open()
            page = doc.new_page(width=595, height=400)
            xcols = [72, 200, 340, 500]
            yrows = [80, 140, 200, 260]
            for y in yrows:
                page.draw_line(pymupdf.Point(72, y), pymupdf.Point(500, y))
            for x in xcols:
                page.draw_line(pymupdf.Point(x, 80), pymupdf.Point(x, 260))
            for r in range(3):
                for c in range(3):
                    page.insert_text((xcols[c] + 8, yrows[r] + 25), f"Cell{r}{c}", fontsize=10)
            doc.save(pdf)
            doc.close()
            d2 = pymupdf.open(pdf)
            try:
                self.assertGreater(len(table_cells(d2[0])), 0)
                blocks = extract_blocks(d2[0])
                texts = [b["text"] for b in blocks]
                self.assertFalse(any("Cell00" in t and "Cell01" in t for t in texts))
                self.assertFalse(any("Cell00" in t and "Cell10" in t for t in texts))
            finally:
                d2.close()


class TestFailureResilience(unittest.TestCase):
    def test_cell_text_stays_in_cell(self):
        from pdftrans.layout import table_cells
        from pdftrans.pipeline import translate_pdf
        from pdftrans.translators import MockTranslator

        with tempfile.TemporaryDirectory() as tmp:
            pdf = os.path.join(tmp, "t.pdf")
            doc = pymupdf.open()
            page = doc.new_page(width=595, height=400)
            xcols = [72, 200, 340, 500]
            yrows = [80, 140, 200, 260]
            for y in yrows:
                page.draw_line(pymupdf.Point(72, y), pymupdf.Point(500, y))
            for x in xcols:
                page.draw_line(pymupdf.Point(x, 80), pymupdf.Point(x, 260))
            size = 8.0
            while size >= 4.0:
                rc = page.insert_textbox(
                    pymupdf.Rect(84, 102, 194, 136),
                    "Long sentence inside the first cell which must stay inside the border wrap wrap. " * 2,
                    fontsize=size,
                )
                if rc >= 0:
                    break
                size -= 0.5
            for r in range(3):
                for c in range(1, 3):
                    page.insert_text((xcols[c] + 8, yrows[r] + 25), f"Cell{r}{c}", fontsize=9)
            doc.save(pdf)
            doc.close()

            d0 = pymupdf.open(pdf)
            cells = table_cells(d0[0])
            d0.close()
            self.assertGreater(len(cells), 0)
            first_cell = min(cells, key=lambda c: (c.y0, c.x0))

            out, _info = translate_pdf(pdf, os.path.join(tmp, "o.pdf"), translator=MockTranslator())
            d2 = pymupdf.open(out)
            try:
                checked = 0
                for b in d2[0].get_text("dict")["blocks"]:
                    for l in b.get("lines", []):
                        for s in l.get("spans", []):
                            sb = pymupdf.Rect(s["bbox"])
                            if sb.intersects(first_cell):
                                self.assertGreaterEqual(sb.x0, first_cell.x0 - 2, s["text"])
                                self.assertLessEqual(sb.x1, first_cell.x1 + 2, s["text"])
                                self.assertGreaterEqual(sb.y0, first_cell.y0 - 2, s["text"])
                                self.assertLessEqual(sb.y1, first_cell.y1 + 2, s["text"])
                                checked += 1
                self.assertGreater(checked, 0)
            finally:
                d2.close()

    def test_failed_block_keeps_source_text(self):
        from pdftrans.translators import BaseTranslator

        class Flaky(BaseTranslator):
            def translate(self, text, src="en", dst="zh-TW"):
                if "third" in text:
                    raise RuntimeError("boom")
                return "【中譯】" + text

        with tempfile.TemporaryDirectory() as tmp:
            src = make_sample_pdf(os.path.join(tmp, "in.pdf"))
            out = os.path.join(tmp, "out.pdf")
            out_path, info = translate_pdf(src, out, translator=Flaky())
            self.assertEqual(info.failed_blocks, 1)
            result = pymupdf.open(out_path)
            text = re.sub(r"\s+", " ", result[0].get_text())
            result.close()
            self.assertIn("sales performance of the third quarter", text)
            self.assertIn("【中譯】Quarterly", text)


@unittest.skipUnless(os.environ.get("RUN_LIVE_TESTS") == "1", "live network tests off")
class TestLiveEngines(unittest.TestCase):
    def test_mymemory(self):
        from pdftrans.translators import MyMemoryTranslator
        import re

        t = MyMemoryTranslator()
        out = t.translate("Quarterly Sales Report", "en", "zh-TW")
        self.assertTrue(re.search(r"[\u4e00-\u9fff]", out), out)


if __name__ == "__main__":
    unittest.main()
