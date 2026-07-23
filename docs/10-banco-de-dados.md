[Voltar ao README](../README.md)

# 10. Banco De Dados

## 10.1 Tabelas existentes

### `empresas`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | INTEGER | PK, autoincrement |
| `codigo_empresa` | INTEGER | obrigatorio, unico |
| `nome_empresa` | TEXT | obrigatorio, `COLLATE NOCASE` |
| `meios_recebimento` | TEXT | legado/compatibilidade, nao usado como regra principal atual |
| `email_contato` | TEXT | opcional |
| `nome_contato` | TEXT | opcional |
| `observacao` | TEXT | opcional, maximo 255 caracteres |
| `diretorio_documentos` | TEXT | opcional |
| `ativa` | INTEGER | default `1`, check `0/1` |

Observacao:

- o campo `meios_recebimento` foi mantido para compatibilidade com bancos antigos
- a regra atual do sistema usa meios de recebimento por documento

### `tipos_documento`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | INTEGER | PK |
| `nome_tipo` | TEXT | obrigatorio, unico, `COLLATE NOCASE` |
| `regra_ocorrencia` | TEXT | obrigatorio, `mensal`, `trimestral` ou `anual_janeiro` |

Uso:

- agrupar documentos
- alimentar seletores de tipo
- definir em quais meses aquele tipo deve ser cobrado

### `meios_recebimento_sistema`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | INTEGER | PK |
| `nome_meio` | TEXT | obrigatorio, unico, `COLLATE NOCASE` |

Uso:

- alimentar o componente de selecao de meios
- permitir renomear/remover meios globais sem apagar historico dos documentos

### `documentos_empresa`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | INTEGER | PK |
| `empresa_id` | INTEGER | FK para `empresas`, `ON DELETE CASCADE` |
| `tipo_documento_id` | INTEGER | FK para `tipos_documento`, `ON DELETE RESTRICT` |
| `meios_recebimento` | TEXT | opcional |
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
| `status` | TEXT | `NULL`, `Recebido`, `Pendente` ou `Encerrado` |
| `updated_by_user_id` | INTEGER | opcional, usuario que fez a ultima alteracao |
| `updated_at` | TEXT | timestamp da ultima alteracao |

Observacao importante:

- `Nao cobrar` nao e persistido nessa tabela
- esse valor e calculado dinamicamente pela regra de ocorrencia do tipo

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
- excluir usuario nao apaga log; o `usuario_id` pode ficar `NULL`

## 10.4 Compatibilidade e migracoes relevantes

- bancos antigos que tinham meio de recebimento na empresa continuam abrindo
- o schema copia `meios_recebimento` legado da empresa para documentos que ainda nao tenham esse dado
- `regra_ocorrencia` e adicionada automaticamente aos tipos em bancos antigos
- observacao de empresa e garantida com validacao em servico e trigger/check no banco

## 10.5 Classes que acessam cada tabela

| Tabela | Repositorio principal | Servicos que usam |
|---|---|---|
| `empresas` | `EmpresaRepository` | `EmpresaService`, `DocumentoService`, `StatusService`, `PendingReportService` |
| `meios_recebimento_sistema` | `DeliveryMethodRepository` | `DeliveryMethodService` |
| `tipos_documento` | `TipoRepository` | `TipoService`, `DocumentoService`, `ImportService` |
| `documentos_empresa` | `DocumentoRepository` | `DocumentoService`, `StatusService`, `PendingReportService`, `ImportService` |
| `periodos` | `PeriodoRepository` | `PeriodoService`, `StatusService`, `PendingReportService` |
| `status_documento_mensal` | `StatusRepository` | `StatusService`, `PendingReportService` |
| `usuarios` | `UsuarioRepository` | `AuthService`, `UserService` |
| `sessoes_lembradas` | `RememberedSessionRepository` | `AuthService` |
| `logs` | `LogRepository` | `AuditService`, `LogService` |

---
