"""Lógica compartilhada entre a interface gráfica e a linha de comando."""

import sys
from pathlib import Path
from typing import Callable

import converters

# No executável (PyInstaller), as pastas ficam ao lado do .exe
if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent

INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"


def ensure_dirs() -> None:
    INPUT_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)


def pending_files(source: str) -> list[Path]:
    """Arquivos em input/ com a extensão de origem escolhida."""
    ensure_dirs()
    return sorted(
        p for p in INPUT_DIR.iterdir()
        if p.is_file() and p.suffix.lower() == f".{source}"
    )


def run(source: str, target: str, opts: dict, log: Callable[[str], None] = print) -> tuple[int, int]:
    """Converte todos os arquivos `source` de input/ para `target` em output/.

    Retorna (convertidos, com erro).
    """
    conv = converters.find(source, target)
    if conv is None:
        raise ValueError(f"Sem conversor de {source} para {target}")

    files = pending_files(source)
    if not files:
        log(f"Nenhum arquivo .{source} encontrado em {INPUT_DIR}")
        return 0, 0

    ok = failed = 0
    for src in files:
        try:
            written = conv.convert(src, OUTPUT_DIR, **opts)
            log(f"[ok] {src.name} -> {len(written)} arquivo(s)")
            ok += 1
        except Exception as e:
            log(f"[erro] {src.name}: {e}")
            failed += 1

    log(f"Concluído: {ok} convertido(s), {failed} com erro.")
    return ok, failed
