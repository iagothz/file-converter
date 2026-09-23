"""Interface gráfica. É o ponto de entrada do executável."""

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

import pymupdf
from PIL import Image, ImageOps, ImageTk

import cleaners
import converters
import core
import settings
import tools
from converters.base import Option
from tools.base import Context, size_text

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:  # sem arrastar e soltar, o resto funciona igual
    TkinterDnD = None

APP = "File Converter"
PAD = {"padx": 8, "pady": 4}
SAME_FOLDER = "Mesma pasta do arquivo original"
DONE = object()  # sinal na fila: a tarefa terminou
THUMB = 150


def _patterns(exts) -> str:
    return " ".join(f"*{e}" for e in exts)


class OptionsForm(ttk.LabelFrame):
    """Monta os campos de uma lista de Option e lê os valores digitados."""

    def __init__(self, master):
        super().__init__(master, text="Opções")
        self.fields: dict[str, tuple[Option, tk.Variable]] = {}

    def show(self, options: list[Option], saved: dict | None = None):
        for child in self.winfo_children():
            child.destroy()
        self.fields.clear()
        saved = saved or {}
        if not options:
            ttk.Label(self, text="Nenhuma opção.").grid(row=0, column=0, sticky="w", **PAD)
            return
        self.columnconfigure(1, weight=1)
        for row, opt in enumerate(options):
            value = saved.get(opt.key, opt.default) if not opt.secret else opt.default
            if opt.type is bool:
                var = tk.BooleanVar(value=bool(value))
                ttk.Checkbutton(self, text=opt.label, variable=var).grid(row=row, column=0, columnspan=3, sticky="w", **PAD)
            else:
                var = tk.StringVar(value=str(value))
                ttk.Label(self, text=opt.label + ":").grid(row=row, column=0, sticky="w", **PAD)
                if opt.choices:
                    if var.get() not in opt.choices:
                        var.set(opt.default)
                    widget = ttk.Combobox(self, textvariable=var, values=opt.choices, state="readonly", width=38)
                elif opt.file:
                    widget = ttk.Frame(self)
                    ttk.Entry(widget, textvariable=var, width=32).pack(side="left", fill="x", expand=True)
                    ttk.Button(widget, text="...", width=3,
                               command=lambda v=var: v.set(filedialog.askopenfilename() or v.get())).pack(side="left")
                else:
                    widget = ttk.Entry(self, textvariable=var, width=40 if opt.type is str else 12,
                                       show="•" if opt.secret else "")
                widget.grid(row=row, column=1, sticky="w", **PAD)
                if opt.hint:
                    ttk.Label(self, text=opt.hint, foreground="gray").grid(row=row, column=2, sticky="w")
            self.fields[opt.key] = (opt, var)

    def values(self) -> dict:
        """Valores convertidos para o tipo de cada opção. ValueError se algum for inválido."""
        result = {}
        for key, (opt, var) in self.fields.items():
            try:
                result[key] = var.get() if opt.type is bool else opt.type(var.get())
            except (ValueError, tk.TclError):
                raise ValueError(f"Valor inválido em \"{opt.label}\": {var.get()}") from None
        return result

    def raw(self) -> dict:
        """Valores para salvar nas preferências (sem senhas)."""
        return {k: var.get() for k, (opt, var) in self.fields.items() if not opt.secret}


