import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor


class TranslationError(RuntimeError):
    pass


class TranslationCancelled(RuntimeError):
    pass


class BaseTranslator:
    name = "base"
    CONCURRENCY = 8

    def translate(self, text, src="en", dst="zh-TW"):
        raise NotImplementedError

    def translate_many(self, texts, src="en", dst="zh-TW", progress=None, abort=None):
        texts = list(texts)
        results = [None] * len(texts)
        if not texts:
            return results
        done = 0

        def work(item):
            idx, text = item
            if abort is not None and abort.is_set():
                raise TranslationCancelled()
            try:
                return idx, self.translate(text, src, dst)
            except TranslationCancelled:
                raise
            except Exception:
                return idx, None

        pool = ThreadPoolExecutor(max_workers=self.CONCURRENCY)
        try:
            for idx, translated in pool.map(work, enumerate(texts)):
                results[idx] = translated
                done += 1
                if progress:
                    progress(done, len(texts))
        except TranslationCancelled:
            pool.shutdown(wait=False, cancel_futures=True)
            raise
        finally:
            pool.shutdown(wait=True)
        return results

    def close(self):
        pass


class MockTranslator(BaseTranslator):
    name = "mock"

    def translate(self, text, src="en", dst="zh-TW"):
        return "【中譯】" + text


def _http_json(url, data=None, headers=None, timeout=30, method=None):
    req = urllib.request.Request(url, headers=headers or {}, method=method)
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, body, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _retry(fn, attempts=4, delays=(2, 5, 10)):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (429, 500, 502, 503) and e.code < 600:
                raise
            if i < attempts - 1:
                time.sleep(delays[min(i, len(delays) - 1)])
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last = e
            if i < attempts - 1:
                time.sleep(delays[min(i, len(delays) - 1)])
    raise TranslationError(f"{fn} failed after {attempts} attempts: {last}")


class MyMemoryTranslator(BaseTranslator):
    name = "mymemory"
    MAX_Q = 480
    CONCURRENCY = 6

    def translate(self, text, src="en", dst="zh-TW"):
        text = text.strip()
        if not text:
            return text
        chunks = _split_chunks(text, self.MAX_Q)
        out = []
        for chunk in chunks:
            url = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode(
                {"q": chunk, "langpair": f"{src}|{dst}"}
            )
            data = _retry(lambda u=url: _http_json(u, headers={"User-Agent": "Mozilla/5.0"}))
            translated = (data.get("responseData") or {}).get("translatedText", "")
            if not translated or data.get("responseStatus") == 403 or "MYMEMORY WARNING" in translated.upper():
                raise TranslationError(f"MyMemory returned no translation (quota?): {translated[:120]}")
            out.append(translated)
        return " ".join(out)


class GoogleTranslator(BaseTranslator):
    name = "google"
    CONCURRENCY = 6

    def translate(self, text, src="en", dst="zh-TW"):
        text = text.strip()
        if not text:
            return text
        url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(
            {"client": "gtx", "sl": src, "tl": dst, "dt": "t", "q": text}
        )
        data = _retry(lambda u=url: _http_json(u, headers={"User-Agent": "Mozilla/5.0"}))
        return "".join(seg[0] for seg in data[0] if seg and seg[0])


class DeepLTranslator(BaseTranslator):
    name = "deepl"
    BATCH_SIZE = 50
    CONCURRENCY = 4

    def translate_many(self, texts, src="en", dst="zh-TW", progress=None, abort=None):
        texts = list(texts)
        results = [None] * len(texts)
        done = 0
        for start in range(0, len(texts), self.BATCH_SIZE):
            if abort is not None and abort.is_set():
                raise TranslationCancelled()
            chunk = texts[start : start + self.BATCH_SIZE]
            payload = {"text": chunk, "target_lang": _deepl_lang(dst)}
            if src:
                payload["source_lang"] = src.upper()
            try:
                data = _retry(
                    lambda p=payload: _http_json(
                        f"https://{self.host}/v2/translate",
                        data=p,
                        headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"},
                    )
                )
                for j, tr in enumerate(data.get("translations", [])):
                    results[start + j] = tr.get("text")
            except Exception as e:
                print(f"[warn] DeepL 批次失敗，該批 {len(chunk)} 段保留英文：{e}")
            done += len(chunk)
            if progress:
                progress(done, len(texts))
        return results

    def __init__(self, api_key=None, host=None):
        self.api_key = api_key or os.environ.get("DEEPL_API_KEY", "")
        self.host = host or os.environ.get("DEEPL_API_HOST", "")
        if not self.api_key:
            raise TranslationError("DeepL 需要 API key：傳入 --deepl-key 或設定環境變數 DEEPL_API_KEY。")
        if not self.host:
            self.host = "api-free.deepl.com" if self.api_key.endswith(":fx") else "api.deepl.com"

    def translate(self, text, src="en", dst="zh-TW"):
        text = text.strip()
        if not text:
            return text
        payload = {"text": [text], "target_lang": _deepl_lang(dst)}
        if src:
            payload["source_lang"] = src.upper()
        data = _retry(
            lambda: _http_json(
                f"https://{self.host}/v2/translate",
                data=payload,
                headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"},
            )
        )
        return data["translations"][0]["text"]


