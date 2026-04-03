[Voltar ao README](../README.md)

# 9. Fluxos Importantes Do Sistema

## 9.1 Inicializacao do sistema

1. `main.main()` cria uma janela bootstrap invisivel.
2. `ensure_database_path()` verifica `config.json`.
3. Se nao houver caminho valido, abre `DatabasePathDialog`.
4. O caminho escolhido e salvo em configuracao do usuario.
5. `build_application_services()` cria `DatabaseManager`.
6. `initialize_schema()` cria e ajusta banco.
7. `LoginWindow` e aberta.

Leitura de banco:

- schema e migracoes
- usuario admin padrao

Gravacao de banco:

- tabelas, indices, admin inicial, normalizacoes eventuais

## 9.2 Login

1. `main.main()` tenta restaurar uma sessao lembrada com `try_restore_saved_login()`.
2. Se houver token valido, `AuthService.authenticate_with_remembered_session()` autentica o usuario e o login visual e pulado.
3. Se nao houver token valido, o usuario digita nome e senha em `LoginWindow`.
4. `login()` chama `AuthService.authenticate()`.
5. O servico busca usuario com `UsuarioRepository.get_by_username(include_password=True)`.
6. A senha e validada por `verify_password()`.
7. Se o usuario marcar lembrar credencial, `AuthService.create_remembered_session()` gera e persiste um token local.
8. `SessionService.login()` grava o usuario em memoria.
9. A janela de login se fecha e `MainWindow` abre.

## 9.3 Cadastro de usuario

1. Usuario admin abre `UserTab`.
2. Preenche username, senha, tipo e status.
3. `save_user()` chama `UserService.create_user()`.
4. O servico valida permissao admin, campos e unicidade.
5. A senha e hasheada por `hash_password()`.
6. `UsuarioRepository.create()` persiste o usuario.
7. `AuditService.log()` registra a criacao.

## 9.4 Cadastro de empresa

1. Usuario abre `EmpresaTab`.
2. Preenche codigo, nome, meios de recebimento, email e contato.
3. `save_company()` chama `EmpresaService.create_empresa()`.
4. O servico valida codigo, nome, email e unicidade.
5. `EmpresaRepository.create()` grava a empresa.
6. `AuditService.log()` registra `CADASTRO_EMPRESA`.
7. A interface limpa o formulario e atualiza listas.

## 9.5 Cadastro de tipo

1. Usuario abre `DocumentoTab`.
2. Informa nome do tipo.
3. Usa o painel lateral de tipos.
4. `save_tipo()` chama `TipoService.create_tipo()`.
5. O servico canonicaliza o nome.
6. O repositório persiste em `tipos_documento`.
7. A lista e atualizada.

## 9.6 Cadastro de documento

1. Usuario seleciona empresa em `DocumentoTab`.
2. Informa nome e tipo.
3. `save_document()` chama `DocumentoService.create_documento()`.
4. O servico valida:
   - empresa existente
   - tipo existente
   - nome nao vazio
   - ausencia de duplicidade
5. `DocumentoRepository.create()` grava o documento.
6. `AuditService.log()` registra a acao.

## 9.7 Alteracao de status

1. Usuario consulta empresa e periodo em `ControleTab`.
2. A grade de documentos e exibida.
3. Ao mudar o `OptionMenu`, `ControleTab.update_status()` e chamado.
4. `StatusService.update_status()` valida documento, periodo e valor.
5. O servico verifica se existe encerramento anterior.
6. O servico faz `upsert`.
7. Se o novo status for `Encerrado`, remove todos os status futuros desse documento.
8. O servico grava logs da alteracao principal e dos futuros removidos.
9. A UI executa nova consulta para refletir a regra de encerramento.

## 9.8 Consulta por periodo

1. Usuario escolhe empresa, ano inicial, mes inicial, ano final opcional e mes final.
2. `ControleTab.consult()` resolve os `period_id`.
3. `StatusService.build_control_view()` valida o intervalo e monta a estrutura.
4. A UI renderiza grupos por tipo e documentos linha a linha.

## 9.9 Geracao de periodos

1. Usuario abre `PeriodoTab`.
2. Informa um ano.
3. `generate_year()` chama `PeriodoService.generate_year()`.
4. O servico cria apenas meses ausentes.
5. A UI informa quantos foram criados e quantos ja existiam.

## 9.10 Exclusao de ano

1. Usuario escolhe o ano na subaba `Excluir ano`.
2. O sistema pede duas confirmacoes.
3. `PeriodoService.delete_year()` delega a `PeriodoRepository.delete_year()`.
4. A exclusao dos periodos remove automaticamente os status mensais relacionados.
5. Empresas, documentos base e tipos permanecem intactos.

## 9.11 Logs

1. Servicos transacionais chamam `AuditService.log()`.
2. O log recebe:
   - usuario logado
   - acao
   - entidade
   - descricao
   - metadados opcionais de empresa e periodo
3. `LogRepository.create()` persiste.
4. `LogTab` recupera esses dados via `LogService`.

## 9.12 Importacao por Excel

1. Usuario abre `EmpresaTab` ou `DocumentoTab`.
2. Seleciona planilha.
3. `ImportService` abre o workbook.
4. Itera linha a linha.
5. Reaproveita os servicos de negocio normais, em vez de fazer insercao direta.
6. Consolida resultado em:
   - importados
   - falhados
   - lista textual de erros

## 9.13 Vinculo de pasta da empresa

1. Usuario seleciona uma empresa na `ControleTab`.
2. Clica em `Abrir pasta...`.
3. A interface abre um seletor de diretorio.
4. `EmpresaService.set_empresa_directory()` normaliza e salva o caminho.
5. `AuditService.log()` registra a alteracao da pasta vinculada.

## 9.14 Relatorio de pendencias

1. Usuario abre a subaba `Relatorio de pendencias` em `PeriodoTab`.
2. Escolhe todas as empresas ou seleciona empresas especificas.
3. Define o intervalo de ate 12 meses.
4. `PendingReportService.export_pending_report()` monta as linhas com status `Pendente`.
5. O sistema exporta a planilha Excel com cabecalho, filtro e colunas ajustadas.

## 9.15 Backup e restauracao do banco

1. Usuario usa o menu `Banco` na `MainWindow`.
2. `create_backup()` gera uma copia SQLite do banco atual.
3. `restore_backup()` valida o arquivo selecionado e sobrescreve o banco em uso.
4. A restauracao exige confirmacao dupla e reinicia a janela principal.

## 9.16 Logout

1. Usuario clica em `Logout` na `MainWindow`.
2. O sistema pede confirmacao.
3. O token de credencial lembrada atual e revogado.
4. `SessionService.logout()` limpa a sessao.
5. A janela principal e destruida.
6. `main.main()` reabre o fluxo de login.

---
