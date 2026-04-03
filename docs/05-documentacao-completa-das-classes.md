[Voltar ao README](../README.md)

# 5. Documentacao Completa Das Classes

## 5.1 Composicao e bootstrap

### `ApplicationServices`

- Arquivo: `documentos_empresa_app/app_context.py`
- Tipo: dataclass container
- Objetivo: agrupar as instancias de servicos para consumo pela UI e pelo bootstrap
- Dados principais: referencias para todos os servicos do sistema
- Quem instancia: `build_application_services()`
- Quem usa: `main.py`, `LoginWindow`, `MainWindow` e abas
- Papel no fluxo: evitar que a UI precise montar dependencias por conta propria

### `DatabaseManager`

- Arquivo: `documentos_empresa_app/database/connection.py`
- Tipo: classe de infraestrutura
- Objetivo: abrir conexoes SQLite e controlar transacoes
- Atributos:
  - `db_path`: caminho do banco
  - `_active_connection`: conexao reutilizada em transacoes aninhadas
  - `_connection_depth`: profundidade de reentrada
- Dependencias: `sqlite3`, `Path`, `contextmanager`
- Papel: garantir `PRAGMA foreign_keys = ON`, commit no sucesso e rollback em falha
- Observacao: essa classe e central para a consistencia dos logs, porque permite que servicos executem mutacao e auditoria na mesma transacao

## 5.2 Repositórios

### `BaseRepository`

- Arquivo: `documentos_empresa_app/database/repositories.py`
- Tipo: base de repositório
- Objetivo: concentrar `_fetchall`, `_fetchone`, `_execute` e `_executemany`
- Dependencias: `DatabaseManager`
- Quem usa: todos os repositórios concretos
- Papel: evitar repeticao de abertura de conexao e conversao de `sqlite3.Row` para `dict`

### `EmpresaRepository`

- Responsabilidade: CRUD de empresas
- Tabela principal: `empresas`
- Metodos relevantes:
  - `list_all()`
  - `get_by_id()`
  - `get_by_code()`
  - `create()`
  - `update_details()`
  - `update_active()`
  - `delete()`
- Dados manipulados: codigo, nome, meios de recebimento, email, nome de contato, ativo

### `TipoRepository`

- Responsabilidade: CRUD de tipos de documento
- Tabela: `tipos_documento`
- Metodos relevantes:
  - `list_all()`
  - `get_by_id()`
  - `get_by_name()`
  - `create()`
  - `update()`
  - `delete()`
  - `is_in_use()`
- Papel adicional: impedir exclusao de tipo em uso

### `UsuarioRepository`

- Responsabilidade: CRUD de usuarios
- Tabela: `usuarios`
- Metodos:
  - `list_all()`
  - `get_by_id()`
  - `get_by_username()`
  - `create()`
  - `update()`
  - `update_password()`
  - `count_admins()`
- Papel adicional: apoiar regras de seguranca e guardrails de admin

### `LogRepository`

- Responsabilidade: persistir e consultar logs
- Tabela: `logs`
- Metodos:
  - `create()`
  - `list_recent()`
  - `list_logged_companies()`
  - `list_log_years()`
  - `list_log_months_by_year()`
- Papel adicional: suportar filtros administrativos por empresa e periodo

### `DocumentoRepository`

- Responsabilidade: CRUD de documentos
- Tabela: `documentos_empresa`
- Metodos:
  - `list_by_company()`
  - `get_by_id()`
  - `find_duplicate()`
  - `create()`
  - `update()`
  - `delete()`
  - `delete_many()`
- Papel adicional: devolver `nome_tipo` via join, para a camada de interface e consulta

### `PeriodoRepository`

- Responsabilidade: CRUD de periodos
- Tabela: `periodos`
- Metodos:
  - `list_all()`
  - `get_by_id()`
  - `create()`
  - `exists()`
  - `list_years()`
  - `list_by_year()`
  - `list_between()`
  - `delete_year()`
- Papel adicional: apoiar filtros de consulta e exclusao em massa por ano

### `StatusRepository`

- Responsabilidade: status mensal de documentos
- Tabela: `status_documento_mensal`
- Metodos:
  - `get_by_document_and_period()`
  - `upsert()`
  - `list_for_documents_and_periods()`
  - `list_future_statuses()`
  - `get_earliest_closure()`
  - `list_earliest_closures()`
  - `delete_future_statuses()`
- Papel adicional: viabilizar a regra de encerramento e a montagem da grade mensal

## 5.3 Servicos de negocio

### `AuthService`

- Objetivo: autenticar usuarios
- Dependencias: `UsuarioRepository`, `verify_password()`
- Papel no fluxo: usado exclusivamente pela tela de login
- Regras principais:
  - usuario e senha obrigatorios
  - senha em hash, nunca em texto puro
  - usuario inativo nao entra

### `AuditService`

- Objetivo: gravar logs estruturados
- Dependencias: `LogRepository`, `SessionService`
- Papel: servico transversal chamado por outros servicos
- Efeito colateral: grava na tabela `logs`

### `EmpresaService`

- Objetivo: encapsular toda a regra de empresas
- Dependencias: `EmpresaRepository`, `AuditService`, `SessionService`
- Dados manipulados: codigo, nome, ativo, meios de recebimento, email e contato
- Papel: validar, normalizar, persistir e auditar operacoes em empresas

### `TipoService`

- Objetivo: gerenciar tipos de documento
- Dependencias: `TipoRepository`
- Papel: validar nome, canonicalizar variacoes textuais e bloquear exclusao em uso

### `DocumentoService`

