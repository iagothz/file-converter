"""Ferramentas de PDF (PyMuPDF)."""

import io
import re
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

from .base import (Context, Option, Tool, dest_dir, each, output_path, parse_pages,
                   size_text, unique)

PDF = (".pdf",)
IMAGES = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff")

PAGES = Option("pages", "Páginas", "", str, hint="ex.: 1-3, 7, 10-  (vazio = todas)")


def _open(src: Path) -> pymupdf.Document:
    doc = pymupdf.open(src)
    if doc.needs_pass:
        doc.close()
        raise ValueError("PDF protegido por senha (use \"Remover senha\" antes)")
    return doc


def _page_set(text: str, count: int) -> list[int]:
    return sorted({i for group in parse_pages(text, count) for i in group})


def _save(doc: pymupdf.Document, dest: Path, **kwargs) -> None:
    doc.save(dest, garbage=3, deflate=True, **kwargs)


# ---- Juntar -------------------------------------------------------------

def _image_as_pdf(src: Path) -> pymupdf.Document:
    """Imagem -> documento PDF de 1 página (respeitando a rotação EXIF)."""
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, "white")
            bg.paste(im, mask=im.getchannel("A"))
            im = bg
        buf = io.BytesIO()
        im.save(buf, format="PNG")
    img = pymupdf.open("png", buf.getvalue())
    return pymupdf.open("pdf", img.convert_to_pdf())


def merge(files, out_dir, opts, ctx: Context):
    out = pymupdf.open()
    toc = []
    for i, src in enumerate(files):
        ctx.progress(i, len(files))
        part = _open(src) if src.suffix.lower() == ".pdf" else _image_as_pdf(src)
        toc.append([1, src.stem, out.page_count + 1])
        pages = part.page_count
        out.insert_pdf(part)
        part.close()
        ctx.log(f"[ok] {src.name}: {pages} página(s)")
    if opts["bookmarks"]:
        out.set_toc(toc)
    dest = unique(dest_dir(files[0], out_dir) / f"{opts['name'].strip().removesuffix('.pdf') or 'unido'}.pdf")
    _save(out, dest)
    ctx.progress(len(files), len(files))
    ctx.log(f"Concluído: {len(files)} arquivo(s), {out.page_count} página(s) -> {dest}")


# ---- Dividir / extrair ---------------------------------------------------

SPLIT_MODES = ("Uma página por arquivo", "Um arquivo por intervalo", "Extrair páginas para um único PDF")


def split(files, out_dir, opts, ctx):
    mode = opts["mode"]

    def run(src):
        with _open(src) as doc:
            groups = parse_pages(opts["pages"], doc.page_count)
            if mode == SPLIT_MODES[2]:
                pages = sorted({i for g in groups for i in g})
                out = pymupdf.open()
                for i in pages:
                    out.insert_pdf(doc, from_page=i, to_page=i)
                dest = output_path(src, out_dir, "_extraido")
                _save(out, dest)
                return f"{len(pages)} página(s) -> {dest}"

            if mode == SPLIT_MODES[0]:
                groups = [[i] for g in groups for i in g]
            folder = unique(dest_dir(src, out_dir) / f"{src.stem}_dividido")
            folder.mkdir()
            digits = len(str(doc.page_count))
            for g in groups:
                out = pymupdf.open()
                out.insert_pdf(doc, from_page=g[0], to_page=g[-1])
                label = f"{g[0] + 1:0{digits}d}" + (f"-{g[-1] + 1:0{digits}d}" if len(g) > 1 else "")
                _save(out, folder / f"{src.stem}_p{label}.pdf")
            return f"{len(groups)} arquivo(s) em {folder}"

    each(files, ctx, run)


# ---- Comprimir -----------------------------------------------------------

LEVELS = {  # (dpi acima do qual reduz, dpi final, qualidade JPEG)
    "Leve (melhor qualidade)": (200, 150, 85),
    "Médio": (150, 120, 70),
    "Forte (menor tamanho)": (100, 96, 50),
}


