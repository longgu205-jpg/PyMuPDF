# PDF 整份翻譯工具（底層 PyMuPDF）

將整份 PDF 文件由英文翻譯成中文（預設繁體中文 zh-TW），保留原頁面位置排版，輸出新的 PDF。

## 階段計畫

| 階段 | 內容 | 狀態 |
|------|------|------|
| 1 | 核心翻譯管線：區塊擷取 → 呼叫翻譯引擎 → 譯文寫回原位置 | ✅ 本次完成 |
| 2 | GUI（tkinter）＋資料夾批次＋進度列 | 下一階段 |
| 3 | Windows exe 打包（一鍵 build.bat，onedir 不包成單一 exe，避免檔案過大、啟動較快） | 待做 |
| 4 | 術語表固定翻譯、雙語對照輸出、排版微調 | 選配 |

## 目錄結構

```
app/
├── pdftrans/
│   ├── translators.py   # 翻譯引擎（MyMemory / Google / DeepL / OpenAI 相容 / Mock）
│   ├── layout.py        # 文字區塊擷取與語言判斷
│   └── pipeline.py      # 翻譯管線：擷取 → 翻譯 → 抹除原文 → 譯文回寫
├── translate_cli.py     # 命令列入口
├── tests/test_pdftrans.py
└── requirements.txt
```

## 在 PyCharm 使用

1. 開啟本專案後，建立 venv：`Settings → Project → Python Interpreter → Add Interpreter → Virtualenv Environment`
2. 終端機執行 `pip install -r app/requirements.txt`
3. 把 `app/translate_cli.py` 設為 Run Configuration，Parameters 填輸入 PDF 路徑即可執行

## 命令列用法

```bash
cd app

# 單一檔案（預設引擎 mymemory，免 API key，英 → 繁中）
python translate_cli.py 樣本.pdf

# 指定輸出
python translate_cli.py 樣本.pdf -o 輸出_中譯.pdf

# 整個資料夾批次（輸出到 <資料夾>_translated/）
python translate_cli.py 某資料夾/

# 簡體中文
python translate_cli.py 樣本.pdf --dst zh-Hans

# 串 DeepL（有免費額度，品質較好）
python translate_cli.py 樣本.pdf --engine deepl --deepl-key 你的KEY

# 串 OpenAI 相容 API（可接任何相容服務）
python translate_cli.py 樣本.pdf --engine openai --openai-key 你的KEY \
    --openai-base https://api.openai.com/v1 --openai-model gpt-4o-mini

# 除錯：只看抓到哪些文字區塊，不翻譯、不呼叫網路
python translate_cli.py 樣本.pdf --dump-text blocks.txt --engine mock
```

## 翻譯引擎比較

| 引擎 | 金鑰 | 說明 |
|------|------|------|
| `mymemory` | 不需要 | 免費，沙箱實測可用；每天有約 5,000 字限制 |
| `google` | 不需要 | 免費非官方端點，部分網路環境會被限流（HTTP 429） |
| `deepl` | 需要 | 品質佳，免費層每月 50 萬字，`api-free.deepl.com` |
| `openai` | 需要 | LLM 翻譯最通順，可串任何 OpenAI 相容服務 |
| `mock` | 不需要 | 測試用，離線產生「【中譯】+原文」 |

## 測試

```bash
cd app
pip install pytest
python -m pytest tests/test_pdftrans.py -v
```

## 已知限制（階段 4 處理）

- 表格內的文字會被當成逐格段落翻譯，欄位寬度有限時可能擠在一起
- 圖片內嵌文字（掃描 PDF）不在處理範圍，需要 OCR 才能翻
- 免費引擎（mymemory/google）不保證專有名詞一致性，商用建議串 DeepL 或 LLM
