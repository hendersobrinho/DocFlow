[Voltar ao README](../README.md)

# 2. Estrutura De Pastas E Arquivos

## 2.1 Estrutura resumida

```text
.
├── README.md
├── main.py
├── requirements.txt
├── documentos_empresa_app.spec
├── assets/
│   └── icons/
│       ├── icon.svg
│       ├── icon.png
│       ├── icon.ico
│       └── icon.icns
├── documentos_empresa_app/
│   ├── __init__.py
│   ├── app_context.py
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   ├── repositories.py
│   │   └── schema.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── models.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── audit_service.py
│   │   ├── auth_service.py
│   │   ├── database_maintenance_service.py
│   │   ├── delivery_method_service.py
│   │   ├── documento_service.py
│   │   ├── empresa_service.py
│   │   ├── import_service.py
│   │   ├── log_service.py
│   │   ├── pending_report_service.py
│   │   ├── periodo_service.py
│   │   ├── session_service.py
│   │   ├── status_service.py
│   │   ├── tipo_service.py
│   │   └── user_service.py
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── controle_tab.py
│   │   ├── delivery_methods_field.py
│   │   ├── documento_tab.py
│   │   ├── edicao_tab.py
│   │   ├── empresa_tab.py
│   │   ├── log_tab.py
│   │   ├── login_window.py
│   │   ├── main_window.py
│   │   ├── periodo_tab.py
│   │   ├── tipo_tab.py
│   │   └── user_tab.py
│   └── utils/
│       ├── __init__.py
│       ├── common.py
│       ├── display.py
│       ├── helpers.py
│       ├── resources.py
│       ├── security.py
│       ├── storage.py
│       └── type_names.py
├── installer/
│   └── G-docs.iss
├── scripts/
│   ├── build_release.bat
│   ├── build_release.sh
│   └── generate_icons.py
└── tests/
    ├── test_display.py
    ├── test_resources.py
    ├── test_services.py
    └── test_storage.py
```

## 2.2 Explicacao por area

### Arquivos de raiz

| Arquivo | Finalidade | Relacao com o sistema |
|---|---|---|
| `main.py` | ponto de entrada da aplicacao | inicializa banco, login e janela principal |
| `README.md` | documentacao principal | explica arquitetura, fluxo e manutencao |
| `requirements.txt` | dependencias Python externas | usado para instalar `openpyxl`, `Pillow` e `pyinstaller` |
| `documentos_empresa_app.spec` | receita de build do PyInstaller | gera a distribuicao `onedir` do app |

### Pasta `assets/icons/`

Concentra os arquivos do icone do sistema de forma organizada e preparada para empacotamento por plataforma.

| Arquivo | Finalidade | Papel |
|---|---|---|
| `icon.svg` | arquivo mestre editavel | fonte principal do design do icone |
| `icon.png` | derivado para Linux e interface | usado na janela Tkinter e em integracao visual no Linux |
| `icon.ico` | derivado para Windows | usado no executavel Windows e no instalador |
| `icon.icns` | derivado para macOS | usado no app bundle do macOS |

### Pasta `documentos_empresa_app/`

E o pacote principal do sistema. Contem o codigo de producao.

#### `app_context.py`

- Centraliza a montagem das dependencias do sistema.
- Cria `DatabaseManager`, repositórios, servicos, sessao e container final.
- E o arquivo que faz a “injeção manual” de dependencias.
- Se relaciona diretamente com `main.py`, `database/` e `services/`.

#### Pasta `database/`

Concentra toda a persistencia relacional e a inicializacao do banco.

| Arquivo | Finalidade | Papel |
|---|---|---|
| `connection.py` | gerenciar conexoes SQLite | abre, fecha, confirma e desfaz transacoes |
| `repositories.py` | CRUD e consultas por tabela | encapsula SQL usado pelos servicos |
| `schema.py` | schema, migracoes e dados iniciais | cria tabelas, indices, admin padrao, consolidacoes e backfills |

#### Pasta `models/`

Contem dataclasses com representacoes conceituais das entidades do dominio.

- Hoje essas classes nao sao a estrutura principal de runtime.
- O sistema opera majoritariamente com dicionarios retornados pelos repositórios.
- Ainda assim, os models documentam o dominio e podem servir de base para futura tipagem/refatoracao.

#### Pasta `services/`

E a camada de regras de negocio.

| Arquivo | Responsabilidade |
|---|---|
| `auth_service.py` | autenticacao de usuario |
| `audit_service.py` | gravacao centralizada de logs |
| `database_maintenance_service.py` | backup e restauracao do banco |
| `delivery_method_service.py` | regras dos meios de recebimento do sistema |
| `empresa_service.py` | regras de empresas |
| `tipo_service.py` | regras de tipos |
| `documento_service.py` | regras de documentos |
| `periodo_service.py` | regras de periodos |
| `status_service.py` | status mensal, regra de encerramento e montagem da visao de controle |
| `import_service.py` | importacao via Excel |
| `pending_report_service.py` | exportacao do relatorio de pendencias |
| `session_service.py` | sessao do usuario logado |
| `user_service.py` | administracao de usuarios |
| `log_service.py` | leitura e filtro de logs |

#### Pasta `ui/`

Contem a interface grafica Tkinter.

| Arquivo | Papel |
|---|---|
| `login_window.py` | janela inicial de login |
| `main_window.py` | janela principal e composicao das abas |
| `controle_tab.py` | consulta e alteracao de status por periodo |
| `empresa_tab.py` | cadastro de empresas |
| `documento_tab.py` | cadastro de documentos por empresa |
| `tipo_tab.py` | tela auxiliar/legada para tipos; nao e montada pela `MainWindow` atual |
| `edicao_tab.py` | tela auxiliar/legada para manutencao consolidada; nao e montada pela `MainWindow` atual |
| `periodo_tab.py` | geracao de periodos e exclusao de ano |
| `user_tab.py` | gestao de usuarios, restrita a admin |
| `log_tab.py` | visualizacao de logs, restrita a admin |
| `delivery_methods_field.py` | componente reutilizavel para meios de recebimento |

#### Pasta `utils/`

Reune funcoes auxiliares, constantes, seguranca e integracoes com ambiente.

| Arquivo | Responsabilidade |
|---|---|
| `common.py` | constantes globais, funcoes de apoio e `ValidationError` |
| `helpers.py` | configuracao, selecao do banco, componentes auxiliares de UI |
| `display.py` | detecao de monitor para posicionamento da janela |
| `resources.py` | localizacao de icones em runtime e build |
| `security.py` | hash e validacao de senha com PBKDF2 |
| `storage.py` | manipulacao de caminhos e nomes de banco |
| `type_names.py` | normalizacao/canonicalizacao de nomes de tipo |

### Pasta `scripts/`

Contem scripts auxiliares para empacotamento:

- `generate_icons.py`: gera os formatos derivados do icone a partir do arquivo mestre
- `build_release.sh`: build em Linux/macOS
- `build_release.bat`: build em Windows

### Pasta `installer/`

Contem o script `G-docs.iss`, usado pelo Inno Setup para gerar instalador Windows.

### Pasta `tests/`

Concentra os testes automatizados.

| Arquivo | O que valida |
|---|---|
| `test_services.py` | regras de negocio, persistencia, logs e importacao |
| `test_display.py` | utilitarios de monitor/tela |
| `test_resources.py` | escolha e organizacao de icones por plataforma |
| `test_storage.py` | utilitarios de caminho e pasta do banco |

### Arquivos `__init__.py`

Servem para marcar os diretorios como pacotes Python. Nao concentram logica relevante.

---