def compress(files, out_dir, opts, ctx):
    threshold, target, quality = LEVELS[opts["level"]]

    def run(src):
        dest = output_path(src, out_dir, "_comprimido")
        with _open(src) as doc:
            doc.rewrite_images(dpi_threshold=threshold, dpi_target=target, quality=quality,
                               set_to_gray=opts["gray"])
            doc.subset_fonts()
            doc.save(dest, garbage=4, deflate=True, deflate_images=True, deflate_fonts=True,
                     clean=True, use_objstms=True)
        before, after = src.stat().st_size, dest.stat().st_size
        if after >= before:
            dest.unlink()
            return f"já está otimizado ({size_text(before)}), nada foi gravado"
        return f"{size_text(before)} -> {size_text(after)} (-{100 - after * 100 // before}%) -> {dest}"

    each(files, ctx, run)


# ---- Girar ---------------------------------------------------------------

ANGLES = {"90° horário": 90, "180°": 180, "90° anti-horário": 270}


def rotate(files, out_dir, opts, ctx):
    angle = ANGLES[opts["angle"]]

    def run(src):
        dest = output_path(src, out_dir, "_girado")
        with _open(src) as doc:
            pages = _page_set(opts["pages"], doc.page_count)
            for i in pages:
                doc[i].set_rotation((doc[i].rotation + angle) % 360)
            _save(doc, dest)
        return f"{len(pages)} página(s) girada(s) -> {dest}"

    each(files, ctx, run)


# ---- Imagens -> PDF ------------------------------------------------------

A4 = pymupdf.paper_rect("a4")
PAGE_SIZES = ("Tamanho da imagem", "A4 (retrato ou paisagem, conforme a imagem)", "A4 retrato")


def images_to_pdf(files, out_dir, opts, ctx):
    out = pymupdf.open()
    margin = opts["margin"] * 72 / 25.4  # mm -> pontos
    for i, src in enumerate(files):
        ctx.progress(i, len(files))
        img_doc = _image_as_pdf(src)
        w, h = img_doc[0].rect.width, img_doc[0].rect.height
        if opts["page_size"] == PAGE_SIZES[0]:
            page = out.new_page(width=w + 2 * margin, height=h + 2 * margin)
        else:
            landscape = opts["page_size"] == PAGE_SIZES[1] and w > h
            page = out.new_page(width=A4.height if landscape else A4.width,
                                height=A4.width if landscape else A4.height)
        area = page.rect + (margin, margin, -margin, -margin)
        page.show_pdf_page(area, img_doc, 0, keep_proportion=True)
        ctx.log(f"[ok] {src.name}")
    dest = unique(dest_dir(files[0], out_dir) / f"{opts['name'].strip().removesuffix('.pdf') or 'imagens'}.pdf")
    _save(out, dest)
    ctx.progress(len(files), len(files))
    ctx.log(f"Concluído: {out.page_count} página(s) -> {dest}")


# ---- Marca d'água --------------------------------------------------------

COLORS = {"Cinza": (0.5, 0.5, 0.5), "Vermelho": (0.8, 0.1, 0.1), "Preto": (0, 0, 0), "Azul": (0.1, 0.2, 0.7)}
WM_POSITIONS = ("Centro, na diagonal", "Centro", "Rodapé")


def _visible_to_page(page, point: pymupdf.Point) -> pymupdf.Point:
    """Converte um ponto da página como ela aparece (girada) para as coordenadas do PDF."""
    return point * page.derotation_matrix


def _watermark_image(path: str, opacity: float) -> bytes:
    with Image.open(path) as im:
        im = im.convert("RGBA")
        im.putalpha(im.getchannel("A").point(lambda a: int(a * opacity)))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
    return buf.getvalue()


