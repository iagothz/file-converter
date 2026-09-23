"""Lógica compartilhada entre a interface gráfica e a linha de comando.

Os arquivos são salvos em `out_dir` ou, se ele não for informado, na mesma
pasta de cada arquivo original. Nada é sobrescrito: se o nome já existir,
o novo arquivo recebe um sufixo " (1)", " (2)"...
"""

from pathlib import Path
from typing import Callable

import cleaners
import converters
from converters.base import unique

Log = Callable[[str], None]


def _dest_dir(src: Path, out_dir: Path | None) -> Path:
    folder = Path(out_dir) if out_dir else src.parent
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _describe(written: list[Path]) -> str:
    if len(written) == 1:
        return str(written[0])
    return f"{len(written)} arquivos em {written[0].parent}"


def run(source: str, target: str, files: list[Path], out_dir: Path | None = None,
        opts: dict | None = None, log: Log = print) -> tuple[int, int]:
    """Converte os arquivos `source` da lista para `target`.

    Retorna (convertidos, com erro). Arquivos de outro formato são ignorados.
    """
    conv = converters.find(source, target)
    if conv is None:
        raise ValueError(f"Sem conversor de {source} para {target}")

    exts = converters.extensions(source)
    ok = failed = 0
    for src in map(Path, files):
        if src.suffix.lower() not in exts:
            log(f"[ignorado] {src.name}: não é .{source}")
            continue
        try:
            written = conv.convert(src, _dest_dir(src, out_dir), **(opts or {}))
            log(f"[ok] {src.name} -> {_describe(written)}")
            ok += 1
        except Exception as e:
            log(f"[erro] {src.name}: {e}")
            failed += 1

    log(f"Concluído: {ok} convertido(s), {failed} com erro.")
    return ok, failed


def strip_metadata(files: list[Path], out_dir: Path | None = None, comments: bool = False,
                   log: Log = print) -> tuple[int, int]:
    """Grava cópias sem metadados dos arquivos da lista.

    Na pasta do original, a cópia recebe o sufixo "_sem-metadados";
    em outra pasta, mantém o nome. Retorna (processados, com erro).
    """
    ok = failed = 0
    for src in map(Path, files):
        clean = cleaners.find(src)
        if clean is None:
            log(f"[ignorado] {src.name}: formato não suportado")
            continue

        folder = _dest_dir(src, out_dir)
        name = src.name if folder.resolve() != src.parent.resolve() else f"{src.stem}_sem-metadados{src.suffix}"
        dest = unique(folder / name)
        try:
            removed = clean(src, dest, comments=comments)
            what = f"removido {', '.join(removed)}" if removed else "nenhum metadado encontrado"
            log(f"[ok] {src.name}: {what} -> {dest}")
            ok += 1
        except Exception as e:
            dest.unlink(missing_ok=True)
            log(f"[erro] {src.name}: {e}")
            failed += 1

    log(f"Concluído: {ok} arquivo(s), {failed} com erro.")
    return ok, failed
