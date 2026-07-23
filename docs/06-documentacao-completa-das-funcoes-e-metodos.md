[Voltar ao README](../README.md)

# 6. Documentacao Completa Das Funcoes E Metodos

## 6.1 Funcoes de bootstrap

### `main()`

- Arquivo: `main.py`
- O que faz: controla o ciclo completo da aplicacao
- Quem chama: execucao direta do script
- Fluxo:
  - resolve caminho do banco
  - tenta montar servicos
  - abre login
  - abre janela principal
  - trata logout retornando para login
- Efeitos colaterais:
  - abre janelas
  - pode mostrar erros de banco
  - pode persistir configuracao do caminho do banco

### `build_application_services(db_path, session_service=None)`

- Arquivo: `app_context.py`
- O que faz: monta todas as dependencias do sistema
- Recebe: caminho do banco e, opcionalmente, uma sessao ja existente
- Retorna: `ApplicationServices`
- Chama:
  - `DatabaseManager`
  - `initialize_schema()`
  - construtores de todos os repositórios
  - construtores de todos os servicos

## 6.2 Funcoes de schema e migracao

### `initialize_schema(db_manager)`

- Arquivo: `database/schema.py`
- O que faz:
  - cria tabelas e indices
  - aplica migracoes de colunas extras
  - normaliza regra de ocorrencia dos tipos
  - normaliza meios de recebimento
  - migra meios legados da empresa para documentos quando necessario
  - garante colunas extras nos logs
  - faz backfill de metadados de logs
  - semeia tipos iniciais
  - cria admin padrao se necessario
  - consolida tipos duplicados
- Quando e chamada: toda vez que o sistema monta `ApplicationServices`

### `ensure_empresa_extra_columns(connection)` e `ensure_tipo_extra_columns(connection)`

- Garantem compatibilidade com bancos antigos que nao tinham colunas mais recentes de empresa e tipo.

### `normalize_empresa_delivery_methods(connection)`, `migrate_empresa_delivery_methods_to_documentos(connection)` e `normalize_documento_delivery_methods(connection)`

- Normalizam valores de `meios_recebimento` e preservam compatibilidade com o modelo antigo por empresa.

### `ensure_log_metadata_columns(connection)` e `backfill_log_metadata(connection)`

- Acrescentam e populam campos estruturados para filtros de logs por empresa e periodo.

### `ensure_default_admin(connection)`

- Cria o usuario `admin/admin` quando ainda nao existe nenhum usuario.

### `consolidate_duplicate_types(connection)`

- Faz consolidacao automatica de tipos sinonimos, com merge de documentos e de status.

## 6.3 Metodos relevantes dos servicos

### `AuthService.authenticate(username, password)`

- Valida campos obrigatorios
- Busca usuario com hash
- Verifica senha
- Bloqueia usuario inativo
- Retorna dicionario do usuario sem `senha_hash`

### `EmpresaService.create_empresa(...)`

- Valida codigo inteiro
- Valida nome
- Valida email opcional
- Valida observacao com limite de 255 caracteres
- Garante unicidade de codigo
- Persiste empresa
- Gera log `CADASTRO_EMPRESA`
- Executa tudo em uma unica transacao

### `EmpresaService.update_empresa(...)`

- Le estado atual
- Persiste alteracoes
- Compara antes/depois
- Gera log `EDICAO_EMPRESA` apenas se houve mudanca real

### `EmpresaService.set_empresa_ativa(...)`

- Alterna ativo/inativo
- Gera log de inativacao ou reativacao

### `EmpresaService.delete_empresa(...)`

- Exclui a empresa
- A exclusao em cascata remove documentos e status relacionados
- Registra `EXCLUSAO_EMPRESA`

### `TipoService.get_or_create_tipo(nome_tipo)`

- Canonicaliza o nome
- Reaproveita tipo existente ou cria um novo com ocorrencia mensal por padrao
- Importante no fluxo de importacao de documentos

### `DocumentoService.create_documento(...)`

- Garante existencia da empresa e do tipo
- Valida nome
- Normaliza meios de recebimento do documento
- Bloqueia duplicidade `(empresa, tipo, nome)`
- Persiste documento
- Registra `CADASTRO_DOCUMENTO`

### `DocumentoService.update_documento(...)`

- Le documento atual
- Valida novo tipo e novo nome
- Bloqueia duplicidade
- Atualiza registro
- Gera `EDICAO_DOCUMENTO` e/ou `ALTERACAO_TIPO_DOCUMENTO`

### `DocumentoService.delete_documento(...)` e `delete_documentos(...)`

- Excluem um ou varios documentos
- A cascata do banco remove status associados
- Registram logs de exclusao

### `PeriodoService.generate_year(ano)`

- Valida ano
- Cria apenas os meses faltantes
- Retorna resumo com criados/existentes

### `PeriodoService.delete_year(ano)`

