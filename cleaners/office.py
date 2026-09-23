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