- Objetivo: gerenciar documentos por empresa
- Dependencias: `DocumentoRepository`, `EmpresaRepository`, `TipoRepository`, `AuditService`, `SessionService`
- Papel: garantir existencia de empresa/tipo, impedir duplicidades, atualizar tipo/nome e registrar logs

### `PeriodoService`

- Objetivo: gerenciar anos e meses do controle
- Dependencias: `PeriodoRepository`
- Papel: gerar anos, validar intervalo de consulta e excluir periodos por ano

### `StatusService`

- Objetivo: gerenciar alteracoes de status e montar a visao consolidada da aba `Controle`
- Dependencias: `EmpresaRepository`, `DocumentoRepository`, `PeriodoRepository`, `StatusRepository`, `AuditService`, `SessionService`
- Papel central:
  - validar status
  - aplicar regra de encerramento
  - remover status futuros quando um documento e encerrado
  - registrar logs de mudanca
  - montar o agrupamento de documentos por tipo e por periodo

### `ImportService`

- Objetivo: importar empresas e documentos a partir de planilhas Excel
- Dependencias: `EmpresaService`, `TipoService`, `DocumentoService`, `openpyxl`
- Papel: ler planilhas, aplicar regras existentes e consolidar resultado de sucesso/falha por linha

### `SessionService`

- Objetivo: manter o usuario logado em memoria
- Dependencias: nenhuma externa
- Papel:
  - armazenar `current_user`
  - responder se a sessao esta autenticada
  - responder se o usuario e admin
  - expor `user_id` e `username` para logs e UI

### `UserService`

- Objetivo: administrar usuarios
- Dependencias: `UsuarioRepository`, `SessionService`, `AuditService`, `hash_password()`
- Papel:
  - restringir acesso a admins
  - criar usuarios
  - editar username, tipo e ativo
  - trocar senha
  - impedir remocao do ultimo admin ativo
  - impedir auto-inativacao e auto-rebaixamento do admin logado

### `LogService`

- Objetivo: oferecer leitura dos logs para a UI administrativa
- Dependencias: `LogRepository`, `SessionService`
- Papel: filtrar logs e bloquear acesso para usuarios comuns

## 5.4 Interface

### `LoginWindow`

- Objetivo: autenticar o usuario antes da abertura do sistema
- Dependencias: `ApplicationServices`, `AuthService`, `SessionService`, `apply_window_icon()`
- Papel: primeira janela do aplicativo

### `MainWindow`

- Objetivo: compor a janela principal, definir geometria, cabecalho e abas
- Dependencias: `ApplicationServices`, abas da UI, `apply_window_icon()`, `display.py`
- Papel: hub visual da aplicacao
- Regra importante: so adiciona abas `Usuarios` e `Logs` quando o usuario logado e admin

### `ControleTab`

- Objetivo: tela operacional principal
- Dependencias: `StatusService`, `PeriodoService`, `CompanySelector`, `ScrollableFrame`
- Papel:
  - escolher empresa e periodo
  - montar consulta
  - renderizar grupos por tipo
  - alterar status mensal

### `EmpresaTab`

- Objetivo: cadastro de empresas
- Dependencias: `EmpresaService`, `ImportService`, `DeliveryMethodService`, `DeliveryMethodsField`
- Papel:
  - criar/editar empresa
  - inativar/reativar/excluir
  - importar empresas por Excel
  - manter meios de recebimento

### `DocumentoTab`

- Objetivo: cadastrar documentos por empresa
- Dependencias: `DocumentoService`, `TipoService`, `ImportService`, `CompanySelector`
- Papel:
  - criar/editar/excluir documento
  - criar e manter tipo no painel lateral
  - importar documentos

### `TipoTab`

- Objetivo: manter tipos de documento em tela isolada de apoio
- Dependencias: `TipoService`
- Papel: CRUD simples de tipos
- Observacao: a `MainWindow` atual nao monta essa tela; a manutencao principal de tipos acontece na lateral da `DocumentoTab`

### `EdicaoTab`

- Objetivo: manutencao consolidada de empresa e documentos vinculados
- Dependencias: `EmpresaService`, `DocumentoService`, `TipoService`, `CompanySelector`, `DeliveryMethodsField`
- Papel: concentrar manutencao de empresa e lote de documentos ja vinculados
- Observacao: a `MainWindow` atual nao monta essa tela

### `PeriodoTab`

- Objetivo: administracao de periodos
- Dependencias: `PeriodoService`, `PendingReportService`
- Papel:
  - gerar os 12 meses de um ano
  - excluir um ano inteiro com dupla confirmacao
  - exportar relatorio de pendencias por empresa e periodo

### `UserTab`

- Objetivo: gerenciar usuarios
- Dependencias: `UserService`
- Papel: criar e editar usuarios e seu estado

### `LogTab`

- Objetivo: consultar logs administrativos
- Dependencias: `LogService`
- Papel:
  - filtrar por empresa, ano e mes
  - listar logs mais recentes

### `DeliveryMethodsField`

- Objetivo: encapsular a selecao de meios de recebimento
- Dependencias: `parse_delivery_methods()`
- Papel: reduzir duplicacao entre `EmpresaTab` e `EdicaoTab`

## 5.5 Models de dominio

As dataclasses em `models/models.py` representam:

- empresa
- tipo
- documento
- periodo
- status mensal
- usuario
- log

Hoje elas nao sao o formato principal trafegado pelo sistema, porque repositórios retornam `dict`. Elas funcionam mais como representacao conceitual do dominio e potencial ponto futuro de refatoracao.

---
