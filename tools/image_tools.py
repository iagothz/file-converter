"""Ferramentas de imagem (Pillow) e OCR (PyMuPDF + Tesseract)."""

import io
import os
from pathlib import Path

import pymupdf
from PIL import Image, ImageChops, ImageOps

import converters
from converters.images import LOSSY, PIL_FORMAT, prepare

from .base import Option, Tool, dest_dir, each, output_path, size_text, unique

IMAGES = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff")


def _format(src: Path) -> str:
    return converters.format_of(src) or "png"


def _open(src: Path) -> Image.Image:
    """Abre a imagem já na orientação correta (EXIF)."""
    with Image.open(src) as im:
        return ImageOps.exif_transpose(im)


def _encode(img: Image.Image, fmt: str, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    kwargs = {"quality": quality} if fmt in LOSSY else {}
    if fmt in ("jpg", "png", "webp"):
        kwargs["optimize"] = True
    prepare(img, fmt).save(buf, format=PIL_FORMAT[fmt], **kwargs)
    return buf.getvalue()


def _write(img: Image.Image, src: Path, out_dir, suffix: str, fmt: str | None = None, quality: int = 95) -> Path:
    fmt = fmt or _format(src)
    dest = output_path(src, out_dir, suffix, f".{fmt}" if fmt != _format(src) else None)
    dest.write_bytes(_encode(img, fmt, quality))
    return dest


# ---- Redimensionar / comprimir ------------------------------------------

RESIZE_MODES = ("Lado maior até (px)", "Largura até (px)", "Altura até (px)", "Porcentagem (%)", "Não redimensionar")
OUTPUT_FORMATS = ("Mesmo do original", "JPG", "WEBP", "PNG")


def _resized(img: Image.Image, mode: str, value: int) -> Image.Image:
    w, h = img.size
    if mode == "Porcentagem (%)":
        scale = value / 100
    elif mode == "Largura até (px)":
        scale = value / w
    elif mode == "Altura até (px)":
        scale = value / h
    elif mode == "Lado maior até (px)":
        scale = value / max(w, h)
    else:
        return img
    if mode != "Porcentagem (%)":
        scale = min(scale, 1)  # "até": nunca aumenta
    if scale == 1:
        return img
    return img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)


def _fit_size(img: Image.Image, fmt: str, quality: int, limit: int) -> tuple[bytes, str]:
    """Codifica tentando ficar abaixo de `limit` bytes: baixa a qualidade e, se preciso, a resolução."""
    for _ in range(10):
        if fmt in LOSSY:
            low, high, best = 10, quality, None
            while low <= high:  # busca binária pela maior qualidade que cabe
                q = (low + high) // 2
                data = _encode(img, fmt, q)
                if len(data) <= limit:
                    best, low = data, q + 1
                else:
                    high = q - 1
            if best:
                return best, ""
        else:
            data = _encode(img, fmt)
            if len(data) <= limit:
                return data, ""
        img = img.resize((max(1, int(img.width * 0.85)), max(1, int(img.height * 0.85))), Image.LANCZOS)
    return _encode(img, fmt, 10), " (não coube no limite)"


def resize(files, out_dir, opts, ctx):
    limit = opts["max_kb"] * 1024

    def run(src):
        img = _resized(_open(src), opts["mode"], opts["value"])
        fmt = _format(src) if opts["format"] == OUTPUT_FORMATS[0] else opts["format"].lower()
        if limit:
            data, note = _fit_size(img, fmt, opts["quality"], limit)
        else:
            data, note = _encode(img, fmt, opts["quality"]), ""
        dest = output_path(src, out_dir, "_otimizado", f".{fmt}" if fmt != _format(src) else None)
        dest.write_bytes(data)
        with Image.open(io.BytesIO(data)) as out:
            size = out.size
        return f"{size[0]}x{size[1]}, {size_text(src.stat().st_size)} -> {size_text(len(data))}{note} -> {dest}"

    each(files, ctx, run)


# ---- Cortar --------------------------------------------------------------

