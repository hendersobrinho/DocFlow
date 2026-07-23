[Voltar ao README](../README.md)

# 7. Relacionamento Entre Classes

## 7.1 Relacao entre interface, servicos e banco

- As telas nunca fazem SQL direto.
- As telas chamam servicos.
- Os servicos chamam repositórios.
- Os repositórios acessam SQLite.
- O resultado volta como dicionario e e usado pela UI.

## 7.2 Relacoes centrais

### `MainWindow` -> abas

`MainWindow` instancia as abas e passa:

- `services`
- callback `refresh_all_tabs`

Isso faz da janela principal um orquestrador visual, nao um concentrador de regra de negocio.

### Abas -> servicos

Cada aba usa o subconjunto minimo de servicos de que precisa:

- `ControleTab` usa `empresa_service`, `periodo_service`, `status_service`
- `EmpresaTab` usa `empresa_service`, `import_service` e `delivery_method_service`
- `DocumentoTab` usa `empresa_service`, `documento_service`, `tipo_service`, `import_service`
- `PeriodoTab` usa `periodo_service`, `pending_report_service` e `empresa_service`
- `UserTab` usa `user_service`
- `LogTab` usa `log_service`

Observacao:

- `TipoTab` e `EdicaoTab` continuam existindo no codigo, mas nao sao montadas pela `MainWindow` atual

### Servicos -> repositórios

Os servicos fazem a traducao de regra de negocio para persistencia.

Exemplos:

- `EmpresaService` usa `EmpresaRepository`
- `DocumentoService` usa `DocumentoRepository`, `EmpresaRepository` e `TipoRepository`
- `StatusService` usa quatro repositórios ao mesmo tempo
- `UserService` usa `UsuarioRepository`

### Servicos -> `AuditService`

Os servicos que alteram estado chamam `AuditService` para gerar log:

- `EmpresaService`
- `DocumentoService`
- `StatusService`
- `UserService`

### `AuditService` -> `SessionService`

`AuditService` consulta quem esta logado via `SessionService`, para preencher `usuario_id` no log.

## 7.3 Tipos de relacionamento

### Heranca

- `EmpresaRepository`, `TipoRepository`, `UsuarioRepository`, `LogRepository`, `DocumentoRepository`, `PeriodoRepository`, `StatusRepository` herdam de `BaseRepository`
- quase todas as telas herdam de `ttk.Frame`
- `LoginWindow` e `MainWindow` herdam de `tk.Tk`
- `DatabasePathDialog` herda de `tk.Toplevel`
- `DeliveryMethodsField` e `CompanySelector` herdam de `ttk.LabelFrame`

### Composicao

- `MainWindow` compoe todas as abas
- `ControleTab` compoe `CompanySelector` e `ScrollableFrame`
- `EmpresaTab` e `EdicaoTab` compoem `DeliveryMethodsField`

### Dependencia

- servicos dependem de repositórios
- UI depende de servicos
- `AuditService` depende de `SessionService`

---
