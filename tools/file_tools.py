"""Ferramentas para arquivos em geral: renomear, hash e duplicados."""

import hashlib
import re
from datetime import datetime
from pathlib import Path

from PIL import Image

from .base import Context, Option, Tool, size_text, unique

# ---- Renomear em lote ----------------------------------------------------

CASES = ("Manter", "minúsculas", "MAIÚSCULAS", "Primeira Letra Maiúscula")
INVALID = re.compile(r'[\\/:*?"<>|]')


def _new_names(files: list[Path], opts: dict) -> list[tuple[Path, Path]]:
    pattern = opts["pattern"] or "{nome}"
    pairs = []
    for i, src in enumerate(files):
        stem = src.stem
        if opts["find"]:
            stem = stem.replace(opts["find"], opts["replace"])
        date = datetime.fromtimestamp(src.stat().st_mtime).strftime("%Y-%m-%d")
        n = str(opts["start"] + i).zfill(opts["digits"])
        name = (pattern.replace("{nome}", stem).replace("{n}", n)
                .replace("{data}", date).replace("{pasta}", src.parent.name))
        name = {"minúsculas": str.lower, "MAIÚSCULAS": str.upper,
                "Primeira Letra Maiúscula": str.title}.get(opts["case"], str)(name).strip()
        if not name or INVALID.search(name):
            raise ValueError(f'nome inválido para {src.name}: "{name}" (não use \\ / : * ? " < > |)')
        pairs.append((src, src.with_name(name + src.suffix.lower() if opts["lower_ext"] else name + src.suffix)))
    return pairs


def rename_preview(files, out_dir, opts, ctx: Context):
    pairs = _new_names(files, opts)
    final = set()
    for src, dest in pairs:
        clash = dest in final or (dest.exists() and dest not in {s for s, _ in pairs})
        final.add(dest)
        ctx.log(f"{src.name}  ->  {dest.name}" + ("  (já existe: receberá um número)" if clash else ""))
    ctx.log(f"{sum(str(s) != str(d) for s, d in pairs)} arquivo(s) serão renomeados. Clique em \"Executar\" para aplicar.")


def rename(files, out_dir, opts, ctx: Context):
    # str(): no Windows, Path ignora maiúsculas e pularia "Foto.jpg" -> "foto.jpg"
    pairs = [(s, d) for s, d in _new_names(files, opts) if str(s) != str(d)]
    temp, done = [], 0
    try:
        # Passo 1: nomes temporários (permite trocar nomes entre arquivos da lista)
        for i, (src, dest) in enumerate(pairs):
            tmp = unique(src.with_name(f".renomeando_{i}{src.suffix}"))
            src.rename(tmp)
            temp.append((src, tmp, dest))
        # Passo 2: nomes finais
        for i, (src, tmp, dest) in enumerate(temp):
            ctx.progress(i, len(temp))
            final = unique(dest)
            tmp.rename(final)
            done += 1
            ctx.renamed(src, final)
            ctx.log(f"[ok] {src.name} -> {final.name}")
    except OSError:
        # Devolve o nome original aos que ficaram com nome temporário
        for src, tmp, _ in temp[done:]:
            if tmp.exists():
                tmp.rename(unique(src))
        raise
    ctx.progress(1, 1)
    ctx.log(f"Concluído: {len(temp)} arquivo(s) renomeado(s).")


# ---- Hash ----------------------------------------------------------------

ALGORITHMS = ("SHA-256", "SHA-1", "MD5", "SHA-512")


def file_hash(path: Path, algorithm: str = "SHA-256") -> str:
    h = hashlib.new(algorithm.replace("-", "").lower())
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hashes(files, out_dir, opts, ctx: Context):
    algorithm, expected = opts["algorithm"], opts["compare"].strip().lower()
    lines = []
    for i, src in enumerate(files):
        ctx.progress(i, len(files))
        try:
            digest = file_hash(src, algorithm)
        except OSError as e:
            ctx.log(f"[erro] {src.name}: {e}")
            continue
        lines.append(f"{digest} *{src.name}")
        verdict = ""
        if expected:
            verdict = "  ✔ CONFERE" if digest == expected else "  ✘ DIFERENTE"
        ctx.log(f"{src.name}\n    {algorithm}: {digest}{verdict}")
    ctx.progress(1, 1)
    if opts["save"] and lines:
        dest = unique(files[0].parent / f"hashes_{algorithm.replace('-', '').lower()}.txt")
        dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        ctx.log(f"Lista salva em {dest}")


# ---- Duplicados ----------------------------------------------------------

DUP_MODES = ("Arquivos idênticos", "Imagens parecidas")
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


