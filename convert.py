"""Conversor de arquivos local (linha de comando).

Uso:
    python convert.py --to png relatorio.pdf
    python convert.py --to jpg --opt quality=80 --out C:\\fotos *.png
    python convert.py --list
    python convert.py --remover-metadados [--comentarios] foto.jpg contrato.docx

Sem --out, os arquivos são salvos na mesma pasta dos originais.
"""

import argparse
import sys
from pathlib import Path

import converters
import core


def main() -> int:
    parser = argparse.ArgumentParser(description="Converte arquivos ou remove seus metadados.")
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
    args = parser.parse_args()

    if args.list:
        for (s, t), m in converters.CONVERTERS.items():
            opts = ", ".join(f"{o.key} (padrão {o.default})" for o in m.options) or "sem opções"
            print(f"{s} -> {t}: {opts}")
        return 0

    if not args.files:
        parser.error("informe ao menos um arquivo")

    if args.remover_metadados:
        _, failed = core.strip_metadata(args.files, args.out, comments=args.comentarios)
        return 1 if failed else 0

    source = args.source or converters.format_of(args.files[0])
    if not args.target:
        parser.error("informe o formato de destino com --to")
    conv = converters.find(source or "", args.target)
    if conv is None:
        parser.error(f"sem conversor de {source} para {args.target} (use --list)")

    known = {o.key: o for o in conv.options}
    opts = {o.key: o.default for o in conv.options}
    for item in args.opt:
        key, _, value = item.partition("=")
        if key not in known:
            parser.error(f"opção desconhecida: {key}")
        opts[key] = known[key].type(value)

    _, failed = core.run(conv.source, conv.target, args.files, args.out, opts)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
