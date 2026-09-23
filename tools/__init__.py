"""Grupos de ferramentas exibidos como abas.

Para adicionar uma ferramenta, crie um Tool(...) na lista TOOLS do módulo
do grupo (ou num módulo novo, incluído em GROUPS). A aba, as opções e os
botões são montados automaticamente.
"""

from . import file_tools, image_tools, pdf_tools
from .base import Tool

GROUPS: list[tuple[str, list[Tool]]] = [
    ("Ferramentas PDF", pdf_tools.TOOLS),
    ("Imagens", image_tools.TOOLS),
    ("Arquivos", file_tools.TOOLS),
]
