# file-converter

Conversor e caixa de ferramentas de arquivos que roda 100% localmente: nada é
enviado para a internet.

## Instalação

```bash
pip install -r requirements.txt
```

## Executável

Gere o `FileConverter.exe` na raiz do projeto:

```bash
build.bat
```

Em todas as abas, adicione arquivos arrastando-os (ou pastas inteiras) para a
lista, ou pelos botões **Adicionar arquivos** / **Adicionar pasta**. Clique num
arquivo da lista para ver uma prévia. Por padrão os resultados são salvos na
mesma pasta de cada original; use **Escolher pasta** para salvar em outro lugar.
Nada é sobrescrito: se o nome já existir, o novo arquivo recebe ` (1)`, ` (2)`...

O programa lembra a última aba, ferramenta, opções e pasta de destino
(em `%APPDATA%\FileConverter\settings.json`). Senhas nunca são salvas.

## Abas

### Converter

| Origem | Destino | Observação |
|--------|---------|------------|
| PDF | PNG, JPG, WEBP, BMP, TIFF | uma imagem por página; opção de DPI |
| PDF | TXT | extrai o texto |
| PNG, JPG, WEBP, BMP, GIF, TIFF, ICO | qualquer outro desses, ou PDF | transparência vira fundo branco em JPG/BMP/PDF; GIF animado usa só o 1º quadro |
| TXT | PDF | A4, fonte monoespaçada |
| CSV | JSON, XLSX | detecta o separador (`,` `;` tab `\|`) |
| JSON | CSV, XLSX | lista de objetos; campos aninhados viram JSON na célula |
| XLSX | CSV, JSON | a aba ativa ou todas (um arquivo por aba) |

`.jpeg` e `.tif` também são aceitos como JPG e TIFF. O formato **De** é
escolhido automaticamente pelos arquivos adicionados.

### Remover metadados

Cria uma cópia sem autor, datas, GPS, câmera, programa usado etc. Os originais
não são alterados. **Ver metadados** mostra o que cada arquivo contém, sem
gravar nada.

| Formato | O que é removido |
|---------|------------------|
| JPG, PNG, WEBP | EXIF (câmera, GPS, data), XMP, IPTC, comentários e textos. Sem recomprimir: a imagem fica idêntica. Em JPG a rotação da foto é mantida |
| TIFF | tags de autor, software, datas, EXIF, GPS, XMP |
| PDF | título, autor, programa, datas, XMP e autor de anotações |
| DOCX, XLSX, PPTX | autor, modificado por, datas, empresa, gerente, modelo, aplicativo, tempo de edição, propriedades personalizadas |

Com **Remover também comentários e alterações controladas**:

- **DOCX:** remove os comentários e aceita todas as alterações controladas, como
  o "Aceitar todas" do Word: o texto inserido fica e o excluído sai.
- **PDF:** remove as anotações (notas, destaques, desenhos). Links e campos de
  formulário são mantidos.

### Ferramentas PDF

| Ferramenta | O que faz |
|------------|-----------|
| Juntar PDFs | une os arquivos na ordem da lista (↑↓ para reordenar); aceita imagens; cria marcadores |
| Dividir / extrair páginas | uma página por arquivo, um arquivo por intervalo (`1-3, 7, 10-`) ou extrai páginas para um PDF |
| Comprimir PDF | recomprime as imagens internas (leve, médio, forte); opção de tons de cinza |
| Girar páginas | todas ou só algumas |
| Imagens → PDF único | uma imagem por página, na ordem da lista; tamanho da imagem ou A4 |
| Marca d'água | texto ou imagem, com opacidade, cor, posição e páginas |
| Numerar páginas | vários formatos e posições; pode pular a capa |
| Proteger com senha | AES-256, com permissões de impressão e cópia |
| Remover senha | exige a senha atual |
| Extrair imagens | salva as imagens do PDF numa pasta |
| Tarjar informações | apaga de verdade CPF, CNPJ, e-mail, telefone, um texto ou uma expressão regular; tem pré-visualização |

### Imagens

| Ferramenta | O que faz |
|------------|-----------|
| Redimensionar / comprimir | lado maior, largura, altura ou porcentagem; formato de saída; limite em KB |
| Cortar | proporções (1:1, 16:9...) ou remove bordas lisas |
| Girar / espelhar | inclui corrigir pela orientação da câmera |
| Tons de cinza | mantém a transparência |
| Gerar ícones | `.ico` de 16 a 256 px ou pacote de favicons para site |
| OCR | texto de imagens e PDFs escaneados, em `.txt` ou PDF pesquisável |

O OCR precisa do [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
instalado (marque o idioma português na instalação). As outras ferramentas
funcionam sem ele.

### Arquivos

| Ferramenta | O que faz |
|------------|-----------|
| Renomear em lote | padrão com `{nome}`, `{n}`, `{data}`, `{pasta}`, localizar/substituir e maiúsculas; tem pré-visualização |
| Hash / verificar integridade | SHA-256, SHA-1, MD5, SHA-512; compara com um hash informado |
| Localizar duplicados | arquivos idênticos ou imagens parecidas. Nunca apaga: no máximo move as cópias para `duplicados/` |

## Linha de comando

```bash
python convert.py --list
python convert.py --to png relatorio.pdf
python convert.py --to jpg --opt quality=80 --out C:\fotos foto1.png foto2.png
python convert.py --remover-metadados --comentarios contrato.docx foto.jpg
python convert.py --ver-metadados foto.jpg
python convert.py --ferramenta juntar-pdfs --opt name=relatorio a.pdf b.pdf
python convert.py --ferramenta renomear-em-lote --opt pattern=ferias_{n} --previa *.jpg
```

`--list` mostra as conversões e as ferramentas com suas opções.

## Adicionando funcionalidades

- **Conversão:** adicione um `Conversion(origem, destino, função, [opções])` à
  lista `CONVERSIONS` de um módulo em `converters/` (veja `converters/images.py`).
  Um módulo novo precisa entrar em `_MODULES` de `converters/__init__.py`.
- **Ferramenta:** adicione um `Tool(nome, descrição, função, extensões, [opções])`
  à lista `TOOLS` de um módulo em `tools/`. Para uma aba nova, inclua o grupo em
  `GROUPS` de `tools/__init__.py`.
- **Remoção de metadados:** crie um módulo em `cleaners/` com `EXTENSIONS`,
  `clean(src, dest, comments=False)` e `inspect(src)`, e inclua-o em `_MODULES`
  de `cleaners/__init__.py`.

As opções (`Option`) viram campos na tela automaticamente: texto, número, lista
(`choices`), caixa de marcar (`type=bool`), senha (`secret`) ou arquivo (`file`).
Depois rode `build.bat` de novo.
