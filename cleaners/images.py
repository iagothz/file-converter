"""Remoção de metadados de imagens.

JPEG, PNG e WEBP: os blocos de metadados são retirados direto do arquivo,
sem recomprimir a imagem (nenhuma perda de qualidade).
TIFF: a imagem é regravada só com os pixels (formato sem perda).
"""

from pathlib import Path

from PIL import Image, ImageOps, ImageSequence

EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff")

ORIENTATION = 0x0112


def clean(src: Path, dest: Path, comments: bool = False) -> list[str]:
    ext = src.suffix.lower()
    if ext in (".tif", ".tiff"):
        return _clean_tiff(src, dest)

    data = src.read_bytes()
    strip = {".png": _strip_png, ".webp": _strip_webp}.get(ext, _strip_jpeg)
    cleaned, removed = strip(data, src)
    dest.write_bytes(cleaned)
    return list(dict.fromkeys(removed))


# ---- JPEG ---------------------------------------------------------------

def _jpeg_segment_name(marker: int, payload: bytes) -> str | None:
    """Nome do metadado contido no segmento, ou None se o segmento deve ficar."""
    if marker == 0xFE:
        return "comentário"
    if marker == 0xE1:
        if payload.startswith(b"Exif\0"):
            return "EXIF (câmera, data, GPS...)"
        if payload.startswith(b"http://ns.adobe.com/"):
            return "XMP"
        return "APP1"
    if marker == 0xE2 and payload.startswith(b"ICC_PROFILE"):
        return None  # perfil de cor: necessário para exibir as cores certas
    if marker == 0xEE and payload.startswith(b"Adobe"):
        return None  # necessário para decodificar JPEGs CMYK
    if marker == 0xED:
        return "IPTC/Photoshop"
    if 0xE1 <= marker <= 0xEF:
        return f"APP{marker - 0xE0}"
    return None


def _strip_jpeg(data: bytes, src: Path) -> tuple[bytes, list[str]]:
    if data[:2] != b"\xff\xd8":
        raise ValueError("JPEG inválido")

    # Mantém só a orientação, senão fotos de celular aparecem giradas
    with Image.open(src) as im:
        orientation = im.getexif().get(ORIENTATION, 1)

    out = bytearray(data[:2])
    insert_at = 2
    removed = []
    i = 2
    while i < len(data):
        if data[i] != 0xFF:
            raise ValueError("JPEG inválido")
        marker = data[i + 1]
        if marker == 0xFF:  # byte de preenchimento
            i += 1
            continue
        if marker in (0xDA, 0xD9):  # início dos dados da imagem / fim
            out += data[i:]
            break
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:
            out += data[i:i + 2]
            i += 2
            continue
        length = int.from_bytes(data[i + 2:i + 4], "big")
        segment = data[i:i + 2 + length]
        name = _jpeg_segment_name(marker, segment[4:])
        if name:
            removed.append(name)
        else:
            out += segment
            if marker == 0xE0 and insert_at == 2:
                insert_at = len(out)
        i += 2 + length

    if orientation != 1:
        exif = Image.Exif()
        exif[ORIENTATION] = orientation
        payload = exif.tobytes()
        out[insert_at:insert_at] = b"\xff\xe1" + (len(payload) + 2).to_bytes(2, "big") + payload

    return bytes(out), removed


# ---- PNG ----------------------------------------------------------------

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_METADATA = {b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"tIME"}


def _strip_png(data: bytes, src: Path) -> tuple[bytes, list[str]]:
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("PNG inválido")

    out = bytearray(PNG_SIGNATURE)
    removed = []
    i = len(PNG_SIGNATURE)
    while i < len(data):
        length = int.from_bytes(data[i:i + 4], "big")
        kind = data[i + 4:i + 8]
        chunk = data[i:i + 12 + length]
        if kind in PNG_METADATA:
            if kind == b"eXIf":
                removed.append("EXIF")
            elif kind == b"tIME":
                removed.append("data de modificação")
            else:
                keyword = chunk[8:].split(b"\0", 1)[0].decode("latin-1")
                removed.append(f"texto ({keyword})")
        else:
            out += chunk
        i += 12 + length
    return bytes(out), removed


# ---- WEBP ---------------------------------------------------------------

def _strip_webp(data: bytes, src: Path) -> tuple[bytes, list[str]]:
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError("WEBP inválido")

    chunks = []
    removed = []
    i = 12
    while i + 8 <= len(data):
        fourcc = data[i:i + 4]
        size = int.from_bytes(data[i + 4:i + 8], "little")
        end = i + 8 + size + (size & 1)
        if fourcc == b"EXIF":
            removed.append("EXIF")
        elif fourcc == b"XMP ":
            removed.append("XMP")
        else:
            chunks.append(bytearray(data[i:end]))
        i = end

    for chunk in chunks:
        if chunk[:4] == b"VP8X":
            chunk[8] &= ~(0x08 | 0x04) & 0xFF  # flags de EXIF e XMP

    body = b"WEBP" + b"".join(chunks)
    return b"RIFF" + len(body).to_bytes(4, "little") + body, removed


# ---- TIFF ---------------------------------------------------------------

TIFF_TAGS = {
    270: "descrição", 271: "fabricante", 272: "modelo", 305: "software",
    306: "data", 315: "autor", 316: "computador", 33432: "copyright",
    34665: "EXIF", 34853: "GPS", 700: "XMP", 33723: "IPTC", 37724: "Photoshop",
}


def _clean_tiff(src: Path, dest: Path) -> list[str]:
    with Image.open(src) as im:
        removed = [label for tag, label in TIFF_TAGS.items() if tag in im.tag_v2]
        compression = im.info.get("compression", "raw")
        dpi = im.info.get("dpi")
        icc = im.info.get("icc_profile")

        frames = []
        for frame in ImageSequence.Iterator(im):
            frame = ImageOps.exif_transpose(frame).copy()
            frame.info = {}
            frames.append(frame)

    kwargs = {"compression": compression}
    if dpi:
        kwargs["dpi"] = dpi
    if icc:
        kwargs["icc_profile"] = icc
    frames[0].save(dest, format="TIFF", save_all=True, append_images=frames[1:], **kwargs)
    return removed
