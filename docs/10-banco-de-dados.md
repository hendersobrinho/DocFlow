[Voltar ao README](../README.md)

# 10. Banco De Dados

## 10.1 Tabelas existentes

### `empresas`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | INTEGER | PK, autoincrement |
| `codigo_empresa` | INTEGER | obrigatorio, unico |
| `nome_empresa` | TEXT | obrigatorio, `COLLATE NOCASE` |
| `meios_recebimento` | TEXT | opcional |
| `email_contato` | TEXT | opcional |
| `nome_contato` | TEXT | opcional |
| `diretorio_documentos` | TEXT | opcional |
| `ativa` | INTEGER | default `1`, check `0/1` |

Uso:

- base de todas as consultas e cadastros
- acessada principalmente por `EmpresaRepository`

### `tipos_documento`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | INTEGER | PK |
| `nome_tipo` | TEXT | obrigatorio, unico, `COLLATE NOCASE` |

Uso:

- agrupar documentos
- alimentar comboboxes de tipo
- consolidar aliases textuais

### `meios_recebimento_sistema`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | INTEGER | PK |
| `nome_meio` | TEXT | obrigatorio, unico, `COLLATE NOCASE` |

Uso:

- alimentar a manutencao de meios de recebimento na interface
- permitir renomear ou remover meios globais sem apagar o historico das empresas

### `documentos_empresa`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | INTEGER | PK |
| `empresa_id` | INTEGER | FK para `empresas`, `ON DELETE CASCADE` |
| `tipo_documento_id` | INTEGER | FK para `tipos_documento`, `ON DELETE RESTRICT` |
| `nome_documento` | TEXT | obrigatorio, `COLLATE NOCASE` |

Restricao importante:

- `UNIQUE (empresa_id, tipo_documento_id, nome_documento)`

### `periodos`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | INTEGER | PK |
| `ano` | INTEGER | obrigatorio |
| `mes` | INTEGER | obrigatorio, `CHECK 1..12` |

Restricao:

- `UNIQUE (ano, mes)`

### `status_documento_mensal`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | INTEGER | PK |
| `documento_empresa_id` | INTEGER | FK para `documentos_empresa`, `ON DELETE CASCADE` |
| `periodo_id` | INTEGER | FK para `periodos`, `ON DELETE CASCADE` |
| `status` | TEXT | `NULL`, `Recebido`, `Pendente`, `Encerrado` |
| `updated_by_user_id` | INTEGER | opcional, usuario que fez a ultima alteracao |
| `updated_at` | TEXT | timestamp da ultima alteracao |

Restricao:

- `UNIQUE (documento_empresa_id, periodo_id)`

### `usuarios`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | INTEGER | PK |
| `username` | TEXT | obrigatorio, unico, `COLLATE NOCASE` |
| `senha_hash` | TEXT | obrigatorio |
| `tipo_usuario` | TEXT | `admin` ou `comum` |
| `ativa` | INTEGER | default `1`, `CHECK 0/1` |
| `criado_em` | TEXT | default `CURRENT_TIMESTAMP` |

### `sessoes_lembradas`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | INTEGER | PK |
| `usuario_id` | INTEGER | FK para `usuarios`, `ON DELETE CASCADE` |
| `selector` | TEXT | obrigatorio, unico |
| `token_hash` | TEXT | obrigatorio |
| `criado_em` | TEXT | default `CURRENT_TIMESTAMP` |
| `ultimo_uso_em` | TEXT | default `CURRENT_TIMESTAMP` |

### `logs`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | INTEGER | PK |
| `usuario_id` | INTEGER | FK para `usuarios`, `ON DELETE SET NULL` |
| `acao` | TEXT | obrigatorio |
| `entidade` | TEXT | obrigatorio |
| `entidade_id` | INTEGER | opcional |
| `empresa_id` | INTEGER | opcional |
| `empresa_nome` | TEXT | opcional |
| `periodo_ano` | INTEGER | opcional |
| `periodo_mes` | INTEGER | opcional |
| `descricao` | TEXT | obrigatorio |
| `data_hora` | TEXT | obrigatorio, default timestamp |

## 10.2 Relacionamentos

- `empresas 1:N documentos_empresa`
- `tipos_documento 1:N documentos_empresa`
- `usuarios 1:N sessoes_lembradas`
- `documentos_empresa 1:N status_documento_mensal`
- `periodos 1:N status_documento_mensal`
- `usuarios 1:N logs`

## 10.3 Integridade e comportamento de exclusao

- excluir empresa remove documentos e status mensais associados
- excluir documento remove status mensais associados
- excluir periodo remove status mensais associados
- excluir tipo e bloqueado se houver documento usando o tipo
- excluir usuario nao apaga log; o `usuario_id` fica `NULL`

## 10.4 Classes que acessam cada tabela

| Tabela | Repositório principal | Servicos que usam |
|---|---|---|
| `empresas` | `EmpresaRepository` | `EmpresaService`, `DocumentoService`, `StatusService` |
| `meios_recebimento_sistema` | `DeliveryMethodRepository` | `DeliveryMethodService` |
| `tipos_documento` | `TipoRepository` | `TipoService`, `DocumentoService`, `ImportService` |
| `documentos_empresa` | `DocumentoRepository` | `DocumentoService`, `StatusService`, `ImportService` |
| `periodos` | `PeriodoRepository` | `PeriodoService`, `StatusService` |
| `status_documento_mensal` | `StatusRepository` | `StatusService` |
| `usuarios` | `UsuarioRepository` | `AuthService`, `UserService` |
| `sessoes_lembradas` | `RememberedSessionRepository` | `AuthService` |
| `logs` | `LogRepository` | `AuditService`, `LogService` |

---
