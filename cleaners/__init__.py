"""Registro de removedores de metadados.

Cada módulo define:
    EXTENSIONS = (".ext", ...)
    def clean(src: Path, dest: Path, comments: bool = False) -> list[str]
        grava em `dest` uma cópia sem metadados e retorna a descrição
        do que foi removido (lista vazia se não havia nada).
        `comments` pede para remover também comentários/anotações,
        quando o formato tiver.
    def inspect(src: Path) -> dict[str, str]
        metadados encontrados, sem alterar nada.
Para adicionar formatos, crie um módulo e inclua-o em _MODULES.
"""

from pathlib import Path

from . import images, office, pdf

_MODULES = [
    images,
    pdf,
    office,
]

CLEANERS = {ext: m.clean for m in _MODULES for ext in m.EXTENSIONS}
INSPECTORS = {ext: m.inspect for m in _MODULES for ext in m.EXTENSIONS}


def extensions() -> tuple[str, ...]:
    return tuple(CLEANERS)


def formats() -> list[str]:
    """Nomes para exibição (sem as variações .jpeg/.tif)."""
    return sorted({e.lstrip(".").upper() for e in CLEANERS} - {"JPEG", "TIF"})


def find(path: Path):
    return CLEANERS.get(path.suffix.lower())


def inspector(path: Path):
    return INSPECTORS.get(path.suffix.lower())