RATIOS = {"1:1": (1, 1), "4:3": (4, 3), "3:4": (3, 4), "16:9": (16, 9), "9:16": (9, 16),
          "3:2": (3, 2), "2:3": (2, 3), "Remover bordas uniformes": None}
ALIGN = ("Centro", "Topo / esquerda", "Base / direita")


def _trim(img: Image.Image, tolerance: int) -> Image.Image:
    rgb = img.convert("RGB")
    background = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
    diff = ImageChops.difference(rgb, background).convert("L").point(lambda p: 255 if p > tolerance else 0)
    box = diff.getbbox()
    return img.crop(box) if box else img


def crop(files, out_dir, opts, ctx):
    ratio, align = RATIOS[opts["ratio"]], opts["align"]

    def run(src):
        img = _open(src)
        before = img.size
        if ratio is None:
            img = _trim(img, opts["tolerance"])
        else:
            w, h = img.size
            target_w, target_h = (w, round(w * ratio[1] / ratio[0]))
            if target_h > h:
                target_w, target_h = round(h * ratio[0] / ratio[1]), h
            factor = {"Centro": 0.5, "Topo / esquerda": 0, "Base / direita": 1}[align]
            left, top = round((w - target_w) * factor), round((h - target_h) * factor)
            img = img.crop((left, top, left + target_w, top + target_h))
        dest = _write(img, src, out_dir, "_cortado")
        return f"{before[0]}x{before[1]} -> {img.width}x{img.height} -> {dest}"

    each(files, ctx, run)


# ---- Girar / espelhar ----------------------------------------------------

TRANSFORMS = {
    "Girar 90° horário": Image.Transpose.ROTATE_270,
    "Girar 90° anti-horário": Image.Transpose.ROTATE_90,
    "Girar 180°": Image.Transpose.ROTATE_180,
    "Espelhar na horizontal": Image.Transpose.FLIP_LEFT_RIGHT,
    "Espelhar na vertical": Image.Transpose.FLIP_TOP_BOTTOM,
    "Só corrigir pela orientação da câmera (EXIF)": None,
}


def transform(files, out_dir, opts, ctx):
    op = TRANSFORMS[opts["operation"]]

    def run(src):
        img = _open(src)
        if op is not None:
            img = img.transpose(op)
        return str(_write(img, src, out_dir, "_girado"))

    each(files, ctx, run)


# ---- Tons de cinza -------------------------------------------------------

def grayscale(files, out_dir, opts, ctx):
    def run(src):
        img = _open(src)
        has_alpha = img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info
        gray = ImageOps.grayscale(img)
        if has_alpha:
            gray.putalpha(img.convert("RGBA").getchannel("A"))
        return str(_write(gray, src, out_dir, "_cinza"))

    each(files, ctx, run)


# ---- Ícones --------------------------------------------------------------

ICON_MODES = (".ico (16 a 256 px)", "Pacote de favicons para site")
FAVICONS = {"favicon-16x16.png": 16, "favicon-32x32.png": 32, "apple-touch-icon.png": 180,
            "android-chrome-192x192.png": 192, "android-chrome-512x512.png": 512}


