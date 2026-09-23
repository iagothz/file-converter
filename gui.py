"""Interface gráfica do conversor. É o ponto de entrada do executável."""

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

import cleaners
import converters
import core

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:  # sem arrastar e soltar, o resto funciona igual
    TkinterDnD = None

PAD = {"padx": 8, "pady": 4}
SAME_FOLDER = "Mesma pasta do arquivo original"
DONE = object()  # sinal na fila de registro: a tarefa terminou


class FileList(ttk.LabelFrame):
    """Lista de arquivos com botões de adicionar/remover e arrastar e soltar."""

    def __init__(self, master, accept: Callable[[Path], bool], filetypes: Callable[[], list],
                 on_change: Callable[[list[Path]], None], log: Callable[[str], None]):
        super().__init__(master, text="Arquivos")
        self.accept, self.filetypes, self.on_change, self.log = accept, filetypes, on_change, log
        self.files: list[Path] = []

        box = ttk.Frame(self)
        box.pack(fill="both", expand=True, padx=8, pady=(4, 0))
        self.listbox = tk.Listbox(box, height=6, selectmode="extended", activestyle="none")
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.listbox.bind("<Delete>", lambda _: self.remove_selected())

        hint = "Arraste arquivos ou pastas para cá" if TkinterDnD else "Clique em \"Adicionar arquivos\""
        self.hint = ttk.Label(self.listbox, text=hint, foreground="gray", background="white")

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", **PAD)
        ttk.Button(buttons, text="Adicionar arquivos...", command=self.ask_files).pack(side="left")
        ttk.Button(buttons, text="Adicionar pasta...", command=self.ask_folder).pack(side="left", padx=6)
        ttk.Button(buttons, text="Limpar lista", command=self.clear).pack(side="right")
        ttk.Button(buttons, text="Remover selecionados", command=self.remove_selected).pack(side="right", padx=6)

        if TkinterDnD:
            for widget in (self, self.listbox, self.hint):
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self._on_drop)

        self._refresh()

    def _on_drop(self, event):
        self.add(Path(p) for p in self.tk.splitlist(event.data))
        return event.action

    def ask_files(self):
        self.add(Path(p) for p in filedialog.askopenfilenames(title="Escolher arquivos", filetypes=self.filetypes()))

    def ask_folder(self):
        folder = filedialog.askdirectory(title="Escolher pasta")
        if folder:
            self.add([Path(folder)])

    def add(self, paths):
        """Adiciona arquivos; pastas são percorridas (com subpastas)."""
        added, ignored = [], 0
        known = set(self.files)
        for path in paths:
            candidates = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
            for p in candidates:
                if not self.accept(p):
                    ignored += 1
                elif p not in known:
                    known.add(p)
                    added.append(p)
        self.files += added
        if ignored:
            self.log(f"[ignorado] {ignored} arquivo(s) de formato não suportado")
        self._refresh()

    def remove_selected(self):
        selected = set(self.listbox.curselection())
        self.files = [f for i, f in enumerate(self.files) if i not in selected]
        self._refresh()

    def clear(self):
        self.files = []
        self._refresh()

    def _refresh(self):
        self.listbox.delete(0, "end")
        for f in self.files:
            self.listbox.insert("end", str(f))
        if self.files:
            self.hint.place_forget()
        else:
            self.hint.place(relx=0.5, rely=0.5, anchor="center")
        self.on_change(self.files)


