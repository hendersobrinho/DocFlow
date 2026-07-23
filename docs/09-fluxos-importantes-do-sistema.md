[Voltar ao README](../README.md)

# 9. Fluxos Importantes Do Sistema

## 9.1 Inicializacao do sistema

1. `main.main()` prepara o bootstrap.
2. `ensure_database_path()` resolve ou solicita o caminho do banco.
3. `build_application_services()` monta repositÃ³rios e servicos.
4. `initialize_schema()` cria tabelas, aplica migracoes leves e semeia dados basicos.
5. `LoginWindow` e aberta.

## 9.2 Login

1. O sistema tenta restaurar credencial lembrada.
2. Se o token for valido, o login visual pode ser pulado.
3. Caso contrario, o usuario informa nome e senha.
4. `AuthService.authenticate()` valida credenciais e estado do usuario.
5. `SessionService.login()` guarda o usuario autenticado em memoria.

## 9.3 Cadastro de empresa

1. O usuario abre `EmpresaTab`.
2. Informa codigo, nome, email, nome do contato e observacao.
3. `EmpresaService.create_empresa()` valida codigo, nome, email e observacao.
4. `EmpresaRepository.create()` persiste a empresa.
5. `AuditService.log()` registra a operacao.

## 9.4 Cadastro de tipo

1. O usuario abre `TipoTab` ou o painel lateral da `DocumentoTab`.
2. Informa nome do tipo.
3. Escolhe a ocorrencia:
   - `Mensal`
   - `Trimestral`
   - `Anual em janeiro`
4. `TipoService.create_tipo()` canonicaliza o nome e normaliza a regra de ocorrencia.
5. `TipoRepository.create()` persiste o tipo.

## 9.5 Cadastro de documento

1. O usuario seleciona a empresa em `DocumentoTab`.
2. Informa nome do documento.
3. Escolhe o tipo do documento.
4. Define um ou mais meios de recebimento do documento.
5. `DocumentoService.create_documento()` valida empresa, tipo, nome e duplicidade.
6. `DocumentoRepository.create()` grava o documento.
7. `AuditService.log()` registra a criacao.

## 9.6 Alteracao de status

1. O usuario consulta empresa e intervalo em `ControleTab`.
2. `StatusService.build_control_view()` monta a grade por tipo/documento/periodo.
3. Para meses cobraveis, a UI exibe `OptionMenu`.
4. Para meses fora da ocorrencia do tipo, a UI exibe `Nao cobrar` automaticamente.
5. `ControleTab.update_status()` chama `StatusService.update_status()`.
6. O servico valida documento, periodo, encerramento anterior e regra de ocorrencia.
7. Se o status for `Encerrado`, remove status futuros.
8. O servico registra o log principal e, quando existir, logs dos status futuros removidos.

## 9.7 Consulta por periodo

1. O usuario escolhe empresa, ano e mes inicial/final.
2. `ControleTab.consult()` resolve os `period_id`.
3. `StatusService.build_control_view()` valida intervalo de no maximo 12 meses.
4. A resposta volta agrupada por tipo, com metadados de ocorrencia e celulas ja prontas para a UI.

## 9.8 Importacao por Excel

### Empresas

1. `ImportService.import_empresas()` abre a planilha.
2. Detecta cabecalho atual ou usa compatibilidade com layout antigo.
3. Cada linha reaproveita `EmpresaService.create_empresa()`.

### Documentos

1. `ImportService.import_documentos()` recebe a empresa ja selecionada.
2. Aceita layout atual com `meios_recebimento`, `nome_documento`, `nome_tipo`.
3. Mantem compatibilidade com layout legado de 2 colunas.
4. Cada linha reaproveita `DocumentoService.create_documento()`.

### Cadastro completo

1. `ImportService.import_cadastros_completos()` processa empresa e documento na mesma linha.
2. O layout atual usa:
   - `codigo_empresa`
   - `nome_empresa`
   - `email_contato`
   - `nome_contato`
   - `meios_recebimento`
   - `nome_documento`
   - `nome_tipo`
   - `observacao`
3. Tipos podem ser reutilizados ou criados automaticamente.
4. Cada linha usa os mesmos servicos de negocio da operacao manual.

## 9.9 Relatorio de pendencias

1. O usuario abre a subaba `Relatorio de pendencias`.
2. Escolhe empresas e periodo.
3. `PendingReportService.list_pending_rows()` ignora meses `Nao cobrar`.
4. Apenas pendencias de meses realmente cobraveis entram no Excel.

## 9.10 Backup e restauracao

1. O usuario usa o menu `Banco` na `MainWindow`.
2. `DatabaseMaintenanceService.create_backup()` gera uma copia manual do banco atual.
3. O backup automatico usa a configuracao local para gerar uma copia datada quando o intervalo vencer.
4. Backups automaticos antigos sao removidos conforme o limite configurado.
5. `restore_backup()` substitui o banco em uso pelo arquivo selecionado.
6. A aplicacao reinicia apos restauracao para recarregar o estado.

## 9.11 Logs

1. Servicos transacionais chamam `AuditService.log()`.
2. O log recebe usuario, acao, descricao e metadados opcionais.
3. `LogRepository.create()` persiste.
4. `LogTab` recupera os dados filtrados por empresa e periodo.

---
