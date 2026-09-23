"""Conversões a partir de PDF (PyMuPDF)."""

from pathlib import Path

import pymupdf
from PIL import Image

from . import images
from .base import Conversion, Option, unique

IMAGE_TARGETS = ["png", "jpg", "webp", "bmp", "tiff"]
DPI = Option("dpi", "Resolução (DPI)", 150, int)


def _to_image(target: str):
    def convert(src: Path, out_dir: Path, dpi: int = 150, **opts) -> list[Path]:
        """Uma imagem por página, em `out_dir/<nome do pdf>/`."""
        dest_dir = unique(out_dir / src.stem)
        dest_dir.mkdir(parents=True, exist_ok=True)

        written = []
        with pymupdf.open(src) as doc:
            digits = len(str(doc.page_count))
            for i, page in enumerate(doc, start=1):
                pix = page.get_pixmap(dpi=dpi)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                dest = dest_dir / f"{src.stem}_p{i:0{digits}d}.{target}"
                images.save(img, dest, target, **opts)
                written.append(dest)
        return written
    return convert


def to_txt(src: Path, out_dir: Path) -> list[Path]:
    dest = unique(out_dir / f"{src.stem}.txt")
    with pymupdf.open(src) as doc:
        text = "\n\n".join(page.get_text() for page in doc)
    dest.write_text(text, encoding="utf-8")
    return [dest]


CONVERSIONS = [
    Conversion("pdf", target, _to_image(target), [DPI, *images.options_for(target)])
    for target in IMAGE_TARGETS
] + [
    Conversion("pdf", "txt", to_txt),
]
