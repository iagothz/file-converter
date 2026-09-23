"""Estrutura comum das ferramentas.

Uma ferramenta recebe a lista de arquivos escolhidos, a pasta de destino
(None = pasta de cada original) e as opções, e relata o andamento por `ctx`.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from converters.base import Option, unique  # noqa: F401  (reexportados para as ferramentas)


@dataclass
class Context:
    log: Callable[[str], None] = print
    progress: Callable[[int, int], None] = lambda done, total: None
    # Avisa que um arquivo da lista mudou de caminho (renomeado/movido)
    renamed: Callable[[Path, Path], None] = lambda old, new: None


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    run: Callable[[list[Path], Path | None, dict, Context], None]
    extensions: tuple[str, ...] | None = None  # None = qualquer arquivo
    options: list[Option] = field(default_factory=list)
    writes_files: bool = True  # False: só mostra resultados (esconde "Salvar em")
    preview: Callable[[list[Path], Path | None, dict, Context], None] | None = None
    ordered: bool = False  # a ordem da lista importa (mostra botões de subir/descer)

    def accepts(self, path: Path) -> bool:
        return self.extensions is None or path.suffix.lower() in self.extensions


def dest_dir(src: Path, out_dir: Path | None) -> Path:
    folder = Path(out_dir) if out_dir else src.parent
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def output_path(src: Path, out_dir: Path | None, suffix: str, ext: str | None = None) -> Path:
    """Caminho livre para o resultado de `src`.

    Na pasta do original o nome ganha `suffix` (para não confundir com ele);
    em outra pasta mantém o nome. `ext` troca a extensão (ex.: ".txt").
    """
    folder = dest_dir(src, out_dir)
    same = folder.resolve() == src.parent.resolve()
    return unique(folder / f"{src.stem}{suffix if same else ''}{ext or src.suffix}")


def each(files: list[Path], ctx: Context, fn: Callable[[Path], str]) -> tuple[int, int]:
    """Aplica `fn` a cada arquivo, registrando o resultado e o progresso.

    `fn` retorna a mensagem de sucesso. Retorna (ok, com erro).
    """
    ok = failed = 0
    for i, src in enumerate(files):
        ctx.progress(i, len(files))
        try:
            ctx.log(f"[ok] {src.name}: {fn(src)}")
            ok += 1
        except Exception as e:
            ctx.log(f"[erro] {src.name}: {e}")
            failed += 1
    ctx.progress(len(files), len(files))
    ctx.log(f"Concluído: {ok} arquivo(s), {failed} com erro.")
    return ok, failed


def size_text(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def parse_pages(text: str, count: int) -> list[list[int]]:
    """Converte "1-3, 7, 10-" em grupos de índices (base 0).

    Vazio = todas as páginas num grupo só. Páginas fora do documento dão erro.
    """
    text = text.strip()
    if not text:
        return [list(range(count))]
    groups = []
    for part in re.split(r"[;,]", text):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d*)\s*-\s*(\d*)|(\d+)", part)
        if not m:
            raise ValueError(f"intervalo inválido: '{part}'")
        if m.group(3):
            start = end = int(m.group(3))
        else:
            start = int(m.group(1) or 1)
            end = int(m.group(2) or count)
        if not (1 <= start <= end <= count):
            raise ValueError(f"páginas fora do documento (1-{count}): '{part}'")
        groups.append(list(range(start - 1, end)))
    return groups
