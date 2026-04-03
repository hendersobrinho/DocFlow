[Voltar ao README](../README.md)

# 18. Icones E Empacotamento Por Sistema Operacional

## 18.1 Onde ficam os icones

O projeto usa a pasta `assets/icons/` como ponto unico de organizacao dos icones:

- `assets/icons/icon.svg`: arquivo mestre/editavel
- `assets/icons/icon.png`: derivado para Linux e para uso interno na interface
- `assets/icons/icon.ico`: derivado para Windows
- `assets/icons/icon.icns`: derivado para macOS

Essa estrutura evita arquivos soltos na raiz e deixa claro qual formato pertence a cada plataforma.

## 18.2 Papel de cada formato

- `icon.svg`: fonte principal de design, mantida para edicao
- `icon.ico`: usado no build Windows e no instalador do Inno Setup
- `icon.icns`: usado no build macOS
- `icon.png`: usado como icone da janela Tkinter e como base para integracao visual no Linux

O executavel final nao depende do SVG diretamente. O SVG existe como arquivo mestre e os formatos finais sao derivados dele.

## 18.3 Como o projeto escolhe o icone

### Runtime da aplicacao

O arquivo `utils/resources.py` centraliza a logica:

- `apply_window_icon(window)` aplica o icone da janela
- `get_window_icon_filenames()` define a ordem de tentativa por sistema
- `get_packaging_icon_filename()` define o formato correto para o build
- `get_packaging_icon_path()` devolve o caminho do icone de empacotamento

Na interface:

- Windows prefere `icon.ico`
- macOS prefere `icon.png` para a janela e usa `icon.icns` no empacotamento
- Linux usa `icon.png` para janela e integracao visual

### Empacotamento

O arquivo `documentos_empresa_app.spec` escolhe o formato do build no momento do empacotamento:

- Windows: `assets/icons/icon.ico`
- macOS: `assets/icons/icon.icns`
- Linux: nao tenta forcar um formato de executavel inadequado; o projeto inclui `icon.png` para janela e integracao visual

Isso atende ao principio de builds separados por sistema operacional.

## 18.4 Geracao dos formatos derivados

O script `scripts/generate_icons.py`:

- le `assets/icons/icon.svg`
- gera `icon.png`
- gera `icon.ico`
- gera `icon.icns`

Ele usa `cairosvg` se estiver disponivel. Quando `cairosvg` nao esta instalado, ele tenta aproveitar o PNG embutido no SVG atual e normaliza o resultado em um canvas quadrado.

## 18.5 Comandos de build por sistema

### Windows

1. garantir que `assets/icons/icon.ico` existe
2. rodar `scripts\\build_release.bat`
3. gerar o instalador com `installer\\G-docs.iss`

Saida esperada do instalador Windows:

- `dist_installer/G-docs-Setup-<versao>.exe`

### macOS

1. garantir que `assets/icons/icon.icns` existe
2. rodar `bash scripts/build_release.sh`

### Linux

1. garantir que `assets/icons/icon.png` existe
2. rodar `bash scripts/build_release.sh`

Observacao importante:

- o build deve ser feito separadamente em cada sistema operacional
- Windows deve gerar o executavel Windows
- macOS deve gerar o app macOS
- Linux deve gerar o build Linux

## 18.6 Arquivos envolvidos no empacotamento

- `assets/icons/`: contem os icones
- `scripts/generate_icons.py`: gera os formatos derivados
- `documentos_empresa_app.spec`: define o build PyInstaller por plataforma
- `scripts/build_release.sh`: build Linux/macOS
- `scripts/build_release.bat`: build Windows
- `installer/G-docs.iss`: instalador Windows usando `icon.ico` e versionando o arquivo final do setup

---