class FileList(ttk.LabelFrame):
    """Lista de arquivos com arrastar e soltar, reordenação e miniatura."""

    def __init__(self, master, accept: Callable[[Path], bool], filetypes: Callable[[], list],
                 on_change: Callable[[], None], log: Callable[[str], None]):
        super().__init__(master, text="Arquivos")
        self.accept, self.filetypes, self.on_change, self.log = accept, filetypes, on_change, log
        self.files: list[Path] = []
        self._thumb = None

        box = ttk.Frame(self)
        box.pack(fill="both", expand=True, padx=8, pady=(4, 0))
        self.listbox = tk.Listbox(box, height=7, selectmode="extended", activestyle="none")
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.preview = ttk.Label(box, text="", anchor="center", justify="center", width=22, compound="top")
        self.preview.pack(side="right", fill="y", padx=(8, 0))
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")
        self.listbox.bind("<Delete>", lambda _: self.remove_selected())
        self.listbox.bind("<<ListboxSelect>>", lambda _: self._show_preview())

        hint = "Arraste arquivos ou pastas para cá" if TkinterDnD else "Clique em \"Adicionar arquivos\""
        self.hint = ttk.Label(self.listbox, text=hint, foreground="gray", background="white")

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", **PAD)
        ttk.Button(buttons, text="Adicionar arquivos...", command=self.ask_files).pack(side="left")
        ttk.Button(buttons, text="Adicionar pasta...", command=self.ask_folder).pack(side="left", padx=6)
        self.order_buttons = ttk.Frame(buttons)
        ttk.Button(self.order_buttons, text="↑", width=3, command=lambda: self.move(-1)).pack(side="left")
        ttk.Button(self.order_buttons, text="↓", width=3, command=lambda: self.move(1)).pack(side="left")
        ttk.Button(buttons, text="Limpar lista", command=self.clear).pack(side="right")
        ttk.Button(buttons, text="Remover selecionados", command=self.remove_selected).pack(side="right", padx=6)

        if TkinterDnD:
            for widget in (self, self.listbox, self.hint):
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self._on_drop)

        self._refresh()

    def set_ordered(self, ordered: bool):
        if ordered:
            self.order_buttons.pack(side="left", padx=6)
        else:
            self.order_buttons.pack_forget()

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

    def replace(self, old: Path, new: Path):
        self.files = [new if f == old else f for f in self.files]
        self._refresh(keep_selection=True)

    def move(self, step: int):
        selected = list(self.listbox.curselection())
        if not selected:
            return
        order = selected if step < 0 else selected[::-1]
        if (step < 0 and order[0] == 0) or (step > 0 and order[0] == len(self.files) - 1):
            return
        for i in order:
            self.files[i], self.files[i + step] = self.files[i + step], self.files[i]
        self._refresh()
        for i in selected:
            self.listbox.selection_set(i + step)

    def remove_selected(self):
        selected = set(self.listbox.curselection())
        self.files = [f for i, f in enumerate(self.files) if i not in selected]
        self._refresh()

    def clear(self):
        self.files = []
        self._refresh()

    def _refresh(self, keep_selection=False):
        selected = self.listbox.curselection() if keep_selection else ()
        self.listbox.delete(0, "end")
        for f in self.files:
            self.listbox.insert("end", f.name + f"   ({f.parent})")
        for i in selected:
            self.listbox.selection_set(i)
        if self.files:
            self.hint.place_forget()
        else:
            self.hint.place(relx=0.5, rely=0.5, anchor="center")
        self._show_preview()
        self.on_change()

    def _show_preview(self):
        selected = self.listbox.curselection()
        if not selected:
            self._thumb = None
            self.preview.configure(image="", text="Selecione um arquivo\npara ver a prévia")
            return
        path = self.files[selected[0]]
        info = path.name if len(path.name) < 24 else path.name[:21] + "..."
        try:
            info += f"\n{size_text(path.stat().st_size)}"
            if path.suffix.lower() == ".pdf":
                with pymupdf.open(path) as doc:
                    page = doc[0]
                    zoom = THUMB / max(page.rect.width, page.rect.height)
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
                    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    info += f" · {doc.page_count} pág."
            else:
                with Image.open(path) as im:
                    info += f" · {im.width}x{im.height}"
                    img = ImageOps.exif_transpose(im)
                    img.thumbnail((THUMB, THUMB))
                    img = img.convert("RGBA")
            self._thumb = ImageTk.PhotoImage(img)
            self.preview.configure(image=self._thumb, text=info)
        except Exception:
            self._thumb = None
            self.preview.configure(image="", text=info + "\n(sem prévia)")