class Tab(ttk.Frame):
    """Base das abas: lista de arquivos, destino, botão de ação, status e registro."""

    action_label = ""

    def __init__(self, master):
        super().__init__(master)
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.out_dir = tk.StringVar(value=SAME_FOLDER)

        self.build()

        self.file_list = FileList(self, self.accept, self.filetypes, lambda _: self.refresh_status(), self.log_queue.put)
        self.file_list.pack(fill="both", expand=True, **PAD)

        dest = ttk.LabelFrame(self, text="Salvar em")
        dest.pack(fill="x", **PAD)
        ttk.Entry(dest, textvariable=self.out_dir, state="readonly").pack(side="left", fill="x", expand=True, **PAD)
        ttk.Button(dest, text="Escolher pasta...", command=self._ask_out_dir).pack(side="left")
        ttk.Button(dest, text="Pasta original", command=lambda: self.out_dir.set(SAME_FOLDER)).pack(side="left", **PAD)

        actions = ttk.Frame(self)
        actions.pack(fill="x", **PAD)
        self.status = ttk.Label(actions, text="")
        self.status.pack(side="left")
        self.action_btn = ttk.Button(actions, text=self.action_label, command=self._start)
        self.action_btn.pack(side="right")

        self.log = tk.Text(self, height=8, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, **PAD)

        self.refresh_status()
        self.after(100, self._drain_log)

    # A implementar pelas abas
    def build(self): ...
    def accept(self, path: Path) -> bool: return True
    def filetypes(self) -> list: return [("Todos os arquivos", "*.*")]
    def status_text(self, files: list[Path]) -> str: return f"{len(files)} arquivo(s) na lista"
    def prepare(self, files: list[Path], out_dir: Path | None): ...  # retorna a tarefa, ou None

    @property
    def files(self) -> list[Path]:
        return self.file_list.files if hasattr(self, "file_list") else []

    def refresh_status(self):
        if hasattr(self, "status"):
            self.status["text"] = self.status_text(self.files)

    def _ask_out_dir(self):
        folder = filedialog.askdirectory(title="Salvar em")
        if folder:
            self.out_dir.set(folder)

    # O tkinter só pode ser usado pela thread principal: a tarefa só escreve
    # na fila, e _drain_log (na thread principal) atualiza a tela.
    def _start(self):
        if not self.files:
            messagebox.showinfo("File Converter", "Adicione arquivos à lista primeiro.")
            return
        out_dir = None if self.out_dir.get() == SAME_FOLDER else Path(self.out_dir.get())
        task = self.prepare(list(self.files), out_dir)
        if task is None:
            return
        self.action_btn["state"] = "disabled"

        def work():
            try:
                task(self.log_queue.put)
            except Exception as e:
                self.log_queue.put(f"[erro] {e}")
            finally:
                self.log_queue.put(DONE)

        threading.Thread(target=work, daemon=True).start()

    def _drain_log(self):
        while not self.log_queue.empty():
            message = self.log_queue.get()
            if message is DONE:
                self.action_btn["state"] = "normal"
                continue
            self.log["state"] = "normal"
            self.log.insert("end", message + "\n")
            self.log.see("end")
            self.log["state"] = "disabled"
        self.after(100, self._drain_log)


def _patterns(exts) -> str:
    return " ".join(f"*{e}" for e in exts)