def watermark(files, out_dir, opts, ctx):
    opacity = max(0, min(100, opts["opacity"])) / 100
    image = _watermark_image(opts["image"], opacity) if opts["image"].strip() else None
    if image is None and not opts["text"].strip():
        raise ValueError("informe o texto ou escolha uma imagem")
    position = opts["position"]

    def run(src):
        dest = output_path(src, out_dir, "_marca")
        with _open(src) as doc:
            pages = _page_set(opts["pages"], doc.page_count)
            for i in pages:
                page = doc[i]
                view = page.rect  # página como aparece na tela
                if image:
                    with Image.open(io.BytesIO(image)) as im:
                        ratio = im.height / im.width
                    width = view.width * (0.25 if position == "Rodapé" else 0.5)
                    cx = view.width / 2
                    cy = view.height - 36 - width * ratio / 2 if position == "Rodapé" else view.height / 2
                    box = pymupdf.Rect(cx - width / 2, cy - width * ratio / 2, cx + width / 2, cy + width * ratio / 2)
                    page.insert_image(box * page.derotation_matrix, stream=image, keep_proportion=True,
                                      rotate=page.rotation)
                else:
                    text, size = opts["text"], opts["font_size"]
                    width = pymupdf.get_text_length(text, fontname="helv", fontsize=size)
                    if position == "Rodapé":
                        anchor = pymupdf.Point(view.width / 2, view.height - 36)
                    else:
                        anchor = pymupdf.Point(view.width / 2, view.height / 2)
                    angle = 45 if position == WM_POSITIONS[0] else 0
                    center = _visible_to_page(page, anchor)
                    start = center + (-width / 2, size / 3)
                    page.insert_text(start, text, fontsize=size, fontname="helv", color=COLORS[opts["color"]],
                                     fill_opacity=opacity, stroke_opacity=opacity,
                                     morph=(center, pymupdf.Matrix(angle + page.rotation)))
            _save(doc, dest)
        return f"{len(pages)} página(s) -> {dest}"

    each(files, ctx, run)


# ---- Numerar páginas -----------------------------------------------------

NUMBER_FORMATS = ("1", "Página 1", "Página 1 de N", "1 / N")
NUMBER_POSITIONS = ("Rodapé, centro", "Rodapé, direita", "Rodapé, esquerda", "Topo, centro", "Topo, direita")


def page_numbers(files, out_dir, opts, ctx):
    fmt, pos, size = opts["format"], opts["position"], opts["font_size"]

    def label(n, total):
        return {"1": f"{n}", "Página 1": f"Página {n}", "Página 1 de N": f"Página {n} de {total}",
                "1 / N": f"{n} / {total}"}[fmt]

    def run(src):
        dest = output_path(src, out_dir, "_numerado")
        with _open(src) as doc:
            first = 1 if opts["skip_first"] else 0
            total = doc.page_count - first + opts["start"] - 1
            for i in range(first, doc.page_count):
                page = doc[i]
                view = page.rect
                text = label(i - first + opts["start"], total)
                width = pymupdf.get_text_length(text, fontname="helv", fontsize=size)
                margin = 28
                y = margin if pos.startswith("Topo") else view.height - margin + size / 2
                if pos.endswith("direita"):
                    x = view.width - margin - width
                elif pos.endswith("esquerda"):
                    x = margin
                else:
                    x = (view.width - width) / 2
                point = _visible_to_page(page, pymupdf.Point(x, y))
                page.insert_text(point, text, fontsize=size, fontname="helv", rotate=page.rotation)
            numbered = doc.page_count - first
            _save(doc, dest)
        return f"{numbered} página(s) numerada(s) -> {dest}"

    each(files, ctx, run)


# ---- Senha ---------------------------------------------------------------

def protect(files, out_dir, opts, ctx):
    password = opts["password"]
    if len(password) < 4:
        raise ValueError("a senha precisa ter ao menos 4 caracteres")
    permissions = pymupdf.PDF_PERM_ACCESSIBILITY
    if opts["allow_print"]:
        permissions |= pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_PRINT_HQ
    if opts["allow_copy"]:
        permissions |= pymupdf.PDF_PERM_COPY

    def run(src):
        dest = output_path(src, out_dir, "_protegido")
        with _open(src) as doc:
            doc.save(dest, garbage=3, deflate=True, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                     user_pw=password, owner_pw=opts["owner_password"] or password, permissions=permissions)
        return f"protegido com AES-256 -> {dest}"

    each(files, ctx, run)


