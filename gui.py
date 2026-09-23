"""Interface gráfica do conversor. É o ponto de entrada do executável."""

import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import converters
import core


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("File Converter")
        self.minsize(460, 380)
        core.ensure_dirs()

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.option_vars: dict[str, tuple[tk.StringVar, type]] = {}

        self._build()
        self._on_source_change()
        self.after(100, self._drain_log)

    # ---- layout -------------------------------------------------------

    def _build(self):
        pad = {"padx": 8, "pady": 4}

        formats = ttk.LabelFrame(self, text="Conversão")
        formats.pack(fill="x", **pad)

        ttk.Label(formats, text="De:").grid(row=0, column=0, sticky="w", **pad)
        self.source = ttk.Combobox(formats, state="readonly", width=12,
                                   values=[s.upper() for s in converters.sources()])
        self.source.grid(row=0, column=1, sticky="w", **pad)
        self.source.bind("<<ComboboxSelected>>", lambda _: self._on_source_change())

        ttk.Label(formats, text="Para:").grid(row=0, column=2, sticky="w", **pad)
        self.target = ttk.Combobox(formats, state="readonly", width=12)
        self.target.grid(row=0, column=3, sticky="w", **pad)
        self.target.bind("<<ComboboxSelected>>", lambda _: self._on_target_change())

        if self.source["values"]:
            self.source.current(0)

        self.options_frame = ttk.LabelFrame(self, text="Opções")
        self.options_frame.pack(fill="x", **pad)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", **pad)
        ttk.Button(buttons, text="Abrir pasta input", command=lambda: os.startfile(core.INPUT_DIR)).pack(side="left")
        ttk.Button(buttons, text="Abrir pasta output", command=lambda: os.startfile(core.OUTPUT_DIR)).pack(side="left", padx=6)
        self.convert_btn = ttk.Button(buttons, text="Converter", command=self._convert)
        self.convert_btn.pack(side="right")

        self.status = ttk.Label(self, text="")
        self.status.pack(fill="x", **pad)

        self.log = tk.Text(self, height=10, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, **pad)

    # ---- eventos ------------------------------------------------------

    def _selected(self) -> tuple[str, str]:
        return self.source.get().lower(), self.target.get().lower()

    def _on_source_change(self):
        source = self.source.get().lower()
        values = [t.upper() for t in converters.targets(source)]
        self.target["values"] = values
        if values:
            self.target.current(0)
        self._on_target_change()

    def _on_target_change(self):
        for child in self.options_frame.winfo_children():
            child.destroy()
        self.option_vars.clear()

        conv = converters.find(*self._selected())
        if conv is None or not conv.OPTIONS:
            ttk.Label(self.options_frame, text="Nenhuma opção para esta conversão.").pack(anchor="w", padx=8, pady=4)
        else:
            for row, opt in enumerate(conv.OPTIONS):
                var = tk.StringVar(value=str(opt.default))
                ttk.Label(self.options_frame, text=opt.label + ":").grid(row=row, column=0, sticky="w", padx=8, pady=4)
                ttk.Entry(self.options_frame, textvariable=var, width=12).grid(row=row, column=1, sticky="w", padx=8, pady=4)
                self.option_vars[opt.key] = (var, opt.type)

        self._refresh_status()

    def _refresh_status(self):
        source, _ = self._selected()
        if source:
            n = len(core.pending_files(source))
            self.status["text"] = f"{n} arquivo(s) .{source} na pasta input"

    def _convert(self):
        source, target = self._selected()
        if not converters.find(source, target):
            messagebox.showwarning("File Converter", "Escolha uma conversão válida.")
            return

        opts = {}
        for key, (var, typ) in self.option_vars.items():
            try:
                opts[key] = typ(var.get())
            except ValueError:
                messagebox.showerror("File Converter", f"Valor inválido para '{key}': {var.get()}")
                return

        self.convert_btn["state"] = "disabled"

        def work():
            try:
                core.run(source, target, opts, log=self.log_queue.put)
            except Exception as e:
                self.log_queue.put(f"[erro] {e}")
            finally:
                self.after(0, self._on_done)

        threading.Thread(target=work, daemon=True).start()

    def _on_done(self):
        self.convert_btn["state"] = "normal"
        self._refresh_status()

    def _drain_log(self):
        while not self.log_queue.empty():
            self.log["state"] = "normal"
            self.log.insert("end", self.log_queue.get() + "\n")
            self.log.see("end")
            self.log["state"] = "disabled"
        self.after(100, self._drain_log)


if __name__ == "__main__":
    App().mainloop()
