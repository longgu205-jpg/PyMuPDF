import os
import re


def load_glossary(path):
    mapping = {}
    if not path or not os.path.exists(path):
        return mapping
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            en, zh = line.split("=", 1)
            en, zh = en.strip(), zh.strip()
            if en and zh:
                mapping[en] = zh
    return mapping


def apply_glossary(text, mapping):
    if not mapping or not text:
        return text
    for en, zh in mapping.items():
        if en.lower() == en:
            pattern = re.compile(re.escape(en), re.IGNORECASE | re.UNICODE)
        else:
            pattern = re.compile(re.escape(en))
        text = pattern.sub(zh, text)
    return text


def save_sample(path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "# 術語表：一行一條，格式 英文術語=中文譯法；# 開頭是註解\n"
            "# 執行時選擇此檔，翻譯結果會固定套用這些詞\n"
            "# 範例：\n"
        )
