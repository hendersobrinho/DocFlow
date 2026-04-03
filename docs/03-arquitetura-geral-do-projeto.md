[Voltar ao README](../README.md)

# 3. Arquitetura Geral Do Projeto

## 3.1 Estilo arquitetural

O projeto segue uma arquitetura em camadas simples, com separacao suficiente para manutencao, mas sem o peso de frameworks ou estruturas excessivamente abstratas.

As camadas sao:

1. Inicializacao e composicao
2. Interface grafica
3. Servicos de negocio
4. Repositórios
5. Persistencia SQLite
6. Utilitarios transversais

## 3.2 Descricao das camadas

### 1. Inicializacao e composicao

Arquivos:

- `main.py`
- `documentos_empresa_app/app_context.py`

Responsabilidade:

- descobrir ou pedir o caminho do banco
- inicializar schema e dados basicos
- montar repositórios e servicos
- orquestrar login, logout e janela principal

### 2. Interface grafica

Arquivos:

- `documentos_empresa_app/ui/*.py`

Responsabilidade:

- exibir formulários, tabelas, filtros e mensagens
- capturar eventos do usuario
- traduzir interacoes em chamadas para servicos
- atualizar o estado visual depois das operacoes

### 3. Servicos de negocio

Arquivos:

- `documentos_empresa_app/services/*.py`

Responsabilidade:

- aplicar validacoes
- impor regras de negocio
- combinar dados de multiplos repositórios
- produzir descricoes de log
- encapsular fluxos transacionais

### 4. Repositórios

Arquivo:

- `documentos_empresa_app/database/repositories.py`

Responsabilidade:

- executar SQL
- isolar operacoes CRUD e consultas
- devolver dados em formato de dicionario

### 5. Persistencia SQLite

Arquivos:

- `documentos_empresa_app/database/connection.py`
- `documentos_empresa_app/database/schema.py`

Responsabilidade:

- abrir conexoes
- controlar commit/rollback
- garantir foreign keys
- criar tabelas e indices
- aplicar migracoes e consolidacoes

### 6. Utilitarios transversais

Arquivos:

- `documentos_empresa_app/utils/*.py`

Responsabilidade:

- constantes compartilhadas
- hash de senha
- icone e recursos
- detecao de monitor
- helpers de configuracao
- normalizacao de nomes e caminhos

## 3.3 Como as camadas conversam entre si

O fluxo de dependencia segue, em geral, esta direcao:

`UI -> Services -> Repositories -> SQLite`

Componentes auxiliares:

- `SessionService` e `AuditService` sao usados transversalmente pelos servicos.
- `helpers.py` e `resources.py` suportam a UI.
- `schema.py` e chamado apenas na inicializacao.

## 3.4 Fluxo de execucao do sistema

### Inicio do sistema

`main.py`:

- cria uma janela bootstrap invisivel
- chama `ensure_database_path()`
- se necessario, abre `DatabasePathDialog`
- com o caminho do banco, chama `build_application_services()`

`app_context.py`:

- cria `DatabaseManager`
- chama `initialize_schema()`
- instancia repositórios
- instancia servicos
- devolve `ApplicationServices`

Depois disso:

- abre `LoginWindow`
- apos autenticacao, abre `MainWindow`
- em logout, volta ao login
- em fechamento normal, encerra o programa

## 3.5 Onde cada preocupacao esta localizada

| Preocupacao | Onde esta |
|---|---|
| inicio da aplicacao | `main.py` |
| composicao de dependencias | `app_context.py` |
| interface | `ui/` |
| regras de negocio | `services/` |
| SQL e CRUD | `database/repositories.py` |
| schema e migracao | `database/schema.py` |
| autenticacao | `services/auth_service.py` |
| sessao atual | `services/session_service.py` |
| logs/auditoria | `services/audit_service.py` e `services/log_service.py` |
| importacao Excel | `services/import_service.py` |
| hash de senha | `utils/security.py` |
| caminhos/configuracao/primeira execucao | `utils/helpers.py`, `utils/storage.py`, `utils/common.py` |

---
