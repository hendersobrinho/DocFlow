[Voltar ao README](../README.md)

# 13. Dependencias E Bibliotecas Usadas

## 13.1 Dependencias externas via `requirements.txt`

### `openpyxl`

- Arquivo de dependencias: `requirements.txt`
- Finalidade: leitura de planilhas Excel
- Onde e usada: `services/import_service.py`
- Por que e necessaria: suportar importacao em lote de empresas e documentos

### `Pillow`

- Arquivo de dependencias: `requirements.txt`
- Finalidade: gerar `icon.png`, `icon.ico` e `icon.icns`
- Onde e usada: `scripts/generate_icons.py`
- Por que e necessaria: manter um fluxo simples de derivacao dos icones por plataforma

### `pyinstaller`

- Arquivo de dependencias: `requirements.txt`
- Finalidade: empacotamento do programa
- Onde e usado:
  - `documentos_empresa_app.spec`
  - scripts de build
- Por que e necessario: gerar distribuicao desktop

## 13.2 Bibliotecas da biblioteca padrao do Python

| Biblioteca | Uso principal |
|---|---|
| `sqlite3` | banco local |
| `tkinter` / `ttk` / `messagebox` / `filedialog` / `simpledialog` | interface grafica |
| `json` | config local |
| `pathlib` | caminhos de arquivos |
| `os`, `sys`, `shutil` | ambiente, caminhos e migracao de config |
| `hashlib`, `hmac` | seguranca de senha |
| `datetime` | timestamp de logs |
| `re`, `unicodedata` | normalizacao textual |
| `dataclasses` | dataclasses de dominio e utilitarios |
| `subprocess` | consulta de monitor via `xrandr` |
| `collections.Counter` | contagem de periodos por ano |
| `tempfile`, `unittest`, `unittest.mock` | testes |

## 13.3 Dependencias opcionais do ambiente

Estas dependencias nao sao obrigatorias para o projeto funcionar em todos os fluxos, mas melhoram a experiencia ou sao usadas por plataforma:

### `python3-tk`

- Em alguns Linuxes, `tkinter` depende de pacote do sistema
- Necessario para abrir a interface

### `gi` / GDK (`python3-gi`)

- Usado opcionalmente em `utils/display.py`
- Finalidade: detectar monitor com mais precisao em Linux

### `xrandr`

- Fallback em Linux para detectar geometria de monitores

### `AppKit`

- Opcional em macOS para obter monitor principal

### `Inno Setup`

- Nao e dependencia Python
- Necessario apenas para gerar instalador Windows a partir de `installer/G-docs.iss`

### `cairosvg`

- Dependencia opcional de desenvolvimento
- Se estiver instalada, `scripts/generate_icons.py` renderiza o `icon.svg` diretamente
- Se nao estiver instalada, o script usa o PNG embutido no SVG atual como fallback

---
