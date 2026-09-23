"""Remoção de metadados de PDF (PyMuPDF)."""

from pathlib import Path

import pymupdf

EXTENSIONS = (".pdf",)

LABELS = {
    "title": "título", "author": "autor", "subject": "assunto",
    "keywords": "palavras-chave", "creator": "programa de criação",
    "producer": "gerador do PDF", "creationDate": "data de criação",
    "modDate": "data de modificação", "trapped": "trapped",
}


def clean(src: Path, dest: Path, comments: bool = False) -> list[str]:
    """`comments`: também apaga as anotações (notas, destaques, desenhos)."""
    with pymupdf.open(src) as doc:
        if doc.needs_pass:
            raise ValueError("PDF protegido por senha")

        removed = [LABELS.get(k, k) for k, v in doc.metadata.items() if v and k in LABELS]
        if doc.get_xml_metadata():
            removed.append("XMP")

        doc.set_metadata({})
        doc.del_xml_metadata()

        if comments:
            total = 0
            for page in doc:
                for annot in list(page.annots()):  # links e campos de formulário ficam
                    page.delete_annot(annot)
                    total += 1
            if total:
                removed.append(f"anotações ({total})")

        # Autor das anotações (comentários, destaques e seus pop-ups): chave /T
        for xref in range(1, doc.xref_length()):
            if doc.xref_get_key(xref, "Type") == ("name", "/Annot") and doc.xref_get_key(xref, "T")[0] != "null":
                doc.xref_set_key(xref, "T", "null")
                removed.append("autor de anotações")

        doc.save(dest, garbage=3, deflate=True)
    return list(dict.fromkeys(removed))


def inspect(src: Path) -> dict[str, str]:
    found = {}
    with pymupdf.open(src) as doc:
        if doc.needs_pass:
            return {"Aviso": "PDF protegido por senha"}
        for key, value in doc.metadata.items():
            if value and key in LABELS:
                found[LABELS[key]] = value
        if doc.get_xml_metadata():
            found["XMP"] = "presente"
        authors, annots = set(), 0
        for page in doc:
            for annot in page.annots():
                annots += 1
                if annot.info.get("title"):
                    authors.add(annot.info["title"])
        if annots:
            found["anotações"] = str(annots)
        if authors:
            found["autor de anotações"] = ", ".join(sorted(authors))
    return found