class ConvertTab(Tab):
    action_label = "Converter"

    def build(self):
        self.option_vars: dict[str, tuple[tk.StringVar, type]] = {}

        formats = ttk.LabelFrame(self, text="Conversão")
        formats.pack(fill="x", **PAD)

        ttk.Label(formats, text="De:").grid(row=0, column=0, sticky="w", **PAD)
        self.source = ttk.Combobox(formats, state="readonly", width=12,
                                   values=[s.upper() for s in converters.sources()])
        self.source.grid(row=0, column=1, sticky="w", **PAD)
        self.source.bind("<<ComboboxSelected>>", lambda _: self._on_source_change())

        ttk.Label(formats, text="Para:").grid(row=0, column=2, sticky="w", **PAD)
        self.target = ttk.Combobox(formats, state="readonly", width=12)
        self.target.grid(row=0, column=3, sticky="w", **PAD)
        self.target.bind("<<ComboboxSelected>>", lambda _: self._on_target_change())

        self.options_frame = ttk.LabelFrame(self, text="Opções")
        self.options_frame.pack(fill="x", **PAD)

        self.source.current(0)
        self._on_source_change()

    def _selected(self) -> tuple[str, str]:
        return self.source.get().lower(), self.target.get().lower()

    def _on_source_change(self):
        values = [t.upper() for t in converters.targets(self.source.get().lower())]
        self.target["values"] = values
        if values:
            self.target.current(0)
        self._on_target_change()

    def _on_target_change(self):
        for child in self.options_frame.winfo_children():
            child.destroy()
        self.option_vars.clear()

        conv = converters.find(*self._selected())
        if conv is None or not conv.options:
            ttk.Label(self.options_frame, text="Nenhuma opção para esta conversão.").pack(anchor="w", **PAD)
        else:
            for row, opt in enumerate(conv.options):
                var = tk.StringVar(value=str(opt.default))
                ttk.Label(self.options_frame, text=opt.label + ":").grid(row=row, column=0, sticky="w", **PAD)
                ttk.Entry(self.options_frame, textvariable=var, width=12).grid(row=row, column=1, sticky="w", **PAD)
                self.option_vars[opt.key] = (var, opt.type)
        self.refresh_status()

    def accept(self, path):
        return converters.format_of(path) is not None

    def filetypes(self):
        all_exts = [e for s in converters.sources() for e in converters.extensions(s)]
        return ([("Arquivos suportados", _patterns(all_exts))]
                + [(s.upper(), _patterns(converters.extensions(s))) for s in converters.sources()]
                + [("Todos os arquivos", "*.*")])

    def status_text(self, files):
        source, _ = self._selected()
        # Escolhe o formato "De" automaticamente pelos arquivos adicionados
        formats = {converters.format_of(f) for f in files}
        if files and source not in formats:
            self.source.set(converters.format_of(files[-1]).upper())
            self.after_idle(self._on_source_change)
            return ""
        matching = sum(converters.format_of(f) == source for f in files)
        text = f"{matching} arquivo(s) .{source}"
        if matching < len(files):
            text += f" ({len(files) - matching} de outro formato serão ignorados)"
        return text

    def prepare(self, files, out_dir):
        source, target = self._selected()
        if not converters.find(source, target):
            messagebox.showwarning("File Converter", "Escolha uma conversão válida.")
            return None

        opts = {}
        for key, (var, typ) in self.option_vars.items():
            try:
                opts[key] = typ(var.get())
            except ValueError:
                messagebox.showerror("File Converter", f"Valor inválido para '{key}': {var.get()}")
                return None

        return lambda log: core.run(source, target, files, out_dir, opts, log=log)


class MetadataTab(Tab):
    action_label = "Remover metadados"

    def build(self):
        info = ttk.LabelFrame(self, text="Remover metadados")
        info.pack(fill="x", **PAD)
        ttk.Label(
            info, justify="left", wraplength=520,
            text=(
                "Remove autor, datas, GPS, câmera, programa usado e outras informações escondidas. "
                "Os originais não são alterados: é criada uma cópia limpa "
                "(com o sufixo \"_sem-metadados\" quando salva na mesma pasta).\n"
                f"Formatos: {', '.join(cleaners.formats())}"
            ),
        ).pack(anchor="w", **PAD)

        self.comments = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            info, variable=self.comments,
            text="Remover também comentários e alterações controladas (DOCX) e anotações (PDF)",
        ).pack(anchor="w", **PAD)
        ttk.Label(
            info, foreground="gray", wraplength=520, justify="left",
            text="As alterações controladas são aceitas: o texto inserido fica e o excluído sai.",
        ).pack(anchor="w", padx=28)

    def accept(self, path):
        return cleaners.find(path) is not None

    def filetypes(self):
        return [("Arquivos suportados", _patterns(cleaners.extensions())), ("Todos os arquivos", "*.*")]

    def prepare(self, files, out_dir):
        comments = self.comments.get()
        return lambda log: core.strip_metadata(files, out_dir, comments=comments, log=log)


class App(TkinterDnD.Tk if TkinterDnD else tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("File Converter")
        self.minsize(600, 640)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=4, pady=4)
        for tab, title in ((ConvertTab, "Converter"), (MetadataTab, "Remover metadados")):
            notebook.add(tab(notebook), text=title)


if __name__ == "__main__":
    App().mainloop()
