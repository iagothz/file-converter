# file-converter

Conversor de arquivos que roda 100% localmente.

## Conversões suportadas

| Origem | Destino | Observação |
|--------|---------|------------|
| PDF | PNG, JPG, WEBP, BMP, TIFF | uma imagem por página; opção de DPI |
| PDF | TXT | extrai o texto |
| PNG, JPG, WEBP, BMP, GIF, TIFF, ICO | qualquer outro desses, ou PDF | transparência vira fundo branco em JPG/BMP/PDF; GIF animado usa só o 1º quadro |
| TXT | PDF | A4, fonte monoespaçada |
| CSV | JSON | detecta o separador (`,` `;` tab `\|`) |
| JSON | CSV | lista de objetos; campos aninhados viram JSON na célula |

`.jpeg` e `.tif` também são aceitos como JPG e TIFF.

## Instalação

```bash
pip install -r requirements.txt
```

## Executável

Gere o `FileConverter.exe` na raiz do projeto:

```bash
build.bat
```

Em cada aba, adicione arquivos arrastando-os (ou pastas inteiras) para a lista,
ou pelos botões **Adicionar arquivos** / **Adicionar pasta**. Por padrão os
resultados são salvos na mesma pasta de cada original; use **Escolher pasta**
para salvar em outro lugar. Nada é sobrescrito: se o nome já existir, o novo
arquivo recebe o sufixo ` (1)`, ` (2)`...

Na aba **Converter**, o formato **De** é escolhido automaticamente pelos
arquivos adicionados.

## Linha de comando

```bash
python convert.py --list
python convert.py --to png relatorio.pdf
python convert.py --to jpg --opt quality=80 --out C:otos foto1.png foto2.png
python convert.py --remover-metadados --comentarios contrato.docx foto.jpg
```

## Remover metadados

Na aba **Remover metadados** é criada uma cópia de cada arquivo sem autor,
datas, GPS, câmera, programa usado etc. Os originais não são alterados. Na mesma
pasta do original, a cópia recebe o sufixo `_sem-metadados`.

| Formato | O que é removido |
|---------|------------------|
| JPG, PNG, WEBP | EXIF (câmera, GPS, data), XMP, IPTC, comentários e textos. Sem recomprimir: a imagem fica idêntica. Em JPG a rotação da foto é mantida |
| TIFF | tags de autor, software, datas, EXIF, GPS, XMP |
| PDF | título, autor, programa, datas, XMP e autor de anotações |
| DOCX, XLSX, PPTX | autor, modificado por, datas, empresa, gerente, modelo, aplicativo, tempo de edição, propriedades personalizadas |

Com a opção **Remover também comentários e alterações controladas** (`--comentarios`):

- **DOCX:** remove os comentários e aceita todas as alterações controladas, como
  o "Aceitar todas" do Word: o texto inserido fica e o excluído sai.
- **PDF:** remove as anotações (notas, destaques, desenhos). Links e campos de
  formulário são mantidos.

## Adicionando formatos

- **Conversão:** adicione um `Conversion(origem, destino, função, [opções])` à
  lista `CONVERSIONS` de um módulo em `converters/` (veja `converters/images.py`).
  Um módulo novo precisa entrar em `_MODULES` de `converters/__init__.py`.
- **Remoção de metadados:** crie um módulo em `cleaners/` com `EXTENSIONS` e
  `clean(src, dest, comments=False)`, e inclua-o em `_MODULES` de `cleaners/__init__.py`.

Depois rode `build.bat` de novo. O menu se atualiza automaticamente.
