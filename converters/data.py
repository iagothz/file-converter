"""Conversões entre CSV e JSON (biblioteca padrão)."""

import csv
import json
from pathlib import Path

from .base import Conversion, Option, unique

DELIMITER = Option("delimiter", "Separador do CSV", ",", str)


def read_csv(src: Path) -> tuple[list[str], list[list[str]]]:
    """Lê um CSV detectando o separador. Retorna (cabeçalho, linhas)."""
    # utf-8-sig remove o BOM que o Excel costuma colocar
    with src.open(encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:  # uma coluna só, ou arquivo vazio
            dialect = csv.excel
        rows = list(csv.reader(f, dialect=dialect))
    return (rows[0], rows[1:]) if rows else ([], [])


def csv_to_json(src: Path, out_dir: Path) -> list[Path]:
    dest = unique(out_dir / f"{src.stem}.json")
    header, rows = read_csv(src)
    records = [dict(zip(header, row)) for row in rows]
    dest.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return [dest]


def json_to_csv(src: Path, out_dir: Path, delimiter: str = ",") -> list[Path]:
    dest = unique(out_dir / f"{src.stem}.csv")
    data = json.loads(src.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        raise ValueError("o JSON precisa ser um objeto ou uma lista de objetos")

    fields = list(dict.fromkeys(k for row in data for k in row))
    with dest.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter=delimiter or ",")
        writer.writeheader()
        for row in data:
            writer.writerow({
                k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                for k, v in row.items()
            })
    return [dest]


CONVERSIONS = [
    Conversion("csv", "json", csv_to_json),
    Conversion("json", "csv", json_to_csv, [DELIMITER]),
]
