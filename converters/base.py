from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class Option:
    """Opção configurável de um conversor ou ferramenta, exibida no menu.

    O campo na tela depende da opção: `type=bool` vira caixa de marcar,
    `choices` vira lista, `secret` esconde o texto (senha) e `file` ganha
    um botão para escolher arquivo.
    """

    key: str
    label: str
    default: Any
    type: type = str
    choices: tuple = ()
    secret: bool = False
    file: bool = False
    hint: str = ""


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
