# file-converter

Conversor de arquivos que roda 100% localmente.

## Conversões suportadas

| Origem | Destino | Observação            |
|--------|---------|-----------------------|
| PDF    | PNG     | uma imagem por página |

## Instalação

```bash
pip install -r requirements.txt
```

## Executável

Gere o `FileConverter.exe` (fica na raiz, ao lado de `input/` e `output/`):

```bash
build.bat
```

No programa escolha o formato **De** e **Para**, ajuste as opções, coloque os arquivos em `input/` (botão "Abrir pasta input") e clique em **Converter**.
Os resultados aparecem em `output/<nome do arquivo>/`.

Se o `.exe` for copiado para outro lugar, as pastas `input/` e `output/` são criadas ao lado dele.

## Linha de comando

```bash
python convert.py --list
python convert.py --from pdf --to png --opt dpi=300
```

## Adicionando uma conversão

1. Crie `converters/<origem>_to_<destino>.py` com `SOURCE`, `TARGET`,
   `OPTIONS` e `convert(src, out_dir, **opções)` (veja `pdf_to_png.py`).
2. Adicione o módulo à lista `_MODULES` em `converters/__init__.py`.
3. Rode `build.bat` de novo. O menu e as opções aparecem automaticamente.
