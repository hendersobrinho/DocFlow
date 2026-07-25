<p align="center">
  <img src="assets/capa.png" alt="Capa do DocFLow" width="100%">
</p>

# DocFLow

Sistema desktop local para controle de recebimento de documentos empresariais.

Versao atual: `1.0.0`

Este repositorio publico foi preparado para portfolio tecnico. O codigo-fonte, a interface e o fluxo principal estao aqui para estudo e demonstracao, mas materiais operacionais privados de licenciamento e distribuicao comercial nao acompanham esta edicao.

O projeto foi pensado para substituir planilhas e controles manuais por um fluxo local, auditavel e simples de operar. O foco e manter o uso direto no escritorio: cadastro de empresas, documentos por tipo, controle mensal de recebimento, dashboard executivo, relatorio de pendencias e backup do banco sem depender de servidor.

## Visao geral

O DocFLow permite:

- cadastrar e manter empresas, com CNPJ para identificacao automatica
- cadastrar documentos por empresa e por tipo
- vincular meios de recebimento por documento
- controlar status por periodo em uma grade mensal, com selecao em lote
- acompanhar a conferencia mensal por empresa em uma visao panoramica
- visualizar um dashboard executivo com KPIs e graficos (distribuicao por situacao, tendencia de conclusao)
- organizar automaticamente documentos recebidos: um agente le arquivos de uma pasta de entrada, identifica a empresa pelo CNPJ e move o arquivo para a pasta correta, com fallback opcional via IA (Claude Haiku) e fila de revisao manual para casos duvidosos
- aplicar regras de ocorrencia mensal, trimestral e anual em janeiro
- exportar pendencias em PDF e Excel
- manter logs administrativos
- gerar backup manual, configurar backup automatico e restaurar o banco pela interface
- alternar entre tema claro e escuro

## Principais recursos

- aplicacao desktop em Python, PySide6 (Qt) e SQLite
- interface com navegacao lateral (sidebar), tema claro/escuro persistente e graficos nativos (QtCharts)
- banco local separado da pasta instalada do programa
- autenticacao com perfis `admin` e `comum`
- login lembrado por perfil do computador, com expiracao de `60` dias e rotacao do token
- logs de alteracoes relevantes
- observacao por empresa com ate `255` caracteres
- status automatico `Nao cobrar` para meses fora da ocorrencia do tipo
- regra de encerramento que bloqueia meses posteriores
- dashboard com indicadores e graficos separados da grade operacional (Panorama)
- agente organizador de documentos com classificacao em camadas (regex de CNPJ local, depois IA como fallback)
- backup automatico configuravel em pasta fora da instalacao
- importacao e exportacao em Excel
- build com `PyInstaller`
- instalador Windows com `Inno Setup`

## Requisitos

### Desenvolvimento e execucao local

- Python `3.10+` (testado com `3.14`)
- dependencias do `requirements.txt` (inclui `PySide6`, o framework de interface)

### Dependencias Python

- `PySide6`
- `openpyxl`
- `Pillow`
- `pypdf`
- `anthropic`
- `cryptography`
- `PyInstaller`

### Dependencias opcionais

- `ANTHROPIC_API_KEY` (variavel de ambiente) para habilitar o fallback por IA do agente organizador de documentos; sem ela, o agente funciona apenas com o casamento local por CNPJ e envia o restante para revisao manual
- `Inno Setup` para gerar o instalador Windows

## Instalacao do ambiente

### Linux / macOS

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Execucao local

### Linux / macOS

```bash
.venv/bin/python main.py
```

### Windows PowerShell

```powershell
.\.venv\Scripts\python.exe main.py
```

## Licenciamento na edicao publica

O fluxo de licenciamento operacional nao faz parte desta publicacao no GitHub.

Na pratica, isso significa:

- a chave privada de licenciamento nao esta versionada aqui
- a geracao operacional de licencas depende de material privado fora deste repositorio
- esta edicao publica deve ser tratada como vitrine tecnica do projeto, nao como pacote pronto para uso em producao

## Primeiro acesso

Em um banco novo, o sistema cria automaticamente um usuario inicial:

- usuario: `admin`
- senha: `admin`

Recomendacao importante:

- altere essa senha imediatamente apos o primeiro login

## Testes

### Suite completa

```bash
python -m unittest discover -s tests
```

### Apenas servicos

```bash
python -m unittest tests.test_services
```

## Empacotamento

Os builds devem ser gerados no proprio sistema operacional de destino.

### Linux

```bash
bash scripts/build_release.sh
```

Saidas esperadas:

- build PyInstaller: `dist/DocFLow/`
- pacote versionado: `dist_release/DocFLow-linux-<arquitetura>-v<versao>.tar.gz`

### macOS

```bash
bash scripts/build_release.sh
```

Saidas esperadas:

- build PyInstaller: `dist/DocFLow/`
- pacote versionado: `dist_release/DocFLow-macos-<arquitetura>-v<versao>.tar.gz`

### Windows

```powershell
scripts\build_release.bat
```

Saidas esperadas:

