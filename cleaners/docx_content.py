"""Remoção de comentários e alterações controladas de DOCX.

As alterações são aceitas (como "Aceitar todas" do Word): o texto inserido
fica e o excluído sai. Usa lxml porque ele preserva os prefixos de namespace;
o Word considera o arquivo corrompido se eles forem renomeados.
"""

import re

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def w(tag: str) -> str:
    return f"{{{W}}}{tag}"


# Partes que contêm o texto do documento
STORY_PART = re.compile(r"word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml")

COMMENT_PARTS = ("comments", "commentsExtended", "commentsIds", "commentsExtensible", "people")
COMMENT_FILES = {f"word/{name}.xml" for name in COMMENT_PARTS}

# Referências às partes de comentário nos arquivos de relacionamento e de tipos
_parts = "|".join(COMMENT_PARTS)
COMMENT_RELATIONSHIP = re.compile(rf'<Relationship\b[^>]*Target="(?:/word/)?(?:{_parts})\.xml"[^>]*/>')
COMMENT_OVERRIDE = re.compile(rf'<Override\b[^>]*PartName="/word/(?:{_parts})\.xml"[^>]*/>')

PROPERTY_CHANGES = [w(t) for t in (
    "rPrChange", "pPrChange", "sectPrChange", "tblPrChange", "trPrChange",
    "tcPrChange", "tblGridChange", "tblPrExChange", "numberingChange",
)]
MOVE_RANGES = [w(t) for t in ("moveFromRangeStart", "moveFromRangeEnd", "moveToRangeStart", "moveToRangeEnd")]


def _attached(el, root) -> bool:
    return any(a is root for a in el.iterancestors())


def _remove(el) -> None:
    parent = el.getparent()
    if parent is not None:
        parent.remove(el)


def _unwrap(el) -> None:
    """Substitui o elemento pelos seus filhos."""
    parent = el.getparent()
    i = parent.index(el)
    for child in reversed(list(el)):
        parent.insert(i, child)
    parent.remove(el)


def accept_revisions(root) -> int:
    count = 0

    for el in list(root.iter(w("del"), w("moveFrom"))):
        if not _attached(el, root):
            continue
        parent = el.getparent()
        if parent.tag == w("trPr"):  # linha de tabela excluída
            _remove(parent.getparent())
        else:  # texto excluído (em rPr/pPr é só a marca)
            _remove(el)
        count += 1

    for el in list(root.iter(w("ins"), w("moveTo"))):
        if _attached(el, root):
            _unwrap(el)
            count += 1

    for el in list(root.iter(*PROPERTY_CHANGES, w("cellIns"), w("cellDel"))):
        if _attached(el, root):
            _remove(el)
            count += 1

    for el in list(root.iter(*MOVE_RANGES)):
        _remove(el)

    return count


def remove_comment_marks(root) -> None:
    for el in list(root.iter(w("commentRangeStart"), w("commentRangeEnd"))):
        _remove(el)
    for ref in list(root.iter(w("commentReference"))):
        run = ref.getparent()
        _remove(run if run.tag == w("r") else ref)


def edit(name: str, data: bytes, stats: dict) -> bytes | None:
    """Edita uma parte do DOCX. Retorna None se a parte deve ser descartada."""
    if name in COMMENT_FILES:
        if name == "word/comments.xml":
            stats["comments"] += len(etree.fromstring(data).findall(w("comment")))
        return None

    if STORY_PART.fullmatch(name):
        root = etree.fromstring(data, etree.XMLParser(huge_tree=True))
        stats["revisions"] += accept_revisions(root)
        remove_comment_marks(root)
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    if name == "[Content_Types].xml":
        return COMMENT_OVERRIDE.sub("", data.decode("utf-8")).encode("utf-8")
    if name == "word/_rels/document.xml.rels":
        return COMMENT_RELATIONSHIP.sub("", data.decode("utf-8")).encode("utf-8")

    return data