- Valida ano
- Exclui periodos daquele ano
- A cascata remove status mensais vinculados
- Nao toca em empresas, tipos ou documentos base

### `PeriodoService.get_periods_between(start_period_id, end_period_id)`

- Valida ordem cronologica
- Garante limite maximo de 12 meses
- Devolve a lista de periodos no intervalo

### `StatusService.update_status(documento_id, periodo_id, status)`

- Valida status
- Garante existencia de documento e periodo
- Detecta status anterior
- Bloqueia alteracao em meses fora da ocorrencia do tipo
- Impede gravacao depois de um encerramento anterior
- Faz `upsert` do status
- Se novo status for `Encerrado`, remove status futuros
- Registra log da alteracao principal
- Registra logs adicionais para status futuros que foram limpos
- Executa tudo em uma transacao unica

### `StatusService.build_control_view(empresa_id, start_period_id, end_period_id)`

- Valida empresa e periodos
- Garante no maximo 12 meses
- Le documentos da empresa
- Le status do intervalo
- Le encerramentos
- Calcula meses cobraveis conforme a ocorrencia do tipo
- Marca `Nao cobrar` automaticamente fora da ocorrencia
- Monta estrutura pronta para renderizacao na aba `Controle`
- Agrupa por `tipo_documento_id`

### `ImportService.import_empresas(file_path)`

- Abre workbook via `openpyxl`
- Le o layout atual de empresas
- Mantem compatibilidade com o layout legado de 2 colunas
- Tenta cadastrar empresa por linha
- Acumula quantidade importada, falhas e mensagens de erro

### `ImportService.import_documentos(file_path, empresa_id)`

- Le o layout atual com `meios_recebimento`, `nome_documento` e `nome_tipo`
- Mantem compatibilidade com o layout legado de 2 colunas
- Garante tipo informado
- Reaproveita ou cria tipo
- Tenta cadastrar documento
- Consolida falhas por linha

### `UserService.create_user(...)`

- Exige admin logado
- Valida username, senha, tipo e ativo
- Garante unicidade
- Faz hash da senha
- Persiste usuario
- Gera log `CRIACAO_USUARIO`

### `UserService.update_user(...)`

- Exige admin
- Valida existencia do usuario
- Garante unicidade do username
- Impede auto-inativacao
- Impede auto-remocao de perfil admin
- Garante que sempre exista pelo menos um admin ativo
- Atualiza dados
- Atualiza senha se fornecida
- Gera logs de edicao, senha e status do usuario

### `LogService.list_logs(...)`

- Exige admin
- Delega para `LogRepository.list_recent()`
- Suporta filtro por empresa, ano e mes

## 6.4 Funcoes utilitarias importantes

### `hash_password(password)` e `verify_password(password, stored_hash)`

- Arquivo: `utils/security.py`
- Papel: proteger senhas com PBKDF2 SHA-256, salt aleatorio e comparacao segura

### `get_default_config_dir()`

- Arquivo: `utils/common.py`
- Papel: definir pasta de configuracao por sistema operacional

### `parse_delivery_methods()` e `normalize_delivery_methods()`

- Papel: normalizar meios de recebimento, canonicalizando valores conhecidos e preservando valores legados

### `normalize_type_occurrence_rule()`, `is_chargeable_period()` e `build_chargeable_closure_key_map()`

- Papel: centralizar a regra de ocorrencia especial dos tipos e o calculo de encerramento valido para meses cobraveis

### `format_period_label()`, `month_key()`, `count_months_between()`

- Papel: dar suporte a regras de periodo e exibicao

### `prompt_database_path()` e `ensure_database_path()`

- Arquivo: `utils/helpers.py`
- Papel: decidir o caminho do banco em primeira execucao ou quando o caminho salvo estiver invalido

### `migrate_legacy_config_dir()`

- Papel: migrar configuracao antiga do diretorio legado para o novo padrao

### `load_auto_backup_settings()`, `save_auto_backup_settings()` e `should_run_auto_backup()`

- Arquivo: `utils/auto_backup.py`
- Papel: carregar configuracao local do backup automatico, normalizar intervalo/retencao e decidir se ja esta na hora de gerar uma nova copia

### `apply_window_icon(window)`

- Arquivo: `utils/resources.py`
- Papel: localizar e aplicar o icone correto da janela Tkinter usando a pasta `assets/icons`

### `get_packaging_icon_filename()` e `get_packaging_icon_path()`

- Arquivo: `utils/resources.py`
- Papel: centralizar qual formato de icone deve ser usado no build de cada sistema operacional

### `generate_icons()`

- Arquivo: `scripts/generate_icons.py`
- Papel: gerar `icon.png`, `icon.ico` e `icon.icns` a partir de `assets/icons/icon.svg`

### Funcoes de `display.py`

- Papel: descobrir monitor preferencial ou principal para centralizar as janelas
- Observacao: usam estrategia por plataforma, com dependencias opcionais em Linux/macOS

---
