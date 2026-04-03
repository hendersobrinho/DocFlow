[Voltar ao README](../README.md)

# 14. UML Textual / Diagrama Descritivo

```text
main.py
  - main()
  - usa helpers.ensure_database_path()
  - usa app_context.build_application_services()
  - abre LoginWindow
  - abre MainWindow

ApplicationServices
  - empresa_service
  - tipo_service
  - documento_service
  - periodo_service
  - status_service
  - import_service
  - auth_service
  - user_service
  - log_service
  - session_service

DatabaseManager
  - db_path
  - _active_connection
  - _connection_depth
  - connect()

BaseRepository
  - db_manager
  - _fetchall()
  - _fetchone()
  - _execute()
  - _executemany()

EmpresaRepository : BaseRepository
  - list_all()
  - get_by_id()
  - get_by_code()
  - create()
  - update_details()
  - update_active()
  - delete()

TipoRepository : BaseRepository
  - list_all()
  - get_by_id()
  - get_by_name()
  - create()
  - update()
  - delete()
  - is_in_use()

DocumentoRepository : BaseRepository
  - list_by_company()
  - get_by_id()
  - find_duplicate()
  - create()
  - update()
  - delete()
  - delete_many()

PeriodoRepository : BaseRepository
  - list_all()
  - get_by_id()
  - create()
  - exists()
  - list_years()
  - list_by_year()
  - list_between()
  - delete_year()

StatusRepository : BaseRepository
  - get_by_document_and_period()
  - upsert()
  - list_for_documents_and_periods()
  - list_future_statuses()
  - get_earliest_closure()
  - list_earliest_closures()
  - delete_future_statuses()

UsuarioRepository : BaseRepository
  - list_all()
  - get_by_id()
  - get_by_username()
  - create()
  - update()
  - update_password()
  - count_admins()

LogRepository : BaseRepository
  - create()
  - list_recent()
  - list_logged_companies()
  - list_log_years()
  - list_log_months_by_year()

SessionService
  - current_user
  - login()
  - logout()
  - is_authenticated()
  - is_admin()
  - get_user_id()
  - get_username()
  - refresh_user()

AuditService
  - log_repository
  - session_service
  - log()

AuthService
  - usuario_repository
  - authenticate()

EmpresaService
  - empresa_repository
  - audit_service
  - session_service
  - create_empresa()
  - update_empresa()
  - set_empresa_ativa()
  - delete_empresa()

TipoService
  - tipo_repository
  - get_or_create_tipo()
  - create_tipo()
  - update_tipo()
  - delete_tipo()

DocumentoService
  - documento_repository
  - empresa_repository
  - tipo_repository
  - audit_service
  - session_service
  - create_documento()
  - update_documento()
  - delete_documento()
  - delete_documentos()

PeriodoService
  - periodo_repository
  - list_periodos()
  - generate_year()
  - delete_year()
  - get_periods_between()

StatusService
  - empresa_repository
  - documento_repository
  - periodo_repository
  - status_repository
  - audit_service
  - session_service
  - update_status()
  - build_control_view()

UserService
  - usuario_repository
  - session_service
  - audit_service
  - create_user()
  - update_user()

LogService
  - log_repository
  - session_service
  - list_logs()
  - list_logged_companies()
  - list_log_years()
  - list_log_months_by_year()

MainWindow : tk.Tk
  - services
  - tabs
  - refresh_all_tabs()
  - logout()

LoginWindow : tk.Tk
  - services
  - login()
  - close()

Tabs : ttk.Frame
  - ControleTab
  - EmpresaTab
  - DocumentoTab
  - PeriodoTab
  - UserTab
  - LogTab

Telas auxiliares nao montadas pela MainWindow atual
  - TipoTab
  - EdicaoTab

Componentes auxiliares
  - CompanySelector : ttk.LabelFrame
  - ScrollableFrame : ttk.Frame
  - DeliveryMethodsField : ttk.LabelFrame
  - DatabasePathDialog : tk.Toplevel
```

---
