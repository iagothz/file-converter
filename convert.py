"""Conversor de arquivos local (linha de comando).

Uso:
    python convert.py --to png relatorio.pdf
    python convert.py --to jpg --opt quality=80 --out C:\\fotos *.png
    python convert.py --list
    python convert.py --remover-metadados [--comentarios] foto.jpg contrato.docx
    python convert.py --ver-metadados foto.jpg
    python convert.py --ferramenta juntar-pdfs --opt name=relatorio a.pdf b.pdf
    python convert.py --ferramenta renomear-em-lote --opt pattern=ferias_{n} --previa *.jpg

Sem --out, os arquivos são salvos na mesma pasta dos originais.
"""

import argparse
import re
import sys
import unicodedata
from pathlib import Path

import converters
import core
import tools
from tools.base import Context


def slug(name: str) -> str:
    """"Juntar PDFs" -> "juntar-pdfs"."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


TOOLS = {slug(t.name): t for _, group in tools.GROUPS for t in group}


def parse_options(parser, options, items: list[str]) -> dict:
    known = {o.key: o for o in options}
    values = {o.key: o.default for o in options}
    for item in items:
        key, _, value = item.partition("=")
        if key not in known:
            parser.error(f"opção desconhecida: {key} (válidas: {', '.join(known) or 'nenhuma'})")
        opt = known[key]
        if opt.type is bool:
            values[key] = value.lower() in ("1", "true", "sim", "s", "yes")
        elif opt.choices and value not in opt.choices:
            parser.error(f"valor inválido para {key}: escolha entre {', '.join(opt.choices)}")
        else:
            values[key] = opt.type(value)
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="Converte arquivos, remove metadados e executa ferramentas.")
    parser.add_argument("files", nargs="*", type=Path, help="arquivos a processar")
    parser.add_argument("--from", dest="source", help="formato de origem (padrão: extensão do 1º arquivo)")
    parser.add_argument("--to", dest="target", help="formato de destino")
    parser.add_argument("--opt", action="append", default=[], metavar="CHAVE=VALOR", help="opção do conversor")
    parser.add_argument("--out", type=Path, help="pasta de destino (padrão: a mesma do original)")
    parser.add_argument("--list", action="store_true", help="lista as conversões disponíveis")
    parser.add_argument("--remover-metadados", action="store_true", help="remove metadados em vez de converter")
    parser.add_argument("--comentarios", action="store_true",
                        help="com --remover-metadados: remove também comentários e alterações controladas "
                             "(DOCX) e anotações (PDF)")
    parser.add_argument("--ver-metadados", action="store_true", help="mostra os metadados sem alterar nada")
    parser.add_argument("--ferramenta", metavar="NOME", help="executa uma ferramenta (veja --list)")
    parser.add_argument("--previa", action="store_true", help="com --ferramenta: só pré-visualiza, se ela permitir")
    args = parser.parse_args()

    if args.list:
        print("Conversões (--to):")
        for (s, t), m in converters.CONVERTERS.items():
            opts = ", ".join(f"{o.key} (padrão {o.default})" for o in m.options) or "sem opções"
            print(f"  {s} -> {t}: {opts}")
        print("\nFerramentas (--ferramenta):")
        for group, tool_list in tools.GROUPS:
            print(f"  {group}:")
            for t in tool_list:
                opts = ", ".join(o.key for o in t.options) or "sem opções"
                print(f"    {slug(t.name)}: {opts}")
        return 0

    if not args.files:
        parser.error("informe ao menos um arquivo")

    if args.ver_metadados:
        core.show_metadata(args.files)
        return 0

    if args.remover_metadados:
        _, failed = core.strip_metadata(args.files, args.out, comments=args.comentarios)
        return 1 if failed else 0

    if args.ferramenta:
        tool = TOOLS.get(slug(args.ferramenta))
        if tool is None:
            parser.error(f"ferramenta desconhecida: {args.ferramenta} (use --list)")
        if args.previa and tool.preview is None:
            parser.error("esta ferramenta não tem pré-visualização")
        files = [f for f in args.files if tool.accepts(f)]
        if not files:
            parser.error("nenhum arquivo serve para esta ferramenta")
        opts = parse_options(parser, tool.options, args.opt)
        failed = []
        ctx = Context(log=lambda m: (print(m), failed.append(m) if m.startswith("[erro]") else None))
        (tool.preview if args.previa else tool.run)(files, args.out, opts, ctx)
        return 1 if failed else 0

    source = args.source or converters.format_of(args.files[0])
    if not args.target:
        parser.error("informe o formato de destino com --to")
    conv = converters.find(source or "", args.target)
    if conv is None:
        parser.error(f"sem conversor de {source} para {args.target} (use --list)")

    opts = parse_options(parser, conv.options, args.opt)
    _, failed = core.run(conv.source, conv.target, args.files, args.out, opts)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