def unprotect(files, out_dir, opts, ctx):
    def run(src):
        with pymupdf.open(src) as doc:
            if not doc.is_encrypted:
                return "o PDF não tem senha, nada foi gravado"
            if doc.needs_pass and not doc.authenticate(opts["password"]):
                raise ValueError("senha incorreta")
            dest = output_path(src, out_dir, "_sem-senha")
            doc.save(dest, garbage=3, deflate=True, encryption=pymupdf.PDF_ENCRYPT_NONE)
        return f"senha removida -> {dest}"

    each(files, ctx, run)


# ---- Extrair imagens -----------------------------------------------------

def extract_images(files, out_dir, opts, ctx):
    minimum = opts["min_size"]

    def run(src):
        folder = unique(dest_dir(src, out_dir) / f"{src.stem}_imagens")
        seen, count = set(), 0
        with _open(src) as doc:
            for page_no, page in enumerate(doc, start=1):
                for info in page.get_images(full=True):
                    xref = info[0]
                    if xref in seen:
                        continue
                    seen.add(xref)
                    image = doc.extract_image(xref)
                    if not image or min(image["width"], image["height"]) < minimum:
                        continue
                    folder.mkdir(exist_ok=True)
                    count += 1
                    (folder / f"{src.stem}_p{page_no}_{count}.{image['ext']}").write_bytes(image["image"])
        return f"{count} imagem(ns) -> {folder}" if count else "nenhuma imagem encontrada"

    each(files, ctx, run)


# ---- Tarjar (redação) ----------------------------------------------------

CPF = r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"
CNPJ = r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"
EMAIL = r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
PHONE = r"(?:\+55 ?)?(?:\(?\d{2}\)? ?)?9?\d{4}[- ]?\d{4}\b"
REDACT_TARGETS = {
    "CPF": [CPF],
    "CNPJ": [CNPJ],
    "E-mail": [EMAIL],
    "Telefone": [PHONE],
    "CPF, CNPJ, e-mail e telefone": [CNPJ, CPF, EMAIL, PHONE],
    "Texto personalizado": None,
    "Expressão regular": None,
}


def _redaction_terms(page, opts) -> list[str]:
    target, custom = opts["target"], opts["text"]
    text = page.get_text()
    if target == "Texto personalizado":
        terms = [t.strip() for t in custom.split(";") if t.strip()]
        if not terms:
            raise ValueError("informe o texto a tarjar (separe vários com ;)")
        return terms
    if target == "Expressão regular":
        if not custom.strip():
            raise ValueError("informe a expressão regular")
        patterns = [custom]
    else:
        patterns = REDACT_TARGETS[target]
    found = []
    for pattern in patterns:
        found += [m.group(0) for m in re.finditer(pattern, text, flags=re.I) if m.group(0).strip()]
    return list(dict.fromkeys(found))


def _redact(files, out_dir, opts, ctx, apply: bool):
    def run(src):
        with _open(src) as doc:
            total, samples = 0, []
            for page in doc:
                for term in _redaction_terms(page, opts):
                    rects = page.search_for(term)
                    if rects:
                        samples.append(term)
                    for rect in rects:
                        page.add_redact_annot(rect, fill=(0, 0, 0))
                        total += 1
                if apply:
                    page.apply_redactions()
            if not total:
                return "nada encontrado (PDFs escaneados não têm texto: use OCR antes)"
            shown = ", ".join(dict.fromkeys(samples))
            if not apply:
                return f"{total} ocorrência(s): {shown[:300]}"
            dest = output_path(src, out_dir, "_tarjado")
            doc.set_metadata({})
            _save(doc, dest, clean=True)
        return f"{total} ocorrência(s) apagada(s) -> {dest}"

    each(files, ctx, run)


def redact(files, out_dir, opts, ctx):
    _redact(files, out_dir, opts, ctx, apply=True)


def redact_preview(files, out_dir, opts, ctx):
    _redact(files, out_dir, opts, ctx, apply=False)


