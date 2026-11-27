# PDF 整份翻譯工具（底層 PyMuPDF）

將整份 PDF 文件由英文翻譯成中文（預設繁體中文 zh-TW），保留原頁面位置排版，輸出新的 PDF。

## 階段計畫

| 階段 | 內容 | 狀態 |
|------|------|------|
| 1 | 核心翻譯管線：區塊擷取 → 呼叫翻譯引擎 → 譯文寫回原位置 | ✅ 完成 |
| 2 | GUI（tkinter）＋資料夾批次＋進度條 | ✅ 完成 |
| 3 | Windows exe 打包（一鍵 build.bat，onedir 不包成單一 exe，避免檔案過大、啟動較快） | ✅ 已提供 build.bat，待 Windows 實測 |
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

## GUI 用法（階段 2）

```bash
cd app
python translate_gui.py
```

或直接在 PyCharm 對 `translate_gui.py` 按 Run。操作方式：

1. 選一個 PDF 檔案，**或**選一個資料夾（會批次處理裡面所有 PDF）
2. 選翻譯引擎（預設 MyMemory 免金鑰）；DeepL / LLM 需在 API Key 欄輸入金鑰
3. API Key 欄旁有「記住 API Key」勾選：勾著時按「開始翻譯」會把引擎/語言/key 存到本機設定檔
   （`%APPDATA%\pdf_translator_config.json`，Windows 上為明碼 JSON，僅建議在自己電腦使用），下次開啟自動填回；取消勾選則存檔時不含 key
4. 按視窗按鈕「開始翻譯」，進度條會即時顯示，完成後可一鍵開啟輸出資料夾
批次模式的輸出預設在 `<輸入資料夾>_translated/`，單檔模式預設與輸入檔同資料夾（`原名_translated.pdf`）。

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

# 串 Groq LLM（免費申請，快，LLM 品質；到 console.groq.com 拿 key）
python translate_cli.py 樣本.pdf --engine groq --groq-key 你的KEY

# 串 OpenAI 相容 API（可接任何相容服務）
python translate_cli.py 樣本.pdf --engine openai --openai-key 你的KEY \
    --openai-base https://api.openai.com/v1 --openai-model gpt-4o-mini

# 除錯：只看抓到哪些文字區塊，不翻譯、不呼叫網路
python translate_cli.py 樣本.pdf --dump-text blocks.txt --engine mock
```

## 打包 Windows exe（給同事用，階段 3）

在 `app` 資料夾內執行 `build.bat`（檔案總管雙擊，或 PyCharm 終端機執行 `build.bat`），它會自動：

1. 建立乾淨的打包用虛擬環境 `build_venv/`
2. 安裝 pymupdf + PyInstaller
3. 先跑完整測試，全綠才繼續
4. 打包成 onedir：`app\dist\PDFTranslator\PDFTranslator.exe`

把**整個 `dist\PDFTranslator` 資料夾**壓成 zip 給同事即可——同事解壓縮後直接執行 `PDFTranslator.exe`，不需要安裝 Python。同事第一次用時輸入自己的 DeepL API key 並勾「記住 API Key」（key 只存在同事自己的電腦 `%APPDATA%\pdf_translator_config.json`）。

注意：

- build.bat 的訊息是英文（避免 Windows 命令列編碼問題）
- 首次打包要下載 PyInstaller，約幾分鐘；產出資料夾約 150~250 MB
- 掃毒軟體偶爾會誤判 PyInstaller 打包的 exe，加入信任即可
- 想換 exe 圖示：在 build.bat 的 PyInstaller 命令加上 `--icon 圖示.ico`（選配）

## 翻譯速度

- 管線採「先收集全部區塊 → 平行批次翻譯 → 統一寫回」：Google/MyMemory/LLM 以多執行緒（6~8）同時請求，DeepL 一次請求打包 50 個區塊，速度遠快於逐區塊串行
- 相同文字區塊自動去重，不重複付費/耗額度
- GUI 有「中斷」按鈕，CLI 按 Ctrl+C；中斷後不產生輸出檔
- 想再快：申請 DeepL 免費 key（每月 50 萬字）是目前品質/速度最佳解

## 翻譯引擎比較

| 引擎 | 金鑰 | 說明 |
|------|------|------|
| `mymemory` | 不需要 | 免費，沙箱實測可用；每天有約 5,000 字限制 |
| `google` | 不需要 | 免費非官方端點，部分網路環境會被限流（HTTP 429） |
| `deepl` | 需要 | 品質佳，免費層每月 50 萬字，`api-free.deepl.com`；繁中送 `ZH-HANT`、簡中送 `ZH-HANS` |
| `groq` | 需要 | LLM 翻譯品質佳，Groq 速度極快，免費申請（console.groq.com） |
| `mock` | 不需要 | 測試用，離線產生「【中譯】+原文」 |

## 測試

```bash
cd app
pip install pytest
python -m pytest tests/test_pdftrans.py -v
```

## 段落重建（排版接近沉浸式翻譯）

PDF 內部常把一個段落的每一行存成獨立小區塊，逐塊翻譯會造成「每行偏短、右側留白、行距不一」。本工具會先把**同段落相鄰行合併**（左右對齊、行距連續、字級相近才合併），再整段重新排版，因此譯文會填充整個段落寬度、行距一致——與 immersive-translate 的整段重排方式相同。表格儲存格內不含併，維持逐格翻譯。

## 表格處理（已支援）

含框線的表格會用 PyMuPDF `find_tables` 自動偵測，**每個儲存格獨立翻譯**，不再把同一列的多格混成一段（這是技術文件譯文不通的主因）。

## 術語表（固定專有名詞）

1. 複製 `glossary_sample.txt` 成 `glossary.txt`，一行一條輸入 `英文=中文`：
   ```
   HMI=人機介面
   batch=批次
   ```
2. GUI 按「術語表（選填）」選檔，或 CLI：
   ```
   python translate_cli.py 檔案.pdf --glossary glossary.txt
   ```
翻譯結果會自動替換成術語表譯法（大小寫不敏感），確保整份文件用語一致。

## 已知限制

- 無框線的假表格以版面偵測不到時，仍以段落處理；空白儲存格多、跨欄合併的複雜表格也可能不完美
- 圖片內嵌文字（掃描 PDF）不在處理範圍，需要 OCR 才能翻
- 免費引擎（mymemory/google）不保證專有名詞一致性，商用建議串 DeepL 或 LLM
