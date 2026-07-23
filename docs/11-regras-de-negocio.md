[Voltar ao README](../README.md)

# 11. Regras De Negocio

## 11.1 Empresas

- `codigo_empresa` deve ser unico
- nome nao pode ficar vazio
- codigo aceita representacoes inteiras como `"101.0"`
- email de contato e opcional, mas quando informado precisa ser valido
- observacao e opcional e aceita no maximo 255 caracteres
- empresa nasce ativa por padrao
- implementacao principal: `EmpresaService`

## 11.2 Tipos de documento

- nome nao pode ficar vazio
- nome nao pode duplicar outro tipo existente
- aliases textuais sao canonicalizados
- cada tipo possui uma `regra_ocorrencia`
- ocorrencias validas:
  - `mensal`
  - `trimestral`
  - `anual_janeiro`
- exclusao e bloqueada se o tipo estiver em uso
- implementacao principal: `TipoService` e `schema.consolidate_duplicate_types()`

## 11.3 Documentos por empresa

- nome nao pode ficar vazio
- nao pode existir duplicidade de `(empresa, tipo, nome)`
- meios de recebimento pertencem ao documento
- meios de recebimento sao normalizados e deduplicados
- mudancas de nome, tipo e meios podem gerar logs proprios
- implementacao principal: `DocumentoService`

## 11.4 Periodos

- ano precisa ser valido
- mes fica entre 1 e 12
- nao pode existir duplicidade de `(ano, mes)`
- consulta e relatorio nao podem exceder 12 meses corridos
- implementacao principal: `PeriodoService`

## 11.5 Status mensal

- valores persistidos permitidos: `NULL`, `Recebido`, `Pendente`, `Encerrado`
- cada documento pode ter apenas um status por periodo
- alteracao para o mesmo valor nao faz nada
- a ultima alteracao guarda usuario e data/hora
- `Nao cobrar` e um estado calculado, nao persistido
- implementacao principal: `StatusService`

## 11.6 Regra de ocorrencia especial

- tipo `Mensal` permite alteracao em todos os meses
- tipo `Trimestral` permite alteracao apenas em `01`, `04`, `07` e `10`
- tipo `Anual em janeiro` permite alteracao apenas em `01`
- meses fora da ocorrencia aparecem automaticamente como `Nao cobrar`
- nao e permitido gravar `Recebido`, `Pendente` ou `Encerrado` em mes nao cobravel
- relatorio de pendencias ignora meses `Nao cobrar`

## 11.7 Regra de encerramento

- quando um documento recebe status `Encerrado` em um mes cobravel:
  - continua aparecendo ate esse mes
  - deixa de aceitar status em meses posteriores
- se havia status futuro preenchido, ele e removido
- nao e permitido gravar novo status depois de um encerramento anterior
- implementacao principal: `StatusService.update_status()` e `build_control_view()`

## 11.8 Permissoes de usuario

- somente admin gerencia usuarios
- somente admin visualiza logs
- usuarios comuns nao recebem as abas `Usuarios` e `Logs`
- implementacao principal: `UserService`, `LogService`, `MainWindow`

## 11.9 Regras de seguranca de usuario

- senha nao pode ficar vazia
- senha e salva com hash PBKDF2
- usuario inativo nao faz login
- login pode ser lembrado por usuario do computador via token local
- o proprio admin logado nao pode:
  - se inativar
  - remover o proprio perfil admin
- o sistema precisa manter pelo menos um admin ativo

## 11.10 Exclusoes em cascata

- empresa -> documentos -> status
- documento -> status
- ano -> periodos -> status
- tipo nao exclui em cascata; e bloqueado quando em uso

## 11.11 Logs

- alteracoes relevantes de empresa, documento, tipo de recebimento, status e usuario sao logadas
- logs carregam usuario, descricao, empresa e periodo quando aplicavel
- operacoes com escrita e log rodam na mesma transacao sempre que necessario

## 11.12 Importacao e modelos

- importacao de empresas aceita layout atual com campos opcionais e continua compativel com planilha antiga de 2 colunas
- importacao de documentos aceita layout atual com `meios_recebimento`, `nome_documento`, `nome_tipo`
- importacao de documentos continua compativel com o layout legado de 2 colunas
- importacao completa usa o layout atual com empresa + documento + observacao
- as abas de empresas e documentos permitem baixar modelos `.xlsx`

## 11.13 Backup e restauracao

- backup gera uma copia completa do SQLite em outro arquivo
- backup automatico gera copias datadas em pasta configuravel pelo usuario
- a pasta padrao fica fora da instalacao, em `Documents/DocFLow/backups` ou `Documentos/DocFLow/backups` quando disponivel
- o usuario configura intervalo em dias e quantos backups automaticos devem ser mantidos
- restauracao substitui o banco atual pelo backup escolhido
- apos restaurar, o sistema reinicia para recarregar os dados com seguranca

---
