"""Conversões de texto puro (PyMuPDF)."""

import html
from pathlib import Path

import pymupdf

from .base import Conversion, Option, unique

FONT_SIZE = Option("font_size", "Tamanho da fonte", 11, int)


def txt_to_pdf(src: Path, out_dir: Path, font_size: int = 11) -> list[Path]:
    dest = unique(out_dir / f"{src.stem}.pdf")
    text = src.read_text(encoding="utf-8", errors="replace")
    body = f'<pre style="font-family: monospace; font-size: {font_size}pt; white-space: pre-wrap">{html.escape(text)}</pre>'

    page = pymupdf.paper_rect("a4")
    where = page + (50, 50, -50, -50)
    story = pymupdf.Story(html=body)
    writer = pymupdf.DocumentWriter(str(dest))
    more = True
    while more:
        device = writer.begin_page(page)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
    writer.close()
    return [dest]


CONVERSIONS = [
    Conversion("txt", "pdf", txt_to_pdf, [FONT_SIZE]),
]
