[Voltar ao README](../README.md)

# 4. Hierarquia Das Classes

## 4.1 Visao geral da organizacao

O sistema nao usa uma hierarquia de heranca profunda. O relacionamento predominante e de composicao e dependencia.

Existe heranca apenas em tres grupos principais:

- repositórios herdam de `BaseRepository`
- janelas/abas herdam de classes Tkinter (`tk.Tk`, `tk.Toplevel`, `ttk.Frame`, `ttk.LabelFrame`)
- entidades de dominio sao dataclasses simples, sem heranca

## 4.2 Mapeamento das classes

| Classe | Arquivo | Tipo | Responsabilidade principal | Instanciada por |
|---|---|---|---|---|
| `ApplicationServices` | `app_context.py` | container | agrupar os servicos do sistema | `build_application_services()` |
| `DatabaseManager` | `database/connection.py` | infraestrutura | gerenciar conexoes/transacoes SQLite | `build_application_services()` |
| `BaseRepository` | `database/repositories.py` | base de repositório | concentrar helpers de acesso ao banco | repositórios concretos |
| `EmpresaRepository` | `database/repositories.py` | repositório | CRUD de empresas | `build_application_services()` |
| `DeliveryMethodRepository` | `database/repositories.py` | repositório | CRUD de meios de recebimento do sistema | `build_application_services()` |
| `TipoRepository` | `database/repositories.py` | repositório | CRUD de tipos | `build_application_services()` |
| `UsuarioRepository` | `database/repositories.py` | repositório | CRUD de usuarios | `build_application_services()` |
| `RememberedSessionRepository` | `database/repositories.py` | repositório | persistencia de credenciais lembradas | `build_application_services()` |
| `LogRepository` | `database/repositories.py` | repositório | gravacao e consulta de logs | `build_application_services()` |
| `DocumentoRepository` | `database/repositories.py` | repositório | CRUD de documentos | `build_application_services()` |
| `PeriodoRepository` | `database/repositories.py` | repositório | CRUD/consulta de periodos | `build_application_services()` |
| `StatusRepository` | `database/repositories.py` | repositório | status mensal e consultas de encerramento | `build_application_services()` |
| `EmpresaService` | `services/empresa_service.py` | servico | regras de empresa e logs associados | `build_application_services()` |
| `DeliveryMethodService` | `services/delivery_method_service.py` | servico | regras dos meios de recebimento e propagacao para documentos | `build_application_services()` |
| `TipoService` | `services/tipo_service.py` | servico | regras de tipos | `build_application_services()` |
| `DocumentoService` | `services/documento_service.py` | servico | regras de documentos e auditoria | `build_application_services()` |
| `PeriodoService` | `services/periodo_service.py` | servico | validacao e gerenciamento de periodos | `build_application_services()` |
| `StatusService` | `services/status_service.py` | servico | alteracao de status, ocorrencia especial, encerramento e consulta consolidada | `build_application_services()` |
| `ImportService` | `services/import_service.py` | servico | importacao de planilhas | `build_application_services()` |
| `PendingReportService` | `services/pending_report_service.py` | servico | gerar/exportar relatorio de pendencias | `build_application_services()` |
| `DatabaseMaintenanceService` | `services/database_maintenance_service.py` | servico | backup e restauracao do banco | `build_application_services()` |
| `AuthService` | `services/auth_service.py` | servico | autenticar usuario | `build_application_services()` |
| `SessionService` | `services/session_service.py` | servico de estado | manter usuario logado | `build_application_services()` ou `main.py` |
| `UserService` | `services/user_service.py` | servico | administracao de usuarios | `build_application_services()` |
| `AuditService` | `services/audit_service.py` | servico transversal | gravar logs estruturados | `build_application_services()` |
| `LogService` | `services/log_service.py` | servico | consulta filtrada de logs | `build_application_services()` |
| `LoginWindow` | `ui/login_window.py` | janela | autenticar usuario | `main.py` |
| `MainWindow` | `ui/main_window.py` | janela principal | compor abas e estado visual global | `main.py` |
| `ControleTab` | `ui/controle_tab.py` | aba | consulta mensal e alteracao de status | `MainWindow` |
| `EmpresaTab` | `ui/empresa_tab.py` | aba | cadastro de empresas | `MainWindow` |
| `DocumentoTab` | `ui/documento_tab.py` | aba | cadastro de documentos | `MainWindow` |
| `TipoTab` | `ui/tipo_tab.py` | tela auxiliar | manutencao isolada de tipos; nao e montada pela `MainWindow` atual | uso auxiliar |
| `EdicaoTab` | `ui/edicao_tab.py` | tela auxiliar | manutencao consolidada de empresa/documentos; nao e montada pela `MainWindow` atual | uso auxiliar |
| `PeriodoTab` | `ui/periodo_tab.py` | aba | gerar periodos, excluir ano e exportar relatorio | `MainWindow` |
| `UserTab` | `ui/user_tab.py` | aba | cadastro/manutencao de usuarios | `MainWindow` |
| `LogTab` | `ui/log_tab.py` | aba | visualizacao de logs | `MainWindow` |
| `DeliveryMethodsField` | `ui/delivery_methods_field.py` | componente | selecionar meios de recebimento por documento | `DocumentoTab`, `EdicaoTab` |
| `DatabasePathDialog` | `utils/helpers.py` | dialogo | escolher local do banco | `prompt_database_path()` |
| `ScrollableFrame` | `utils/helpers.py` | componente | fornecer rolagem vertical para grids grandes | `ControleTab` |
| `CompanySelector` | `utils/helpers.py` | componente | selecionar empresa por codigo/nome | `ControleTab`, `EmpresaTab`, `DocumentoTab`, `EdicaoTab` |
| `ScreenBounds` | `utils/display.py` | dataclass utilitaria | representar area de monitor | funcoes de display |
| `Empresa`, `TipoDocumento`, `DocumentoEmpresa`, `Periodo`, `StatusDocumentoMensal`, `Usuario`, `LogRegistro` | `models/models.py` | entidades | representar o dominio em dataclasses | atualmente, uso conceitual/documental |

## 4.3 Dependencias mais relevantes

- `MainWindow` depende de `ApplicationServices`.
- Cada aba depende do subconjunto de servicos que usa via `services`.
- `EmpresaService`, `DocumentoService`, `StatusService` e `UserService` dependem de `AuditService` e `SessionService`.
- `AuthService` depende de `UsuarioRepository`.
- `AuditService` depende de `LogRepository` e `SessionService`.
- `DatabaseManager` e compartilhado por todos os repositórios.

---
