"""Conversões entre formatos de imagem e de imagem para PDF (Pillow)."""

from pathlib import Path

from PIL import Image

from .base import Conversion, Option, unique

FORMATS = ["png", "jpg", "webp", "bmp", "gif", "tiff", "ico"]

PIL_FORMAT = {
    "png": "PNG", "jpg": "JPEG", "webp": "WEBP", "bmp": "BMP",
    "gif": "GIF", "tiff": "TIFF", "ico": "ICO", "pdf": "PDF",
}

# Formatos sem canal alfa: a transparência vira fundo branco
NO_ALPHA = {"jpg", "bmp", "pdf"}

QUALITY = Option("quality", "Qualidade (1-100)", 90, int)
LOSSY = {"jpg", "webp"}


def options_for(target: str) -> list[Option]:
    return [QUALITY] if target in LOSSY else []


def prepare(img: Image.Image, target: str) -> Image.Image:
    """Ajusta o modo de cor da imagem para o que o formato de destino aceita."""
    if target in NO_ALPHA:
        if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
            img = img.convert("RGBA")
            background = Image.new("RGB", img.size, "white")
            background.paste(img, mask=img.getchannel("A"))
            return background
        return img.convert("RGB")
    if img.mode not in ("1", "L", "LA", "P", "RGB", "RGBA"):
        img = img.convert("RGBA")
    return img


def save(img: Image.Image, dest: Path, target: str, quality: int = 90) -> None:
    kwargs = {"quality": quality} if target in LOSSY else {}
    prepare(img, target).save(dest, format=PIL_FORMAT[target], **kwargs)


def _to(target: str):
    def convert(src: Path, out_dir: Path, **opts) -> list[Path]:
        dest = unique(out_dir / f"{src.stem}.{target}")
        with Image.open(src) as img:
            save(img, dest, target, **opts)
        return [dest]
    return convert


CONVERSIONS = [
    Conversion(source, target, _to(target), options_for(target))
    for source in FORMATS
    for target in FORMATS + ["pdf"]
    if source != target
]
