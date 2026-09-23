"""Conversor de PDF para PNG (uma imagem por página)."""

from pathlib import Path

import pymupdf

from .base import Option

SOURCE = "pdf"
TARGET = "png"
OPTIONS = [
    Option("dpi", "Resolução (DPI)", 150, int),
]


def convert(src: Path, out_dir: Path, dpi: int = 150) -> list[Path]:
    """Converte cada página de `src` em um PNG dentro de `out_dir/<nome do pdf>/`."""
    dest_dir = out_dir / src.stem
    dest_dir.mkdir(parents=True, exist_ok=True)

    written = []
    with pymupdf.open(src) as doc:
        digits = len(str(doc.page_count))
        for i, page in enumerate(doc, start=1):
            pix = page.get_pixmap(dpi=dpi)
            dest = dest_dir / f"{src.stem}_p{i:0{digits}d}.png"
            pix.save(dest)
            written.append(dest)
    return written
