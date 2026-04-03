[Voltar ao README](../README.md)

# 15. Ordem Ideal Para Estudar O Projeto

## 15.1 Roteiro recomendado

### Etapa 1: entender o bootstrap

Leia nesta ordem:

1. `main.py`
2. `documentos_empresa_app/app_context.py`
3. `documentos_empresa_app/database/connection.py`
4. `documentos_empresa_app/database/schema.py`

Objetivo:

- entender como o sistema sobe
- como o banco e preparado
- como os servicos sao montados

### Etapa 2: entender o modelo de persistencia

Leia:

1. `documentos_empresa_app/database/repositories.py`
2. `documentos_empresa_app/models/models.py`

Objetivo:

- entender tabelas, CRUD e consultas principais

### Etapa 3: entender a regra de negocio central

Leia:

1. `services/empresa_service.py`
2. `services/documento_service.py`
3. `services/periodo_service.py`
4. `services/status_service.py`
5. `services/tipo_service.py`

Objetivo:

- entender o coracao funcional do sistema
- principalmente cadastro, consulta e encerramento

### Etapa 4: entender autenticacao e auditoria

Leia:

1. `services/session_service.py`
2. `services/auth_service.py`
3. `services/user_service.py`
4. `services/audit_service.py`
5. `services/log_service.py`

### Etapa 5: entender a interface

Leia:

1. `ui/login_window.py`
2. `ui/main_window.py`
3. `ui/controle_tab.py`
4. `ui/empresa_tab.py`
5. `ui/documento_tab.py`
6. `ui/periodo_tab.py`
7. `ui/user_tab.py`
8. `ui/log_tab.py`
9. `ui/edicao_tab.py` (tela auxiliar/legada, nao montada pela `MainWindow` atual)
10. `ui/tipo_tab.py` (tela auxiliar/legada, nao montada pela `MainWindow` atual)

### Etapa 6: entender utilitarios e empacotamento

Leia:

1. `utils/common.py`
2. `utils/helpers.py`
3. `utils/security.py`
4. `utils/storage.py`
5. `utils/display.py`
6. `utils/resources.py`
7. `documentos_empresa_app.spec`
8. `scripts/build_release.*`
9. `installer/G-docs.iss`

### Etapa 7: validar entendimento pelos testes

Leia por ultimo:

1. `tests/test_services.py`
2. `tests/test_display.py`
3. `tests/test_storage.py`

Isso ajuda a fixar o comportamento esperado do sistema.

---
