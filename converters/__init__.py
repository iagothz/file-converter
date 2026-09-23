"""Registro de conversores disponíveis.

Para adicionar um novo conversor, crie um módulo em converters/ com:
    SOURCE   = "ext de origem"   (ex.: "pdf")
    TARGET   = "ext de destino"  (ex.: "png")
    OPTIONS  = [Option(...), ...] (pode ser vazio)
    def convert(src: Path, out_dir: Path, **opções) -> list[Path]
e adicione-o à lista _MODULES abaixo. O menu é montado automaticamente.
"""

from . import pdf_to_png

_MODULES = [
    pdf_to_png,
]

CONVERTERS = {(m.SOURCE, m.TARGET): m for m in _MODULES}


def sources() -> list[str]:
    return sorted({s for s, _ in CONVERTERS})


def targets(source: str) -> list[str]:
    return sorted(t for s, t in CONVERTERS if s == source)


def find(source: str, target: str):
    return CONVERTERS.get((source.lower().lstrip("."), target.lower().lstrip(".")))
