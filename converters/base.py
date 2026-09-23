from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Option:
    """Opção configurável de um conversor, exibida no menu."""

    key: str
    label: str
    default: Any
    type: type = str
