"""Preferências do usuário (última ferramenta, opções, pasta de destino...).

Gravadas em %APPDATA%\\FileConverter\\settings.json. Senhas nunca são salvas.
"""

import json
import os
from pathlib import Path

FOLDER = Path(os.environ.get("APPDATA") or Path.home()) / "FileConverter"
FILE = FOLDER / "settings.json"


def load() -> dict:
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(data: dict) -> None:
    try:
        FOLDER.mkdir(parents=True, exist_ok=True)
        tmp = FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(FILE)
    except OSError:
        pass  # preferências são opcionais: nunca devem impedir o uso do app