TOOLS = [
    Tool("Juntar PDFs", "Une os arquivos da lista em um único PDF, na ordem da lista. Imagens também podem entrar.",
         merge, PDF + IMAGES, [
             Option("name", "Nome do arquivo final", "unido"),
             Option("bookmarks", "Criar marcadores com o nome de cada arquivo", True, bool),
         ], ordered=True),
    Tool("Dividir / extrair páginas", "Separa o PDF em vários arquivos ou extrai só algumas páginas.",
         split, PDF, [
             Option("mode", "Modo", SPLIT_MODES[0], choices=SPLIT_MODES),
             PAGES,
         ]),
    Tool("Comprimir PDF", "Reduz o tamanho recomprimindo as imagens internas e removendo dados desnecessários.",
         compress, PDF, [
             Option("level", "Nível", "Médio", choices=tuple(LEVELS)),
             Option("gray", "Converter imagens para tons de cinza", False, bool),
         ]),
    Tool("Girar páginas", "Gira todas as páginas ou só as escolhidas.",
         rotate, PDF, [Option("angle", "Ângulo", "90° horário", choices=tuple(ANGLES)), PAGES]),
    Tool("Imagens -> PDF único", "Junta as imagens da lista em um único PDF, uma por página, na ordem da lista.",
         images_to_pdf, IMAGES, [
             Option("name", "Nome do arquivo final", "imagens"),
             Option("page_size", "Tamanho da página", PAGE_SIZES[1], choices=PAGE_SIZES),
             Option("margin", "Margem (mm)", 10, int),
         ], ordered=True),
    Tool("Marca d'água", "Adiciona um texto ou uma imagem sobre as páginas.",
         watermark, PDF, [
             Option("text", "Texto", "CONFIDENCIAL"),
             Option("image", "Imagem (opcional, substitui o texto)", "", file=True),
             Option("position", "Posição", WM_POSITIONS[0], choices=WM_POSITIONS),
             Option("opacity", "Opacidade (%)", 25, int),
             Option("font_size", "Tamanho da fonte", 60, int),
             Option("color", "Cor", "Cinza", choices=tuple(COLORS)),
             PAGES,
         ]),
    Tool("Numerar páginas", "Escreve o número em cada página.",
         page_numbers, PDF, [
             Option("format", "Formato", "Página 1 de N", choices=NUMBER_FORMATS),
             Option("position", "Posição", NUMBER_POSITIONS[0], choices=NUMBER_POSITIONS),
             Option("font_size", "Tamanho da fonte", 10, int),
             Option("start", "Começar em", 1, int),
             Option("skip_first", "Não numerar a primeira página (capa)", False, bool),
         ]),
    Tool("Proteger com senha", "Criptografa o PDF (AES-256): a senha é pedida para abrir.",
         protect, PDF, [
             Option("password", "Senha para abrir", "", secret=True),
             Option("owner_password", "Senha do proprietário (opcional)", "", secret=True,
                    hint="permite mudar as permissões; vazio = a mesma senha"),
             Option("allow_print", "Permitir imprimir", True, bool),
             Option("allow_copy", "Permitir copiar texto", False, bool),
         ]),
    Tool("Remover senha", "Cria uma cópia sem senha. É preciso saber a senha atual.",
         unprotect, PDF, [Option("password", "Senha atual", "", secret=True)]),
    Tool("Extrair imagens", "Salva as imagens contidas no PDF em uma pasta.",
         extract_images, PDF, [Option("min_size", "Ignorar imagens menores que (px)", 32, int)]),
    Tool("Tarjar informações", "Apaga de verdade (não só cobre) CPF, e-mail, telefone ou um texto escolhido. "
         "Use \"Pré-visualizar\" para ver o que será tarjado.",
         redact, PDF, [
             Option("target", "O que tarjar", "CPF, CNPJ, e-mail e telefone", choices=tuple(REDACT_TARGETS)),
             Option("text", "Texto ou expressão", "", hint="para texto personalizado, separe vários com ;"),
         ], preview=redact_preview),
]