def _dhash(path: Path) -> int:
    """Hash perceptual (diferença de brilho entre pixels vizinhos) de 64 bits."""
    with Image.open(path) as im:
        small = im.convert("L").resize((9, 8), Image.LANCZOS)
    px = list(small.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (px[row * 9 + col] > px[row * 9 + col + 1])
    return bits


def _identical_groups(files, ctx) -> list[list[Path]]:
    by_size: dict[int, list[Path]] = {}
    for f in files:
        by_size.setdefault(f.stat().st_size, []).append(f)
    candidates = [f for group in by_size.values() if len(group) > 1 for f in group]
    by_hash: dict[str, list[Path]] = {}
    for i, f in enumerate(candidates):
        ctx.progress(i, len(candidates))
        by_hash.setdefault(file_hash(f), []).append(f)
    return [g for g in by_hash.values() if len(g) > 1]


def _similar_groups(files, threshold, ctx) -> list[list[Path]]:
    images = [f for f in files if f.suffix.lower() in IMAGE_EXTS]
    hashes_ = []
    for i, f in enumerate(images):
        ctx.progress(i, len(images))
        try:
            hashes_.append((f, _dhash(f)))
        except Exception as e:
            ctx.log(f"[ignorado] {f.name}: {e}")
    parent = list(range(len(hashes_)))  # união de conjuntos

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(hashes_)):
        for j in range(i + 1, len(hashes_)):
            if (hashes_[i][1] ^ hashes_[j][1]).bit_count() <= threshold:
                parent[root(j)] = root(i)
    groups: dict[int, list[Path]] = {}
    for i, (f, _) in enumerate(hashes_):
        groups.setdefault(root(i), []).append(f)
    return [g for g in groups.values() if len(g) > 1]


def duplicates(files, out_dir, opts, ctx: Context):
    if opts["mode"] == DUP_MODES[0]:
        groups = _identical_groups(files, ctx)
    else:
        groups = _similar_groups(files, opts["threshold"], ctx)
    ctx.progress(1, 1)
    if not groups:
        ctx.log("Nenhum duplicado encontrado.")
        return

    wasted = 0
    for n, group in enumerate(groups, start=1):
        # Mantém o mais antigo; os outros são as "cópias extras"
        group.sort(key=lambda p: p.stat().st_mtime)
        ctx.log(f"Grupo {n}:")
        ctx.log(f"    manter:  {group[0]}")
        for extra in group[1:]:
            wasted += extra.stat().st_size
            if opts["move"]:
                folder = extra.parent / "duplicados"
                folder.mkdir(exist_ok=True)
                dest = unique(folder / extra.name)
                extra.rename(dest)
                ctx.renamed(extra, dest)
                ctx.log(f"    movido:  {extra} -> {dest}")
            else:
                ctx.log(f"    cópia:   {extra}")
    extras = sum(len(g) - 1 for g in groups)
    ctx.log(f"Concluído: {len(groups)} grupo(s), {extras} cópia(s) extra(s) ocupando {size_text(wasted)}.")


TOOLS = [
    Tool("Renomear em lote", "Renomeia os arquivos da lista. Use {nome}, {n} (número), {data} (modificação) "
         "e {pasta}. Clique em \"Pré-visualizar\" antes.",
         rename, None, [
             Option("pattern", "Novo nome", "{nome}_{n}", hint="a extensão é mantida"),
             Option("find", "Localizar", ""),
             Option("replace", "Substituir por", ""),
             Option("case", "Maiúsculas", "Manter", choices=CASES),
             Option("start", "Numerar a partir de", 1, int),
             Option("digits", "Dígitos do número", 3, int),
             Option("lower_ext", "Extensão em minúsculas", True, bool),
         ], writes_files=False, preview=rename_preview, ordered=True),
    Tool("Hash / verificar integridade", "Calcula o hash dos arquivos e, se informado, compara com o esperado.",
         hashes, None, [
             Option("algorithm", "Algoritmo", "SHA-256", choices=ALGORITHMS),
             Option("compare", "Comparar com (opcional)", ""),
             Option("save", "Salvar lista .txt ao lado do 1º arquivo", False, bool),
         ], writes_files=False),
    Tool("Localizar duplicados", "Encontra arquivos idênticos ou imagens parecidas. Nada é apagado.",
         duplicates, None, [
             Option("mode", "Procurar", DUP_MODES[0], choices=DUP_MODES),
             Option("threshold", "Sensibilidade (imagens)", 6, int, hint="0 = quase idênticas; 10+ = mais tolerante"),
             Option("move", "Mover cópias extras para a subpasta \"duplicados\"", False, bool),
         ], writes_files=False),
]
