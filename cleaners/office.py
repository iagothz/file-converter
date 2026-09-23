"""Remoção de metadados de documentos do Office (DOCX, XLSX, PPTX).

Esses arquivos são ZIPs; as propriedades do documento ficam em docProps/.
Os XMLs são editados como texto para não alterar mais nada no arquivo.
"""

import re
import zipfile
from pathlib import Path

from . import docx_content

EXTENSIONS = (".docx", ".xlsx", ".pptx")

CORE_LABELS = {
    "creator": "autor", "lastModifiedBy": "modificado por", "created": "data de criação",
    "modified": "data de modificação", "lastPrinted": "última impressão",
    "title": "título", "subject": "assunto", "keywords": "palavras-chave",
    "description": "comentários", "category": "categoria", "revision": "revisão",
    "contentStatus": "status", "identifier": "identificador", "language": "idioma",
    "version": "versão",
}

APP_LABELS = {
    "Company": "empresa", "Manager": "gerente", "Template": "modelo",
    "HyperlinkBase": "base de hiperlink", "Application": "aplicativo",
    "AppVersion": "versão do aplicativo", "TotalTime": "tempo de edição",
}

# Elementos com prefixo dentro de core.xml, ex.: <dc:creator>...</dc:creator>
CORE_ROOT = re.compile(r"<cp:coreProperties\b[^>]*[^/]>(.*)</cp:coreProperties>", re.S)
CORE_ELEMENT = re.compile(r"<((?:dc|cp|dcterms):(\w+))\b[^>]*?(?:/>|>(.*?)</\1>)", re.S)
CUSTOM_PROPERTY = re.compile(r'<property\b[^>]*\bname="([^"]*)"[^>]*>.*?</property>', re.S)

# Data mínima do formato ZIP: esconde quando o arquivo foi editado
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


def _clean_core(xml: str, removed: list[str]) -> str:
    def drop(m):
        if (m.group(3) or "").strip():
            removed.append(CORE_LABELS.get(m.group(2), m.group(2)))
        return ""

    root = CORE_ROOT.search(xml)
    if not root:
        return xml
    return xml[:root.start(1)] + CORE_ELEMENT.sub(drop, root.group(1)) + xml[root.end(1):]


def _clean_app(xml: str, removed: list[str]) -> str:
    for tag, label in APP_LABELS.items():
        pattern = re.compile(rf"<{tag}>(.*?)</{tag}>|<{tag}\s*/>", re.S)
        if any((m.group(1) or "").strip() for m in pattern.finditer(xml)):
            removed.append(label)
        xml = pattern.sub("", xml)
    return xml


def _clean_custom(xml: str, removed: list[str]) -> str:
    def drop(m):
        removed.append(f"propriedade personalizada ({m.group(1)})")
        return ""
    return CUSTOM_PROPERTY.sub(drop, xml)


EDITORS = {
    "docProps/core.xml": _clean_core,
    "docProps/app.xml": _clean_app,
    "docProps/custom.xml": _clean_custom,
}


def clean(src: Path, dest: Path, comments: bool = False) -> list[str]:
    """`comments`: também remove comentários e aceita alterações controladas (DOCX)."""
    removed: list[str] = []
    stats = {"comments": 0, "revisions": 0}
    strip_content = comments and src.suffix.lower() == ".docx"

    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dest, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item)
            editor = EDITORS.get(item.filename)
            if editor:
                data = editor(data.decode("utf-8"), removed).encode("utf-8")
            elif strip_content:
                data = docx_content.edit(item.filename, data, stats)
                if data is None:
                    continue
            item.date_time = ZIP_EPOCH
            zout.writestr(item, data)

    if stats["comments"]:
        removed.append(f"comentários ({stats['comments']})")
    if stats["revisions"]:
        removed.append(f"alterações controladas aceitas ({stats['revisions']})")
    return list(dict.fromkeys(removed))


def inspect(src: Path) -> dict[str, str]:
    found = {}
    with zipfile.ZipFile(src) as z:
        names = set(z.namelist())

        def read(name):
            return z.read(name).decode("utf-8") if name in names else ""

        root = CORE_ROOT.search(read("docProps/core.xml"))
        for m in CORE_ELEMENT.finditer(root.group(1) if root else ""):
            if (m.group(3) or "").strip():
                found[CORE_LABELS.get(m.group(2), m.group(2))] = m.group(3).strip()
        app = read("docProps/app.xml")
        for tag, label in APP_LABELS.items():
            m = re.search(rf"<{tag}>(.*?)</{tag}>", app, re.S)
            if m and m.group(1).strip():
                found[label] = m.group(1).strip()
        for m in CUSTOM_PROPERTY.finditer(read("docProps/custom.xml")):
            found[f"propriedade personalizada ({m.group(1)})"] = re.sub(r"<[^>]+>", "", m.group(0)).strip()

        if src.suffix.lower() == ".docx":
            comments = read("word/comments.xml")
            if comments:
                found["comentários"] = str(comments.count("<w:comment "))
            body = read("word/document.xml")
            revisions = len(re.findall(r"<w:(?:ins|del|moveFrom|moveTo) ", body))
            if revisions:
                found["alterações controladas"] = str(revisions)
            authors = set(re.findall(r'w:author="([^"]*)"', comments + body))
            if authors:
                found["autores de comentários/alterações"] = ", ".join(sorted(authors))
    return found