class Tab(ttk.Frame):
    """Base das abas: lista de arquivos, destino, botões, progresso e registro."""

    action_label = "Executar"
    preview_label = ""

    def __init__(self, master, app: "App", key: str):
        super().__init__(master)
        self.app, self.key = app, key
        self.state = app.prefs.setdefault("tabs", {}).setdefault(key, {})
        self.queue: queue.Queue = queue.Queue()
        self.out_dir = tk.StringVar(value=self.state.get("out_dir") or SAME_FOLDER)

        self.build()

        self.file_list = FileList(self, lambda p: self.accept(p), self.filetypes, self.refresh_status, self.queue.put)
        self.file_list.pack(fill="both", expand=True, **PAD)

        self.dest = ttk.LabelFrame(self, text="Salvar em")
        self.dest.pack(fill="x", **PAD)
        ttk.Entry(self.dest, textvariable=self.out_dir, state="readonly").pack(side="left", fill="x", expand=True, **PAD)
        ttk.Button(self.dest, text="Escolher pasta...", command=self._ask_out_dir).pack(side="left")
        ttk.Button(self.dest, text="Pasta original", command=lambda: self.out_dir.set(SAME_FOLDER)).pack(side="left", **PAD)

        actions = ttk.Frame(self)
        actions.pack(fill="x", **PAD)
        self.status = ttk.Label(actions, text="")
        self.status.pack(side="left")
        self.action_btn = ttk.Button(actions, text=self.action_label, command=lambda: self._start(preview=False))
        self.action_btn.pack(side="right")
        self.preview_btn = ttk.Button(actions, text=self.preview_label or "Pré-visualizar",
                                      command=lambda: self._start(preview=True))
        self.progress = ttk.Progressbar(actions, length=160, mode="determinate")
        self.progress.pack(side="right", padx=8)

        logs = ttk.Frame(self)
        logs.pack(fill="both", expand=True, **PAD)
        self.log = tk.Text(logs, height=8, state="disabled", wrap="word")
        log_scroll = ttk.Scrollbar(logs, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        self.set_preview(bool(self.preview_label))
        self.refresh_status()
        self.after(100, self._drain_queue)

    # ---- a implementar pelas abas ----
    def build(self): ...
    def accept(self, path: Path) -> bool: return True
    def filetypes(self) -> list: return [("Todos os arquivos", "*.*")]
    def status_text(self, files: list[Path]) -> str: return f"{len(files)} arquivo(s) na lista"
    def prepare(self, files: list[Path], out_dir: Path | None, preview: bool): ...  # tarefa(ctx) ou None
    def save_state(self): ...

    # ---- comum ----
    @property
    def files(self) -> list[Path]:
        return self.file_list.files if hasattr(self, "file_list") else []

    def set_preview(self, visible: bool, label: str = ""):
        if label:
            self.preview_btn.configure(text=label)
        if visible:
            self.preview_btn.pack(side="right", before=self.progress)
        else:
            self.preview_btn.pack_forget()

    def set_dest_visible(self, visible: bool):
        if visible:
            self.dest.pack(fill="x", before=self.status.master, **PAD)
        else:
            self.dest.pack_forget()

    def refresh_status(self):
        if hasattr(self, "status"):
            self.status["text"] = self.status_text(self.files)

    def _ask_out_dir(self):
        folder = filedialog.askdirectory(title="Salvar em")
        if folder:
            self.out_dir.set(folder)

    def _start(self, preview: bool):
        if not self.files:
            messagebox.showinfo(APP, "Adicione arquivos à lista primeiro.")
            return
        out_dir = None if self.out_dir.get() == SAME_FOLDER else Path(self.out_dir.get())
        try:
            task = self.prepare(list(self.files), out_dir, preview)
        except ValueError as e:
            messagebox.showerror(APP, str(e))
            return
        if task is None:
            return
        self.app.save_prefs()
        for button in (self.action_btn, self.preview_btn):
            button["state"] = "disabled"
        self.progress["value"] = 0

        # O tkinter só pode ser usado pela thread principal: a tarefa só escreve
        # na fila, e _drain_queue (na thread principal) atualiza a tela.
        ctx = Context(log=self.queue.put,
                      progress=lambda done, total: self.queue.put(("progress", done, total)),
                      renamed=lambda old, new: self.queue.put(("renamed", old, new)))

        def work():
            try:
                task(ctx)
            except Exception as e:
                self.queue.put(f"[erro] {e}")
            finally:
                self.queue.put(DONE)

        self._write_log(("— Pré-visualização —" if preview else "—" * 20))
        threading.Thread(target=work, daemon=True).start()

    def _write_log(self, message: str):
        self.log["state"] = "normal"
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log["state"] = "disabled"

    def _drain_queue(self):
        while not self.queue.empty():
            item = self.queue.get()
            if item is DONE:
                for button in (self.action_btn, self.preview_btn):
                    button["state"] = "normal"
                self.refresh_status()
            elif isinstance(item, tuple) and item[0] == "progress":
                self.progress.configure(maximum=max(item[2], 1), value=item[1])
            elif isinstance(item, tuple) and item[0] == "renamed":
                self.file_list.replace(item[1], item[2])
            else:
                self._write_log(item)
        self.after(100, self._drain_queue)

    def _base_state(self) -> dict:
        out = self.out_dir.get()
        return {"out_dir": "" if out == SAME_FOLDER else out}


class ConvertTab(Tab):
    action_label = "Converter"

    def build(self):
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

        self.form = OptionsForm(self)
        self.form.pack(fill="x", **PAD)
        self.saved_options: dict = self.state.get("options", {})
        self._pair = None

        source = self.state.get("source", "")
        self.source.set(source.upper() if source in converters.sources() else converters.sources()[0].upper())
        self._on_source_change(self.state.get("target"))

    def _selected(self) -> tuple[str, str]:
        return self.source.get().lower(), self.target.get().lower()

    def _on_source_change(self, target: str | None = None):
        values = [t.upper() for t in converters.targets(self.source.get().lower())]
        self.target["values"] = values
        if values:
            self.target.set(target.upper() if target and target.upper() in values else values[0])
        self._on_target_change()

    def _on_target_change(self):
        if self._pair:
            self.saved_options[self._pair] = self.form.raw()
        self._pair = ">".join(self._selected())
        conv = converters.find(*self._selected())
        self.form.show(conv.options if conv else [], self.saved_options.get(self._pair))
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

    def prepare(self, files, out_dir, preview):
        source, target = self._selected()
        if not converters.find(source, target):
            raise ValueError("Escolha uma conversão válida.")
        opts = self.form.values()
        return lambda ctx: core.run(source, target, files, out_dir, opts, log=ctx.log, progress=ctx.progress)

    def save_state(self):
        self.saved_options[self._pair] = self.form.raw()
        source, target = self._selected()
        return {**self._base_state(), "source": source, "target": target, "options": self.saved_options}


class MetadataTab(Tab):
    action_label = "Remover metadados"
    preview_label = "Ver metadados"

    def build(self):
        info = ttk.LabelFrame(self, text="Remover metadados")
        info.pack(fill="x", **PAD)
        ttk.Label(
            info, justify="left", wraplength=620,
            text=("Remove autor, datas, GPS, câmera, programa usado e outras informações escondidas. "
                  "Os originais não são alterados: é criada uma cópia limpa (com o sufixo "
                  "\"_sem-metadados\" quando salva na mesma pasta). Use \"Ver metadados\" para "
                  f"conferir antes.\nFormatos: {', '.join(cleaners.formats())}"),
        ).pack(anchor="w", **PAD)

        self.comments = tk.BooleanVar(value=self.state.get("comments", False))
        ttk.Checkbutton(
            info, variable=self.comments,
            text="Remover também comentários e alterações controladas (DOCX) e anotações (PDF)",
        ).pack(anchor="w", **PAD)
        ttk.Label(info, foreground="gray", wraplength=620, justify="left",
                  text="As alterações controladas são aceitas: o texto inserido fica e o excluído sai.",
                  ).pack(anchor="w", padx=28)

    def accept(self, path):
        return cleaners.find(path) is not None

    def filetypes(self):
        return [("Arquivos suportados", _patterns(cleaners.extensions())), ("Todos os arquivos", "*.*")]

    def prepare(self, files, out_dir, preview):
        if preview:
            return lambda ctx: core.show_metadata(files, log=ctx.log, progress=ctx.progress)
        comments = self.comments.get()
        return lambda ctx: core.strip_metadata(files, out_dir, comments=comments, log=ctx.log, progress=ctx.progress)

    def save_state(self):
        return {**self._base_state(), "comments": self.comments.get()}


class ToolTab(Tab):
    """Aba com um grupo de ferramentas (tools.GROUPS)."""

    def __init__(self, master, app, key, tool_list: list):
        self.tool_list = tool_list
        super().__init__(master, app, key)
        self._on_tool_change()

    def build(self):
        top = ttk.LabelFrame(self, text="Ferramenta")
        top.pack(fill="x", **PAD)
        names = [t.name for t in self.tool_list]
        self.tool_box = ttk.Combobox(top, state="readonly", values=names, width=40)
        self.tool_box.set(self.state.get("tool") if self.state.get("tool") in names else names[0])
        self.tool_box.pack(anchor="w", **PAD)
        self.tool_box.bind("<<ComboboxSelected>>", lambda _: self._on_tool_change())
        self.description = ttk.Label(top, wraplength=620, justify="left")
        self.description.pack(anchor="w", **PAD)

        self.form = OptionsForm(self)
        self.form.pack(fill="x", **PAD)
        self.saved_options: dict = self.state.get("options", {})
        self._current = None

    @property
    def tool(self):
        return next(t for t in self.tool_list if t.name == self.tool_box.get())

    def _on_tool_change(self):
        if self._current:
            self.saved_options[self._current] = self.form.raw()
        tool = self.tool
        self._current = tool.name
        self.description["text"] = tool.description
        self.form.show(tool.options, self.saved_options.get(tool.name))
        self.set_preview(tool.preview is not None)
        self.set_dest_visible(tool.writes_files)
        self.file_list.set_ordered(tool.ordered)
        self.refresh_status()

    def accept(self, path):
        return any(t.accepts(path) for t in self.tool_list)

    def filetypes(self):
        tool = self.tool
        if tool.extensions is None:
            return [("Todos os arquivos", "*.*")]
        return [("Arquivos suportados", _patterns(tool.extensions)), ("Todos os arquivos", "*.*")]

    def status_text(self, files):
        if not hasattr(self, "tool_box"):
            return ""
        usable = sum(self.tool.accepts(f) for f in files)
        text = f"{usable} arquivo(s)"
        if usable < len(files):
            text += f" ({len(files) - usable} não servem para esta ferramenta)"
        return text

    def prepare(self, files, out_dir, preview):
        tool, opts = self.tool, self.form.values()
        usable = [f for f in files if tool.accepts(f)]
        if not usable:
            raise ValueError("Nenhum arquivo da lista serve para esta ferramenta.")
        run = tool.preview if preview else tool.run
        if not tool.writes_files:
            out_dir = None
        return lambda ctx: run(usable, out_dir, opts, ctx)

    def save_state(self):
        self.saved_options[self._current] = self.form.raw()
        return {**self._base_state(), "tool": self._current, "options": self.saved_options}


class App(TkinterDnD.Tk if TkinterDnD else tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP)
        self.minsize(720, 760)
        self.prefs = settings.load()
        if self.prefs.get("geometry"):
            self.geometry(self.prefs["geometry"])

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=4, pady=4)
        self.tabs: list[Tab] = [ConvertTab(self.notebook, self, "Converter"),
                                MetadataTab(self.notebook, self, "Remover metadados")]
        self.tabs += [ToolTab(self.notebook, self, name, tool_list) for name, tool_list in tools.GROUPS]
        for tab in self.tabs:
            self.notebook.add(tab, text=tab.key)
        selected = self.prefs.get("tab", 0)
        if isinstance(selected, int) and 0 <= selected < len(self.tabs):
            self.notebook.select(selected)

        self.protocol("WM_DELETE_WINDOW", self._close)

    def save_prefs(self):
        for tab in self.tabs:
            self.prefs["tabs"][tab.key] = tab.save_state()
        self.prefs["tab"] = self.notebook.index(self.notebook.select())
        self.prefs["geometry"] = self.geometry()
        settings.save(self.prefs)

    def _close(self):
        self.save_prefs()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
