[Voltar ao README](../README.md)

# 18. Icones E Empacotamento Por Sistema Operacional

## 18.1 Estrutura de icones

O projeto usa `assets/icons/` como pasta central de icones:

- `icon.svg`: arquivo mestre editavel
- `icon.png`: usado pela interface e como base visual para Linux
- `icon.ico`: usado no build e no instalador Windows
- `icon.icns`: usado no build macOS

O script `scripts/generate_icons.py` regenera os formatos derivados a partir do `icon.svg`.

## 18.2 Arquivos de build

Os arquivos envolvidos no empacotamento sao:

- `documentos_empresa_app.spec`: receita do `PyInstaller`
- `scripts/build_release.sh`: build Linux/macOS
- `scripts/build_release.bat`: build Windows
- `assets/installer/DocFLow.iss`: instalador Windows com `Inno Setup`

## 18.3 Como o projeto escolhe os icones

### Runtime

`documentos_empresa_app/utils/resources.py` centraliza a busca dos icones em tempo de execucao.

- Windows prefere `icon.ico`
- macOS prefere `icon.png` para a janela e `icon.icns` no empacotamento
- Linux prefere `icon.png`

### Empacotamento

`documentos_empresa_app.spec` escolhe o icone de empacotamento conforme o sistema operacional onde o build esta sendo executado.

## 18.4 Build por plataforma

Os builds devem ser gerados no proprio sistema operacional de destino.

### Linux

```bash
bash scripts/build_release.sh
```

Saidas:

- `dist/DocFLow/`
- `dist_release/DocFLow-linux-<arquitetura>-v<versao>.tar.gz`

### macOS

```bash
bash scripts/build_release.sh
```

Saidas:

- `dist/DocFLow/`
- `dist_release/DocFLow-macos-<arquitetura>-v<versao>.tar.gz`

### Windows

```powershell
scripts\build_release.bat
```

Saidas:

- `dist\DocFLow\`
- `dist_release\DocFLow-win64-v<versao>.zip`
- `dist_installer\DocFLow-Setup-<versao>.exe` se o `Inno Setup` estiver disponivel no `PATH`

## 18.5 Validacoes executadas pelos scripts

Os scripts de release:

- verificam dependencias Python necessarias
- executam os testes por padrao antes do build
- regeneram os icones antes do empacotamento
- produzem um artefato versionado pronto para distribuicao

Para pular os testes:

### Linux / macOS

```bash
RUN_TESTS=0 bash scripts/build_release.sh
```

### Windows

```powershell
$env:RUN_TESTS=0
scripts\build_release.bat
```

## 18.6 Observacoes importantes

- `PyInstaller` gera distribuicao `onedir`
- o build Linux foi validado localmente neste projeto
- o build Windows foi revisado estruturalmente e depende de execucao no proprio Windows
- o instalador Windows continua separado do build base porque depende do `Inno Setup`

---
