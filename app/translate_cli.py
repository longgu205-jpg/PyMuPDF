import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pdftrans.pipeline import translate_path
from pdftrans.translators import TranslationCancelled, create_translator


def build_arg_parser():
    p = argparse.ArgumentParser(
        description="PDF 整份英→中翻譯工具（底層 PyMuPDF）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("input", help="輸入 PDF 檔案或整個資料夾（資料夾會批次處理所有 PDF）")
    p.add_argument("-o", "--output", help="輸出 PDF（或資料夾輸出目錄）；預設：<原名>_translated.pdf")
    p.add_argument("--engine", default="mymemory", choices=["mymemory", "google", "deepl", "openai", "mock"], help="翻譯引擎")
    p.add_argument("--src", default="en", help="來源語言")
    p.add_argument("--dst", default="zh-TW", help="目標語言（zh-TW 繁中 / zh-Hans 簡中）")
    p.add_argument("--deepl-key", default=None, help="DeepL API key（或環境變數 DEEPL_API_KEY）")
    p.add_argument("--openai-key", default=None, help="OpenAI 相容 API key（或環境變數 OPENAI_API_KEY）")
    p.add_argument("--openai-base", default=None, help="OpenAI 相容 API base URL（或 OPENAI_BASE_URL）")
    p.add_argument("--openai-model", default=None, help="模型名稱（或 OPENAI_MODEL）")
    p.add_argument("--dump-text", default=None, help="把擷取到的原文區塊另存成 txt（除錯用）")
    p.add_argument("--glossary", default=None, help="術語表檔案（一行一條：英文=中文），固定專有名詞譯法")
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    if not os.path.exists(args.input):
        print(f"錯誤：找不到輸入 {args.input}")
        return 2

    translator = create_translator(
        args.engine,
        **_engine_kwargs(args),
    )

    from pdftrans.glossary import load_glossary

    last = {"pct": -1}

    def cb(info, stage):
        pct = info.percent
        if pct != last["pct"] or stage in ("start", "done"):
            print(f"[{stage}] 進度 {pct}%（{info.done_blocks}/{info.total_blocks} 區塊）")
            last["pct"] = pct

    try:
        results = translate_path(
            args.input,
            args.output,
            translator=translator,
            src=args.src,
            dst=args.dst,
            progress_cb=cb,
            dump_text=args.dump_text,
            glossary=load_glossary(args.glossary) if args.glossary else None,
        )
    except (KeyboardInterrupt, TranslationCancelled):
        print("已中斷：未產生輸出檔。")
        return 130
    n_fail = sum(r[1].failed_blocks for r in results)
    for out_path, info in results:
        print(f"完成：{out_path}（{info.page_count} 頁 / {info.total_blocks} 區塊 / 失敗 {info.failed_blocks}）")
    return 1 if n_fail else 0


def _engine_kwargs(args):
    if args.engine == "deepl":
        return {"api_key": args.deepl_key}
    if args.engine == "openai":
        return {
            "api_key": args.openai_key,
            "base_url": args.openai_base,
            "model": args.openai_model,
        }
    return {}


if __name__ == "__main__":
    raise SystemExit(main())
