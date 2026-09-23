"""Registro de conversores disponíveis.

Para adicionar conversões, crie um módulo em converters/ com uma lista
CONVERSIONS = [Conversion(origem, destino, função, [Option(...)]), ...]
e adicione-o à lista _MODULES abaixo. O menu é montado automaticamente.
"""

from pathlib import Path

from . import data, images, pdf, sheets, text
from .base import Conversion

_MODULES = [
    pdf,
    images,
    text,
    data,
    sheets,
]

CONVERTERS: dict[tuple[str, str], Conversion] = {
    (c.source, c.target): c for m in _MODULES for c in m.CONVERSIONS
}

# Extensões aceitas para cada formato de origem
EXTENSIONS = {
    "jpg": (".jpg", ".jpeg"),
    "tiff": (".tiff", ".tif"),
}


def extensions(fmt: str) -> tuple[str, ...]:
    return EXTENSIONS.get(fmt, (f".{fmt}",))


def sources() -> list[str]:
    return sorted({s for s, _ in CONVERTERS})


def targets(source: str) -> list[str]:
    return sorted(t for s, t in CONVERTERS if s == source)


def find(source: str, target: str) -> Conversion | None:
    return CONVERTERS.get((source.lower().lstrip("."), target.lower().lstrip(".")))


def format_of(path: Path) -> str | None:
    """Formato de origem correspondente à extensão do arquivo."""
    ext = path.suffix.lower()
    return next((fmt for fmt in sources() if ext in extensions(fmt)), None)