class OpenAITranslator(BaseTranslator):
    name = "openai"
    CONCURRENCY = 4

    def __init__(self, api_key=None, base_url=None, model=None, prompt=None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self.prompt = prompt or os.environ.get("OPENAI_PROMPT", "")
        if not self.api_key:
            raise TranslationError("LLM 引擎需要 API key：傳入 --openai-key 或設定環境變數 OPENAI_API_KEY。")

    def translate(self, text, src="en", dst="zh-TW"):
        text = text.strip()
        if not text:
            return text
        dst_name = _lang_name(dst)
        system = self.prompt or (
            f"You are a professional {src} to {dst_name} translator for business documents. "
            f"Translate the user text into natural, fluent {dst_name}. "
            "Output ONLY the translation, no notes, no quotes, keep the original line structure and placeholder tokens unchanged."
        )
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
        }
        data = _retry(
            lambda: _http_json(
                f"{self.base_url}/chat/completions",
                data=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        )
        return data["choices"][0]["message"]["content"].strip()


class GroqTranslator(OpenAITranslator):
    name = "groq"
    CONCURRENCY = 8

    def __init__(self, api_key=None, base_url=None, model=None, prompt=None):
        if not api_key:
            api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            raise TranslationError(
                "Groq 引擎需要 API key：到 console.groq.com 免費申請，傳入 --groq-key 或設定環境變數 GROQ_API_KEY。"
            )
        super().__init__(
            api_key=api_key,
            base_url=base_url or os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            model=model or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
            prompt=prompt,
        )


ENGINES = {
    "mymemory": MyMemoryTranslator,
    "google": GoogleTranslator,
    "deepl": DeepLTranslator,
    "groq": GroqTranslator,
    "openai": OpenAITranslator,
    "mock": MockTranslator,
}


ENGINE_KWARG_ALIASES = {
    "deepl": {"deepl_key": "api_key"},
    "groq": {"groq_key": "api_key"},
    "openai": {"openai_key": "api_key", "openai_base": "base_url", "openai_model": "model"},
}


def create_translator(engine="mymemory", **kwargs):
    try:
        cls = ENGINES[engine]
    except KeyError:
        raise TranslationError(f"未知引擎：{engine}，可選：{', '.join(sorted(ENGINES))}")
    for from_name, to_name in ENGINE_KWARG_ALIASES.get(engine, {}).items():
        if from_name in kwargs:
            kwargs[to_name] = kwargs.pop(from_name)
    return cls(**kwargs)


def _deepl_lang(dst):
    return {
        "zh-TW": "ZH-HANT",
        "zh-Hant": "ZH-HANT",
        "zh-HK": "ZH-HANT",
        "zh": "ZH",
        "zh-Hans": "ZH-HANS",
        "en": "EN-US",
    }.get(dst, dst.upper())


def _lang_name(dst):
    return {
        "zh-TW": "Traditional Chinese",
        "zh-Hant": "Traditional Chinese",
        "zh": "Chinese",
        "zh-Hans": "Simplified Chinese",
        "en": "English",
    }.get(dst, dst)


def _split_chunks(text, limit):
    import re

    if len(text) <= limit:
        return [text]
    sentences = re.split(r"(?<=[.!?。！？])\s+", text)
    chunks, current = [], ""
    for s in sentences:
        while len(s) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(s[:limit])
            s = s[limit:]
        if not current:
            current = s
        elif len(current) + 1 + len(s) <= limit:
            current = current + " " + s
        else:
            chunks.append(current)
            current = s
    if current:
        chunks.append(current)
    return chunks
