import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pdftrans.job import (
    ENGINE_LABELS,
    engine_to_label,
    label_to_engine,
    parse_key,
    validate_input,
)
from pdftrans.pipeline import translate_pdf
from pdftrans.translators import ENGINES, create_translator

APP_TITLE = "PDF 英→中翻譯工具"


class TranslatorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("720x540")
        self.minsize(640, 480)
        self.queue = queue.Queue()
        self.worker = None
        self.abort_event = None
        self.var_input = tk.StringVar(value="")
        self.var_out = tk.StringVar(value="")
        self._build_widgets()
        self.after(100, self._poll_queue)

    def _build_widgets(self):
        pad = {"padx": 10, "pady": 6}
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True)

        row = ttk.Frame(frame)
        row.pack(fill="x", **pad)
        ttk.Button(row, text="1. 選擇 PDF 檔案", command=self.choose_pdf).pack(side="left")
        ttk.Button(row, text="或選擇整個資料夾（批次）", command=self.choose_folder).pack(side="left", padx=8)
        ttk.Label(row, textvariable=self.var_input, foreground="#333").pack(side="left", fill="x", expand=True)

        row2 = ttk.Frame(frame)
        row2.pack(fill="x", **pad)
        ttk.Label(row2, text="翻譯引擎：").pack(side="left")
        self.cmb_engine = ttk.Combobox(
            row2, values=[engine_to_label(n) for n in ENGINES], state="readonly", width=34
        )
        self.cmb_engine.current(0)
        self.cmb_engine.pack(side="left")
        self.cmb_engine.bind("<<ComboboxSelected>>", lambda _e: self._toggle_key_hint())

        ttk.Label(row2, text="  目標語言：").pack(side="left")
        self.cmb_lang = ttk.Combobox(
            row2, values=["zh-TW（繁體中文）", "zh-Hans（簡體中文）"], state="readonly", width=18
        )
        self.cmb_lang.current(0)
        self.cmb_lang.pack(side="left")

        row3 = ttk.Frame(frame)
        row3.pack(fill="x", **pad)
        ttk.Label(row3, text="API Key：").pack(side="left")
        self.var_key = tk.StringVar()
        ttk.Entry(row3, textvariable=self.var_key, width=48, show="*").pack(side="left")
        self.lbl_key_hint = ttk.Label(row3, text="", foreground="#777")
        self.lbl_key_hint.pack(side="left", padx=6)

        row4 = ttk.Frame(frame)
        row4.pack(fill="x", **pad)
        ttk.Button(row4, text="輸出資料夾（選填）", command=self.choose_out).pack(side="left")
        ttk.Label(row4, textvariable=self.var_out, foreground="#555").pack(side="left", padx=8)

        row5 = ttk.Frame(frame)
        row5.pack(fill="x", **pad)
        self.btn_start = ttk.Button(row5, text="2. 開始翻譯", command=self.start)
        self.btn_start.pack(side="left")
        self.btn_abort = ttk.Button(row5, text="中斷", command=self.abort, state="disabled")
        self.btn_abort.pack(side="left", padx=(8, 0))
        self.progress = ttk.Progressbar(row5, mode="determinate", length=380)
        self.progress.pack(side="left", padx=12)
        self.lbl_pct = ttk.Label(row5, text="0%")
        self.lbl_pct.pack(side="left")

        ttk.Label(frame, text="訊息記錄：").pack(anchor="w", **pad)
        self.txt_log = tk.Text(frame, height=16, state="disabled", wrap="word")
        self.txt_log.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self._toggle_key_hint()

    def _toggle_key_hint(self):
        engine = label_to_engine(self.cmb_engine.get())
        hints = {
            "deepl": "DeepL key 到 deepl.com 免費申請",
            "openai": "格式：API_KEY 或 BASE_URL|API_KEY|MODEL",
        }
        self.lbl_key_hint.configure(text=hints.get(engine, "此引擎不需要 key"))

    def choose_pdf(self):
        path = filedialog.askopenfilename(title="選擇 PDF", filetypes=[("PDF 檔案", "*.pdf")])
        if path:
            self.var_input.set(path)

    def choose_folder(self):
        path = filedialog.askdirectory(title="選擇資料夾（批次處理所有 PDF）")
        if path:
            self.var_input.set(path)

    def choose_out(self):
        path = filedialog.askdirectory(title="選擇輸出資料夾")
        if path:
            self.var_out.set(path)

    def _log(self, msg):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", msg + "\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def collect_job(self):
        input_obj = self.var_input.get().strip()
        files, batch_out = validate_input(input_obj)
        engine = label_to_engine(self.cmb_engine.get())
        dst = "zh-TW" if self.cmb_lang.get().startswith("zh-TW") else "zh-Hans"
        engine_kwargs = parse_key(engine, self.var_key.get().strip())
        out = self.var_out.get().strip() or (batch_out if len(files) > 1 else None)
        return engine, dst, files, out, engine_kwargs

    def start(self):
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("進行中", "已有翻譯在執行中。")
            return
        try:
            job = self.collect_job()
        except ValueError as e:
            messagebox.showerror("錯誤", str(e))
            return
        engine, dst, files, out, engine_kwargs = job
        self.btn_start.configure(state="disabled")
        self.btn_abort.configure(state="normal")
        self.progress.configure(value=0)
        self.abort_event = threading.Event()
        self._log(f"引擎：{engine}｜目標語言：{dst}｜共 {len(files)} 個檔案")
        self.worker = threading.Thread(target=self._run, args=job, daemon=True)
        self.worker.start()

    def abort(self):
        if self.abort_event:
            self.abort_event.set()
            self._log("正在中斷，等目前請求結束…")
        self.btn_abort.configure(state="disabled")

    def _run(self, engine, dst, files, out, engine_kwargs):
        try:
            translator = create_translator(engine, **engine_kwargs)

            def cb(info, stage):
                self.queue.put(("progress", info, stage))

            results = []
            if out:
                os.makedirs(out, exist_ok=True)
            for i, src_pdf in enumerate(files, 1):
                target = (
                    os.path.join(
                        out,
                        os.path.splitext(os.path.basename(src_pdf))[0] + "_translated.pdf",
                    )
                    if out
                    else None
                )
                self.queue.put(("file", f"[{i}/{len(files)}] {os.path.basename(src_pdf)}", None))
                results.append(
                    translate_pdf(
                        src_pdf,
                        target,
                        translator=translator,
                        src="en",
                        dst=dst,
                        progress_cb=cb,
                        abort=self.abort_event,
                    )
                )
            self.queue.put(("done", results, None))
        except Exception as e:
            self.queue.put(("error", None, f"{type(e).__name__}: {e}"))

    def _poll_queue(self):
        try:
            while True:
                kind, a, b = self.queue.get_nowait()
                if kind == "progress":
                    info, stage = a, b
                    self.progress.configure(maximum=100, value=info.percent)
                    self.lbl_pct.configure(text=f"{info.percent}%")
                    if stage not in ("start", "done"):
                        self._log(f"  {stage}：{info.done_blocks}/{info.total_blocks} 區塊")
                elif kind == "file":
                    self._log(a)
                elif kind == "done":
                    results = a
                    for out_path, info in results:
                        self._log(f"完成：{out_path}（{info.page_count} 頁，失敗 {info.failed_blocks} 區塊）")
                    self.btn_start.configure(state="normal")
                    self.btn_abort.configure(state="disabled")
                    first_out = results[0][0] if results else None
                    if first_out and messagebox.askyesno("完成", "翻譯完成！要開啟輸出資料夾嗎？"):
                        self._open_folder(os.path.dirname(first_out) or ".")
                elif kind == "error":
                    if b.startswith("TranslationCancelled"):
                        self._log("已中斷：使用者要求停止，本次未產生輸出檔。")
                        messagebox.showinfo("已中斷", "翻譯已中斷，未產生輸出檔。")
                    else:
                        self._log("錯誤：" + b)
                        messagebox.showerror("翻譯失敗", b)
                    self.btn_start.configure(state="normal")
                    self.btn_abort.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _open_folder(self, path):
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
        except OSError:
            pass


def main():
    app = TranslatorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
