[Voltar ao README](../README.md)

# 11. Regras De Negocio

## 11.1 Empresas

- `codigo_empresa` deve ser unico
- nome nao pode ficar vazio
- codigo deve ser inteiro, inclusive aceitando representacoes como `"101.0"`
- empresa nasce ativa por padrao
- email de contato e opcional, mas quando informado precisa ser valido
- meios de recebimento sao normalizados
- implementacao principal: `EmpresaService`

## 11.2 Tipos de documento

- nome nao pode ficar vazio
- nome nao pode duplicar outro tipo existente
- aliases textuais sao canonicalizados
- exclusao bloqueada se o tipo estiver em uso
- implementacao principal: `TipoService`, `schema.consolidate_duplicate_types()`

## 11.3 Documentos por empresa

- nome nao pode ficar vazio
- nao pode existir duplicidade de `(empresa, tipo, nome)`
- o mesmo nome pode existir em outra empresa
- mudancas de tipo e nome geram logs proprios
- implementacao principal: `DocumentoService`

## 11.4 Periodos

- ano precisa ser valido
- mes fica entre 1 e 12
- nao pode existir duplicidade de `(ano, mes)`
- consulta nao pode exceder 12 meses corridos
- implementacao principal: `PeriodoService`

## 11.5 Status mensal

- valores permitidos: `NULL`, `Recebido`, `Pendente`, `Encerrado`
- cada documento pode ter apenas um status por periodo
- alteracao para o mesmo valor nao faz nada
- a ultima alteracao guarda usuario e data/hora para consulta posterior
- implementacao principal: `StatusService`

## 11.6 Regra de encerramento

- quando um documento recebe status `Encerrado` em um mes:
  - continua aparecendo ate esse mes
  - deixa de aparecer em meses posteriores
- se havia status futuro preenchido, ele e removido
- nao e permitido gravar novo status depois de um encerramento anterior
- implementacao principal: `StatusService.update_status()` e `build_control_view()`

## 11.7 Permissoes de usuario

- somente admin gerencia usuarios
- somente admin visualiza logs
- usuarios comuns nao recebem as abas `Usuarios` e `Logs`
- implementacao principal: `UserService`, `LogService`, `MainWindow`

## 11.8 Regras de seguranca de usuario

- senha nao pode ficar vazia
- senha e salva com hash PBKDF2
- usuario inativo nao faz login
- login pode ser lembrado por usuario do computador via token local
- o proprio admin logado nao pode:
  - se inativar
  - remover o proprio perfil admin
- o sistema precisa manter pelo menos um admin ativo

## 11.9 Exclusoes em cascata

- empresa -> documentos -> status
- documento -> status
- ano -> periodos -> status
- tipo nao exclui em cascata; e bloqueado quando em uso

## 11.10 Logs

- alteracoes relevantes de empresa, documento, status e usuario sao logadas
- logs carregam usuario, descricao, empresa e periodo quando aplicavel
- operacoes com escrita e log rodam na mesma transacao

## 11.11 Seletores e filtros

- selecao de empresa por nome exige escolha explicita da sugestao
- `F2` abre a lista de empresas com filtro em tempo real
- filtros de logs podem usar empresa, ano e mes
- consulta principal usa ano e mes separados para evitar listas longas

## 11.12 Importacao e modelos

- importacao de empresas aceita layout atual com campos opcionais e continua compativel com planilha antiga de 2 colunas
- importacao de documentos exige empresa previamente selecionada
- as abas de empresas e documentos permitem visualizar o layout e baixar um modelo `.xlsx`

## 11.13 Backup e restauracao

- backup gera uma copia completa do SQLite em outro arquivo
- restauracao substitui o banco atual pelo backup escolhido
- apos restaurar, o sistema reinicia para recarregar os dados com seguranca

---
