"""Conversor de arquivos local (linha de comando).

Uso:
    python convert.py --from pdf --to png
    python convert.py --from pdf --to png --opt dpi=300
    python convert.py --list
"""

import argparse
import sys

import converters
import core


def main() -> int:
    parser = argparse.ArgumentParser(description="Converte os arquivos da pasta input/ e salva em output/.")
    parser.add_argument("--from", dest="source", default="pdf", help="formato de origem (padrão: pdf)")
    parser.add_argument("--to", dest="target", default="png", help="formato de destino (padrão: png)")
    parser.add_argument("--opt", action="append", default=[], metavar="CHAVE=VALOR", help="opção do conversor")
    parser.add_argument("--list", action="store_true", help="lista as conversões disponíveis")
    args = parser.parse_args()

    if args.list:
        for (s, t), m in converters.CONVERTERS.items():
            opts = ", ".join(f"{o.key} (padrão {o.default})" for o in m.OPTIONS) or "sem opções"
            print(f"{s} -> {t}: {opts}")
        return 0

    conv = converters.find(args.source, args.target)
    if conv is None:
        parser.error(f"sem conversor de {args.source} para {args.target} (use --list)")

    known = {o.key: o for o in conv.OPTIONS}
    opts = {o.key: o.default for o in conv.OPTIONS}
    for item in args.opt:
        key, _, value = item.partition("=")
        if key not in known:
            parser.error(f"opção desconhecida: {key}")
        opts[key] = known[key].type(value)

    _, failed = core.run(conv.SOURCE, conv.TARGET, opts)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
