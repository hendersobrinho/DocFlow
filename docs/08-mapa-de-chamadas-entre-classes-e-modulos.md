[Voltar ao README](../README.md)

# 8. Mapa De Chamadas Entre Classes E Modulos

## 8.1 Mapa principal de inicializacao

`main.main()`
-> `helpers.ensure_database_path()`
-> `helpers.prompt_database_path()` / `DatabasePathDialog`
-> `app_context.build_application_services()`
-> `schema.initialize_schema()`
-> instanciacao dos repositórios
-> instanciacao dos servicos
-> `LoginWindow`
-> `AuthService.authenticate()`
-> `SessionService.login()`
-> `MainWindow`
-> abas

## 8.2 Mapa do cadastro de empresa

`EmpresaTab.save_company()`
-> `EmpresaService.create_empresa()` ou `EmpresaService.update_empresa()`
-> `EmpresaRepository.create()` / `EmpresaRepository.update_details()`
-> `AuditService.log()`
-> `LogRepository.create()`
-> `MainWindow.refresh_all_tabs()`

## 8.3 Mapa do cadastro de documento

`DocumentoTab.save_document()`
-> `DocumentoService.create_documento()` ou `update_documento()`
-> `EmpresaRepository.get_by_id()`
-> `TipoRepository.get_by_id()`
-> `DocumentoRepository.find_duplicate()`
-> `DocumentoRepository.create()` / `update()`
-> `AuditService.log()`
-> `LogRepository.create()`

## 8.4 Mapa da alteracao de status

`ControleTab.update_status()`
-> `StatusService.update_status()`
-> `DocumentoRepository.get_by_id()`
-> `PeriodoRepository.get_by_id()`
-> `StatusRepository.get_by_document_and_period()`
-> `StatusRepository.get_earliest_closure()`
-> `StatusRepository.upsert()`
-> `StatusRepository.list_future_statuses()` e `delete_future_statuses()` se houver encerramento
-> `AuditService.log()` uma ou mais vezes
-> `LogRepository.create()`
-> UI atualiza com `consult()`

## 8.5 Mapa da consulta de controle

`ControleTab.consult()`
-> `StatusService.build_control_view()`
-> `PeriodoRepository.get_by_id()`
-> `PeriodoRepository.list_between()`
-> `DocumentoRepository.list_by_company()`
-> `StatusRepository.list_for_documents_and_periods()`
-> `StatusRepository.list_earliest_closures()`
-> retorno de estrutura consolidada para `ControleTab.render_result()`

## 8.6 Mapa do login

`LoginWindow.login()`
-> `AuthService.authenticate()`
-> `UsuarioRepository.get_by_username(include_password=True)`
-> `verify_password()`
-> `SessionService.login()`
-> `MainWindow`

## 8.7 Mapa da visualizacao de logs

`LogTab.refresh_data()`
-> `LogService.list_logs()`
-> `LogService._ensure_admin()`
-> `LogRepository.list_recent()`
-> join com `usuarios` e `empresas`
-> retorno para a `Treeview`

---
