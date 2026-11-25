import os

ENGINE_LABELS = {
    "mymemory": "MyMemory（免金鑰，預設）",
    "google": "Google 免費端點（免金鑰）",
    "deepl": "DeepL（需 API key，品質佳）",
    "openai": "LLM OpenAI 相容（需 API key）",
    "mock": "Mock 離線測試（不連網）",
}


def engine_to_label(name):
    return ENGINE_LABELS.get(name, name)


def label_to_engine(label):
    for name, text in ENGINE_LABELS.items():
        if text == label:
            return name
    return label


def index_pdf_files(input_obj):
    if os.path.isdir(input_obj):
        found = [
            os.path.join(input_obj, n)
            for n in sorted(os.listdir(input_obj))
            if n.lower().endswith(".pdf")
        ]
        return found, input_obj.rstrip("\\/") + "_translated"
    return [input_obj], None


def validate_input(input_obj):
    if not input_obj or not os.path.exists(input_obj):
        raise ValueError("請先選擇存在的 PDF 檔案或資料夾。")
    files, batch_out = index_pdf_files(input_obj)
    if not files:
        raise ValueError("沒有找到任何 PDF。")
    return files, batch_out


def parse_key(engine, raw):
    if engine == "deepl":
        if not raw:
            raise ValueError("DeepL 需要 API key（到 deepl.com 免費申請）。")
        return {"deepl_key": raw}
    if engine == "openai":
        if not raw:
            raise ValueError("LLM 引擎需要 API key。")
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) == 3:
            base, key, model = parts
        elif len(parts) == 1:
            base, key, model = None, parts[0], None
        else:
            raise ValueError("LLM key 格式：API_KEY 或 BASE_URL|API_KEY|MODEL")
        return {"openai_key": key, "openai_base": base, "openai_model": model}
    return {}