def _square(img: Image.Image) -> Image.Image:
    img = img.convert("RGBA")
    side = max(img.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
    return canvas


def icons(files, out_dir, opts, ctx):
    def run(src):
        img = _square(_open(src))
        if opts["mode"] == ICON_MODES[0]:
            dest = output_path(src, out_dir, "", ".ico")
            sizes = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
            img.resize((256, 256), Image.LANCZOS).save(dest, format="ICO", sizes=sizes)
            return str(dest)
        folder = unique(dest_dir(src, out_dir) / f"{src.stem}_favicons")
        folder.mkdir()
        for name, size in FAVICONS.items():
            img.resize((size, size), Image.LANCZOS).save(folder / name, optimize=True)
        img.resize((48, 48), Image.LANCZOS).save(folder / "favicon.ico", format="ICO",
                                                 sizes=[(16, 16), (32, 32), (48, 48)])
        return f"{len(FAVICONS) + 1} arquivos -> {folder}"

    each(files, ctx, run)


# ---- OCR -----------------------------------------------------------------

OCR_OUTPUTS = ("Texto (.txt)", "PDF pesquisável")
TESSERACT_HELP = ("o OCR precisa do Tesseract instalado. Baixe em "
                  "https://github.com/UB-Mannheim/tesseract/wiki e marque o idioma português na instalação.")


def _tessdata() -> str:
    try:
        return pymupdf.get_tessdata()
    except Exception:
        pass
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        candidate = Path(base) / "Tesseract-OCR" / "tessdata"
        if candidate.is_dir():
            return str(candidate)
    raise RuntimeError(TESSERACT_HELP)


def _pixmaps(src: Path):
    """Cada página (PDF) ou a imagem como Pixmap RGB."""
    if src.suffix.lower() == ".pdf":
        with pymupdf.open(src) as doc:
            for page in doc:
                yield page.get_pixmap(dpi=300)
    else:
        buf = io.BytesIO()
        _open(src).convert("RGB").save(buf, format="PNG")
        yield pymupdf.Pixmap(buf.getvalue())


def ocr(files, out_dir, opts, ctx):
    tessdata = _tessdata()
    language = opts["language"]

    def run(src):
        if opts["output"] == OCR_OUTPUTS[0]:
            texts = []
            for pix in _pixmaps(src):
                page_doc = pymupdf.open("pdf", pix.pdfocr_tobytes(language=language, tessdata=tessdata))
                texts.append(page_doc[0].get_text())
            dest = output_path(src, out_dir, "_ocr", ".txt")
            dest.write_text("\n\n".join(texts), encoding="utf-8")
            words = sum(len(t.split()) for t in texts)
            return f"{words} palavra(s) -> {dest}"

        out = pymupdf.open()
        for pix in _pixmaps(src):
            out.insert_pdf(pymupdf.open("pdf", pix.pdfocr_tobytes(language=language, tessdata=tessdata)))
        dest = output_path(src, out_dir, "_ocr", ".pdf")
        out.save(dest, garbage=3, deflate=True)
        return f"{out.page_count} página(s) -> {dest}"

    each(files, ctx, run)


TOOLS = [
    Tool("Redimensionar / comprimir", "Reduz a resolução e o tamanho das imagens, com limite opcional em KB.",
         resize, IMAGES, [
             Option("mode", "Redimensionar", RESIZE_MODES[0], choices=RESIZE_MODES),
             Option("value", "Valor", 1920, int),
             Option("format", "Formato de saída", OUTPUT_FORMATS[0], choices=OUTPUT_FORMATS),
             Option("quality", "Qualidade (1-100)", 85, int, hint="vale para JPG e WEBP"),
             Option("max_kb", "Tamanho máximo (KB)", 0, int, hint="0 = sem limite"),
         ]),
    Tool("Cortar", "Corta para uma proporção (ex.: quadrado para redes sociais) ou remove bordas lisas.",
         crop, IMAGES, [
             Option("ratio", "Proporção", "1:1", choices=tuple(RATIOS)),
             Option("align", "Manter", "Centro", choices=ALIGN),
             Option("tolerance", "Tolerância para bordas", 10, int, hint="0-255; só para remover bordas"),
         ]),
    Tool("Girar / espelhar", "Gira ou espelha as imagens.",
         transform, IMAGES, [Option("operation", "Operação", "Girar 90° horário", choices=tuple(TRANSFORMS))]),
    Tool("Tons de cinza", "Converte as imagens para preto e branco (tons de cinza), mantendo a transparência.",
         grayscale, IMAGES),
    Tool("Gerar ícones", "Cria um .ico com vários tamanhos ou o pacote de favicons de um site.",
         icons, IMAGES, [Option("mode", "Gerar", ICON_MODES[0], choices=ICON_MODES)]),
    Tool("OCR (reconhecer texto)", "Lê o texto de imagens e PDFs escaneados. Requer o Tesseract instalado.",
         ocr, IMAGES + (".pdf",), [
             Option("output", "Gerar", OCR_OUTPUTS[0], choices=OCR_OUTPUTS),
             Option("language", "Idioma", "por", choices=("por", "eng", "por+eng")),
         ]),
]