- build PyInstaller: `dist\DocFLow\`
- executavel principal: `dist\DocFLow\DocFLow.exe`
- pacote versionado: `dist_release\DocFLow-win64-v<versao>.zip`
- se o `Inno Setup` estiver no `PATH`, o script tambem tenta gerar o instalador

Se a pasta `dist\DocFLow\` for criada vazia ou sem `DocFLow.exe`, o build nao terminou corretamente. Nesse caso, rode manualmente:

```powershell
py -m PyInstaller --noconfirm --clean documentos_empresa_app.spec
```

e confira a ultima mensagem de erro do `PyInstaller`. Em Windows, as causas mais comuns sao antivirus/Defender removendo o executavel durante o build ou dependencias ausentes no ambiente Python usado pelo script.

### Pular testes no build

Por padrao, os scripts de release executam os testes antes do empacotamento.

#### Linux / macOS

```bash
RUN_TESTS=0 bash scripts/build_release.sh
```

#### Windows PowerShell

```powershell
$env:RUN_TESTS=0
scripts\build_release.bat
```

## Estrutura do projeto

```text
.
├── main.py
├── README.md
├── requirements.txt
├── documentos_empresa_app.spec
├── assets/
│   └── installer/
├── docs/
├── scripts/
├── tests/
└── documentos_empresa_app/
    ├── app_context.py
    ├── database/
    ├── models/
    ├── services/
    ├── qt_ui/
    └── utils/
```

## Pastas principais

- `documentos_empresa_app/`: codigo-fonte da aplicacao
- `documentos_empresa_app/database/`: conexao, repositorios e schema SQLite
- `documentos_empresa_app/services/`: regras de negocio (inclui o agente organizador de documentos)
- `documentos_empresa_app/qt_ui/`: interface PySide6 (paginas, dialogos, widgets, tema e viewmodels)
- `documentos_empresa_app/utils/`: constantes, seguranca, recursos e helpers
- `assets/installer/`: script do Inno Setup para Windows
- `scripts/`: build e geracao de icones
- `tests/`: testes automatizados
- `docs/`: documentacao tecnica detalhada

## Arquivos de release importantes

- `documentos_empresa_app.spec`: receita do `PyInstaller`
- `scripts/build_release.sh`: build Linux/macOS com pacote `.tar.gz`
- `scripts/build_release.bat`: build Windows com `.zip` e tentativa opcional de instalador
- `assets/installer/DocFLow.iss`: instalador Windows
- `scripts/generate_icons.py`: gera `icon.png`, `icon.ico` e `icon.icns`

## Banco e seguranca

- o banco e SQLite local
- o caminho do banco e salvo no perfil do usuario do computador
- o login lembrado e local ao perfil do sistema operacional
- a credencial lembrada expira em `60` dias sem uso
- o token lembrado e renovado automaticamente a cada autenticacao bem-sucedida
- o backup automatico fica em pasta configuravel, com padrao em `Documents/DocFLow/backups` ou `Documentos/DocFLow/backups` quando disponivel
- backups restaurados precisam conter a estrutura esperada do sistema
- erros inesperados sao registrados em `error.log`, na mesma pasta de configuracao do usuario, em vez de fechar o programa silenciosamente

## Fluxo principal de uso

1. Fazer login.
2. Cadastrar empresas manualmente ou por importacao (incluindo CNPJ, se for usar o agente organizador).
3. Cadastrar documentos por empresa.
4. Definir ou revisar tipos e meios de recebimento.
5. Gerar os periodos do ano.
6. Controlar os status na aba `Controle`.
7. Acompanhar o resumo executivo na aba `Dashboard` e a grade operacional em `Panorama`.
8. Processar a pasta de entrada em `Revisao de Documentos` para organizar arquivos recebidos automaticamente.
9. Exportar pendencias ou consultar logs quando necessario.
10. Configurar backup automatico ou gerar backup manual periodicamente.

## Regras de negocio principais

- empresa e unica por `codigo_empresa`
- documento e unico por `(empresa, tipo_documento, nome_documento)`
- consultas e relatorios aceitam no maximo `12` meses por vez
- tipos podem ser `Mensal`, `Trimestral` ou `Anual em janeiro`
- meses fora da ocorrencia aparecem como `Nao cobrar`
- `Encerrado` bloqueia meses posteriores do documento
- o agente organizador nunca cadastra empresa nova sozinho: documentos sem correspondencia clara vao para a fila de revisao manual

## Documentacao tecnica

Os documentos detalhados continuam na pasta [`docs/`](docs). Alguns refletem ainda a versao anterior da interface (Tkinter) e estao sendo atualizados; os mais confiaveis para a estrutura atual sao:

- [Banco de dados](docs/10-banco-de-dados.md)
- [Dependencias e bibliotecas](docs/13-dependencias-e-bibliotecas-usadas.md)
- [Icones e empacotamento](docs/18-icones-e-empacotamento-por-sistema-operacional.md)
- [Git e empacotamento](docs/19-observacoes-importantes-para-git-e-empacotamento.md)
- [Configuracao de seguranca, IA e backup](docs/21-configuracao-seguranca-ia-e-backup.md)

## O que nao deve ir para o Git

- bancos locais
- artefatos de build (`build/`, `dist/`, `dist_release/`, `dist_installer/`)
- ambientes virtuais
- caches
- planilhas exportadas localmente

## Status desta revisao

- interface reconstruida em PySide6 (Qt), com tema claro/escuro, dashboard com graficos e todas as telas migradas do Tkinter
- agente organizador de documentos com classificacao por CNPJ e fallback opcional via IA
- `.gitignore` ampliado para artefatos de release e arquivos SQLite auxiliares
- README refeito para uso, manutencao e distribuicao
