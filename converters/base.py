from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class Option:
    """Opção configurável de um conversor, exibida no menu."""

    key: str
    label: str
    default: Any
    type: type = str


@dataclass(frozen=True)
class Conversion:
    """Uma conversão de `source` para `target`.

    `convert(src, out_dir, **opções)` grava os arquivos em `out_dir` e
    retorna a lista de caminhos gerados.
    """

    source: str
    target: str
    convert: Callable[..., list[Path]]
    options: list[Option] = field(default_factory=list)


def unique(path: Path) -> Path:
    """`path` se ainda não existe; senão `nome (1).ext`, `nome (2).ext`..."""
    candidate, n = path, 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        n += 1
    return candidate
