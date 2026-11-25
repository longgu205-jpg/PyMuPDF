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
            blocks = extract_blocks(doc[0])
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
            helvetica = [t for f, t in spans if "Fangti" not in f and f != "ZapfDingbats"]
            non_date = [t for t in helvetica if "2024-10-01" not in t]
            self.assertEqual(non_date, [])
            cjk_text = re.sub(r"\s+", " ", " ".join(t for f, t in spans if "Fangti" in f))
            self.assertIn("【中譯】Quarterly Sales Report", cjk_text)
            self.assertGreater(len(spans), 2)
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
